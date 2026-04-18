import logging
import uuid
from typing import List, Tuple

from api.schemas.estimate import LineaPresupuesto, Presupuesto, PresupuestoConsolidado
from db.models import PresupuestoModel
from db.persistence import async_session_maker

logger = logging.getLogger(__name__)

def calcular_presupuesto_consolidado(presupuesto: Presupuesto, cliente_id: str) -> PresupuestoConsolidado:
    """
    Toma un Presupuesto (con sus líneas), suma los subtotales para obtener el subtotal general,
    calcula el IVA (21%), y el total final. Separa las líneas que están pendientes de precio.
    """
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

    # Si había líneas pendientes, el total no es definitivo, pero devolvemos lo que hay.
    return PresupuestoConsolidado(
        cliente_id=cliente_id,
        plano_id=presupuesto.plano_id,
        lineas=presupuesto.lineas, # Todas las líneas
        subtotal=subtotal,
        iva=iva,
        total=total,
        lineas_pendientes=lineas_pendientes,
        status="pending_review"
    )

async def guardar_presupuesto_en_db(consolidado: PresupuestoConsolidado) -> PresupuestoModel:
    """
    Guarda el presupuesto consolidado en la base de datos PostgreSQL usando SQLAlchemy.
    """
    nuevo_presupuesto = PresupuestoModel(
        id=str(uuid.uuid4()),
        cliente_id=consolidado.cliente_id,
        plano_id=consolidado.plano_id,
        subtotal=consolidado.subtotal,
        iva=consolidado.iva,
        total=consolidado.total,
        lineas=[linea.model_dump() for linea in consolidado.lineas],
        lineas_pendientes=[linea.model_dump() for linea in consolidado.lineas_pendientes],
        status=consolidado.status
    )
    
    async with async_session_maker() as session:
        session.add(nuevo_presupuesto)
        await session.commit()
        await session.refresh(nuevo_presupuesto)
        
        logger.info(f"Presupuesto consolidado guardado en DB con id: {nuevo_presupuesto.id}")
        return nuevo_presupuesto

async def execute_consolidation(presupuesto: Presupuesto, cliente_id: str) -> PresupuestoConsolidado:
    consolidado = calcular_presupuesto_consolidado(presupuesto, cliente_id)
    await guardar_presupuesto_en_db(consolidado)
    return consolidado
