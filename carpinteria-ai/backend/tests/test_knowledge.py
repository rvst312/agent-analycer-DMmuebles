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

CLIENTE_TEST = "cliente_test_crud"
# GET /knowledge solo filtra por categoría (no por cliente) y pagina con
# limit<=100. Todos los registros de prueba usan esta categoría exclusiva para
# localizarlos de forma determinista sin depender del resto de la base real.
CATEGORIA_TEST = "categoria_test_crud"


@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup: Ensure clean state for test client
    precios_collection.delete(where={"cliente": CLIENTE_TEST})
    yield
    # Teardown: Clean up
    precios_collection.delete(where={"cliente": CLIENTE_TEST})


def _payload(id, documento, material, precio_unitario):
    return {
        "id": id,
        "documento": documento,
        "metadatos": {
            "material": material,
            "cliente": CLIENTE_TEST,
            "precio_unitario": precio_unitario,
            "unidad": "m2",
            "version": "1.0",
            "categoria": CATEGORIA_TEST,
        },
    }


def _listar_test(**params):
    """Lista los registros de prueba (por categoría exclusiva, hasta 100)."""
    query = {"categoria": CATEGORIA_TEST, "limit": 100, **params}
    response = client.get("/knowledge", params=query)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    return data


def _buscar(items, id):
    return next((item for item in items if item["id"] == id), None)


def test_create_knowledge():
    response = client.post(
        "/knowledge",
        json=_payload("test_precio_001", "Material de prueba CRUD", "Madera Prueba", 50.0),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "success"
    assert "test_precio_001" in body["message"]

    # Verificar lo que quedó almacenado en ChromaDB
    stored = precios_collection.get(ids=["test_precio_001"])
    assert stored["ids"] == ["test_precio_001"]
    assert stored["documents"][0] == "Material de prueba CRUD"
    assert stored["metadatas"][0]["material"] == "Madera Prueba"
    assert stored["metadatas"][0]["precio_unitario"] == 50.0
    assert stored["metadatas"][0]["activo"] is True


def test_create_knowledge_requires_documento():
    # El campo antiguo `texto` ya no es válido: el esquema exige `documento`.
    payload = _payload("test_precio_005", "irrelevante", "Madera Prueba", 50.0)
    payload["texto"] = payload.pop("documento")

    response = client.post("/knowledge", json=payload)

    assert response.status_code == 422
    assert precios_collection.get(ids=["test_precio_005"])["ids"] == []


def test_create_knowledge_incomplete_metadata():
    payload = _payload("test_precio_006", "Material incompleto", "Madera Prueba", 50.0)
    del payload["metadatos"]["unidad"]

    response = client.post("/knowledge", json=payload)

    assert response.status_code == 400
    assert "Metadatos incompletos" in response.json()["detail"]
    assert precios_collection.get(ids=["test_precio_006"])["ids"] == []


def test_get_knowledge():
    # Insert first
    client.post(
        "/knowledge",
        json=_payload("test_precio_002", "Material de prueba CRUD 2", "Madera Prueba 2", 60.0),
    )

    data = _listar_test()

    # Encontrar el que insertamos
    found = _buscar(data, "test_precio_002")
    assert found is not None
    assert found["documento"] == "Material de prueba CRUD 2"
    assert found["metadatos"]["material"] == "Madera Prueba 2"
    assert found["metadatos"]["precio_unitario"] == 60.0
    assert found["metadatos"]["activo"] is True


def test_update_knowledge():
    # Insert first
    client.post(
        "/knowledge",
        json=_payload("test_precio_003", "Material de prueba CRUD 3", "Madera Prueba 3", 70.0),
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
    assert response.json()["status"] == "success"

    # Verify update
    data = _listar_test()
    found = _buscar(data, "test_precio_003")
    assert found is not None
    assert found["metadatos"]["precio_unitario"] == 75.5
    assert found["metadatos"]["version"] == "1.1"
    assert found["metadatos"]["material"] == "Madera Prueba 3"  # Should remain unchanged


def test_update_knowledge_errors():
    # Sin campos a actualizar -> 400
    response = client.patch("/knowledge/test_precio_003", json={})
    assert response.status_code == 400

    # Id inexistente -> 404
    response = client.patch("/knowledge/test_precio_inexistente", json={"precio_unitario": 10.0})
    assert response.status_code == 404


def test_deactivate_knowledge():
    # Borrado lógico: PATCH activo=false (el registro sigue existiendo)
    client.post(
        "/knowledge",
        json=_payload("test_precio_007", "Material de prueba CRUD 7", "Madera Prueba 7", 90.0),
    )

    response = client.patch("/knowledge/test_precio_007", json={"activo": False})
    assert response.status_code == 200

    # Verify it's inactive
    data = _listar_test(activos_only=True)
    assert _buscar(data, "test_precio_007") is None  # No debería aparecer si activos_only=true

    data_all = _listar_test(activos_only=False)
    found_all = _buscar(data_all, "test_precio_007")
    assert found_all is not None
    assert found_all["metadatos"]["activo"] is False


def test_delete_knowledge():
    # Insert first
    client.post(
        "/knowledge",
        json=_payload("test_precio_004", "Material de prueba CRUD 4", "Madera Prueba 4", 80.0),
    )
    assert _buscar(_listar_test(), "test_precio_004") is not None

    # Delete (físico: DELETE /knowledge/{id} elimina el registro de ChromaDB)
    response = client.delete("/knowledge/test_precio_004")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Ya no aparece ni como activo ni en el listado completo
    assert _buscar(_listar_test(activos_only=True), "test_precio_004") is None
    assert _buscar(_listar_test(activos_only=False), "test_precio_004") is None
    assert precios_collection.get(ids=["test_precio_004"])["ids"] == []


def test_import_knowledge_csv():
    # CSV content with 2 valid rows and 1 invalid row (missing material)
    csv_content = f"""material,cliente,precio_unitario,unidad,categoria,texto,version,id
Madera Roble,{CLIENTE_TEST},150.0,m2,{CATEGORIA_TEST},Texto roble,1.0,import_001
,{CLIENTE_TEST},20.0,unidad,herrajes,Tornillos,1.0,import_002
Cristal,{CLIENTE_TEST},80.5,m2,{CATEGORIA_TEST},Texto cristal,1.0,import_003
"""
    files = {"file": ("test.csv", csv_content, "text/csv")}

    response = client.post("/knowledge/import", files=files)
    assert response.status_code == 200
    data = response.json()

    assert data["procesadas"] == 2
    assert len(data["errores"]) == 1
    assert data["errores"][0]["fila"] == 3
    assert "material" in data["errores"][0]["error"]

    # Verify the inserted data (GET /knowledge pagina de 10 en 10 por defecto:
    # se filtra por la categoría de prueba y se pide el máximo de 100).
    all_data = _listar_test(activos_only=True)
    materiales = sorted(item["metadatos"]["material"] for item in all_data)
    assert materiales == ["Cristal", "Madera Roble"]

    roble = next(item for item in all_data if item["metadatos"]["material"] == "Madera Roble")
    assert roble["documento"] == "Texto roble"
    assert roble["metadatos"]["precio_unitario"] == 150.0
    assert roble["metadatos"]["cliente"] == CLIENTE_TEST
    assert roble["metadatos"]["activo"] is True

    cristal = next(item for item in all_data if item["metadatos"]["material"] == "Cristal")
    assert cristal["documento"] == "Texto cristal"
    assert cristal["metadatos"]["precio_unitario"] == 80.5

    # La columna `id` del CSV se respeta; la fila inválida no se inserta
    inserted_ids = [item["id"] for item in all_data]
    assert "import_001" in inserted_ids
    assert "import_003" in inserted_ids
    assert "import_002" not in inserted_ids
    assert precios_collection.get(ids=["import_002"])["ids"] == []

def test_import_knowledge_invalid_file():
    # Text file instead of CSV
    files = {"file": ("test.txt", "some content", "text/plain")}
    response = client.post("/knowledge/import", files=files)
    assert response.status_code == 400
    assert "debe ser un CSV" in response.json()["detail"]

def test_import_knowledge_missing_columns():
    csv_content = """material,cliente,precio_unitario
Madera,cliente_test_crud,100.0"""
    files = {"file": ("test.csv", csv_content, "text/csv")}
    response = client.post("/knowledge/import", files=files)
    assert response.status_code == 400
    assert "Faltan columnas requeridas" in response.json()["detail"]
