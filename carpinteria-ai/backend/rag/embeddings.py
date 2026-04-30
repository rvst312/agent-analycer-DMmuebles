import os
import uuid
from typing import List, Dict, Any, Optional
from chromadb.utils import embedding_functions
import chromadb

# Absolute default so ChromaDB finds the same directory regardless of working dir
_DEFAULT_CHROMA_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chroma_data")
)

# Use HTTP client when CHROMA_HOST/CHROMA_PORT are set (Docker), otherwise local PersistentClient
_chroma_host = os.environ.get("CHROMA_HOST")
_chroma_port = os.environ.get("CHROMA_PORT")
if _chroma_host and _chroma_port:
    chroma_client = chromadb.HttpClient(host=_chroma_host, port=int(_chroma_port))
else:
    chroma_client = chromadb.PersistentClient(
        path=os.environ.get("CHROMA_PERSIST_PATH", _DEFAULT_CHROMA_PATH)
    )

emb_fn = embedding_functions.DefaultEmbeddingFunction()
precios_collection = chroma_client.get_or_create_collection(
    name="precios",
    embedding_function=emb_fn
)

def upsert_precio(id: str, texto: str, metadatos: dict) -> None:
    """
    Inserta o actualiza un precio en ChromaDB.
    Los metadatos obligatorios son: material, cliente, precio_unitario, unidad, version, categoria.
    """
    required_keys = {"material", "cliente", "precio_unitario", "unidad", "version", "categoria"}
    if not required_keys.issubset(metadatos.keys()):
        missing = required_keys - set(metadatos.keys())
        raise ValueError(f"Metadatos incompletos. Faltan: {missing}")
    
    # Asegurarnos de que el precio_unitario sea float
    try:
        metadatos["precio_unitario"] = float(metadatos["precio_unitario"])
    except ValueError:
        raise ValueError("precio_unitario debe ser un número (float)")

    # Añadir campo 'activo' por defecto si no existe
    if "activo" not in metadatos:
        metadatos["activo"] = True

    precios_collection.upsert(
        ids=[id],
        documents=[texto],
        metadatas=[metadatos]
    )

def get_precios(skip: int = 0, limit: int = 10, activos_only: bool = False) -> List[Dict[str, Any]]:
    """
    Lista los precios con paginación. Opcionalmente filtra por activo=True.
    """
    where_clause = {"activo": True} if activos_only else None
    results = precios_collection.get(
        limit=limit,
        offset=skip,
        where=where_clause
    )
    
    formatted_results = []
    if results and results.get("ids"):
        for i in range(len(results["ids"])):
            formatted_results.append({
                "id": results["ids"][i],
                "documento": results["documents"][i] if results.get("documents") else "",
                "metadatos": results["metadatas"][i] if results.get("metadatas") else {}
            })
    return formatted_results

def update_precio_metadata(id: str, metadatos_update: dict) -> None:
    """
    Actualiza solo los metadatos de un precio existente sin re-indexar el embedding.
    """
    # Obtener el precio actual para no sobrescribir metadatos que no se envíen
    current = precios_collection.get(ids=[id])
    if not current or not current.get("ids") or len(current["ids"]) == 0:
        raise ValueError(f"No se encontró el precio con id {id}")
        
    current_metadata = current["metadatas"][0] if current.get("metadatas") else {}
    
    # Actualizar con los nuevos valores
    for k, v in metadatos_update.items():
        if v is not None:
            if k == "precio_unitario":
                try:
                    current_metadata[k] = float(v)
                except ValueError:
                    raise ValueError("precio_unitario debe ser un número (float)")
            else:
                current_metadata[k] = v
                
    precios_collection.update(
        ids=[id],
        metadatas=[current_metadata]
    )

def delete_precio_logico(id: str) -> None:
    """
    Realiza un borrado lógico marcando el precio como inactivo.
    """
    update_precio_metadata(id, {"activo": False})

def query_precios(texto: str, cliente_id: str, version: Optional[str] = None, n_results: int = 5) -> List[Dict[str, Any]]:
    """
    Busca precios similares filtrando por cliente_id, activo=True y opcionalmente por version.
    Returns [] safely when no documents match or when n_results > collection size.
    """
    conditions: List[Dict[str, Any]] = [
        {"cliente": {"$eq": cliente_id}},
        {"activo": {"$eq": True}},
    ]
    if version:
        conditions.append({"version": {"$eq": version}})
    where_clause: Dict[str, Any] = {"$and": conditions}

    try:
        results = precios_collection.query(
            query_texts=[texto],
            n_results=n_results,
            where=where_clause
        )
    except Exception as e:
        # ChromaDB raises ValueError when n_results > number of matching documents (including 0)
        import logging as _log
        _log.getLogger(__name__).warning(
            f"ChromaDB query returned no results for '{texto}' (cliente={cliente_id}): {e}"
        )
        return []

    formatted_results = []
    if results and results.get("ids") and len(results["ids"]) > 0:
        for i in range(len(results["ids"][0])):
            formatted_results.append({
                "id": results["ids"][0][i],
                "documento": results["documents"][0][i] if results.get("documents") else "",
                "metadatos": results["metadatas"][0][i] if results.get("metadatas") else {},
                "distancia": results["distances"][0][i] if results.get("distances") else 0.0
            })

    return formatted_results

def seed_datos_ejemplo() -> None:
    """
    Puebla la colección 'precios' con datos de ejemplo para desarrollo.
    """
    datos_ejemplo = [
        {
            "id": "precio_madera_roble_001",
            "texto": "Madera de roble alta calidad para muebles premium",
            "metadatos": {
                "material": "Roble",
                "cliente": "cliente_test_1",
                "precio_unitario": 120.50,
                "unidad": "m2",
                "version": "1.0",
                "categoria": "materia_prima"
            }
        },
        {
            "id": "precio_tornillos_001",
            "texto": "Tornillos de acero inoxidable 5mm",
            "metadatos": {
                "material": "Acero Inoxidable",
                "cliente": "cliente_test_1",
                "precio_unitario": 0.15,
                "unidad": "unidad",
                "version": "1.0",
                "categoria": "herrajes"
            }
        },
        {
            "id": "precio_barniz_001",
            "texto": "Barniz mate transparente para madera",
            "metadatos": {
                "material": "Barniz",
                "cliente": "cliente_test_2",
                "precio_unitario": 25.00,
                "unidad": "litro",
                "version": "1.0",
                "categoria": "acabados"
            }
        }
    ]
    
    for dato in datos_ejemplo:
        upsert_precio(dato["id"], dato["texto"], dato["metadatos"])

class EmbeddingModel:
    """
    Modelo de embeddings para representar documentos de precios.
    Utiliza la función de embeddings por defecto de ChromaDB.
    """
    def __init__(self):
        # Utiliza el modelo por defecto de ChromaDB (all-MiniLM-L6-v2)
        self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
        
    def embed(self, text: str) -> List[float]:
        """
        Genera un embedding para un texto dado.
        """
        embeddings = self.embedding_function([text])
        if embeddings and len(embeddings) > 0:
            return embeddings[0].tolist() if hasattr(embeddings[0], 'tolist') else list(embeddings[0])
        return []
        
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Genera embeddings para una lista de textos.
        """
        embeddings = self.embedding_function(texts)
        return [emb.tolist() if hasattr(emb, 'tolist') else list(emb) for emb in embeddings]

