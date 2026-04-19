from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import logging

from db.persistence import get_checkpointer
from langgraph.types import Command

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Workflow"])

class ResumeRequest(BaseModel):
    estimate_id: str
    approved: bool
    notes: str = ""

@router.post("/resume", status_code=status.HTTP_200_OK)
async def resume_workflow(request: ResumeRequest):
    """
    Reanuda el workflow después de una interrupción (HITL - human_approval).
    """
    logger.info(f"Reanudando workflow para estimate_id: {request.estimate_id} con approved={request.approved}")
    
    try:
        async with get_checkpointer() as checkpointer:
            # Compilamos el workflow con el checkpointer persistente
            from graph.workflow import workflow
            graph_with_cp = workflow.compile(checkpointer=checkpointer)
            
            config = {"configurable": {"thread_id": request.estimate_id}}
            
            # Verificamos si hay un estado guardado
            state = await graph_with_cp.aget_state(config)
            
            if not state.next:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No hay un workflow pausado para estimate_id: {request.estimate_id}"
                )
                
            if "human_approval" not in state.next:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El workflow {request.estimate_id} no está esperando aprobación humana (estado actual: {state.next})"
                )
            
            # Reanudamos el workflow enviando la respuesta del usuario
            # Usamos Command(resume=...) para reanudar el nodo interrumpido
            resume_data = {
                "approved": request.approved,
                "notes": request.notes
            }
            
            # Esto avanzará el grafo a partir del interrupt()
            await graph_with_cp.ainvoke(Command(resume=resume_data), config=config)
            
            return {
                "status": "resumed",
                "estimate_id": request.estimate_id,
                "approved": request.approved
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reanudando workflow {request.estimate_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno al reanudar: {str(e)}")

