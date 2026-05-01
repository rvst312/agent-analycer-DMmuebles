import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from db.models import PresupuestoModel, ProyectoModel
from db.persistence import async_session_maker, get_checkpointer
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "application/pdf"}
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _nombre_modulo(filename: str, index: int) -> str:
    stem = Path(filename).stem.strip()
    return stem if stem else f"Módulo {index + 1}"


async def _process_estimate_for_project(
    estimate_id: str,
    file_path: str,
    cliente_id: str,
    content_type: str,
    proyecto_id: str,
    nombre_modulo: str,
):
    from core.events import publish, start, stop
    logger.info(f"Project {proyecto_id}: processing module '{nombre_modulo}' ({estimate_id})")
    start(estimate_id)
    try:
        async with get_checkpointer() as checkpointer:
            from graph.workflow import workflow
            graph = workflow.compile(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": estimate_id}}
            initial_state = {
                "archivo_path": file_path,
                "cliente_id": cliente_id,
                "status": "pending",
                "thread_id": estimate_id,
                "content_type": content_type,
                "proyecto_id": proyecto_id,
                "nombre_modulo": nombre_modulo,
            }

            async for chunk in graph.astream(initial_state, config=config):
                node_name = list(chunk.keys())[0]
                node_update = chunk[node_name]
                event: dict = {
                    "type": "node_complete",
                    "node": node_name,
                    "status": node_update.get("status"),
                }
                if node_update.get("presupuesto_consolidado"):
                    event["presupuesto_consolidado"] = node_update["presupuesto_consolidado"]
                if node_update.get("error"):
                    event["error"] = node_update["error"]
                publish(estimate_id, event)

            state = await graph.aget_state(config)
            if state.next and "human_approval" in state.next:
                publish(estimate_id, {"type": "workflow_paused", "status": "pending_review"})

    except Exception as e:
        logger.error(f"Error processing module {estimate_id} for project {proyecto_id}: {e}", exc_info=True)
        publish(estimate_id, {"type": "error", "error": str(e)})
        try:
            async with async_session_maker() as session:
                res = await session.execute(
                    select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
                )
                rec = res.scalars().first()
                if rec:
                    rec.status = "error"
                    rec.updated_at = datetime.now(timezone.utc)
                    await session.commit()
        except Exception:
            pass
    finally:
        stop(estimate_id)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_project(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    cliente_id: str = Form(...),
):
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    for f in files:
        if f.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo no permitido: {f.content_type}. Solo PNG, JPEG o PDF.",
            )

    proyecto_id = str(uuid.uuid4())
    estimate_ids: List[str] = []

    for idx, f in enumerate(files):
        estimate_id = str(uuid.uuid4())
        ext = f.filename.rsplit(".", 1)[-1] if "." in f.filename else ""
        fname = f"{estimate_id}.{ext}" if ext else estimate_id
        file_path = os.path.join(UPLOAD_DIR, fname)
        try:
            with open(file_path, "wb") as buf:
                shutil.copyfileobj(f.file, buf)
        except Exception as e:
            logger.error(f"Error saving file for project {proyecto_id}: {e}")
            raise HTTPException(status_code=500, detail="Error al guardar archivo.")

        nombre = _nombre_modulo(f.filename, idx)

        async with async_session_maker() as session:
            record = PresupuestoModel(
                id=estimate_id,
                cliente_id=cliente_id,
                plano_id=estimate_id,
                image_path=file_path,
                status="processing",
                lineas=[],
                lineas_pendientes=[],
                proyecto_id=proyecto_id,
                nombre_modulo=nombre,
            )
            session.add(record)
            await session.commit()

        estimate_ids.append(estimate_id)
        background_tasks.add_task(
            _process_estimate_for_project,
            estimate_id, file_path, cliente_id, f.content_type, proyecto_id, nombre,
        )

    async with async_session_maker() as session:
        proyecto = ProyectoModel(
            id=proyecto_id,
            cliente_id=cliente_id,
            status="processing",
            estimate_ids=estimate_ids,
        )
        session.add(proyecto)
        await session.commit()

    return {"proyecto_id": proyecto_id, "estimate_ids": estimate_ids, "status": "processing"}


@router.get("/{proyecto_id}", status_code=status.HTTP_200_OK)
async def get_project(proyecto_id: str):
    async with async_session_maker() as session:
        res = await session.execute(
            select(ProyectoModel).where(ProyectoModel.id == proyecto_id)
        )
        proyecto = res.scalars().first()

    if not proyecto:
        raise HTTPException(status_code=404, detail=f"Proyecto {proyecto_id} no encontrado.")

    async with async_session_maker() as session:
        res = await session.execute(
            select(PresupuestoModel).where(PresupuestoModel.proyecto_id == proyecto_id)
        )
        modulos = res.scalars().all()

    modulos_data = []
    for m in modulos:
        modulos_data.append({
            "estimate_id": m.plano_id,
            "nombre_modulo": m.nombre_modulo,
            "status": m.status,
            "subtotal": m.subtotal,
            "iva": m.iva,
            "total": m.total,
            "lineas": m.lineas or [],
            "lineas_pendientes": m.lineas_pendientes or [],
            "resumen": m.resumen,
            "image_url": (
                f"/uploads/{os.path.basename(m.image_path)}"
                if m.image_path else None
            ),
        })

    statuses = {m["status"] for m in modulos_data}
    if all(s == "approved" for s in statuses):
        proyecto_status = "approved"
    elif any(s == "rejected" for s in statuses):
        proyecto_status = "rejected"
    elif any(s == "error" for s in statuses):
        proyecto_status = "error"
    elif all(s == "pending_review" for s in statuses):
        proyecto_status = "pending_review"
    else:
        proyecto_status = "processing"

    return {
        "proyecto_id": proyecto_id,
        "cliente_id": proyecto.cliente_id,
        "status": proyecto_status,
        "holded_estimate_id": proyecto.holded_estimate_id,
        "modulos": modulos_data,
        "total": sum(m["total"] for m in modulos_data),
    }


@router.post("/{proyecto_id}/approve", status_code=status.HTTP_200_OK)
async def approve_project(proyecto_id: str, body: dict = {}):
    """Build one Holded line per module (from resumen) and send a single estimate."""
    import time
    from services.holded_service import crear_presupuesto

    async with async_session_maker() as session:
        res = await session.execute(
            select(ProyectoModel).where(ProyectoModel.id == proyecto_id)
        )
        proyecto = res.scalars().first()

    if not proyecto:
        raise HTTPException(status_code=404, detail=f"Proyecto {proyecto_id} no encontrado.")

    async with async_session_maker() as session:
        res = await session.execute(
            select(PresupuestoModel).where(PresupuestoModel.proyecto_id == proyecto_id)
        )
        modulos = res.scalars().all()

    if not modulos:
        raise HTTPException(status_code=400, detail="El proyecto no tiene módulos.")

    # Build one Holded item per module using resumen if available
    items = []
    for m in modulos:
        nombre = m.nombre_modulo or m.plano_id
        resumen = m.resumen or {}
        descripcion = resumen.get("descripcion", nombre)
        subtotal = resumen.get("subtotal", m.subtotal or 0.0)
        items.append({
            "name": f"{nombre}: {descripcion}",
            "units": 1,
            "subtotal": round(subtotal, 2),
            "tax": 21,
        })

    # Send to Holded using a synthetic object
    class _FakePresupuesto:
        def __init__(self, lineas):
            self.lineas = lineas

    class _FakeLinea:
        def __init__(self, item):
            self.descripcion = item["name"]
            self.cantidad = item["units"]
            self.subtotal = item["subtotal"]

    fake = _FakePresupuesto([_FakeLinea(it) for it in items])
    holded_id = crear_presupuesto(proyecto.cliente_id, fake)

    if not holded_id:
        raise HTTPException(status_code=502, detail="Fallo al crear presupuesto en Holded.")

    now = datetime.now(timezone.utc)
    async with async_session_maker() as session:
        for m in modulos:
            m.status = "approved"
            m.updated_at = now
            session.add(m)

        res2 = await session.execute(
            select(ProyectoModel).where(ProyectoModel.id == proyecto_id)
        )
        proy = res2.scalars().first()
        if proy:
            proy.holded_estimate_id = holded_id
            proy.status = "approved"
            proy.updated_at = now

        await session.commit()

    return {"holded_estimate_id": holded_id, "status": "approved"}


@router.post("/{proyecto_id}/reject", status_code=status.HTTP_200_OK)
async def reject_project(proyecto_id: str, body: dict = {}):
    async with async_session_maker() as session:
        res = await session.execute(
            select(PresupuestoModel).where(PresupuestoModel.proyecto_id == proyecto_id)
        )
        modulos = res.scalars().all()

        now = datetime.now(timezone.utc)
        for m in modulos:
            m.status = "rejected"
            m.updated_at = now
            session.add(m)

        res2 = await session.execute(
            select(ProyectoModel).where(ProyectoModel.id == proyecto_id)
        )
        proy = res2.scalars().first()
        if proy:
            proy.status = "rejected"
            proy.updated_at = now

        await session.commit()

    return {"status": "rejected"}
