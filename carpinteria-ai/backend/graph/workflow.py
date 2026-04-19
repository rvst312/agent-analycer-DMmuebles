import base64
import logging
from typing import Any, Dict, Optional, TypedDict

from agents.consolidation_agent import execute_consolidation
from agents.pricing_agent import calculate_pricing
from agents.vision_agent import analyze_plan
from api.schemas.estimate import (PlanoAnalizado, Presupuesto,
                                  PresupuestoConsolidado)
from db.models import JobLogModel, PresupuestoModel
from db.persistence import get_session
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from services.holded_service import crear_presupuesto
from services.notification_service import notify_n8n_error

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GraphState(TypedDict):
    plano_id: Optional[str]
    archivo_path: Optional[str]
    cliente_id: Optional[str]
    plano_analizado: Optional[Dict[str, Any]]
    presupuesto_consolidado: Optional[Dict[str, Any]]
    status: str
    error: Optional[str]
    thread_id: Optional[str]
    # Usaremos esto internamente para pasar el presupuesto antes de consolidar
    # Si strict TypedDict is needed, I'll add it.
    presupuesto_calculado: Optional[Dict[str, Any]]
    motivo_rechazo: Optional[str]

def receive_input(state: GraphState):
    logger.info("Node: receive_input")
    return {"status": "received"}

def vision_analysis(state: GraphState):
    logger.info("Node: vision_analysis")
    file_path = state.get("archivo_path")
    
    if not file_path:
        return {"status": "error", "error": "No file_path provided"}
        
    try:
        with open(file_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {"status": "error", "error": f"Failed to read image file: {str(e)}"}
        
    plano_id = state.get("cliente_id", "unknown")
    
    result = analyze_plan(image_base64=image_base64, plano_id=plano_id)
    
    if result.error:
        return {"status": "error", "error": result.error, "plano_analizado": result.model_dump()}
        
    return {"status": "vision_analyzed", "plano_analizado": result.model_dump(), "plano_id": plano_id}

def extract_entities(state: GraphState):
    logger.info("Node: extract_entities")
    return {"status": "entities_extracted"}

def rag_pricing(state: GraphState):
    logger.info("Node: rag_pricing")
    vision_result = state.get("plano_analizado")
    
    if not vision_result:
        return {"status": "error", "error": "No plano_analizado found"}
        
    try:
        plano = PlanoAnalizado(**vision_result)
        cliente_id = state.get("cliente_id", "unknown")
        presupuesto = calculate_pricing(plano, cliente_id)
        
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
    
    # Pause the workflow here and wait for human input
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
        
        # En una implementación real se debería buscar o crear el contacto en Holded usando sus datos.
        # Por ahora asumimos que cliente_id es el NIF o un ID válido, o podríamos hacer mock de su ID de contacto
        # Para cumplir con el issue asumo que ya tenemos el contactId, o usamos el cliente_id.
        # Para robustez, podemos buscarlo o pasarlo directamente:
        contact_id = cliente_id
        
        holded_id = crear_presupuesto(contact_id, presupuesto)
        if not holded_id:
            return {"status": "error", "error": "Falló la creación del presupuesto en Holded"}
            
        # Guardar en BD
        plano_id = state.get("plano_id")
        if plano_id:
            async for session in get_session():
                # Actualizar el presupuesto model
                from sqlalchemy import select
                result = await session.execute(select(PresupuestoModel).where(PresupuestoModel.plano_id == plano_id))
                presupuesto_db = result.scalar_one_or_none()
                if presupuesto_db:
                    presupuesto_db.holded_estimate_id = holded_id
                    await session.commit()
                break
                
        return {"status": "sent_to_holded"}
    except Exception as e:
        logger.error(f"Error enviando a Holded: {e}")
        return {"status": "error", "error": f"Error enviando a Holded: {str(e)}"}

def notify_team(state: GraphState):
    logger.info("Node: notify_team")
    if state.get("status") == "rejected":
        motivo = state.get("motivo_rechazo", "Sin motivo")
        logger.info(f"Notificando al equipo: Presupuesto rechazado. Motivo: {motivo}")
    else:
        logger.info("Notificando al equipo: Presupuesto aprobado y procesado exitosamente.")
    return {"status": "completed"}

async def handle_error(state: GraphState):
    error_msg = state.get('error', 'Unknown error')
    logger.error(f"Node: handle_error. Error: {error_msg}")
    
    plano_id = state.get("plano_id", "unknown")
    job_id = state.get("thread_id", "unknown")
    
    # Intentar determinar el nodo que falló basado en el status o error
    nodo = "unknown"
    if "pricing" in error_msg.lower():
        nodo = "rag_pricing"
    elif "consolidation" in error_msg.lower() or "consolidate" in error_msg.lower():
        nodo = "consolidate"
    elif "file_path" in error_msg.lower() or "image" in error_msg.lower() or "vision" in error_msg.lower():
        nodo = "vision_analysis"
    elif "plano_analizado" in error_msg.lower():
        nodo = "rag_pricing"
        
    # Registramos en la BD
    try:
        async for session in get_session():
            job_log = JobLogModel(
                job_id=job_id,
                nodo=nodo,
                error_type="workflow_error",
                mensaje=error_msg
            )
            session.add(job_log)
            await session.commit()
            break # Solo necesitamos una sesión
    except Exception as e:
        logger.error(f"Error al guardar job_log en BD: {e}")
        
    # Notificamos a n8n
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

app_workflow = workflow.compile()
