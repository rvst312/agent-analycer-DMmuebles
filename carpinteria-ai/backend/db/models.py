import uuid
from sqlalchemy import Column, String, Float, JSON, DateTime
from datetime import datetime, timezone
from db.persistence import Base


class PresupuestoModel(Base):
    __tablename__ = "presupuestos"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    cliente_id = Column(String, nullable=False)
    plano_id = Column(String, nullable=False, index=True)
    image_path = Column(String, nullable=True)
    subtotal = Column(Float, nullable=False, default=0.0)
    iva = Column(Float, nullable=False, default=0.0)
    total = Column(Float, nullable=False, default=0.0)
    lineas = Column(JSON, nullable=False, default=list)
    lineas_pendientes = Column(JSON, nullable=False, default=list)
    status = Column(String, default="processing", nullable=False)
    holded_estimate_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class JobLogModel(Base):
    __tablename__ = "job_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, nullable=False, index=True)
    nodo = Column(String, nullable=False)
    error_type = Column(String, nullable=True)
    mensaje = Column(String, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
