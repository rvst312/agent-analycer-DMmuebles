import os
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings

class ChromaClient:
    """
    Cliente para interactuar con ChromaDB para RAG.
    Maneja la persistencia de embeddings y colecciones para precios.
    """
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, persist_path: str = "./chroma_data"):
        # Utilizamos PersistentClient si host/port no se proveen
        env_persist_path = os.environ.get("CHROMA_PERSIST_PATH", persist_path)
        
        if host and port:
            self.client = chromadb.HttpClient(host=host, port=port)
        else:
            self.client = chromadb.PersistentClient(path=env_persist_path)
            
    def create_collection(self, name: str):
        """Crea o obtiene una colección"""
        return self.client.get_or_create_collection(name=name)
        
    def add_documents(self, collection: str, documents: List[Dict[str, Any]]):
        """
        Añade documentos a una colección.
        documents: Lista de dicts con 'id', 'text', 'metadata'
        """
        col = self.client.get_or_create_collection(name=collection)
        
        ids = [doc["id"] for doc in documents]
        texts = [doc["text"] for doc in documents]
        metadatas = [doc.get("metadata", {}) for doc in documents]
        
        col.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas
        )
        
    def query(self, collection: str, query_text: str = "", filters: Dict[str, Any] = None, top_k: int = 1) -> List[Dict[str, Any]]:
        """
        Consulta documentos en una colección.
        Si query_text está vacío, sólo filtra por metadata.
        """
        col = self.client.get_collection(name=collection)
        
        # Si no hay texto de búsqueda, obtenemos por filtros
        if not query_text:
            results = col.get(where=filters, limit=top_k)
            formatted_results = []
            if results and results["ids"]:
                for i in range(len(results["ids"])):
                    formatted_results.append({
                        "id": results["ids"][i],
                        "metadata": results["metadatas"][i] if results["metadatas"] else {},
                        "text": results["documents"][i] if results["documents"] else "",
                        "distance": 0.0
                    })
            return formatted_results
            
        # Si hay texto, hacemos búsqueda vectorial
        query_args = {
            "query_texts": [query_text],
            "n_results": top_k
        }
        
        if filters:
            query_args["where"] = filters
            
        results = col.query(**query_args)
        
        formatted_results = []
        if results and results["ids"] and len(results["ids"]) > 0:
            for i in range(len(results["ids"][0])):
                formatted_results.append({
                    "id": results["ids"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "distance": results["distances"][0][i] if results["distances"] else 0.0
                })
                
        return formatted_results
        
    def init_collections(self):
        """Inicializa las colecciones iniciales necesarias para el sistema"""
        collections = ["pricing_materials", "pricing_labor", "pricing_finishes"]
        for col in collections:
            self.create_collection(col)
            
        return collections
