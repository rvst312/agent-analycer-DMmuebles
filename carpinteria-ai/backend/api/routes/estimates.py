import logging
import os
import shutil
import uuid
from typing import Optional

from db.persistence import get_checkpointer
from fastapi import (APIRouter, BackgroundTasks, File, Form, HTTPException,
                     UploadFile, status)
from graph.workflow import app_workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/estimates", tags=["Estimates"])

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "application/pdf"}
UPLOAD_DIR = "/tmp/carpinteria_uploads"

# Asegurar que el directorio temporal exista
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def process_estimate(estimate_id: str, file_path: str, cliente_id: str):
    """
    Función que ejecuta el grafo en background.
    """
    logger.info(f"Iniciando procesamiento en background para estimate_id: {estimate_id}")
    try:
        # Aquí se obtiene el checkpointer async y se compila el grafo con él
        # pero para mantenerlo simple y usar lo existente, usamos ainvoke
        
        # Necesitamos usar el checkpointer real de la DB para guardar el estado
        async with get_checkpointer() as checkpointer:
            # Re-compilar el grafo con el checkpointer
            from graph.workflow import workflow
            graph_with_cp = workflow.compile(checkpointer=checkpointer)
            
            config = {"configurable": {"thread_id": estimate_id}}
            initial_state = {
                "archivo_path": file_path,
                "cliente_id": cliente_id,
                "status": "pending",
                "thread_id": estimate_id
            }
            
            await graph_with_cp.ainvoke(initial_state, config=config)
            logger.info(f"Procesamiento finalizado (o en pausa) para estimate_id: {estimate_id}")
            
    except Exception as e:
        logger.error(f"Error procesando estimate_id {estimate_id}: {e}")

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
    
    background_tasks.add_task(process_estimate, estimate_id, file_path, cliente_id)
    
    return {
        "estimate_id": estimate_id,
        "status": "processing"
    }

@router.get("", status_code=status.HTTP_200_OK)
async def list_estimates():
    """
    Devuelve la lista de todos los presupuestos (threads) procesados.
    """
    try:
        async with get_checkpointer() as checkpointer:
            from graph.workflow import workflow
            graph_with_cp = workflow.compile(checkpointer=checkpointer)
            
            seen_threads = set()
            estimates = []
            
            async for checkpoint_tuple in checkpointer.alist(None):
                thread_id = checkpoint_tuple.config["configurable"].get("thread_id")
                if not thread_id or thread_id in seen_threads:
                    continue
                
                seen_threads.add(thread_id)
                
                # Opcional: limitar a los últimos 100 para no sobrecargar
                if len(seen_threads) > 100:
                    break
                
                config = {"configurable": {"thread_id": thread_id}}
                state_snapshot = await graph_with_cp.aget_state(config)
                
                if not state_snapshot or not state_snapshot.values:
                    continue
                    
                state_values = state_snapshot.values
                next_nodes = state_snapshot.next
                
                current_status = state_values.get("status", "unknown")
                error = state_values.get("error")
                
                if next_nodes and "human_approval" in next_nodes:
                    current_status = "human_approval_required"
                elif not next_nodes and current_status not in ["error", "rejected", "handled_error"]:
                    current_status = "completed"
                elif current_status == "handled_error":
                    current_status = "error"
                    
                # Obtener la fecha del checkpoint
                updated_at = checkpoint_tuple.checkpoint.get("ts", "")
                
                estimates.append({
                    "estimate_id": thread_id,
                    "status": current_status,
                    "plano_id": state_values.get("plano_id"),
                    "cliente_id": state_values.get("cliente_id"),
                    "updated_at": updated_at,
                    "error": error
                })
                
            return {"estimates": estimates}
            
    except Exception as e:
        logger.error(f"Error listando estimates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno listando presupuestos: {str(e)}"
        )

@router.get("/{estimate_id}", status_code=status.HTTP_200_OK)
async def get_estimate_status(estimate_id: str):
    """
    Consulta el estado de un presupuesto por su ID (thread_id).
    """
    try:
        async with get_checkpointer() as checkpointer:
            from graph.workflow import workflow
            graph_with_cp = workflow.compile(checkpointer=checkpointer)
            
            config = {"configurable": {"thread_id": estimate_id}}
            state_snapshot = await graph_with_cp.aget_state(config)
            
            if not state_snapshot or not state_snapshot.values:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Estimate {estimate_id} no encontrado."
                )
                
            state_values = state_snapshot.values
            next_nodes = state_snapshot.next
            
            current_status = state_values.get("status", "unknown")
            error = state_values.get("error")
            
            if next_nodes and "human_approval" in next_nodes:
                current_status = "human_approval_required"
            elif not next_nodes and current_status not in ["error", "rejected"]:
                current_status = "completed"
                
            response = {
                "estimate_id": estimate_id,
                "status": current_status,
                "plano_id": state_values.get("plano_id"),
                "cliente_id": state_values.get("cliente_id"),
                "image_url": f"/uploads/{os.path.basename(state_values.get('archivo_path', ''))}" if state_values.get("archivo_path") else None,
                "plano_analizado": state_values.get("plano_analizado"),
                "presupuesto_calculado": state_values.get("presupuesto_calculado"),
                "presupuesto_consolidado": state_values.get("presupuesto_consolidado"),
                "motivo_rechazo": state_values.get("motivo_rechazo")
            }
            
            if error:
                response["error"] = error
                
            return response
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error consultando estimate_id {estimate_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno consultando el estado: {str(e)}"
        )
