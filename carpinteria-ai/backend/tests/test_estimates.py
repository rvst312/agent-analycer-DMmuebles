import pytest
from fastapi.testclient import TestClient
import io

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
