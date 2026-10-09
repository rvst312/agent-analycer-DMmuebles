import asyncio
import glob
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import storage
from api.auth import verify_jefe_obra_token_flexible
from core.events import publish, start, stop, subscribe, unsubscribe
from db.models import PresupuestoModel
from db.persistence import async_session_maker, get_checkpointer
from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                     HTTPException, UploadFile, status)
from typing import List
from fastapi.responses import StreamingResponse
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Todo el router requiere un JWT válido (rol jefe_obra o admin). Se usa la
# variante flexible para que el endpoint SSE /stream pueda autenticarse por
# query param (?token=), ya que EventSource no admite cabeceras personalizadas.
router = APIRouter(
    prefix="/estimates",
    tags=["Estimates"],
    dependencies=[Depends(verify_jefe_obra_token_flexible)],
)

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "application/pdf"}
# Modelo para las llamadas de texto cortas (descripción de grupo, título).
TEXT_MODEL = os.getenv("TEXT_MODEL", "claude-haiku-5-5")
MAX_FILE_MB = 25          # tamaño máximo por archivo subido
MAX_FILES_PER_UPLOAD = 10  # nº máximo de planos por presupuesto


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


async def _render_pdf_pages_for_viewer(estimate_id: str, file_paths: List[str], content_types: List[str]) -> List[str]:
    """
    Convierte las páginas de los PDFs a PNG y las guarda como archivos de
    visualización (archivos_keys). El visor muestra imágenes (zoom/lupa) en vez
    del <iframe> de PDF, que se veía como una caja negra.
    """
    from core.plan_images import is_pdf, render_pdf_to_pngs

    display_keys: List[str] = []
    for i, path in enumerate(file_paths):
        ct = content_types[i] if i < len(content_types) else None
        if not is_pdf(path, ct):
            display_keys.append(os.path.basename(path))
            continue
        try:
            pages = await asyncio.to_thread(render_pdf_to_pngs, path)
            for n, png in enumerate(pages, start=1):
                key = f"{estimate_id}_{i}_p{n}.png"
                await storage.save(png, key, "image/png")
                display_keys.append(key)
            logger.info(f"Viewer: {len(pages)} páginas PNG renderizadas para archivo {i} de {estimate_id}")
        except Exception as e:
            logger.error(f"Viewer: fallo renderizando PDF {path}: {e} — se mantiene el PDF")
            display_keys.append(os.path.basename(path))

    try:
        async with async_session_maker() as session:
            res = await session.execute(
                select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
            )
            rec = res.scalars().first()
            if rec:
                rec.archivos_keys = display_keys
                await session.commit()
    except Exception as e:
        logger.error(f"Viewer: no se pudieron guardar archivos_keys de {estimate_id}: {e}")
    return display_keys


async def process_estimate(estimate_id: str, file_paths: List[str], cliente_id: str, content_types: List[str], notas_contexto: str = "", archivos_nombres: List[str] | None = None):
    """Run the graph in background, streaming SSE events as each node completes."""
    logger.info(f"Iniciando procesamiento en background para estimate_id: {estimate_id}")
    try:
        # Páginas del PDF → PNG para el visor. Dentro del try: si algo escapa,
        # el finally hace stop() y el estado no queda colgado en 'processing'.
        try:
            display_keys = await _render_pdf_pages_for_viewer(estimate_id, file_paths, content_types)
            # Avisar al visor de que ya hay imágenes (el snapshot SSE inicial
            # pudo entregar las keys del PDF, previas al render).
            publish(estimate_id, {
                "type": "viewer_ready",
                "image_urls": [storage.get_url(k) for k in display_keys],
            })
        except Exception as e:
            logger.error(f"Viewer: render de páginas falló para {estimate_id}: {e} — continúa el análisis")
        async with get_checkpointer() as checkpointer:
            from graph.workflow import workflow
            graph_with_cp = workflow.compile(checkpointer=checkpointer)

            config = {"configurable": {"thread_id": estimate_id}}
            initial_state = {
                "archivo_path": file_paths[0],
                "archivos_paths": file_paths,
                "archivos_content_types": content_types,
                "archivos_nombres": archivos_nombres or [],
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
    nombre_cliente: str = Form(""),
    notas_contexto: str = Form(""),
):
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Se requiere al menos un archivo.")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Máximo {MAX_FILES_PER_UPLOAD} archivos por presupuesto."
        )

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
    nombres_originales: List[str] = []  # nombres tal como los subió el usuario

    try:
        for i, f in enumerate(files):
            extension = f.filename.split('.')[-1] if f.filename and '.' in f.filename else ''
            filename = f"{estimate_id}_{i}.{extension}" if extension else f"{estimate_id}_{i}"
            ct = f.content_type or "image/jpeg"
            file_bytes = await f.read()
            if len(file_bytes) > MAX_FILE_MB * 1024 * 1024:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El archivo «{f.filename}» supera el máximo de {MAX_FILE_MB} MB."
                )
            await storage.save(file_bytes, filename, ct)
            file_paths.append(storage.local_path(filename))
            filenames.append(filename)
            content_types.append(ct)
            nombres_originales.append(f.filename or "")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error guardando archivos: {e}")
        raise HTTPException(status_code=500, detail="Error al guardar los archivos subidos.")

    # Register in DB — image_path stores the first filename (key), archivos_keys stores all
    try:
        async with async_session_maker() as session:
            record = PresupuestoModel(
                id=estimate_id,
                cliente_id=cliente_id,
                nombre_cliente=nombre_cliente or None,
                plano_id=estimate_id,
                image_path=filenames[0],
                archivos_keys=filenames,
                archivos_origen=filenames,  # keys originales (para re-análisis)
                status="processing",
                lineas=[],
                lineas_pendientes=[],
            )
            session.add(record)
            await session.commit()
    except Exception as e:
        logger.error(f"Error registrando estimate en DB: {e}")

    invalidar_cache_listado()
    start(estimate_id)
    background_tasks.add_task(process_estimate, estimate_id, file_paths, cliente_id, content_types, notas_contexto, nombres_originales)

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


# Micro-caché del listado: las notificaciones de CADA usuario lo consultan cada
# 10s. 5s de TTL absorbe el polling de toda la oficina sin afectar a la frescura.
_list_cache: dict = {"data": None, "ts": 0.0}
_LIST_TTL = 5.0


def invalidar_cache_listado() -> None:
    _list_cache["data"] = None


@router.get("", status_code=status.HTTP_200_OK)
async def list_estimates():
    """Returns estimates from PostgreSQL ordered by creation date (newest first)."""
    import time as _time
    if _list_cache["data"] is not None and _time.monotonic() - _list_cache["ts"] < _LIST_TTL:
        return _list_cache["data"]
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
                    "nombre_cliente": r.nombre_cliente,
                    "total": r.total,
                    "image_url": image_url,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                })

        respuesta = {"estimates": estimates}
        _list_cache["data"] = respuesta
        _list_cache["ts"] = _time.monotonic()
        return respuesta

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
                await session.delete(record)
            await session.commit()

        invalidar_cache_listado()
        # Borrar TODOS los archivos del estimate por prefijo: PDF original,
        # páginas del visor ({id}_{i}_p{n}.png) y recortes ({id}_crop_*.png).
        # Evita huérfanos en disco/R2 (los nombres siempre empiezan por el id).
        try:
            n = await storage.delete_prefix(f"{estimate_id}_")
            logger.info(f"delete_estimate {estimate_id}: {n} archivos eliminados")
        except Exception as e:
            logger.warning(f"delete_estimate {estimate_id}: limpieza de archivos incompleta: {e}")
        return
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando estimate {estimate_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno eliminando el presupuesto: {str(e)}"
        )


async def _reanalizar_plano(estimate_id: str, record, instruccion: str):
    """Re-analiza los archivos ORIGINALES del plano con la corrección como contexto."""
    import base64
    import glob
    import re as _re

    from agents.vision_agent import analyze_plan

    keys = record.archivos_origen or []
    if not keys:
        # Estimates antiguos sin archivos_origen: buscar originales en disco
        patron = _re.compile(rf"^{_re.escape(estimate_id)}_\d+\.(pdf|png|jpe?g)$", _re.I)
        keys = sorted(
            os.path.basename(p)
            for p in glob.glob(os.path.join(storage.UPLOAD_DIR, f"{estimate_id}_*"))
            if patron.match(os.path.basename(p))
        )
    if not keys:
        raise HTTPException(status_code=409, detail="No se encuentran los archivos originales del plano.")

    file_paths: List[str] = []
    for k in keys:
        lp = storage.local_path(k)
        if not os.path.exists(lp):
            res = await storage.fetch(k)  # R2 fallback
            if res is None:
                raise HTTPException(status_code=409, detail=f"No se encuentra el archivo original {k}.")
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            with open(lp, "wb") as f:
                f.write(res[0])
        file_paths.append(lp)

    notas = (
        f"CORRECCIÓN DEL PRESUPUESTADOR (ha visto el plano, es FIABLE — priorízala "
        f"sobre tu propia interpretación): {instruccion}"
    ) if instruccion else None

    from agents.lecciones import cargar_lecciones
    from core.plan_images import extract_pdf_text_pages, is_pdf
    from graph.workflow import _cargar_paginas_para_vision

    lecciones = await cargar_lecciones()
    todas: list = []
    proyecto = ""
    for idx, path in enumerate(file_paths):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        pl = path.lower()
        mt = "application/pdf" if pl.endswith(".pdf") else ("image/png" if pl.endswith(".png") else "image/jpeg")
        page_imgs = await _cargar_paginas_para_vision(estimate_id, idx, path)
        # Capa de texto del PDF: cotas/rótulos/mediciones exactos para la visión.
        pdf_text: List[str] = []
        if is_pdf(path):
            pdf_text = await asyncio.to_thread(extract_pdf_text_pages, path)
            logger.info(f"corregir/reanalizar {estimate_id}: archivo {idx+1} → "
                        f"{sum(1 for t in pdf_text if t)}/{len(pdf_text)} páginas con texto")
        result = await asyncio.to_thread(
            analyze_plan, image_base64=b64, media_type=mt, plano_id=estimate_id,
            notes=notas, file_index=idx + 1, file_total=len(file_paths),
            page_images=page_imgs or None,
            lecciones=lecciones or None,
            pdf_text_pages=pdf_text or None,
        )
        if result.error:
            logger.warning(f"corregir/reanalizar {estimate_id}: error archivo {idx+1}: {result.error}")
            continue
        for p in (result.partidas or []):
            p.archivo_idx = idx
        todas.extend(result.partidas or [])
        if not proyecto and getattr(result, "proyecto", ""):
            proyecto = result.proyecto
    return todas, proyecto, file_paths


@router.post("/{estimate_id}/corregir", status_code=status.HTTP_200_OK)
async def corregir_estimate(estimate_id: str, body: dict):
    """
    Corrección con IA del presupuesto ya generado:
    - {instruccion}                → edita TODAS las partidas (sin re-mirar el plano) y recalcula.
    - {instruccion, ref}           → solo esa partida (el resto no se toca).
    - {instruccion?, reanalizar}   → vuelve a analizar el plano con la corrección como contexto.
    """
    from agents.corrector import corregir_partidas_con_ia
    from agents.pricing_agent import _price_partidas
    from api.schemas.estimate import Partida
    from graph.workflow import _asignar_refs_unicos, _generar_recortes_partidas

    instruccion = (body.get("instruccion") or "").strip()
    ref = (body.get("ref") or "").strip() or None
    reanalizar = bool(body.get("reanalizar"))
    if not instruccion and not reanalizar:
        raise HTTPException(status_code=400, detail="Escribe la corrección a aplicar.")

    async with async_session_maker() as session:
        result = await session.execute(
            select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
        )
        record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Estimate {estimate_id} no encontrado.")

    partidas = [Partida(**p) for p in (record.partidas or [])]
    cliente_id = record.cliente_id or "general"
    refs_previos = {p.ref for p in partidas}

    proyecto_nuevo = ""
    file_paths = None
    if reanalizar:
        nuevas, proyecto_nuevo, file_paths = await _reanalizar_plano(estimate_id, record, instruccion)
        if not nuevas:
            raise HTTPException(status_code=502, detail="El re-análisis no detectó partidas. Inténtalo de nuevo.")
    else:
        if not partidas:
            raise HTTPException(
                status_code=409,
                detail="Este presupuesto no tiene las partidas guardadas (es anterior a esta función). Usa «Volver a analizar el plano».",
            )
        objetivo = [p for p in partidas if p.ref == ref] if ref else partidas
        if ref and not objetivo:
            raise HTTPException(status_code=404, detail=f"No existe la partida {ref}.")
        try:
            corregidas = await asyncio.to_thread(corregir_partidas_con_ia, objetivo, instruccion)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            logger.error(f"corregir {estimate_id}: {e}")
            raise HTTPException(status_code=502, detail="La corrección con IA falló. Inténtalo de nuevo.")
        if ref:
            # Sustituir SOLO la partida objetivo por su versión corregida
            # (la IA puede haberla dividido en varias).
            nuevas = []
            for p in partidas:
                if p.ref == ref:
                    nuevas.extend(corregidas)
                else:
                    nuevas.append(p)
        else:
            nuevas = corregidas

    _asignar_refs_unicos(nuevas)

    # Recalcular con la calculadora (determinista). En un hilo: los rodapiés
    # consultan Chroma (embeddings, CPU) y bloquearían el event loop.
    lineas_n, _tot, titulos, descripciones, faltantes = await asyncio.to_thread(
        _price_partidas, nuevas, cliente_id
    )

    if ref and not reanalizar:
        # Corrección por partida: solo se reemplazan las líneas de los refs
        # afectados; el resto (incl. ediciones manuales en otros grupos) se conserva.
        afectados = {ref} | ({p.ref for p in nuevas} - refs_previos)
        lineas_ref = [l.model_dump() for l in lineas_n if (l.ref or "") in afectados]
        antiguas = record.lineas or []
        idx_insert = next((i for i, l in enumerate(antiguas) if (l.get("ref") or "") in afectados), len(antiguas))
        finales = [l for l in antiguas if (l.get("ref") or "") not in afectados]
        finales[idx_insert:idx_insert] = lineas_ref
    else:
        afectados = {p.ref for p in nuevas}
        lineas_ref = None
        finales = [l.model_dump() for l in lineas_n]

    subtotal = round(sum(l["subtotal"] for l in finales if not l.get("precio_pendiente")), 2)
    iva = round(subtotal * 0.21, 2)
    total = round(subtotal + iva, 2)

    # Persistir todo
    async with async_session_maker() as session:
        result = await session.execute(
            select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
        )
        rec = result.scalars().first()
        if rec:
            rec.partidas = [p.model_dump() for p in nuevas]
            rec.lineas = finales
            rec.subtotal, rec.iva, rec.total = subtotal, iva, total
            rec.titulos_grupo = titulos or {}
            rec.descripciones_grupo = descripciones or {}
            rec.familias_faltantes = sorted(faltantes) if faltantes else []
            if proyecto_nuevo:
                rec.proyecto = proyecto_nuevo
            rec.correcciones = (rec.correcciones or []) + [{
                "fecha": datetime.now(timezone.utc).isoformat(),
                "instruccion": instruccion, "ref": ref, "reanalizar": reanalizar,
            }]
            rec.updated_at = datetime.now(timezone.utc)
            await session.commit()

    # APRENDIZAJE CONTINUO: destilar la corrección en una regla general para
    # que los próximos análisis lean mejor. Best-effort, nunca bloquea.
    if instruccion:
        try:
            from agents.corrector import corregir_partidas_con_ia  # noqa: F401 (ya importado)
            from agents.lecciones import destilar_leccion, guardar_leccion
            leccion = await asyncio.to_thread(
                destilar_leccion, instruccion,
                [p.model_dump() for p in partidas],
                [p.model_dump() for p in nuevas],
            )
            if leccion:
                await guardar_leccion(leccion, plano_id=estimate_id, cliente_id=cliente_id)
        except Exception as e:
            logger.warning(f"corregir {estimate_id}: no se pudo aprender de la corrección: {e}")

    # Recortes nuevos si se re-analizó (persiste imagenes_grupo en BD)
    if reanalizar and file_paths:
        try:
            await _generar_recortes_partidas(estimate_id, nuevas, file_paths)
        except Exception as e:
            logger.error(f"corregir/reanalizar {estimate_id}: recortes fallaron: {e}")

    async with async_session_maker() as session:
        result = await session.execute(
            select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
        )
        rec = result.scalars().first()
        imagenes = (rec.imagenes_grupo if rec else None) or {}

    return {
        "lineas": finales,
        "lineas_afectadas": lineas_ref,
        "refs_afectados": sorted(afectados),
        "subtotal": subtotal, "iva": iva, "total": total,
        "titulos_grupo": titulos or {},
        "descripciones_grupo": descripciones or {},
        "familias_faltantes": sorted(faltantes) if faltantes else [],
        "imagenes_grupo": imagenes,
        "proyecto": proyecto_nuevo or record.proyecto or "",
    }


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


@router.post("/{estimate_id}/generate-description", status_code=status.HTTP_200_OK)
async def generate_group_description(estimate_id: str, body: dict):
    """
    Use Claude to generate a single 3-line commercial description for a
    budget group (one Holded item per ref, e.g. "A03", "E02"...).
    Body: { "ref": "A03", "lineas": [...LineaPresupuesto] }
    """
    import anthropic as _anthropic

    ref = body.get("ref", "")
    lineas = body.get("lineas", [])

    if not lineas:
        raise HTTPException(status_code=400, detail="lineas is required")

    lineas_text = "\n".join(
        f"- {l.get('descripcion', '')} | cant: {l.get('cantidad', 1)} | precio_unitario: {l.get('precio_unitario', 0)} €"
        for l in lineas
    )

    prompt = f"""Eres un redactor técnico para una empresa de carpintería y mobiliario a medida.
Genera una descripción profesional para el grupo de presupuesto "{ref}" con las siguientes piezas:

{lineas_text}

La descripción debe tener EXACTAMENTE 3 líneas, en este formato:
1. Primera línea: "Suministro e instalación de [descripción breve del mueble, incluyendo tipo y elementos principales: puertas, cajones, bandejas, etc.]." (ej: "Suministro e instalación de armario con 3 puertas abatibles, 2 cajones interiores y 3 bandejas extraíbles.")
2. Segunda línea: "Medidas aprox: [ancho]x[alto]" (ej: "Medidas aprox: 150x250")
3. Tercera línea: "Material y terminación: [material y acabado exterior], [material y acabado interior]" (ej: "Material y terminación: Exterior laca blanca, interior melamina textil")

Sé conciso y técnico. No repitas información. Usa el español de España. No incluyas precios. No incluyas herrajes ni observaciones de montaje.
Devuelve SOLO el texto de la descripción (máximo 3 líneas), sin cabeceras ni explicaciones."""

    try:
        client = _anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        message = client.messages.create(
            model=TEXT_MODEL,
            max_tokens=1024,  # sitio para el razonamiento adaptativo + 3 líneas
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
        )
        # Leer por tipo: la respuesta puede empezar con bloques "thinking".
        description = "".join(b.text for b in message.content if b.type == "text").strip()
        return {"description": description}
    except Exception as e:
        logger.error(f"Error generating description for {estimate_id}/{ref}: {e}")
        raise HTTPException(status_code=500, detail="Error generando descripción con IA")


@router.post("/{estimate_id}/generate-title", status_code=status.HTTP_200_OK)
async def generate_estimate_title(estimate_id: str, body: dict):
    """
    Use Claude to generate a single short project title (4-5 words) for the
    whole estimate. Sent to Holded as one header item at 0 € (editable).
    Body: { "lineas": [...LineaPresupuesto] }
    """
    import anthropic as _anthropic

    lineas = body.get("lineas", [])
    if not lineas:
        raise HTTPException(status_code=400, detail="lineas is required")

    lineas_text = "\n".join(f"- {l.get('descripcion', '')}" for l in lineas)

    prompt = f"""Eres un redactor técnico para una empresa de carpintería y mobiliario a medida.
Genera un título corto (4-5 palabras) que resuma el proyecto completo de presupuesto, a partir de estas piezas:

{lineas_text}

Ej: "Armarios y puertas de paso", "Cocina y vestidor a medida".
No incluyas precios ni códigos de referencia. Usa el español de España.
Devuelve SOLO el título, sin comillas ni explicaciones."""

    try:
        client = _anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        message = client.messages.create(
            model=TEXT_MODEL,
            max_tokens=1024,  # sitio para el razonamiento adaptativo + el título
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
        )
        titulo = "".join(b.text for b in message.content if b.type == "text").strip()
        return {"titulo": titulo}
    except Exception as e:
        logger.error(f"Error generating title for {estimate_id}: {e}")
        raise HTTPException(status_code=500, detail="Error generando título con IA")


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
                "nombre_cliente": db_record.nombre_cliente,
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
                "imagenes_grupo": db_record.imagenes_grupo or {},
                "proyecto": (state_values.get("plano_analizado") or {}).get("proyecto") or db_record.proyecto or "",
            }
            # La BD es la fuente de verdad de líneas/totales: las correcciones
            # con IA y los guardados manuales escriben ahí (el checkpoint de
            # LangGraph se queda congelado en la pausa de aprobación).
            if db_record.lineas:
                base_cons = response.get("presupuesto_consolidado") or {}
                response["presupuesto_consolidado"] = {
                    **base_cons,
                    "lineas": db_record.lineas,
                    "subtotal": db_record.subtotal or 0.0,
                    "iva": db_record.iva or 0.0,
                    "total": db_record.total or 0.0,
                    "titulos_grupo": db_record.titulos_grupo or base_cons.get("titulos_grupo") or {},
                    "descripciones_grupo": db_record.descripciones_grupo or base_cons.get("descripciones_grupo") or {},
                    "familias_faltantes": db_record.familias_faltantes or base_cons.get("familias_faltantes") or [],
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
        "nombre_cliente": db_record.nombre_cliente,
        "image_url": image_url,
        "image_urls": _all_image_urls(estimate_id, archivos_keys=db_record.archivos_keys),
        "imagenes_grupo": db_record.imagenes_grupo or {},
        "proyecto": db_record.proyecto or "",
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
            "titulos_grupo": db_record.titulos_grupo or {},
            "descripciones_grupo": db_record.descripciones_grupo or {},
            "familias_faltantes": db_record.familias_faltantes or [],
        }
    return response
