from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, status
import uuid
import os
import shutil
import logging
from typing import Optional

from graph.workflow import app_workflow
from db.persistence import get_checkpointer

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
