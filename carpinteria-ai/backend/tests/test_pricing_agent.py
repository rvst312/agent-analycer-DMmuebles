import pytest
from unittest.mock import patch
import os
from api.schemas.estimate import PlanoAnalizado, ComponenteArmario, TipoComponente
from agents.pricing_agent import calculate_pricing, get_k_labor

def test_get_k_labor(monkeypatch):
    monkeypatch.setenv("K_LABOR_TABLERO", "15.5")
    monkeypatch.setenv("K_LABOR_PUERTA", "20.0")
    
    assert get_k_labor("tablero") == 15.5
    assert get_k_labor("puerta") == 20.0
    assert get_k_labor("cajon") == 0.0 # No set, defaults to 0.0

@patch("agents.pricing_agent.query_precios")
def test_calculate_pricing(mock_query_precios, monkeypatch):
    monkeypatch.setenv("K_LABOR_TABLERO", "5.0")
    monkeypatch.setenv("K_LABOR_HERRAJE", "1.0")
    
    # Mock RAG response
    def mock_query(texto, cliente_id, version=None, n_results=1):
        if "Roble" in texto:
            return [{
                "id": "1",
                "metadatos": {"precio_unitario": "50.0"}
            }]
        return [] # No encontrado
        
    mock_query_precios.side_side_effect = mock_query
    mock_query_precios.side_effect = mock_query
    
    plano = PlanoAnalizado(
        plano_id="plano_test_1",
        confidence_score=0.9,
        raw_reasoning="test",
        componentes=[
            ComponenteArmario(
                tipo=TipoComponente.TABLERO,
                material="Roble",
                acabado="Barnizado",
                ancho_cm=100.0,
                largo_cm=200.0,
                cantidad=2
            ),
            ComponenteArmario(
                tipo=TipoComponente.HERRAJE,
                material="Acero",
                acabado="Mate",
                ancho_cm=10.0,
                largo_cm=10.0,
                cantidad=4
            )
        ]
    )
    
    presupuesto = calculate_pricing(plano, "cliente_test")
    
    assert presupuesto.plano_id == "plano_test_1"
    assert len(presupuesto.lineas) == 2
    
    # Linea 1: Tablero Roble (precio_unitario 50.0)
    # Area: 1m x 2m = 2m2
    # Coste material por unidad: 2m2 * 50 = 100
    # K_labor: 5.0
    # Coste total por unidad: 105.0
    # Subtotal para 2 unidades: 210.0
    linea1 = presupuesto.lineas[0]
    assert linea1.precio_pendiente is False
    assert linea1.cantidad == 2
    assert linea1.precio_unitario == 105.0
    assert linea1.subtotal == 210.0
    
    # Linea 2: Herraje Acero (precio_pendiente True)
    # Area: 0.1m x 0.1m = 0.01m2
    # Precio: 0.0 (pendiente)
    # K_labor: 1.0
    # Coste total por unidad: 1.0
    # Subtotal para 4 unidades: 4.0
    # Aunque subtotal es calculado, si precio_pendiente es True, no se debe sumar al total del presupuesto según implementación actual
    # Wait, my implementation sum total only if not precio_pendiente:
    # "if not precio_pendiente: total += subtotal"
    linea2 = presupuesto.lineas[1]
    assert linea2.precio_pendiente is True
    assert linea2.subtotal == 4.0
    
    assert presupuesto.total == 210.0
