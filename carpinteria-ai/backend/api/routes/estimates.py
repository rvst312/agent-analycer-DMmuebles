import asyncio
import glob
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import storage
from core.events import publish, start, stop, subscribe, unsubscribe
from db.models import PresupuestoModel
from db.persistence import async_session_maker, get_checkpointer
from fastapi import (APIRouter, BackgroundTasks, File, Form, HTTPException,
                     UploadFile, status)
from typing import List
from fastapi.responses import StreamingResponse
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/estimates", tags=["Estimates"])

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "application/pdf"}


def _all_image_urls(
    estimate_id: str,
    archivos_paths: list | None = None,
    archivos_keys: list | None = None,
) -> list[str]:
    """Return public URLs for all files belonging to this estimate."""
    # Priority 1: R2/S3 keys stored in DB (most reliable)
    if archivos_keys:
        return [storage.get_url(k) for k in archivos_keys]
    # Priority 2: LangGraph state paths (convert basename → URL)
    if archivos_paths:
        return [storage.get_url(os.path.basename(p)) for p in archivos_paths]
    # Fallback: scan local UPLOAD_DIR (only works in local/dev mode)
    if not storage.is_cloud():
        def _sort_key(p: str) -> int:
            stem = os.path.splitext(os.path.basename(p))[0]
            idx = stem.rsplit("_", 1)[-1]
            return int(idx) if idx.isdigit() else 999
        files = sorted(glob.glob(os.path.join(storage.UPLOAD_DIR, f"{estimate_id}_*")), key=_sort_key)
        return [storage.get_url(os.path.basename(f)) for f in files]
    return []


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


async def process_estimate(estimate_id: str, file_paths: List[str], cliente_id: str, content_types: List[str]):
    """Run the graph in background, streaming SSE events as each node completes."""
    logger.info(f"Iniciando procesamiento en background para estimate_id: {estimate_id}")
    try:
        async with get_checkpointer() as checkpointer:
            from graph.workflow import workflow
            graph_with_cp = workflow.compile(checkpointer=checkpointer)

            config = {"configurable": {"thread_id": estimate_id}}
            initial_state = {
                "archivo_path": file_paths[0],
                "archivos_paths": file_paths,
                "archivos_content_types": content_types,
                "cliente_id": cliente_id,
                "notas_contexto": notas_contexto or None,
                "status": "pending",
                "thread_id": estimate_id,
                "content_type": content_types[0],
            }

            async for chunk in graph_with_cp.astream(initial_state, config=config):
                node_name = list(chunk.keys())[0]
                node_update = chunk[node_name]

                # LangGraph emits {"__interrupt__": (Interrupt(...),)} as a tuple when
                # interrupt() fires — skip it here; the pause is handled below via aget_state.
                if node_name == "__interrupt__" or not isinstance(node_update, dict):
                    continue

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
    files: List[UploadFile] = File(...),
    cliente_id: str = Form(...),
    notas_contexto: str = Form(""),
):
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Se requiere al menos un archivo.")

    for f in files:
        if f.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipo no permitido: {f.content_type}. Solo PNG, JPEG o PDF."
            )

    estimate_id = str(uuid.uuid4())
    file_paths: List[str] = []   # local paths — for the vision agent
    filenames: List[str] = []    # basenames — stored as R2 keys in DB
    content_types: List[str] = []

    try:
        for i, f in enumerate(files):
            extension = f.filename.split('.')[-1] if f.filename and '.' in f.filename else ''
            filename = f"{estimate_id}_{i}.{extension}" if extension else f"{estimate_id}_{i}"
            ct = f.content_type or "image/jpeg"
            file_bytes = await f.read()
            await storage.save(file_bytes, filename, ct)
            file_paths.append(storage.local_path(filename))
            filenames.append(filename)
            content_types.append(ct)
    except Exception as e:
        logger.error(f"Error guardando archivos: {e}")
        raise HTTPException(status_code=500, detail="Error al guardar los archivos subidos.")

    # Register in DB — image_path stores the first filename (key), archivos_keys stores all
    try:
        async with async_session_maker() as session:
            record = PresupuestoModel(
                id=estimate_id,
                cliente_id=cliente_id,
                plano_id=estimate_id,
                image_path=filenames[0],
                archivos_keys=filenames,
                status="processing",
                lineas=[],
                lineas_pendientes=[],
            )
            session.add(record)
            await session.commit()
    except Exception as e:
        logger.error(f"Error registrando estimate en DB: {e}")

    start(estimate_id)
    background_tasks.add_task(process_estimate, estimate_id, file_paths, cliente_id, content_types)

    return {"estimate_id": estimate_id, "status": "processing", "num_files": len(file_paths)}


@router.patch("/{estimate_id}/lineas", status_code=status.HTTP_200_OK)
async def update_estimate_lineas(estimate_id: str, body: dict):
    """Persist manually-edited budget lines back to PostgreSQL."""
    lineas = body.get("lineas")
    if lineas is None:
        raise HTTPException(status_code=400, detail="lineas is required")

    subtotal = float(body.get("subtotal", 0))
    iva = float(body.get("iva", 0))
    total = float(body.get("total", 0))

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
            )
            record = result.scalars().first()
            if not record:
                raise HTTPException(status_code=404, detail=f"Estimate {estimate_id} not found")
            record.lineas = lineas
            record.subtotal = subtotal
            record.iva = iva
            record.total = total
            record.updated_at = datetime.now(timezone.utc)
            await session.commit()
        return {"saved": True, "count": len(lineas)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating lineas for {estimate_id}: {e}")
        raise HTTPException(status_code=500, detail="Error saving lineas")


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
                image_url = storage.get_url(os.path.basename(record.image_path)) if record.image_path else None
                image_urls = _all_image_urls(estimate_id, archivos_keys=record.archivos_keys)
                yield f"data: {json.dumps({'type': 'current_state', 'status': record.status, 'total': record.total, 'lineas': record.lineas or [], 'image_url': image_url, 'image_urls': image_urls})}\n\n"
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
                image_url = storage.get_url(os.path.basename(r.image_path)) if r.image_path else None
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
                keys = record.archivos_keys or (
                    [os.path.basename(record.image_path)] if record.image_path else []
                )
                for key in keys:
                    await storage.delete(key)
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


@router.post("/{estimate_id}/learn-components", status_code=status.HTTP_200_OK)
async def save_component_corrections(estimate_id: str, body: dict):
    """Store corrected component data as training feedback for the vision agent."""
    from db.models import ComponentFeedbackModel

    componentes_originales = body.get("componentes_originales", [])
    componentes_corregidos = body.get("componentes_corregidos", [])

    if not componentes_corregidos:
        raise HTTPException(status_code=400, detail="componentes_corregidos is required")

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
            )
            record = result.scalars().first()
            if not record:
                raise HTTPException(status_code=404, detail=f"Estimate {estimate_id} not found")

            feedback = ComponentFeedbackModel(
                plano_id=estimate_id,
                cliente_id=record.cliente_id,
                componentes_originales=componentes_originales,
                componentes_corregidos=componentes_corregidos,
            )
            session.add(feedback)
            await session.commit()

        logger.info(f"Component corrections saved for {estimate_id}: {len(componentes_corregidos)} components")
        return {"saved": True, "count": len(componentes_corregidos)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving component corrections for {estimate_id}: {e}")
        raise HTTPException(status_code=500, detail="Error saving component corrections")


@router.post("/{estimate_id}/learn-pricing", status_code=status.HTTP_200_OK)
async def save_pricing_corrections(estimate_id: str, body: dict):
    """
    Store price corrections as training feedback and update ChromaDB so future RAG
    queries return improved pricing for the same materials.
    """
    from db.models import PriceFeedbackModel
    from rag.embeddings import apply_price_feedback

    correcciones = body.get("correcciones", [])
    if not correcciones:
        raise HTTPException(status_code=400, detail="correcciones is required")

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
            )
            record = result.scalars().first()
            if not record:
                raise HTTPException(status_code=404, detail=f"Estimate {estimate_id} not found")

            cliente_id = record.cliente_id

            # Try to update ChromaDB for each correction
            enriched = []
            for c in correcciones:
                descripcion = c.get("descripcion", "")
                precio_corregido = float(c.get("precio_corregido", 0))
                updated = False
                if descripcion and precio_corregido > 0:
                    updated = apply_price_feedback(cliente_id, descripcion, precio_corregido)
                enriched.append({**c, "chroma_updated": updated})

            feedback = PriceFeedbackModel(
                plano_id=estimate_id,
                cliente_id=cliente_id,
                correcciones=enriched,
            )
            session.add(feedback)
            await session.commit()

        updated_count = sum(1 for c in enriched if c.get("chroma_updated"))
        logger.info(
            f"Price feedback saved for {estimate_id}: {len(enriched)} corrections, "
            f"{updated_count} ChromaDB entries updated"
        )
        return {"saved": True, "total": len(enriched), "chroma_updated": updated_count}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving price feedback for {estimate_id}: {e}")
        raise HTTPException(status_code=500, detail="Error saving price feedback")


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

            archivos_paths = state_values.get("archivos_paths") or (
                [state_values["archivo_path"]] if state_values.get("archivo_path") else []
            )
            response: dict = {
                "estimate_id": estimate_id,
                "status": current_status,
                "plano_id": state_values.get("plano_id"),
                "cliente_id": state_values.get("cliente_id"),
                "image_url": (
                    storage.get_url(os.path.basename(archivos_paths[0]))
                    if archivos_paths else None
                ),
                "image_urls": _all_image_urls(
                    estimate_id,
                    archivos_paths=archivos_paths,
                    archivos_keys=db_record.archivos_keys,
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
    image_url = storage.get_url(os.path.basename(db_record.image_path)) if db_record.image_path else None
    response = {
        "estimate_id": estimate_id,
        "status": db_record.status,
        "plano_id": db_record.plano_id,
        "cliente_id": db_record.cliente_id,
        "image_url": image_url,
        "image_urls": _all_image_urls(estimate_id, archivos_keys=db_record.archivos_keys),
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
