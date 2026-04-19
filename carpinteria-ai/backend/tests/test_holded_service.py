import pytest
from unittest.mock import patch, MagicMock
import requests

from api.schemas.holded import ContactoSchema
from api.schemas.estimate import PresupuestoConsolidado, LineaPresupuesto
from services.holded_service import buscar_contacto, crear_contacto, get_or_create_contacto, crear_presupuesto

@pytest.fixture
def mock_contacto():
    return ContactoSchema(
        nombre="Test Contact",
        nif="12345678A",
        email="test@example.com",
        telefono="123456789"
    )

@patch("services.holded_service.requests.get")
def test_buscar_contacto_success(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = [{"id": "contact_123"}]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    result = buscar_contacto("12345678A")
    assert result == "contact_123"
    mock_get.assert_called_once()

@patch("services.holded_service.requests.get")
def test_buscar_contacto_not_found(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    result = buscar_contacto("12345678A")
    assert result is None

@patch("services.holded_service.requests.get")
def test_buscar_contacto_timeout(mock_get):
    mock_get.side_effect = requests.exceptions.Timeout()

    result = buscar_contacto("12345678A")
    assert result is None

@patch("services.holded_service.requests.post")
def test_crear_contacto_success(mock_post, mock_contacto):
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": 1, "id": "contact_456"}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    result = crear_contacto(mock_contacto)
    assert result == "contact_456"
    mock_post.assert_called_once()

@patch("services.holded_service.requests.post")
def test_crear_contacto_error(mock_post, mock_contacto):
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": 0, "info": "Error"}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    result = crear_contacto(mock_contacto)
    assert result is None

@patch("services.holded_service.buscar_contacto")
@patch("services.holded_service.crear_contacto")
def test_get_or_create_contacto_exists(mock_crear, mock_buscar, mock_contacto):
    mock_buscar.return_value = "contact_123"
    
    result = get_or_create_contacto("12345678A", mock_contacto)
    assert result == "contact_123"
    mock_buscar.assert_called_once_with("12345678A")
    mock_crear.assert_not_called()

@patch("services.holded_service.buscar_contacto")
@patch("services.holded_service.crear_contacto")
def test_get_or_create_contacto_not_exists(mock_crear, mock_buscar, mock_contacto):
    mock_buscar.return_value = None
    mock_crear.return_value = "contact_456"
    
    result = get_or_create_contacto("12345678A", mock_contacto)
    assert result == "contact_456"
    mock_buscar.assert_called_once_with("12345678A")
    mock_crear.assert_called_once_with(mock_contacto)

@pytest.fixture
def mock_presupuesto_consolidado():
    return PresupuestoConsolidado(
        cliente_id="cliente_123",
        plano_id="plano_123",
        lineas=[
            LineaPresupuesto(
                descripcion="Madera Roble",
                cantidad=2,
                precio_unitario=50.0,
                subtotal=100.0,
                precio_pendiente=False
            )
        ],
        subtotal=100.0,
        iva=21.0,
        total=121.0,
        lineas_pendientes=[]
    )

@patch("services.holded_service.requests.post")
def test_crear_presupuesto_success(mock_post, mock_presupuesto_consolidado):
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": 1, "id": "estimate_123"}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    result = crear_presupuesto("contact_123", mock_presupuesto_consolidado)
    
    assert result == "estimate_123"
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "contactId" in kwargs["json"]
    assert kwargs["json"]["contactId"] == "contact_123"
    assert "items" in kwargs["json"]
    assert len(kwargs["json"]["items"]) == 1
    assert kwargs["json"]["items"][0]["name"] == "Madera Roble"

@patch("services.holded_service.requests.post")
def test_crear_presupuesto_error(mock_post, mock_presupuesto_consolidado):
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": 0, "info": "Error"}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    result = crear_presupuesto("contact_123", mock_presupuesto_consolidado)
    assert result is None

@patch("services.holded_service.requests.post")
def test_crear_presupuesto_timeout(mock_post, mock_presupuesto_consolidado):
    mock_post.side_effect = requests.exceptions.Timeout()

    result = crear_presupuesto("contact_123", mock_presupuesto_consolidado)
    assert result is None
