from typing import List
from chromadb.utils import embedding_functions

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
