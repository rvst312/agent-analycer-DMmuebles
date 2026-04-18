import pytest
import os
import chromadb
from unittest.mock import patch
from chromadb.utils import embedding_functions

from api.schemas.estimate import PlanoAnalizado, ComponenteArmario, TipoComponente
from agents.pricing_agent import calculate_pricing, get_k_labor
import rag.embeddings

@pytest.fixture(scope="module")
def mock_chroma_collection():
    """
    Fixture que crea un EphemeralClient de ChromaDB con datos mock.
    Parchea precios_collection en rag.embeddings para que use este cliente en memoria.
    """
    client = chromadb.EphemeralClient()
    emb_fn = embedding_functions.DefaultEmbeddingFunction()
    collection = client.create_collection(name="test_precios", embedding_function=emb_fn)
    
    # Mock prices for tablero, puerta, herraje
    # Client: "cliente_1"
    docs = [
        "Tablero MDF Roble natural tablero",
        "Puerta madera Roble barnizado puerta",
        "Herraje Acero inoxidable mate herraje",
        "Tablero Pino natural tablero" # For another client
    ]
    ids = ["tablero_1", "puerta_1", "herraje_1", "tablero_2"]
    metadatas = [
        {"material": "Roble", "cliente": "cliente_1", "precio_unitario": 20.0, "unidad": "m2", "version": "1.0", "categoria": "materia_prima", "activo": True},
        {"material": "Roble", "cliente": "cliente_1", "precio_unitario": 50.0, "unidad": "m2", "version": "1.0", "categoria": "materia_prima", "activo": True},
        {"material": "Acero", "cliente": "cliente_1", "precio_unitario": 5.0, "unidad": "unidad", "version": "1.0", "categoria": "herraje", "activo": True},
        {"material": "Pino", "cliente": "cliente_2", "precio_unitario": 10.0, "unidad": "m2", "version": "1.0", "categoria": "materia_prima", "activo": True}
    ]
    collection.add(documents=docs, ids=ids, metadatas=metadatas)
    
    # Patch the collection in rag.embeddings
    with patch.object(rag.embeddings, 'precios_collection', collection):
        yield collection

def test_get_k_labor(monkeypatch):
    monkeypatch.setenv("K_LABOR_TABLERO", "15.5")
    monkeypatch.setenv("K_LABOR_PUERTA", "20.0")
    
    assert get_k_labor("tablero") == 15.5
    assert get_k_labor("puerta") == 20.0
    assert get_k_labor("cajon") == 0.0 # No set, defaults to 0.0

def test_calculate_pricing_correct_c_total(mock_chroma_collection, monkeypatch):
    """Test: cálculo de C_total correcto para tablero de 2m x 0.6m a precio conocido"""
    monkeypatch.setenv("K_LABOR_TABLERO", "10.0")
    
    plano = PlanoAnalizado(
        plano_id="plano_1",
        confidence_score=0.9,
        raw_reasoning="test",
        componentes=[
            ComponenteArmario(
                tipo=TipoComponente.TABLERO,
                material="Roble",
                acabado="natural",
                ancho_cm=60.0,
                largo_cm=200.0,
                cantidad=1
            )
        ]
    )
    
    presupuesto = calculate_pricing(plano, "cliente_1")
    
    # Area = 2m * 0.6m = 1.2 m2
    # Precio unitario = 20.0 (from mock ChromaDB)
    # C_total unitario = (1.2 * 20.0) + 10.0 (k_labor) = 24.0 + 10.0 = 34.0
    # Total = 34.0
    
    assert len(presupuesto.lineas) == 1
    linea = presupuesto.lineas[0]
    
    assert linea.precio_pendiente is False
    assert linea.precio_unitario == 34.0
    assert linea.subtotal == 34.0
    assert presupuesto.total == 34.0

def test_calculate_pricing_precio_pendiente(mock_chroma_collection, monkeypatch):
    """Test: componente sin precio devuelve precio_pendiente: true"""
    monkeypatch.setenv("K_LABOR_CAJON", "5.0")
    
    plano = PlanoAnalizado(
        plano_id="plano_2",
        confidence_score=0.9,
        raw_reasoning="test",
        componentes=[
            ComponenteArmario(
                tipo=TipoComponente.CAJON,
                material="Cristal", # No tenemos precio de cristal para cliente_1
                acabado="templado",
                ancho_cm=50.0,
                largo_cm=50.0,
                cantidad=2
            )
        ]
    )
    
    presupuesto = calculate_pricing(plano, "cliente_1")
    
    assert len(presupuesto.lineas) == 1
    linea = presupuesto.lineas[0]
    
    assert linea.precio_pendiente is True
    # Area = 0.5 * 0.5 = 0.25
    # Precio unitario RAG = 0
    # C_total unitario = 0 + 5.0 = 5.0
    # Subtotal = 5.0 * 2 = 10.0
    assert linea.precio_unitario == 5.0
    assert linea.subtotal == 10.0
    
    # Total del presupuesto no debe sumar componentes con precio pendiente
    assert presupuesto.total == 0.0

def test_calculate_pricing_filter_by_cliente(mock_chroma_collection, monkeypatch):
    """Test: filtro por cliente_id no devuelve precios de otro cliente"""
    monkeypatch.setenv("K_LABOR_TABLERO", "10.0")
    
    plano = PlanoAnalizado(
        plano_id="plano_3",
        confidence_score=0.9,
        raw_reasoning="test",
        componentes=[
            ComponenteArmario(
                tipo=TipoComponente.TABLERO,
                material="Pino",
                acabado="natural",
                ancho_cm=100.0,
                largo_cm=100.0,
                cantidad=1
            )
        ]
    )
    
    # Si buscamos con cliente_1, no debe encontrar el precio del Pino que es de cliente_2
    presupuesto_c1 = calculate_pricing(plano, "cliente_1")
    assert presupuesto_c1.lineas[0].precio_pendiente is True
    
    # Si buscamos con cliente_2, debe encontrar el precio del Pino (10.0)
    presupuesto_c2 = calculate_pricing(plano, "cliente_2")
    assert presupuesto_c2.lineas[0].precio_pendiente is False
    
    # Area 1m2 * 10.0 = 10.0 + k_labor 10.0 = 20.0
    assert presupuesto_c2.lineas[0].precio_unitario == 20.0

