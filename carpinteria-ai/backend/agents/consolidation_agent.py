import logging
import uuid
from datetime import datetime, timezone
from typing import List, Tuple

from api.schemas.estimate import LineaPresupuesto, Presupuesto, PresupuestoConsolidado
from db.models import PresupuestoModel
from db.persistence import async_session_maker
from sqlalchemy import select

logger = logging.getLogger(__name__)


def calcular_presupuesto_consolidado(presupuesto: Presupuesto, cliente_id: str) -> PresupuestoConsolidado:
    subtotal = 0.0
    lineas_resueltas: List[LineaPresupuesto] = []
    lineas_pendientes: List[LineaPresupuesto] = []

    for linea in presupuesto.lineas:
        if linea.precio_pendiente:
            lineas_pendientes.append(linea)
        else:
            lineas_resueltas.append(linea)
            subtotal += linea.subtotal

    iva = subtotal * 0.21
    total = subtotal + iva

    return PresupuestoConsolidado(
        cliente_id=cliente_id,
        plano_id=presupuesto.plano_id,
        lineas=presupuesto.lineas,
        subtotal=subtotal,
        iva=iva,
        total=total,
        lineas_pendientes=lineas_pendientes,
        status="pending_review"
    )


async def guardar_presupuesto_en_db(consolidado: PresupuestoConsolidado) -> PresupuestoModel:
    """
    Upsert: update the existing record (created at POST /estimates time) or insert if missing.
    """
    lineas_json = [l.model_dump() for l in consolidado.lineas]
    pendientes_json = [l.model_dump() for l in consolidado.lineas_pendientes]
    now = datetime.now(timezone.utc)

    async with async_session_maker() as session:
        result = await session.execute(
            select(PresupuestoModel).where(PresupuestoModel.plano_id == consolidado.plano_id)
        )
        record = result.scalar_one_or_none()

        if record:
            record.cliente_id = consolidado.cliente_id
            record.subtotal = consolidado.subtotal
            record.iva = consolidado.iva
            record.total = consolidado.total
            record.lineas = lineas_json
            record.lineas_pendientes = pendientes_json
            record.status = "pending_review"
            record.updated_at = now
            await session.commit()
            await session.refresh(record)
            logger.info(f"Presupuesto actualizado en DB: {record.id}")
            return record
        else:
            nuevo = PresupuestoModel(
                id=str(uuid.uuid4()),
                cliente_id=consolidado.cliente_id,
                plano_id=consolidado.plano_id,
                subtotal=consolidado.subtotal,
                iva=consolidado.iva,
                total=consolidado.total,
                lineas=lineas_json,
                lineas_pendientes=pendientes_json,
                status="pending_review",
            )
            session.add(nuevo)
            await session.commit()
            await session.refresh(nuevo)
            logger.info(f"Presupuesto insertado en DB: {nuevo.id}")
            return nuevo


async def execute_consolidation(presupuesto: Presupuesto, cliente_id: str) -> PresupuestoConsolidado:
    consolidado = calcular_presupuesto_consolidado(presupuesto, cliente_id)
    await guardar_presupuesto_en_db(consolidado)
    return consolidado
