import base64
import hashlib
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
from rag.embeddings import upsert_precio
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
    cliente_id: Optional[str]
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
    if few_shot_examples:
        logger.info(f"vision_analysis: {len(few_shot_examples)} few-shot examples para cliente={cliente_id}")

    all_componentes: list = []
    reasoning_parts: list = []
    confidence_sum = 0.0
    errors: list = []

    for idx, file_path in enumerate(file_paths):
        media_type = _resolve_media_type(file_path, content_types[idx] if idx < len(content_types) else None)
        try:
            with open(file_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            errors.append(f"Archivo {idx+1}: {str(e)}")
            continue

        result = analyze_plan(
            image_base64=image_base64,
            media_type=media_type,
            plano_id=plano_id,
            few_shot_examples=few_shot_examples,
            file_index=idx + 1,
            file_total=len(file_paths),
        )

        if result.error:
            logger.warning(f"vision_analysis: error en archivo {idx+1}: {result.error}")
            errors.append(f"Archivo {idx+1}: {result.error}")
            continue

        logger.info(f"vision_analysis: archivo {idx+1}/{len(file_paths)} → {len(result.componentes)} componentes detectados")
        all_componentes.extend(result.componentes)
        reasoning_parts.append(f"[Plano {idx+1}] {result.raw_reasoning}")
        confidence_sum += result.confidence_score

    if not all_componentes:
        error_msg = "; ".join(errors) if errors else "No se detectaron componentes en ninguna imagen"
        return {"status": "error", "error": error_msg, "plano_id": plano_id}

    avg_confidence = confidence_sum / len(file_paths)
    merged_reasoning = " | ".join(reasoning_parts)

    import json as _json
    from api.schemas.estimate import PlanoAnalizado as _PA
    merged = _PA(
        plano_id=plano_id,
        componentes=all_componentes,
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

        def on_line_added(linea_dict: dict) -> None:
            if thread_id:
                from core.events import publish
                publish(thread_id, {"type": "line_added", "linea": linea_dict})

        presupuesto = calculate_pricing(plano, cliente_id, on_line_added=on_line_added)

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

        holded_id = crear_presupuesto(contact_id, presupuesto)
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
                    presupuesto_db.updated_at = datetime.now(timezone.utc)
                    await session.commit()

        return {"status": "sent_to_holded"}
    except Exception as e:
        logger.error(f"Error enviando a Holded: {e}")
        return {"status": "error", "error": f"Error enviando a Holded: {str(e)}"}


async def learn_prices(state: GraphState):
    """Upsert confirmed line prices back into ChromaDB so future estimates improve."""
    logger.info("Node: learn_prices")

    consolidado_dict = state.get("presupuesto_consolidado")
    plano_dict = state.get("plano_analizado")

    if not consolidado_dict or not plano_dict:
        logger.warning("learn_prices: missing state, skipping learning")
        return {}

    try:
        consolidado = PresupuestoConsolidado(**consolidado_dict)
        plano = PlanoAnalizado(**plano_dict)
    except Exception as e:
        logger.error(f"learn_prices: failed to parse state: {e}")
        return {}

    learned = 0
    for idx, linea in enumerate(consolidado.lineas):
        if linea.precio_pendiente or linea.precio_unitario <= 0:
            continue

        if idx >= len(plano.componentes):
            continue

        comp = plano.componentes[idx]
        material = comp.material.strip()
        acabado = comp.acabado.strip()
        tipo = comp.tipo.value

        query_text = f"{material} {acabado} {tipo}"
        doc_id = "learned_" + hashlib.md5(query_text.lower().encode()).hexdigest()[:16]

        metadatos = {
            "material": material,
            "acabado": acabado,
            "tipo": tipo,
            "cliente": "general",
            "precio_unitario": linea.precio_unitario,
            "unidad": "m2",
            "version": "learned",
            "categoria": tipo,
            "source": "human_approved",
            "activo": True,
        }

        try:
            upsert_precio(doc_id, query_text, metadatos)
            learned += 1
            logger.info(f"learn_prices: '{query_text}' → {linea.precio_unitario:.2f} €/m2")
        except Exception as e:
            logger.error(f"learn_prices: failed to upsert '{query_text}': {e}")

    logger.info(f"learn_prices: {learned}/{len(consolidado.lineas)} prices learned")
    return {}


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
workflow.add_node("learn_prices", learn_prices)
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
    {"error": "handle_error", "continue": "learn_prices"}
)
# learn_prices is best-effort: failures are logged but never block the workflow
workflow.add_edge("learn_prices", "notify_team")
workflow.add_conditional_edges(
    "notify_team",
    check_error,
    {"error": "handle_error", "continue": END}
)
workflow.add_edge("handle_error", END)
