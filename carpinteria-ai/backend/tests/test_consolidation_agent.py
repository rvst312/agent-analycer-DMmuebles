import pytest
from unittest.mock import AsyncMock, patch
from api.schemas.estimate import LineaPresupuesto, Presupuesto
from agents.consolidation_agent import calcular_presupuesto_consolidado, execute_consolidation

@pytest.fixture
def mock_presupuesto():
    return Presupuesto(
        plano_id="plano_123",
        lineas=[
            LineaPresupuesto(
                descripcion="Tablero de Roble",
                cantidad=2,
                precio_unitario=50.0,
                subtotal=100.0,
                precio_pendiente=False
            ),
            LineaPresupuesto(
                descripcion="Herraje Especial",
                cantidad=1,
                precio_unitario=0.0,
                subtotal=0.0,
                precio_pendiente=True
            )
        ],
        total=100.0
    )

def test_calcular_presupuesto_consolidado(mock_presupuesto):
    consolidado = calcular_presupuesto_consolidado(mock_presupuesto, "cliente_456")
    
    assert consolidado.cliente_id == "cliente_456"
    assert consolidado.plano_id == "plano_123"
    assert consolidado.subtotal == 100.0
    assert consolidado.iva == 21.0
    assert consolidado.total == 121.0
    assert len(consolidado.lineas_pendientes) == 1
    assert consolidado.lineas_pendientes[0].descripcion == "Herraje Especial"
    assert consolidado.status == "pending_review"

@pytest.mark.anyio
@patch("agents.consolidation_agent.guardar_presupuesto_en_db", new_callable=AsyncMock)
async def test_execute_consolidation(mock_guardar, mock_presupuesto):
    consolidado = await execute_consolidation(mock_presupuesto, "cliente_456")
    
    assert consolidado.subtotal == 100.0
    assert consolidado.total == 121.0
    mock_guardar.assert_called_once_with(consolidado)
