"""
CRUD precios en ChromaDB
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from typing import List
import csv
import io
import uuid

from api.auth import verify_admin_token
from api.schemas.knowledge import PrecioCreate, PrecioUpdate, PrecioResponse
from rag.embeddings import (
    upsert_precio,
    get_precios,
    update_precio_metadata,
    delete_precio_logico
)

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(verify_admin_token)]
)

@router.get("", response_model=List[PrecioResponse])
def get_knowledge(
    skip: int = Query(0, ge=0, description="Número de resultados a saltar"),
    limit: int = Query(10, ge=1, le=100, description="Número máximo de resultados"),
    activos_only: bool = Query(False, description="Si es True, devuelve solo precios activos"),
    search: str = Query(None, description="Búsqueda por texto en el documento"),
    categoria: str = Query(None, description="Filtrar por categoría")
):
    """
    Lista todos los precios con paginación y filtros opcionales.
    """
    try:
        precios = get_precios(
            skip=skip, 
            limit=limit, 
            activos_only=activos_only, 
            search=search, 
            categoria=categoria
        )
        return precios
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_knowledge(precio: PrecioCreate):
    """
    Inserta un nuevo precio en ChromaDB.
    Valida que los metadatos requeridos estén presentes.
    """
    try:
        precio_id = precio.resolved_id()
        upsert_precio(id=precio_id, texto=precio.documento, metadatos=precio.metadatos)
        return {"status": "success", "message": f"Precio {precio_id} insertado correctamente"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{precio_id}", response_model=dict)
def update_knowledge(precio_id: str, metadata_update: PrecioUpdate):
    """
    Actualiza solo metadatos de un precio existente (sin re-indexar el embedding).
    Solo permite actualizar: precio_unitario, version, activo.
    """
    update_dict = metadata_update.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No se enviaron campos para actualizar")
        
    try:
        update_precio_metadata(precio_id, update_dict)
        return {"status": "success", "message": f"Metadatos del precio {precio_id} actualizados"}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{precio_id}", response_model=dict)
def delete_knowledge(precio_id: str):
    """
    Elimina físicamente el precio de ChromaDB.
    """
    try:
        from rag.embeddings import delete_precio
        delete_precio(precio_id)
        return {"status": "success", "message": f"Precio {precio_id} eliminado correctamente"}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/normalize-clients", response_model=dict)
def normalize_client_fields():
    """
    One-time migration: lowercase all 'cliente' metadata values in ChromaDB.
    Safe to call multiple times (idempotent).
    """
    from rag.embeddings import precios_collection
    batch = 500
    offset = 0
    updated = 0
    while True:
        results = precios_collection.get(limit=batch, offset=offset, include=["metadatas", "documents", "embeddings"])
        ids = results.get("ids", [])
        if not ids:
            break
        metadatas = results.get("metadatas", [])
        to_update_ids = []
        to_update_metas = []
        for i, meta in enumerate(metadatas):
            raw = meta.get("cliente", "")
            normalised = str(raw).strip().lower()
            if raw != normalised:
                meta["cliente"] = normalised
                to_update_ids.append(ids[i])
                to_update_metas.append(meta)
        if to_update_ids:
            precios_collection.update(ids=to_update_ids, metadatas=to_update_metas)
            updated += len(to_update_ids)
        offset += batch
        if len(ids) < batch:
            break
    return {"updated": updated, "message": f"Normalización completada: {updated} registros actualizados"}


@router.post("/import", response_model=dict, status_code=status.HTTP_200_OK)
async def import_knowledge(file: UploadFile = File(...)):
    """
    Carga un CSV con precios y los procesa en lote hacia ChromaDB.
    Requisitos: material, cliente, precio_unitario, unidad, categoria.
    Límite: 5000 filas.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="El archivo debe ser un CSV")
    
    content = await file.read()
    try:
        decoded_content = content.decode('utf-8-sig') # handle BOM if present
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="El archivo debe estar codificado en UTF-8")
        
    reader = csv.DictReader(io.StringIO(decoded_content))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="El CSV está vacío o no tiene encabezados")
        
    required_columns = {"material", "cliente", "precio_unitario", "unidad", "categoria"}
    actual_columns = set(col.strip() for col in reader.fieldnames if col)
    
    if not required_columns.issubset(actual_columns):
        missing = required_columns - actual_columns
        raise HTTPException(status_code=400, detail=f"Faltan columnas requeridas: {missing}")
        
    procesadas = 0
    errores = []
    
    for i, row in enumerate(reader, start=2): # start=2 because row 1 is header
        if i - 1 > 5000:
            errores.append({"fila": i, "error": "Límite de 5000 filas excedido. Se ignoraron las filas restantes."})
            break
            
        try:
            # Prepare metadata
            precio_unitario_str = row.get("precio_unitario", "").strip()
            if not precio_unitario_str:
                raise ValueError("precio_unitario está vacío")
                
            try:
                precio_unitario = float(precio_unitario_str)
            except ValueError:
                raise ValueError("precio_unitario debe ser numérico")
                
            metadatos = {
                "material": row.get("material", "").strip(),
                "cliente": row.get("cliente", "").strip(),
                "precio_unitario": precio_unitario,
                "unidad": row.get("unidad", "").strip(),
                "categoria": row.get("categoria", "").strip(),
                "version": row.get("version", "1.0").strip(),
                "activo": True
            }
            
            # Check for empty required string fields
            for k in required_columns:
                if k != "precio_unitario" and not metadatos[k]:
                    raise ValueError(f"El campo '{k}' no puede estar vacío")
            
            texto = row.get("texto", "").strip()
            if not texto:
                texto = f"{metadatos['material']} para {metadatos['categoria']}"
                
            item_id = row.get("id", "").strip()
            if not item_id:
                item_id = str(uuid.uuid4())
            
            upsert_precio(id=item_id, texto=texto, metadatos=metadatos)
            procesadas += 1
            
        except ValueError as ve:
            errores.append({"fila": i, "error": str(ve)})
        except Exception as e:
            errores.append({"fila": i, "error": f"Error inesperado: {str(e)}"})
            
    return {"procesadas": procesadas, "errores": errores}
