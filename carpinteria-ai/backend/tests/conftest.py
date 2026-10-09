"""
Configuración común de pytest.

`storage.UPLOAD_DIR` vale por defecto `/app/uploads` (ruta del contenedor) y
`main.py` hace `os.makedirs` al importarse → fuera de Docker la colección de
los tests que importan `main` falla con "Read-only file system: '/app'".
Este conftest se carga ANTES que cualquier módulo de test, así que basta con
apuntar UPLOAD_DIR a un directorio temporal (si no viene ya definido).
"""
import atexit
import os
import shutil
import tempfile

if "UPLOAD_DIR" not in os.environ:
    _upload_dir = tempfile.mkdtemp(prefix="carpinteria-test-uploads-")
    os.environ["UPLOAD_DIR"] = _upload_dir
    atexit.register(shutil.rmtree, _upload_dir, ignore_errors=True)
