import pytest
from fastapi.testclient import TestClient
import io
from unittest.mock import patch, AsyncMock, MagicMock

from main import app

client = TestClient(app)

def test_create_estimate_valid_image():
    # Creamos un archivo de imagen en memoria simulado
    file_content = b"fake image data"
    file = io.BytesIO(file_content)
    file.name = "plano.png"
    
    response = client.post(
        "/estimates",
        data={"cliente_id": "cliente_123"},
        files={"file": ("plano.png", file, "image/png")}
    )
    
    assert response.status_code == 202
    data = response.json()
    assert "estimate_id" in data
    assert data["status"] == "processing"

def test_create_estimate_valid_pdf():
    file_content = b"fake pdf data"
    file = io.BytesIO(file_content)
    file.name = "documento.pdf"
    
    response = client.post(
        "/estimates",
        data={"cliente_id": "cliente_456"},
        files={"file": ("documento.pdf", file, "application/pdf")}
    )
    
    assert response.status_code == 202
    data = response.json()
    assert "estimate_id" in data
    assert data["status"] == "processing"

def test_create_estimate_invalid_mime_type():
    file_content = b"fake text data"
    file = io.BytesIO(file_content)
    file.name = "documento.txt"
    
    response = client.post(
        "/estimates",
        data={"cliente_id": "cliente_789"},
        files={"file": ("documento.txt", file, "text/plain")}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Tipo de archivo no permitido" in data["detail"]

class MockStateSnapshot:
    def __init__(self, values, next_nodes=()):
        self.values = values
        self.next = next_nodes

class MockCheckpointerContext:
    async def __aenter__(self):
        return MagicMock()
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

def mock_get_checkpointer():
    return MockCheckpointerContext()

@patch("api.routes.estimates.get_checkpointer", side_effect=mock_get_checkpointer)
@patch("graph.workflow.workflow.compile")
def test_get_estimate_status_not_found(mock_compile, mock_cp):
    mock_graph = AsyncMock()
    mock_graph.aget_state.return_value = None
    mock_compile.return_value = mock_graph

    response = client.get("/estimates/no-existe")
    
    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]

@patch("api.routes.estimates.get_checkpointer", side_effect=mock_get_checkpointer)
@patch("graph.workflow.workflow.compile")
def test_get_estimate_status_processing(mock_compile, mock_cp):
    mock_graph = AsyncMock()
    mock_graph.aget_state.return_value = MockStateSnapshot(
        values={"status": "processing", "cliente_id": "c1"},
        next_nodes=("some_node",)
    )
    mock_compile.return_value = mock_graph

    response = client.get("/estimates/123")
    
    assert response.status_code == 200
    data = response.json()
    assert data["estimate_id"] == "123"
    assert data["status"] == "processing"
    assert data["cliente_id"] == "c1"

@patch("api.routes.estimates.get_checkpointer", side_effect=mock_get_checkpointer)
@patch("graph.workflow.workflow.compile")
def test_get_estimate_status_human_approval(mock_compile, mock_cp):
    mock_graph = AsyncMock()
    mock_graph.aget_state.return_value = MockStateSnapshot(
        values={"status": "consolidated", "plano_id": "p1"},
        next_nodes=("human_approval",)
    )
    mock_compile.return_value = mock_graph

    response = client.get("/estimates/123")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "human_approval_required"
    assert data["plano_id"] == "p1"

@patch("api.routes.estimates.get_checkpointer", side_effect=mock_get_checkpointer)
@patch("graph.workflow.workflow.compile")
def test_get_estimate_status_completed(mock_compile, mock_cp):
    mock_graph = AsyncMock()
    mock_graph.aget_state.return_value = MockStateSnapshot(
        values={"status": "sent_to_holded"},
        next_nodes=()
    )
    mock_compile.return_value = mock_graph

    response = client.get("/estimates/123")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"

@patch("api.routes.estimates.get_checkpointer", side_effect=mock_get_checkpointer)
@patch("graph.workflow.workflow.compile")
def test_get_estimate_status_error(mock_compile, mock_cp):
    mock_graph = AsyncMock()
    mock_graph.aget_state.return_value = MockStateSnapshot(
        values={"status": "error", "error": "Fallo el OCR"},
        next_nodes=()
    )
    mock_compile.return_value = mock_graph

    response = client.get("/estimates/123")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert data["error"] == "Fallo el OCR"

class MockCheckpointTuple:
    def __init__(self, thread_id, status, next_nodes=(), ts="2026-04-19T00:00:00Z"):
        self.config = {"configurable": {"thread_id": thread_id}}
        self.checkpoint = {"ts": ts}
        self.status = status
        self.next_nodes = next_nodes

class MockCheckpointerWithList(MockCheckpointerContext):
    def __init__(self, tuples):
        self.tuples = tuples
        self.mock_cp = AsyncMock()
        
        async def mock_alist(*args, **kwargs):
            for t in self.tuples:
                yield t
        
        self.mock_cp.alist = mock_alist
        
    async def __aenter__(self):
        return self.mock_cp

@patch("api.routes.estimates.get_checkpointer")
@patch("graph.workflow.workflow.compile")
def test_list_estimates(mock_compile, mock_get_cp):
    # Crear datos simulados
    t1 = MockCheckpointTuple("t1", "processing", ("some_node",))
    t2 = MockCheckpointTuple("t2", "consolidated", ("human_approval",))
    
    mock_cp_instance = MockCheckpointerWithList([t1, t2])
    mock_get_cp.return_value = mock_cp_instance
    
    mock_graph = AsyncMock()
    
    # Simulamos el aget_state para que devuelva el estado correspondiente
    async def mock_aget_state(config):
        thread_id = config["configurable"]["thread_id"]
        if thread_id == "t1":
            return MockStateSnapshot(values={"status": "processing", "cliente_id": "c1"}, next_nodes=("some_node",))
        elif thread_id == "t2":
            return MockStateSnapshot(values={"status": "consolidated", "plano_id": "p2"}, next_nodes=("human_approval",))
        return None
        
    mock_graph.aget_state = mock_aget_state
    mock_compile.return_value = mock_graph

    response = client.get("/estimates")
    
    assert response.status_code == 200
    data = response.json()
    assert "estimates" in data
    estimates = data["estimates"]
    assert len(estimates) == 2
    
    # Validar el primer estimate
    e1 = next(e for e in estimates if e["estimate_id"] == "t1")
    assert e1["status"] == "processing"
    assert e1["cliente_id"] == "c1"
    
    # Validar el segundo estimate
    e2 = next(e for e in estimates if e["estimate_id"] == "t2")
    assert e2["status"] == "human_approval_required"
    assert e2["plano_id"] == "p2"
