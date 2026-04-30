import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone

from core.events import publish, start, stop, subscribe, unsubscribe
from db.models import PresupuestoModel
from db.persistence import async_session_maker, get_checkpointer
from fastapi import (APIRouter, BackgroundTasks, File, Form, HTTPException,
                     UploadFile, status)
from fastapi.responses import StreamingResponse
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/estimates", tags=["Estimates"])

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "application/pdf"}
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)


async def _db_set_error(estimate_id: str, error_msg: str) -> None:
    """Mark estimate as error in PostgreSQL. Called when process_estimate fails outside the workflow."""
    try:
        async with async_session_maker() as session:
            res = await session.execute(
                select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
            )
            rec = res.scalars().first()
            if rec and rec.status == "processing":
                rec.status = "error"
                rec.updated_at = datetime.now(timezone.utc)
                await session.commit()
    except Exception as e:
        logger.error(f"Error actualizando estado a 'error' en DB para {estimate_id}: {e}")


async def process_estimate(estimate_id: str, file_path: str, cliente_id: str, content_type: str):
    """Run the graph in background, streaming SSE events as each node completes."""
    logger.info(f"Iniciando procesamiento en background para estimate_id: {estimate_id}")
    try:
        async with get_checkpointer() as checkpointer:
            from graph.workflow import workflow
            graph_with_cp = workflow.compile(checkpointer=checkpointer)

            config = {"configurable": {"thread_id": estimate_id}}
            initial_state = {
                "archivo_path": file_path,
                "cliente_id": cliente_id,
                "status": "pending",
                "thread_id": estimate_id,
                "content_type": content_type,
            }

            async for chunk in graph_with_cp.astream(initial_state, config=config):
                node_name = list(chunk.keys())[0]
                node_update = chunk[node_name]

                event: dict = {
                    "type": "node_complete",
                    "node": node_name,
                    "status": node_update.get("status"),
                }
                if node_update.get("plano_analizado"):
                    event["plano_analizado"] = node_update["plano_analizado"]
                if node_update.get("presupuesto_calculado"):
                    event["presupuesto_calculado"] = node_update["presupuesto_calculado"]
                if node_update.get("presupuesto_consolidado"):
                    event["presupuesto_consolidado"] = node_update["presupuesto_consolidado"]
                if node_update.get("error"):
                    event["error"] = node_update["error"]

                publish(estimate_id, event)

                # Write totals + lineas back to PostgreSQL as soon as consolidation finishes
                if node_name == "consolidate" and node_update.get("presupuesto_consolidado"):
                    consolidado = node_update["presupuesto_consolidado"]
                    try:
                        async with async_session_maker() as session:
                            res = await session.execute(
                                select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
                            )
                            records = res.scalars().all()
                            for rec in records:
                                rec.lineas = consolidado.get("lineas", [])
                                rec.subtotal = consolidado.get("subtotal", 0.0)
                                rec.iva = consolidado.get("iva", 0.0)
                                rec.total = consolidado.get("total", 0.0)
                                rec.status = "pending_review"
                                rec.updated_at = datetime.now(timezone.utc)
                            if records:
                                await session.commit()
                    except Exception as db_err:
                        logger.error(f"Error updating DB totals for {estimate_id}: {db_err}")

            # Check if paused at human_approval interrupt
            state = await graph_with_cp.aget_state(config)
            if state.next and "human_approval" in state.next:
                publish(estimate_id, {"type": "workflow_paused", "status": "pending_review"})

    except Exception as e:
        logger.error(f"Error procesando estimate_id {estimate_id}: {e}", exc_info=True)
        publish(estimate_id, {"type": "error", "error": str(e)})
        # Ensure DB doesn't stay stuck at 'processing' forever when the workflow crashes
        # before LangGraph's handle_error node can update it.
        await _db_set_error(estimate_id, str(e))
    finally:
        stop(estimate_id)  # always publish "done" and remove from active set


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_estimate(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    cliente_id: str = Form(...)
):
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo no permitido: {file.content_type}. Solo se permite PNG, JPEG o PDF."
        )

    estimate_id = str(uuid.uuid4())
    extension = file.filename.split('.')[-1] if '.' in file.filename else ''
    filename = f"{estimate_id}.{extension}" if extension else estimate_id
    file_path = os.path.join(UPLOAD_DIR, filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Error guardando el archivo: {e}")
        raise HTTPException(status_code=500, detail="Error al guardar el archivo subido.")

    # Register in DB immediately so it appears on the dashboard straight away
    try:
        async with async_session_maker() as session:
            record = PresupuestoModel(
                id=estimate_id,
                cliente_id=cliente_id,
                plano_id=estimate_id,
                image_path=file_path,
                status="processing",
                lineas=[],
                lineas_pendientes=[],
            )
            session.add(record)
            await session.commit()
    except Exception as e:
        logger.error(f"Error registrando estimate en DB: {e}")

    # Mark as active BEFORE adding the background task so SSE subscribers
    # don't miss the window between task registration and task execution.
    start(estimate_id)
    background_tasks.add_task(process_estimate, estimate_id, file_path, cliente_id, file.content_type)

    return {"estimate_id": estimate_id, "status": "processing"}


@router.get("/{estimate_id}/stream")
async def stream_estimate_events(estimate_id: str):
    """
    SSE endpoint. Events:
      current_state   — snapshot on connect
      line_added      — one pricing line computed
      node_complete   — a workflow node finished
      workflow_paused — reached human_approval interrupt
      error           — workflow error
      done            — stream ends
    """
    async def event_generator():
        # 1. Always send a snapshot immediately so the UI has something to render
        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
                )
                record = result.scalars().first()
            if record:
                image_url = (
                    f"/uploads/{os.path.basename(record.image_path)}"
                    if record.image_path else None
                )
                yield f"data: {json.dumps({'type': 'current_state', 'status': record.status, 'total': record.total, 'lineas': record.lineas or [], 'image_url': image_url})}\n\n"
        except Exception as e:
            logger.error(f"SSE snapshot error for {estimate_id}: {e}")

        # 2. Subscribe to live events (returns None if already finished)
        queue = subscribe(estimate_id)
        if queue is None:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "done":
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe(estimate_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", status_code=status.HTTP_200_OK)
async def list_estimates():
    """Returns estimates from PostgreSQL ordered by creation date (newest first)."""
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PresupuestoModel).order_by(PresupuestoModel.created_at.desc()).limit(100)
            )
            records = result.scalars().all()

            estimates = []
            for r in records:
                image_url = (
                    f"/uploads/{os.path.basename(r.image_path)}"
                    if r.image_path else None
                )
                estimates.append({
                    "estimate_id": r.plano_id,
                    "status": r.status,
                    "cliente_id": r.cliente_id,
                    "total": r.total,
                    "image_url": image_url,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                })

        return {"estimates": estimates}

    except Exception as e:
        logger.error(f"Error listando estimates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno listando presupuestos: {str(e)}"
        )


@router.delete("/{estimate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_estimate(estimate_id: str):
    """Deletes an estimate from the database and removes its associated image."""
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
            )
            records = result.scalars().all()

            if not records:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Estimate {estimate_id} no encontrado."
                )

            for record in records:
                if record.image_path and os.path.exists(record.image_path):
                    try:
                        os.remove(record.image_path)
                    except Exception as e:
                        logger.warning(f"No se pudo eliminar la imagen {record.image_path}: {e}")
                await session.delete(record)

            await session.commit()
            return
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando estimate {estimate_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno eliminando el presupuesto: {str(e)}"
        )


@router.get("/{estimate_id}", status_code=status.HTTP_200_OK)
async def get_estimate_status(estimate_id: str):
    """
    Returns full estimate detail.
    Tries the LangGraph checkpoint first (richest state), falls back to PostgreSQL
    when the checkpoint is missing or unreadable (e.g. workflow errored before writing one).
    """

    # --- 1. Verify the estimate exists in DB (fast, avoids hitting checkpointer for unknown IDs) ---
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
            )
            db_record = result.scalars().first()
    except Exception as e:
        logger.error(f"Error consultando DB para {estimate_id}: {e}")
        raise HTTPException(status_code=500, detail="Error interno consultando el estado.")

    if not db_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Estimate {estimate_id} no encontrado."
        )

    # --- 2. Try the LangGraph checkpoint (has the richest state) ---
    try:
        async with get_checkpointer() as checkpointer:
            from graph.workflow import workflow
            graph_with_cp = workflow.compile(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": estimate_id}}
            state_snapshot = await graph_with_cp.aget_state(config)

        if state_snapshot and state_snapshot.values:
            state_values = state_snapshot.values
            next_nodes = state_snapshot.next

            current_status = state_values.get("status", "unknown")
            error = state_values.get("error")

            if next_nodes and "human_approval" in next_nodes:
                current_status = "human_approval_required"
            elif not next_nodes and current_status not in ["error", "rejected"]:
                current_status = "completed"

            response: dict = {
                "estimate_id": estimate_id,
                "status": current_status,
                "plano_id": state_values.get("plano_id"),
                "cliente_id": state_values.get("cliente_id"),
                "image_url": (
                    f"/uploads/{os.path.basename(state_values.get('archivo_path', ''))}"
                    if state_values.get("archivo_path") else None
                ),
                "plano_analizado": state_values.get("plano_analizado"),
                "presupuesto_calculado": state_values.get("presupuesto_calculado"),
                "presupuesto_consolidado": state_values.get("presupuesto_consolidado"),
                "motivo_rechazo": state_values.get("motivo_rechazo"),
            }
            if error:
                response["error"] = error
            return response

    except Exception as e:
        logger.warning(f"Checkpoint no disponible para {estimate_id}, usando DB. Error: {e}")

    # --- 3. DB fallback — checkpoint missing or unreadable ---
    image_url = (
        f"/uploads/{os.path.basename(db_record.image_path)}"
        if db_record.image_path else None
    )
    response = {
        "estimate_id": estimate_id,
        "status": db_record.status,
        "plano_id": db_record.plano_id,
        "cliente_id": db_record.cliente_id,
        "image_url": image_url,
    }
    if db_record.lineas:
        response["presupuesto_consolidado"] = {
            "lineas": db_record.lineas,
            "subtotal": db_record.subtotal or 0.0,
            "iva": db_record.iva or 0.0,
            "total": db_record.total or 0.0,
            "cliente_id": db_record.cliente_id,
            "plano_id": db_record.plano_id,
            "status": db_record.status,
        }
    return response
