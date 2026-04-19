import logging
import os

import httpx

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
APPROVAL_TIMEOUT_HOURS = int(os.getenv("APPROVAL_TIMEOUT_HOURS", "24"))

async def notify_slack(message: str):
    """
    Envía una notificación a Slack o n8n webhook.
    """
    if not SLACK_WEBHOOK_URL:
        logger.warning(f"No SLACK_WEBHOOK_URL configured. Would have sent: {message}")
        return
        
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                SLACK_WEBHOOK_URL,
                json={"text": message},
                timeout=10.0
            )
            response.raise_for_status()
            logger.info("Notificación de Slack enviada con éxito.")
    except Exception as e:
        logger.error(f"Error al enviar notificación a Slack: {e}")

async def check_pending_approvals(checkpointer):
    """
    Función que puede ser llamada por un cron o tarea en background
    para verificar presupuestos pendientes y notificar por Slack si exceden
    el timeout configurado.
    """
    logger.info(f"Verificando presupuestos pendientes de aprobación por más de {APPROVAL_TIMEOUT_HOURS} horas...")
    # Aquí iría la lógica para consultar el checkpointer o la base de datos
    # y buscar threads en estado 'human_approval' cuyo timestamp sea anterior
    # a (now - APPROVAL_TIMEOUT_HOURS).
    # Por cada uno, llamar a notify_slack(f"Presupuesto {estimate_id} lleva más de {APPROVAL_TIMEOUT_HOURS}h esperando aprobación.")
    pass

async def notify_n8n_error(plano_id: str, nodo: str, mensaje: str):
    """
    Envía una notificación de error al webhook de n8n.
    """
    if not N8N_WEBHOOK_URL:
        logger.warning(f"No N8N_WEBHOOK_URL configured. Would have sent error for plano_id {plano_id}")
        return
        
    payload = {
        "plano_id": plano_id,
        "nodo": nodo,
        "mensaje": mensaje,
        "tipo": "ERROR_WORKFLOW"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                N8N_WEBHOOK_URL,
                json=payload,
                timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"Notificación de error enviada a n8n para plano {plano_id}")
    except Exception as e:
        logger.error(f"Error al enviar notificación a n8n: {e}")

