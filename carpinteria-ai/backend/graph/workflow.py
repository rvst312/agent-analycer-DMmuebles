"""
Grafo LangGraph con nodos, aristas e interrupt()
"""
from typing import TypedDict, Dict, Any, Optional
from langgraph.graph import StateGraph, END
import logging
import base64
from agents.vision_agent import analyze_plan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GraphState(TypedDict):
    input_data: Dict[str, Any]
    status: str
    error: Optional[str]
    vision_result: Optional[Dict[str, Any]]

def receive_input(state: GraphState):
    logger.info("Node: receive_input")
    return {"status": "received"}

def vision_analysis(state: GraphState):
    logger.info("Node: vision_analysis")
    input_data = state.get("input_data", {})
    file_path = input_data.get("file_path")
    
    if not file_path:
        return {"status": "error", "error": "No file_path provided in input_data"}
        
    try:
        with open(file_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {"status": "error", "error": f"Failed to read image file: {str(e)}"}
        
    # Extraer cliente_id u otro dato si se requiere como plano_id
    plano_id = input_data.get("cliente_id", "unknown")
    
    # Llamar al agente
    result = analyze_plan(image_base64=image_base64, plano_id=plano_id)
    
    if result.error:
        return {"status": "error", "error": result.error, "vision_result": result.model_dump()}
        
    return {"status": "vision_analyzed", "vision_result": result.model_dump()}

def extract_entities(state: GraphState):
    logger.info("Node: extract_entities")
    return {"status": "entities_extracted"}

def rag_pricing(state: GraphState):
    logger.info("Node: rag_pricing")
    return {"status": "priced"}

def consolidate(state: GraphState):
    logger.info("Node: consolidate")
    return {"status": "consolidated"}

def human_approval(state: GraphState):
    logger.info("Node: human_approval (HITL)")
    # Lógica de interrupción manejada por langgraph al compilar el grafo con checkpointer
    return {"status": "pending_approval"}

def send_to_holded(state: GraphState):
    logger.info("Node: send_to_holded")
    return {"status": "sent_to_holded"}

def notify_team(state: GraphState):
    logger.info("Node: notify_team")
    return {"status": "completed"}

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

workflow.set_entry_point("receive_input")
workflow.add_edge("receive_input", "vision_analysis")

def check_vision_error(state: GraphState):
    if state.get("status") == "error":
        return "error"
    return "continue"

workflow.add_conditional_edges(
    "vision_analysis",
    check_vision_error,
    {
        "error": END,
        "continue": "extract_entities"
    }
)

workflow.add_edge("extract_entities", "rag_pricing")
workflow.add_edge("rag_pricing", "consolidate")
workflow.add_edge("consolidate", "human_approval")
workflow.add_edge("human_approval", "send_to_holded")
workflow.add_edge("send_to_holded", "notify_team")
workflow.add_edge("notify_team", END)

# Exportar el grafo sin compilar para tests, y compilado para la app (sin checkpointer por ahora para que no falle al importar si no hay db)
app_workflow = workflow.compile()
