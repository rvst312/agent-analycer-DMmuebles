import logging
from typing import Any, Dict, Literal, Optional

from api.auth import verify_jefe_obra_token
from db.persistence import get_checkpointer
from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.types import Command
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Workflow"])

class ResumeRequest(BaseModel):
    thread_id: str
    action: Literal["approve", "reject"]
    ajustes: Optional[Dict[str, Any]] = None
    motivo: Optional[str] = None

@router.post("/resume", status_code=status.HTTP_200_OK)
async def resume_workflow(request: ResumeRequest, token: dict = Depends(verify_jefe_obra_token)):
    """
    Reanuda el workflow después de una interrupción (HITL - human_approval).
    """
    logger.info(f"Reanudando workflow para thread_id: {request.thread_id} con action={request.action}")
    
    try:
        async with get_checkpointer() as checkpointer:
            # Compilamos el workflow con el checkpointer persistente
            from graph.workflow import workflow
            graph_with_cp = workflow.compile(checkpointer=checkpointer)
            
            config = {"configurable": {"thread_id": request.thread_id}}
            
            # Verificamos si hay un estado guardado
            state = await graph_with_cp.aget_state(config)
            
            if not state.next:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No hay un workflow pausado para thread_id: {request.thread_id}"
                )
                
            if "human_approval" not in state.next:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El workflow {request.thread_id} no está esperando aprobación humana (estado actual: {state.next})"
                )
            
            # Reanudamos el workflow enviando la respuesta del usuario
            resume_data = {
                "action": request.action,
                "ajustes": request.ajustes,
                "motivo": request.motivo
            }
            
            # Esto avanzará el grafo a partir del interrupt()
            await graph_with_cp.ainvoke(Command(resume=resume_data), config=config)
            
            return {
                "status": "resumed",
                "thread_id": request.thread_id,
                "action": request.action
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reanudando workflow {request.thread_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error interno al reanudar: {str(e)}")

