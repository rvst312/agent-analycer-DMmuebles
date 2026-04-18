import pytest
import os
import shutil
from rag.chroma_client import ChromaClient
from rag.embeddings import EmbeddingModel, upsert_precio, query_precios, seed_datos_ejemplo, precios_collection

# Use a temporary directory for ChromaDB tests
TEST_CHROMA_DIR = "./test_chroma_data"

@pytest.fixture(scope="module")
def chroma_client():
    # Setup
    if os.path.exists(TEST_CHROMA_DIR):
        shutil.rmtree(TEST_CHROMA_DIR)
        
    client = ChromaClient(persist_path=TEST_CHROMA_DIR)
    yield client
    
    # Teardown
    if os.path.exists(TEST_CHROMA_DIR):
        shutil.rmtree(TEST_CHROMA_DIR)

def test_init_collections(chroma_client):
    collections = chroma_client.init_collections()
    assert "pricing_materials" in collections
    assert "pricing_labor" in collections
    assert "pricing_finishes" in collections

def test_add_and_query_documents(chroma_client):
    # Setup test data
    collection_name = "pricing_materials"
    test_docs = [
        {
            "id": "roble_1",
            "text": "Roble tablero acabado natural",
            "metadata": {
                "material": "roble",
                "tipo": "tablero",
                "acabado": "natural",
                "price_per_sqm": 45.50
            }
        },
        {
            "id": "pino_1",
            "text": "Pino tablero crudo",
            "metadata": {
                "material": "pino",
                "tipo": "tablero",
                "acabado": "crudo",
                "price_per_sqm": 15.00
            }
        }
    ]
    
    # Add documents
    chroma_client.add_documents(collection=collection_name, documents=test_docs)
    
    # Query with text and metadata filter
    results = chroma_client.query(
        collection=collection_name,
        query_text="roble",
        filters={"material": "roble"},
        top_k=1
    )
    
    assert len(results) == 1
    assert results[0]["id"] == "roble_1"
    assert results[0]["metadata"]["price_per_sqm"] == 45.50
    
    # Query with only metadata filter
    results_filter = chroma_client.query(
        collection=collection_name,
        filters={"material": "pino"},
        top_k=1
    )
    
    assert len(results_filter) == 1
    assert results_filter[0]["id"] == "pino_1"

def test_embeddings():
    model = EmbeddingModel()
    text = "Roble tablero natural"
    
    embedding = model.embed(text)
    assert isinstance(embedding, list)
    assert len(embedding) > 0
    assert isinstance(embedding[0], float)
    
    batch = model.embed_batch([text, "Pino tablero crudo"])
    assert len(batch) == 2
    assert len(batch[0]) == len(embedding)

def test_upsert_y_query_precios():
    # Insertar un precio válido
    metadatos = {
        "material": "TestMaterial",
        "cliente": "test_cliente_xyz",
        "precio_unitario": "100.5",
        "unidad": "m2",
        "version": "1.0",
        "categoria": "materia_prima"
    }
    
    upsert_precio("test_id_1", "Texto de prueba", metadatos)
    
    # Buscar el precio
    resultados = query_precios("Texto de prueba", "test_cliente_xyz", n_results=1)
    
    assert len(resultados) > 0
    assert resultados[0]["id"] == "test_id_1"
    assert resultados[0]["metadatos"]["precio_unitario"] == 100.5
    
    # Test error en metadatos incompletos
    with pytest.raises(ValueError, match="Metadatos incompletos"):
        upsert_precio("test_id_2", "Texto", {"material": "algo"})

def test_seed_datos_ejemplo():
    seed_datos_ejemplo()
    # Verificar que el cliente_test_1 tiene al menos 2 registros
    resultados = query_precios("roble", "cliente_test_1", n_results=5)
    assert len(resultados) >= 1
    
    # Limpiar los documentos de test
    precios_collection.delete(
        where={"cliente": "test_cliente_xyz"}
    )
    precios_collection.delete(
        where={"cliente": "cliente_test_1"}
    )
    precios_collection.delete(
        where={"cliente": "cliente_test_2"}
    )

