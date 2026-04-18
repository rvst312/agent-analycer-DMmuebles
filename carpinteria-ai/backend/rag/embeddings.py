import uuid
from typing import List, Dict, Any, Optional
from chromadb.utils import embedding_functions
import chromadb

# Initialize the ChromaDB client
chroma_client = chromadb.PersistentClient(path="./chroma_data")
# Default embedding function
emb_fn = embedding_functions.DefaultEmbeddingFunction()
# Get or create the collection for prices
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

    precios_collection.upsert(
        ids=[id],
        documents=[texto],
        metadatas=[metadatos]
    )

def query_precios(texto: str, cliente_id: str, version: Optional[str] = None, n_results: int = 5) -> List[Dict[str, Any]]:
    """
    Busca precios similares filtrando por cliente_id y opcionalmente por version.
    """
    where_clause: Dict[str, Any]
    if version:
        where_clause = {
            "$and": [
                {"cliente": {"$eq": cliente_id}},
                {"version": {"$eq": version}}
            ]
        }
    else:
        where_clause = {"cliente": cliente_id}
        
    results = precios_collection.query(
        query_texts=[texto],
        n_results=n_results,
        where=where_clause
    )
    
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

