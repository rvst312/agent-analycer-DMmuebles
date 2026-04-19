import base64
import logging
from typing import Any, Dict, Optional, TypedDict

from agents.consolidation_agent import execute_consolidation
from agents.pricing_agent import calculate_pricing
from agents.vision_agent import analyze_plan
from api.schemas.estimate import PlanoAnalizado, Presupuesto
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

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
    
    if isinstance(approval_response, dict) and approval_response.get("approved"):
        return {"status": "approved"}
    else:
        # If rejected or not explicitly approved, set to rejected
        # Or maybe it's just a status update
        return {"status": "rejected"}

def send_to_holded(state: GraphState):
    logger.info("Node: send_to_holded")
    return {"status": "sent_to_holded"}

def notify_team(state: GraphState):
    logger.info("Node: notify_team")
    return {"status": "completed"}

def handle_error(state: GraphState):
    logger.error(f"Node: handle_error. Error: {state.get('error')}")
    return {"status": "handled_error"}

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

workflow.add_conditional_edges(
    "human_approval",
    check_error,
    {"error": "handle_error", "continue": "send_to_holded"}
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
