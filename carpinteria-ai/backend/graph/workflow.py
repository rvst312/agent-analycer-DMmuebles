import asyncio
import base64
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TypedDict

from agents.consolidation_agent import execute_consolidation
from agents.pricing_agent import calculate_pricing
from agents.vision_agent import analyze_plan
from api.schemas.estimate import (PlanoAnalizado, Presupuesto,
                                  PresupuestoConsolidado)
from db.models import JobLogModel, PresupuestoModel
from db.persistence import async_session_maker
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from rag.vision_feedback import get_recent_corrections
from services.holded_service import crear_presupuesto
from services.notification_service import notify_n8n_error
from sqlalchemy import select

os.environ["LANGGRAPH_ALLOW_MODULES"] = "api.schemas.estimate"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GraphState(TypedDict):
    plano_id: Optional[str]
    archivo_path: Optional[str]                   # primer archivo (compatibilidad)
    archivos_paths: Optional[list]                # todos los archivos subidos
    archivos_content_types: Optional[list]        # content-type de cada archivo
    archivos_nombres: Optional[list]              # nombres originales (pista de proyecto)
    cliente_id: Optional[str]
    notas_contexto: Optional[str]                 # contexto del usuario para el análisis
    plano_analizado: Optional[Dict[str, Any]]
    presupuesto_consolidado: Optional[Dict[str, Any]]
    status: str
    error: Optional[str]
    thread_id: Optional[str]
    presupuesto_calculado: Optional[Dict[str, Any]]
    motivo_rechazo: Optional[str]
    content_type: Optional[str]


async def _update_db_status(estimate_id: str, status: str) -> None:
    if not estimate_id:
        return
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PresupuestoModel).where(PresupuestoModel.plano_id == estimate_id)
            )
            record = result.scalar_one_or_none()
            if record:
                record.status = status
                record.updated_at = datetime.now(timezone.utc)
                await session.commit()
    except Exception as e:
        logger.error(f"Error updating DB status for {estimate_id}: {e}")


def receive_input(state: GraphState):
    logger.info("Node: receive_input")
    return {"status": "received"}


_PREFIJO_REF_FAMILIA = {
    "puerta_paso_abatible": "PA", "puerta_paso_corredera": "PC",
    "cerramiento": "CE", "rodapie": "RD", "armario": "AR", "vestidor": "VE",
    "mueble_bano": "MB", "mueble_varios": "MV", "balda_pared": "BP", "otro": "OT",
}


def _asignar_refs_unicos(partidas: list) -> None:
    """
    Garantiza un ref único por partida ANTES de recortes y pricing. Si dos
    partidas de familias distintas comparten ref (p.ej. "SIN-REF"), la UI las
    agruparía y sumaría juntas (rodapié mezclado con puertas). Aquí se separan.
    """
    usados: set = set()
    for i, p in enumerate(partidas):
        base = (p.ref or "").strip()
        if not base or base.upper() in ("SIN-REF", "SINREF", "N/A"):
            base = f"{_PREFIJO_REF_FAMILIA.get(p.familia or 'otro', 'PT')}{i+1:02d}"
        ref = base
        n = 2
        while ref in usados:
            ref = f"{base}-{n}"
            n += 1
        usados.add(ref)
        p.ref = ref


async def _generar_recortes_partidas(plano_id: str, partidas: list, file_paths: list) -> None:
    """
    Recorta del plano la zona (pagina + bbox_pct) de cada partida y guarda un PNG
    por ref. El mapping ref→url se persiste en presupuestos.imagenes_grupo para
    que el frontend muestre el dibujo junto a su partida.
    """
    import storage as _storage
    from core.plan_images import crop_bbox_png, is_pdf, render_pdf_page

    async def _get_page_png(archivo_idx: int, pagina: int):
        """
        Página como PNG. Primero reutiliza el PNG que ya generó el visor
        ({plano_id}_{i}_p{n}.png); solo si no existe renderiza ESA página
        (nunca el PDF entero otra vez). Sin caché en memoria: una página cada vez.
        """
        if archivo_idx >= len(file_paths):
            return None
        path = file_paths[archivo_idx]
        if is_pdf(path):
            key_visor = f"{plano_id}_{archivo_idx}_p{pagina}.png"
            resultado = await _storage.fetch(key_visor)
            if resultado is not None:
                return resultado[0]
            return await asyncio.to_thread(render_pdf_page, path, pagina)
        # imagen suelta: una sola "página"
        with open(path, "rb") as f:
            return f.read()

    imagenes: dict = {}
    for p in partidas:
        ref = p.ref or "SIN-REF"
        if ref in imagenes or len(p.bbox_pct or []) != 4:
            continue
        pagina = p.pagina if p.pagina >= 1 else 1
        page_png = await _get_page_png(p.archivo_idx, pagina)
        if not page_png:
            continue
        crop = await asyncio.to_thread(crop_bbox_png, page_png, p.bbox_pct)
        if not crop:
            continue
        key = f"{plano_id}_crop_{ref.replace('/', '-')}.png"
        await _storage.save(crop, key, "image/png")
        imagenes[ref] = _storage.get_url(key)

    if not imagenes:
        return
    logger.info(f"vision_analysis: {len(imagenes)} recortes de partida generados")
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PresupuestoModel).where(PresupuestoModel.plano_id == plano_id)
            )
            record = result.scalar_one_or_none()
            if record:
                record.imagenes_grupo = imagenes
                await session.commit()
    except Exception as e:
        logger.error(f"vision_analysis: no se pudo guardar imagenes_grupo: {e}")


async def _cargar_paginas_para_vision(plano_id: str, archivo_idx: int, file_path: str) -> list:
    """
    Carga las páginas del visor (PNG ya ORIENTADAS) y las reduce para enviarlas
    a la visión como imágenes. Así la visión ve el plano derecho y sus bbox de
    recorte usan exactamente el mismo eje que el visor.
    """
    import storage as _storage
    from core.plan_images import MAX_PAGES, downscale_for_vision, is_pdf

    if not is_pdf(file_path):
        return []
    paginas: list = []
    n = 1
    while n <= MAX_PAGES:
        res = await _storage.fetch(f"{plano_id}_{archivo_idx}_p{n}.png")
        if res is None:
            break
        paginas.append(await asyncio.to_thread(downscale_for_vision, res[0]))
        n += 1
    return paginas


def _resolve_media_type(file_path: str, hint: Optional[str]) -> str:
    if hint and hint in {"image/jpeg", "image/png", "application/pdf"}:
        return hint
    fp = file_path.lower()
    if fp.endswith(".png"):  return "image/png"
    if fp.endswith(".pdf"):  return "application/pdf"
    return "image/jpeg"


async def vision_analysis(state: GraphState):
    logger.info("Node: vision_analysis")
    plano_id = state.get("thread_id") or state.get("cliente_id", "unknown")

    # Recopilar todos los archivos a analizar
    file_paths: list = state.get("archivos_paths") or []
    content_types: list = state.get("archivos_content_types") or []
    if not file_paths:
        single = state.get("archivo_path")
        if not single:
            return {"status": "error", "error": "No file_path provided", "plano_id": plano_id}
        file_paths = [single]
        content_types = [state.get("content_type", "image/jpeg")]

    cliente_id = state.get("cliente_id", "unknown")
    few_shot_examples = await get_recent_corrections(cliente_id, n=3)

    # Reglas aprendidas de correcciones anteriores → se inyectan en la visión
    from agents.lecciones import cargar_lecciones
    lecciones = await cargar_lecciones()
    if lecciones:
        logger.info(f"vision_analysis: {len(lecciones)} lecciones aprendidas inyectadas")
    if few_shot_examples:
        logger.info(f"vision_analysis: {len(few_shot_examples)} few-shot examples para cliente={cliente_id}")

    all_componentes: list = []
    all_armarios: list = []
    all_partidas: list = []
    proyecto = ""
    reasoning_parts: list = []
    confidence_sum = 0.0
    errors: list = []
    tipo_plano = "general"
    processed = 0

    for idx, file_path in enumerate(file_paths):
        media_type = _resolve_media_type(file_path, content_types[idx] if idx < len(content_types) else None)
        try:
            with open(file_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            errors.append(f"Archivo {idx+1}: {str(e)}")
            continue

        # El nombre original del archivo suele contener el proyecto (calle+número),
        # p.ej. "carpinteria goya - estudio.pdf" → se pasa como pista a la visión.
        nombres = state.get("archivos_nombres") or []
        nombre_orig = nombres[idx] if idx < len(nombres) else ""
        notas = state.get("notas_contexto") or ""
        if nombre_orig:
            notas = (notas + "\n" if notas else "") + \
                f"Nombre del archivo subido: «{nombre_orig}». Si el plano no rotula el " \
                "proyecto (calle y número), dedúcelo de este nombre de archivo."

        # Páginas del visor ya orientadas → la visión ve el plano derecho y los
        # recortes cuadran. Si aún no existen (render falló), cae al PDF crudo.
        page_imgs = await _cargar_paginas_para_vision(plano_id, idx, file_path)
        if page_imgs:
            logger.info(f"vision_analysis: archivo {idx+1} → visión con {len(page_imgs)} páginas orientadas")

        # Capa de texto del PDF (planos vectoriales): cotas, rótulos y mediciones
        # EXACTOS que la visión usa con prioridad sobre lo que lee en la imagen.
        from core.plan_images import extract_pdf_text_pages, is_pdf
        pdf_text: list = []
        if is_pdf(file_path):
            pdf_text = await asyncio.to_thread(extract_pdf_text_pages, file_path)
            logger.info(f"vision_analysis: archivo {idx+1} → capa de texto en "
                        f"{sum(1 for t in pdf_text if t)}/{len(pdf_text)} páginas")

        # analyze_plan es síncrono y hace varias llamadas bloqueantes a Claude
        # (decenas de segundos con PDFs). Lo ejecutamos en un hilo para no
        # bloquear el event loop de FastAPI (congelaría el resto de requests/SSE).
        result = await asyncio.to_thread(
            analyze_plan,
            image_base64=image_base64,
            media_type=media_type,
            plano_id=plano_id,
            few_shot_examples=few_shot_examples,
            file_index=idx + 1,
            file_total=len(file_paths),
            notes=notas or None,
            page_images=page_imgs or None,
            lecciones=lecciones or None,
            pdf_text_pages=pdf_text or None,
        )

        if result.error:
            logger.warning(f"vision_analysis: error en archivo {idx+1}: {result.error}")
            errors.append(f"Archivo {idx+1}: {result.error}")
            continue

        tipo_plano = result.tipo_plano

        if getattr(result, "partidas", None):
            logger.info(f"vision_analysis: archivo {idx+1}/{len(file_paths)} → {len(result.partidas)} partidas detectadas")
            for p in result.partidas:
                p.archivo_idx = idx  # de qué archivo subido viene (para el recorte)
            all_partidas.extend(result.partidas)
        if not proyecto and getattr(result, "proyecto", ""):
            proyecto = result.proyecto
        elif result.tipo_plano == "armario" and result.armarios:
            logger.info(f"vision_analysis: archivo {idx+1}/{len(file_paths)} → {len(result.armarios)} armarios detectados")
            all_armarios.extend(result.armarios)
        else:
            logger.info(f"vision_analysis: archivo {idx+1}/{len(file_paths)} → {len(result.componentes)} componentes detectados")
            all_componentes.extend(result.componentes)

        reasoning_parts.append(f"[Plano {idx+1}] {result.raw_reasoning}")
        confidence_sum += result.confidence_score
        processed += 1

    if not all_componentes and not all_armarios and not all_partidas:
        error_msg = "; ".join(errors) if errors else "No se detectaron partidas en ninguna imagen"
        return {"status": "error", "error": error_msg, "plano_id": plano_id}

    avg_confidence = confidence_sum / max(processed, 1)
    merged_reasoning = " | ".join(reasoning_parts)

    # Refs únicos por partida (evita que la UI mezcle familias en un grupo)
    if all_partidas:
        _asignar_refs_unicos(all_partidas)

    # Persistir en BD el proyecto (calle + número) y las PARTIDAS detectadas:
    # deben sobrevivir al checkpoint (el título del presupuesto y la función
    # de "corregir con IA" dependen de ellos).
    if proyecto or all_partidas:
        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(PresupuestoModel).where(PresupuestoModel.plano_id == plano_id)
                )
                record = result.scalar_one_or_none()
                if record:
                    if proyecto:
                        record.proyecto = proyecto
                    if all_partidas:
                        record.partidas = [p.model_dump() for p in all_partidas]
                    await session.commit()
        except Exception as e:
            logger.error(f"vision_analysis: no se pudo persistir proyecto/partidas: {e}")

    # Recortes del plano por partida (best-effort: nunca bloquea el análisis)
    if all_partidas:
        try:
            await _generar_recortes_partidas(plano_id, all_partidas, file_paths)
        except Exception as e:
            logger.error(f"vision_analysis: fallo generando recortes: {e}")

    import json as _json
    from api.schemas.estimate import PlanoAnalizado as _PA
    merged = _PA(
        plano_id=plano_id,
        tipo_plano="partidas" if all_partidas else tipo_plano,
        proyecto=proyecto,
        partidas=all_partidas,
        componentes=all_componentes,
        armarios=all_armarios if all_armarios else None,
        confidence_score=round(avg_confidence, 3),
        raw_reasoning=merged_reasoning,
    )
    return {
        "status": "vision_analyzed",
        "plano_analizado": _json.loads(merged.model_dump_json()),
        "plano_id": plano_id,
    }


def extract_entities(state: GraphState):
    logger.info("Node: extract_entities")
    return {"status": "entities_extracted"}


async def rag_pricing(state: GraphState):
    logger.info("Node: rag_pricing")
    vision_result = state.get("plano_analizado")

    if not vision_result:
        return {"status": "error", "error": "No plano_analizado found"}

    try:
        plano = PlanoAnalizado(**vision_result)
        cliente_id = state.get("cliente_id", "unknown")
        thread_id = state.get("thread_id")

        # El pricing bloquea CPU (embeddings de Chroma) → a un hilo. El callback
        # re-entra al event loop: publish() usa asyncio.Queue (no thread-safe).
        loop = asyncio.get_running_loop()

        def on_line_added(linea_dict: dict) -> None:
            if thread_id:
                from core.events import publish
                loop.call_soon_threadsafe(
                    publish, thread_id, {"type": "line_added", "linea": linea_dict}
                )

        presupuesto = await asyncio.to_thread(
            calculate_pricing, plano, cliente_id, on_line_added=on_line_added
        )

        return {
            "status": "priced",
            "presupuesto_calculado": presupuesto.model_dump()
        }
    except Exception as e:
        logger.error(f"Error in pricing: {str(e)}")
        return {"status": "error", "error": f"Failed in pricing: {str(e)}"}


async def consolidate(state: GraphState):
    logger.info("Node: consolidate")
    pricing_result = state.get("presupuesto_calculado")

    if not pricing_result:
        return {"status": "error", "error": "No presupuesto_calculado found"}

    try:
        presupuesto = Presupuesto(**pricing_result)
        cliente_id = state.get("cliente_id", "unknown")

        consolidado = await execute_consolidation(presupuesto, cliente_id)

        return {
            "status": "consolidated",
            "presupuesto_consolidado": consolidado.model_dump()
        }
    except Exception as e:
        logger.error(f"Error in consolidation: {str(e)}")
        return {"status": "error", "error": f"Failed in consolidation: {str(e)}"}


def human_approval(state: GraphState):
    logger.info("Node: human_approval (HITL)")

    thread_id = state.get("thread_id") or state.get("cliente_id")

    approval_response = interrupt({
        "message": "Waiting for human approval",
        "thread_id": thread_id,
        "presupuesto_consolidado": state.get("presupuesto_consolidado")
    })

    logger.info(f"Received human approval response: {approval_response}")

    if isinstance(approval_response, dict):
        action = approval_response.get("action")

        if action == "approve":
            updates = {"status": "approved"}
            ajustes = approval_response.get("ajustes")
            if ajustes and state.get("presupuesto_consolidado"):
                presupuesto_actualizado = state["presupuesto_consolidado"].copy()
                presupuesto_actualizado.update(ajustes)
                updates["presupuesto_consolidado"] = presupuesto_actualizado
            return updates
        elif action == "reject":
            motivo = approval_response.get("motivo", "No especificado")
            logger.info(f"Presupuesto rechazado. Motivo: {motivo}")
            return {"status": "rejected", "motivo_rechazo": motivo}

    return {"status": "rejected", "motivo_rechazo": "Sin acción definida"}


async def send_to_holded(state: GraphState):
    logger.info("Node: send_to_holded")

    consolidado_dict = state.get("presupuesto_consolidado")
    if not consolidado_dict:
        return {"status": "error", "error": "No hay presupuesto consolidado para enviar a Holded"}

    try:
        presupuesto = PresupuestoConsolidado(**consolidado_dict)
        cliente_id = state.get("cliente_id", "unknown")
        contact_id = cliente_id

        # crear_presupuesto usa requests (bloqueante, timeout 10s); a un hilo
        # para no bloquear el event loop.
        holded_id = await asyncio.to_thread(crear_presupuesto, contact_id, presupuesto)
        if not holded_id:
            return {"status": "error", "error": "Falló la creación del presupuesto en Holded"}

        plano_id = state.get("plano_id")
        if plano_id:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(PresupuestoModel).where(PresupuestoModel.plano_id == plano_id)
                )
                presupuesto_db = result.scalar_one_or_none()
                if presupuesto_db:
                    presupuesto_db.holded_estimate_id = holded_id
                    presupuesto_db.status = "approved"
                    # Sincronizar la BD con LO QUE SE ENVIÓ a Holded (el humano
                    # pudo ajustar líneas/totales en la aprobación).
                    presupuesto_db.lineas = [l.model_dump() for l in presupuesto.lineas]
                    presupuesto_db.subtotal = presupuesto.subtotal
                    presupuesto_db.iva = presupuesto.iva
                    presupuesto_db.total = presupuesto.total
                    presupuesto_db.titulos_grupo = presupuesto.titulos_grupo or {}
                    presupuesto_db.descripciones_grupo = presupuesto.descripciones_grupo or {}
                    presupuesto_db.updated_at = datetime.now(timezone.utc)
                    await session.commit()

        return {"status": "sent_to_holded"}
    except Exception as e:
        logger.error(f"Error enviando a Holded: {e}")
        return {"status": "error", "error": f"Error enviando a Holded: {str(e)}"}


# NOTA: se eliminó el nodo `learn_prices`. Aprendía automáticamente al aprobar,
# pero solo procesaba líneas NO pendientes (precio ya existente en la KB) y
# reescribía `linea.precio_unitario` —que en el camino genérico es €/pieza
# (area·precio_kb + mano de obra)— etiquetándolo como €/m². Eso inflaba el
# precio en cada ciclo (bucle de sobreprecio) y desalineaba línea↔componente por
# índice si el humano reordenaba. El aprendizaje real y correcto lo cubre el
# endpoint /estimates/{id}/learn-pricing (feedback humano → apply_price_feedback),
# que actualiza el precio del item existente en vez de crear entradas corruptas.


async def notify_team(state: GraphState):
    logger.info("Node: notify_team")
    if state.get("status") == "rejected":
        motivo = state.get("motivo_rechazo", "Sin motivo")
        logger.info(f"Notificando al equipo: Presupuesto rechazado. Motivo: {motivo}")
        plano_id = state.get("plano_id")
        await _update_db_status(plano_id, "rejected")
    else:
        logger.info("Notificando al equipo: Presupuesto aprobado y procesado exitosamente.")
    return {"status": "completed"}


async def handle_error(state: GraphState):
    error_msg = state.get('error', 'Unknown error')
    logger.error(f"Node: handle_error. Error: {error_msg}")

    # Use thread_id as fallback — plano_id may not be set yet on very early failures
    job_id = state.get("thread_id", "unknown")
    plano_id = state.get("plano_id") or job_id

    nodo = "unknown"
    if "pricing" in error_msg.lower():
        nodo = "rag_pricing"
    elif "consolidation" in error_msg.lower() or "consolidate" in error_msg.lower():
        nodo = "consolidate"
    elif "file_path" in error_msg.lower() or "image" in error_msg.lower() or "vision" in error_msg.lower():
        nodo = "vision_analysis"
    elif "plano_analizado" in error_msg.lower():
        nodo = "rag_pricing"

    try:
        async with async_session_maker() as session:
            job_log = JobLogModel(
                job_id=job_id,
                nodo=nodo,
                error_type="workflow_error",
                mensaje=error_msg
            )
            session.add(job_log)
            await session.commit()
    except Exception as e:
        logger.error(f"Error al guardar job_log en BD: {e}")

    await _update_db_status(plano_id, "error")
    await notify_n8n_error(plano_id=plano_id, nodo=nodo, mensaje=error_msg)

    return {"status": "error"}


# Construcción del grafo
workflow = StateGraph(GraphState)

workflow.add_node("receive_input", receive_input)
workflow.add_node("vision_analysis", vision_analysis)
workflow.add_node("extract_entities", extract_entities)
workflow.add_node("rag_pricing", rag_pricing)
workflow.add_node("consolidate", consolidate)
workflow.add_node("human_approval", human_approval)
workflow.add_node("send_to_holded", send_to_holded)
workflow.add_node("notify_team", notify_team)
workflow.add_node("handle_error", handle_error)

workflow.set_entry_point("receive_input")


def check_error(state: GraphState):
    if state.get("status") == "error":
        return "error"
    return "continue"


workflow.add_conditional_edges(
    "receive_input",
    check_error,
    {"error": "handle_error", "continue": "vision_analysis"}
)
workflow.add_conditional_edges(
    "vision_analysis",
    check_error,
    {"error": "handle_error", "continue": "extract_entities"}
)
workflow.add_conditional_edges(
    "extract_entities",
    check_error,
    {"error": "handle_error", "continue": "rag_pricing"}
)
workflow.add_conditional_edges(
    "rag_pricing",
    check_error,
    {"error": "handle_error", "continue": "consolidate"}
)
workflow.add_conditional_edges(
    "consolidate",
    check_error,
    {"error": "handle_error", "continue": "human_approval"}
)


def check_approval(state: GraphState):
    if state.get("status") == "error":
        return "error"
    elif state.get("status") == "rejected":
        return "rejected"
    return "approved"


workflow.add_conditional_edges(
    "human_approval",
    check_approval,
    {"error": "handle_error", "rejected": "notify_team", "approved": "send_to_holded"}
)
workflow.add_conditional_edges(
    "send_to_holded",
    check_error,
    {"error": "handle_error", "continue": "notify_team"}
)
workflow.add_conditional_edges(
    "notify_team",
    check_error,
    {"error": "handle_error", "continue": END}
)
workflow.add_edge("handle_error", END)
