"""
CRUD precios en ChromaDB
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List

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
    activos_only: bool = Query(False, description="Si es True, devuelve solo precios activos")
):
    """
    Lista todos los precios con paginación.
    """
    try:
        precios = get_precios(skip=skip, limit=limit, activos_only=activos_only)
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
        upsert_precio(id=precio.id, texto=precio.texto, metadatos=precio.metadatos)
        return {"status": "success", "message": f"Precio {precio.id} insertado correctamente"}
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
    Realiza un borrado lógico marcando el precio como inactivo (activo=False).
    """
    try:
        delete_precio_logico(precio_id)
        return {"status": "success", "message": f"Precio {precio_id} marcado como inactivo"}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
