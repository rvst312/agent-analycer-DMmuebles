import pytest
from fastapi.testclient import TestClient
from main import app
from api.auth import verify_admin_token
from rag.embeddings import precios_collection

# Override the authentication dependency for testing
def override_verify_admin_token():
    return {"role": "admin", "sub": "testadmin"}

app.dependency_overrides[verify_admin_token] = override_verify_admin_token

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup: Ensure clean state for test client
    precios_collection.delete(where={"cliente": "cliente_test_crud"})
    yield
    # Teardown: Clean up
    precios_collection.delete(where={"cliente": "cliente_test_crud"})

def test_create_knowledge():
    response = client.post(
        "/knowledge",
        json={
            "id": "test_precio_001",
            "texto": "Material de prueba CRUD",
            "metadatos": {
                "material": "Madera Prueba",
                "cliente": "cliente_test_crud",
                "precio_unitario": 50.0,
                "unidad": "m2",
                "version": "1.0",
                "categoria": "materia_prima"
            }
        }
    )
    assert response.status_code == 201
    assert response.json()["status"] == "success"

def test_get_knowledge():
    # Insert first
    client.post(
        "/knowledge",
        json={
            "id": "test_precio_002",
            "texto": "Material de prueba CRUD 2",
            "metadatos": {
                "material": "Madera Prueba 2",
                "cliente": "cliente_test_crud",
                "precio_unitario": 60.0,
                "unidad": "m2",
                "version": "1.0",
                "categoria": "materia_prima"
            }
        }
    )
    
    response = client.get("/knowledge?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    # Encontrar el que insertamos
    found = next((item for item in data if item["id"] == "test_precio_002"), None)
    assert found is not None
    assert found["metadatos"]["precio_unitario"] == 60.0
    assert found["metadatos"]["activo"] is True

def test_update_knowledge():
    # Insert first
    client.post(
        "/knowledge",
        json={
            "id": "test_precio_003",
            "texto": "Material de prueba CRUD 3",
            "metadatos": {
                "material": "Madera Prueba 3",
                "cliente": "cliente_test_crud",
                "precio_unitario": 70.0,
                "unidad": "m2",
                "version": "1.0",
                "categoria": "materia_prima"
            }
        }
    )
    
    # Update
    response = client.patch(
        "/knowledge/test_precio_003",
        json={
            "precio_unitario": 75.5,
            "version": "1.1"
        }
    )
    assert response.status_code == 200
    
    # Verify update
    get_response = client.get("/knowledge")
    data = get_response.json()
    found = next((item for item in data if item["id"] == "test_precio_003"), None)
    assert found is not None
    assert found["metadatos"]["precio_unitario"] == 75.5
    assert found["metadatos"]["version"] == "1.1"
    assert found["metadatos"]["material"] == "Madera Prueba 3" # Should remain unchanged

def test_delete_knowledge():
    # Insert first
    client.post(
        "/knowledge",
        json={
            "id": "test_precio_004",
            "texto": "Material de prueba CRUD 4",
            "metadatos": {
                "material": "Madera Prueba 4",
                "cliente": "cliente_test_crud",
                "precio_unitario": 80.0,
                "unidad": "m2",
                "version": "1.0",
                "categoria": "materia_prima"
            }
        }
    )
    
    # Delete (Logical)
    response = client.delete("/knowledge/test_precio_004")
    assert response.status_code == 200
    
    # Verify it's inactive
    get_response = client.get("/knowledge?activos_only=true")
    data = get_response.json()
    found = next((item for item in data if item["id"] == "test_precio_004"), None)
    assert found is None # No debería aparecer si activos_only=true
    
    get_all_response = client.get("/knowledge?activos_only=false")
    data_all = get_all_response.json()
    found_all = next((item for item in data_all if item["id"] == "test_precio_004"), None)
    assert found_all is not None
    assert found_all["metadatos"]["activo"] is False
