import io
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
import storage
from api.auth import verify_jefe_obra_token_flexible
from api.routes.estimates import invalidar_cache_listado
from db.models import PresupuestoModel

client = TestClient(app)


@pytest.fixture(autouse=True)
def jefe_obra_autenticado():
    """
    El router /estimates exige un JWT (jefe_obra o admin). Se sustituye la
    dependencia por una que devuelve un usuario de prueba y se retira al
    acabar cada test para no filtrar el override a otros módulos de test.
    Además se vacía el micro-caché del listado (TTL 5 s) entre tests.
    """
    app.dependency_overrides[verify_jefe_obra_token_flexible] = (
        lambda: {"role": "jefe_obra", "sub": "test"}
    )
    invalidar_cache_listado()
    yield
    app.dependency_overrides.pop(verify_jefe_obra_token_flexible, None)
    invalidar_cache_listado()


# ── Helpers de mocking (BD, checkpointer, almacenamiento) ─────────────────────

class _SessionCtx:
    """Sustituto de `async with async_session_maker() as session`."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _make_session(record=None, records=None):
    """Sesión SQLAlchemy falsa: execute() -> scalars().first()/all()."""
    result = MagicMock()
    result.scalars.return_value.first.return_value = record
    result.scalars.return_value.all.return_value = records or []
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _patch_session(session):
    return patch(
        "api.routes.estimates.async_session_maker",
        side_effect=lambda: _SessionCtx(session),
    )


def _db_record(**overrides):
    """Fila de PresupuestoModel mínima (sin líneas guardadas por defecto)."""
    base = dict(
        plano_id="123", cliente_id="c1", nombre_cliente="Cliente Uno",
        image_path="123_0.png", archivos_keys=["123_0.png"], status="processing",
        lineas=[], subtotal=0.0, iva=0.0, total=0.0,
        titulos_grupo={}, descripciones_grupo={}, imagenes_grupo={},
        familias_faltantes=[], proyecto="Goya 23",
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc), updated_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class MockStateSnapshot:
    def __init__(self, values, next_nodes=()):
        self.values = values
        self.next = next_nodes


class MockCheckpointerContext:
    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@contextmanager
def _estado_mockeado(record, snapshot=None, aget_state_error=None):
    """
    Parchea lo que usa GET /estimates/{id}: la BD (existencia del estimate),
    el checkpointer y `workflow.compile(...).aget_state`.
    """
    session = _make_session(record=record)
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=snapshot, side_effect=aget_state_error)
    with _patch_session(session), \
            patch("api.routes.estimates.get_checkpointer", side_effect=MockCheckpointerContext) as cp, \
            patch("graph.workflow.workflow.compile", return_value=graph) as compile_:
        yield SimpleNamespace(session=session, graph=graph, checkpointer=cp, compile=compile_)


@pytest.fixture
def upload_env():
    """Entorno para POST /estimates sin ejecutar el pipeline real ni tocar BD/disco."""
    session = _make_session()
    with patch("api.routes.estimates.process_estimate", new_callable=AsyncMock) as process, \
            patch("api.routes.estimates.storage.save", new_callable=AsyncMock) as save, \
            patch("api.routes.estimates.start") as start, \
            _patch_session(session):
        yield SimpleNamespace(process=process, save=save, start=start, session=session)


# ── Autenticación ─────────────────────────────────────────────────────────────

def test_estimates_requires_authentication():
    # Sin el override, el router rechaza peticiones sin JWT.
    app.dependency_overrides.pop(verify_jefe_obra_token_flexible, None)

    response = client.get("/estimates")

    assert response.status_code == 401
    assert response.json()["detail"] == "No autenticado"


# ── POST /estimates ───────────────────────────────────────────────────────────

def test_create_estimate_valid_image(upload_env):
    response = client.post(
        "/estimates",
        data={
            "cliente_id": "cliente_123",
            "nombre_cliente": "Cliente 123",
            "notas_contexto": "Armario lacado blanco",
        },
        files=[("files", ("plano.png", io.BytesIO(b"fake image data"), "image/png"))],
    )

    assert response.status_code == 202
    data = response.json()
    estimate_id = data["estimate_id"]
    uuid.UUID(estimate_id)  # es un UUID válido
    assert data["status"] == "processing"
    assert data["num_files"] == 1

    # El archivo se guarda con clave "<estimate_id>_<n>.<ext>" y su content-type
    upload_env.save.assert_awaited_once_with(
        b"fake image data", f"{estimate_id}_0.png", "image/png"
    )

    # Se registra en BD como "processing" con los datos del formulario
    record = upload_env.session.add.call_args.args[0]
    assert isinstance(record, PresupuestoModel)
    assert record.plano_id == estimate_id
    assert record.cliente_id == "cliente_123"
    assert record.nombre_cliente == "Cliente 123"
    assert record.status == "processing"
    assert record.image_path == f"{estimate_id}_0.png"
    assert record.archivos_keys == [f"{estimate_id}_0.png"]
    upload_env.session.commit.assert_awaited_once()

    # Se abre el canal SSE y se lanza el pipeline en background con los datos subidos
    upload_env.start.assert_called_once_with(estimate_id)
    upload_env.process.assert_awaited_once_with(
        estimate_id,
        [storage.local_path(f"{estimate_id}_0.png")],
        "cliente_123",
        ["image/png"],
        "Armario lacado blanco",
        ["plano.png"],
    )


def test_create_estimate_valid_pdf(upload_env):
    response = client.post(
        "/estimates",
        data={"cliente_id": "cliente_456"},
        files=[("files", ("documento.pdf", io.BytesIO(b"fake pdf data"), "application/pdf"))],
    )

    assert response.status_code == 202
    data = response.json()
    estimate_id = data["estimate_id"]
    assert data["status"] == "processing"
    assert data["num_files"] == 1

    upload_env.save.assert_awaited_once_with(
        b"fake pdf data", f"{estimate_id}_0.pdf", "application/pdf"
    )
    record = upload_env.session.add.call_args.args[0]
    assert record.cliente_id == "cliente_456"
    assert record.nombre_cliente is None  # sin nombre_cliente en el formulario
    assert record.archivos_keys == [f"{estimate_id}_0.pdf"]
    upload_env.process.assert_awaited_once_with(
        estimate_id,
        [storage.local_path(f"{estimate_id}_0.pdf")],
        "cliente_456",
        ["application/pdf"],
        "",
        ["documento.pdf"],
    )


def test_create_estimate_multiple_files(upload_env):
    response = client.post(
        "/estimates",
        data={"cliente_id": "cliente_789"},
        files=[
            ("files", ("planta.png", io.BytesIO(b"png bytes"), "image/png")),
            ("files", ("detalle.pdf", io.BytesIO(b"pdf bytes"), "application/pdf")),
        ],
    )

    assert response.status_code == 202
    data = response.json()
    estimate_id = data["estimate_id"]
    assert data["num_files"] == 2

    assert upload_env.save.await_count == 2
    upload_env.save.assert_any_await(b"png bytes", f"{estimate_id}_0.png", "image/png")
    upload_env.save.assert_any_await(b"pdf bytes", f"{estimate_id}_1.pdf", "application/pdf")

    record = upload_env.session.add.call_args.args[0]
    assert record.archivos_keys == [f"{estimate_id}_0.png", f"{estimate_id}_1.pdf"]
    # image_path guarda la clave del primer archivo
    assert record.image_path == f"{estimate_id}_0.png"
    upload_env.process.assert_awaited_once_with(
        estimate_id,
        [storage.local_path(f"{estimate_id}_0.png"), storage.local_path(f"{estimate_id}_1.pdf")],
        "cliente_789",
        ["image/png", "application/pdf"],
        "",
        ["planta.png", "detalle.pdf"],
    )


def test_create_estimate_invalid_mime_type(upload_env):
    response = client.post(
        "/estimates",
        data={"cliente_id": "cliente_789"},
        files=[("files", ("documento.txt", io.BytesIO(b"fake text data"), "text/plain"))],
    )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Tipo no permitido" in data["detail"]
    assert "text/plain" in data["detail"]

    # Nada se guarda, se registra ni se procesa
    upload_env.save.assert_not_awaited()
    upload_env.session.add.assert_not_called()
    upload_env.process.assert_not_awaited()


def test_create_estimate_too_many_files(upload_env):
    files = [("files", (f"p{i}.png", io.BytesIO(b"x"), "image/png")) for i in range(11)]

    response = client.post("/estimates", data={"cliente_id": "cliente_789"}, files=files)

    assert response.status_code == 400
    assert "Máximo 10" in response.json()["detail"]
    upload_env.save.assert_not_awaited()
    upload_env.process.assert_not_awaited()


def test_create_estimate_requires_files_field(upload_env):
    # El campo antiguo `file` ya no es válido: el endpoint espera `files`.
    response = client.post(
        "/estimates",
        data={"cliente_id": "cliente_123"},
        files={"file": ("plano.png", io.BytesIO(b"fake image data"), "image/png")},
    )

    assert response.status_code == 422
    upload_env.save.assert_not_awaited()
    upload_env.process.assert_not_awaited()


# ── GET /estimates/{id} ───────────────────────────────────────────────────────

def test_get_estimate_status_not_found():
    with _estado_mockeado(record=None) as env:
        response = client.get("/estimates/no-existe")

    assert response.status_code == 404
    assert "no encontrado" in response.json()["detail"]
    # Un id desconocido no llega a consultar el checkpointer
    env.checkpointer.assert_not_called()


def test_get_estimate_status_processing():
    snapshot = MockStateSnapshot(
        values={"status": "processing", "cliente_id": "c1"},
        next_nodes=("some_node",),
    )
    with _estado_mockeado(_db_record(), snapshot):
        response = client.get("/estimates/123")

    assert response.status_code == 200
    data = response.json()
    assert data["estimate_id"] == "123"
    assert data["status"] == "processing"
    assert data["cliente_id"] == "c1"
    assert data["nombre_cliente"] == "Cliente Uno"
    assert data["image_urls"] == [storage.get_url("123_0.png")]


def test_get_estimate_status_human_approval():
    snapshot = MockStateSnapshot(
        values={"status": "consolidated", "plano_id": "p1"},
        next_nodes=("human_approval",),
    )
    with _estado_mockeado(_db_record(), snapshot):
        response = client.get("/estimates/123")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "human_approval_required"
    assert data["plano_id"] == "p1"


def test_get_estimate_status_completed():
    snapshot = MockStateSnapshot(values={"status": "sent_to_holded"}, next_nodes=())
    with _estado_mockeado(_db_record(), snapshot):
        response = client.get("/estimates/123")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"


def test_get_estimate_status_error():
    snapshot = MockStateSnapshot(
        values={"status": "error", "error": "Fallo el OCR"},
        next_nodes=(),
    )
    with _estado_mockeado(_db_record(), snapshot):
        response = client.get("/estimates/123")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert data["error"] == "Fallo el OCR"


def test_get_estimate_status_db_lines_override_checkpoint():
    # La BD es la fuente de verdad de líneas/totales (correcciones y ediciones
    # manuales escriben ahí; el checkpoint se queda congelado).
    lineas = [{"descripcion": "Armario A01", "importe": 100.0}]
    snapshot = MockStateSnapshot(
        values={
            "status": "consolidated",
            "presupuesto_consolidado": {"lineas": [], "total": 0.0},
        },
        next_nodes=("human_approval",),
    )
    record = _db_record(lineas=lineas, subtotal=100.0, iva=21.0, total=121.0)
    with _estado_mockeado(record, snapshot):
        response = client.get("/estimates/123")

    assert response.status_code == 200
    consolidado = response.json()["presupuesto_consolidado"]
    assert consolidado["lineas"] == lineas
    assert consolidado["subtotal"] == 100.0
    assert consolidado["iva"] == 21.0
    assert consolidado["total"] == 121.0


@pytest.mark.parametrize(
    "snapshot, aget_state_error",
    [
        pytest.param(None, None, id="checkpoint-inexistente"),
        pytest.param(None, RuntimeError("checkpoint ilegible"), id="checkpoint-ilegible"),
    ],
)
def test_get_estimate_status_falls_back_to_db(snapshot, aget_state_error):
    lineas = [{"descripcion": "Armario A01", "importe": 100.0}]
    record = _db_record(
        status="pending_review", lineas=lineas, subtotal=100.0, iva=21.0, total=121.0,
    )
    with _estado_mockeado(record, snapshot, aget_state_error):
        response = client.get("/estimates/123")

    assert response.status_code == 200
    data = response.json()
    assert data["estimate_id"] == "123"
    assert data["status"] == "pending_review"
    assert data["cliente_id"] == "c1"
    assert data["presupuesto_consolidado"]["lineas"] == lineas
    assert data["presupuesto_consolidado"]["total"] == 121.0


# ── GET /estimates (listado) ──────────────────────────────────────────────────

def test_list_estimates():
    t1 = _db_record(plano_id="t1", cliente_id="c1", nombre_cliente="Cliente Uno",
                    status="processing", image_path="t1_0.png", total=0.0)
    t2 = _db_record(plano_id="t2", cliente_id="c2", nombre_cliente="Cliente Dos",
                    status="pending_review", image_path="t2_0.png", total=1210.0)
    session = _make_session(records=[t1, t2])

    with _patch_session(session):
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
    assert e1["nombre_cliente"] == "Cliente Uno"
    assert e1["image_url"] == storage.get_url("t1_0.png")
    assert e1["created_at"] == "2026-04-19T00:00:00+00:00"
    assert e1["updated_at"] is None

    # Validar el segundo estimate (el estado sale de la BD, no del checkpoint)
    e2 = next(e for e in estimates if e["estimate_id"] == "t2")
    assert e2["status"] == "pending_review"
    assert e2["cliente_id"] == "c2"
    assert e2["total"] == 1210.0


def test_list_estimates_is_cached_between_polls():
    session = _make_session(records=[_db_record(plano_id="t1", image_path="t1_0.png")])

    with _patch_session(session):
        first = client.get("/estimates")
        second = client.get("/estimates")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    # El segundo poll se sirve del micro-caché: una sola consulta a la BD
    assert session.execute.await_count == 1


def test_list_estimates_db_error_returns_500():
    session = _make_session()
    session.execute = AsyncMock(side_effect=RuntimeError("db caída"))

    with _patch_session(session):
        response = client.get("/estimates")

    assert response.status_code == 500
    assert "Error interno listando presupuestos" in response.json()["detail"]
