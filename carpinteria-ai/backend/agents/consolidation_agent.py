import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from api.schemas.estimate import LineaPresupuesto, Presupuesto, PresupuestoConsolidado, ResumenModulo
from db.models import PresupuestoModel
from db.persistence import async_session_maker
from sqlalchemy import select

logger = logging.getLogger(__name__)


def _generate_resumen(nombre: str, lineas: List[LineaPresupuesto], subtotal: float) -> ResumenModulo:
    top = sorted([l for l in lineas if not l.precio_pendiente], key=lambda x: x.subtotal, reverse=True)[:3]
    partes = [f"{l.descripcion.split(chr(10))[0][:40]}" for l in top]
    descripcion = "; ".join(partes) if partes else "Módulo de carpintería"
    iva = subtotal * 0.21
    return ResumenModulo(
        nombre=nombre or "Módulo",
        descripcion=descripcion,
        subtotal=round(subtotal, 2),
        total_con_iva=round(subtotal + iva, 2),
    )


def calcular_presupuesto_consolidado(
    presupuesto: Presupuesto, cliente_id: str, nombre_modulo: str = ""
) -> PresupuestoConsolidado:
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
    resumen = _generate_resumen(nombre_modulo, presupuesto.lineas, subtotal) if nombre_modulo else None

    return PresupuestoConsolidado(
        cliente_id=cliente_id,
        plano_id=presupuesto.plano_id,
        lineas=presupuesto.lineas,
        subtotal=subtotal,
        iva=iva,
        total=total,
        lineas_pendientes=lineas_pendientes,
        status="pending_review",
        resumen=resumen,
        nombre_modulo=nombre_modulo or None,
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
            record.nombre_modulo = consolidado.nombre_modulo
            record.resumen = consolidado.resumen.model_dump() if consolidado.resumen else None
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
                nombre_modulo=consolidado.nombre_modulo,
                resumen=consolidado.resumen.model_dump() if consolidado.resumen else None,
            )
            session.add(nuevo)
            await session.commit()
            await session.refresh(nuevo)
            logger.info(f"Presupuesto insertado en DB: {nuevo.id}")
            return nuevo


async def execute_consolidation(
    presupuesto: Presupuesto, cliente_id: str, nombre_modulo: str = ""
) -> PresupuestoConsolidado:
    consolidado = calcular_presupuesto_consolidado(presupuesto, cliente_id, nombre_modulo)
    await guardar_presupuesto_en_db(consolidado)
    return consolidado
