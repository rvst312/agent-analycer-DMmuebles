import uuid
from sqlalchemy import Column, String, Float, JSON, DateTime
from datetime import datetime, timezone
from db.persistence import Base


class PresupuestoModel(Base):
    __tablename__ = "presupuestos"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    cliente_id = Column(String, nullable=False)
    nombre_cliente = Column(String, nullable=True)
    plano_id = Column(String, nullable=False, index=True)
    image_path = Column(String, nullable=True)
    subtotal = Column(Float, nullable=False, default=0.0)
    iva = Column(Float, nullable=False, default=0.0)
    total = Column(Float, nullable=False, default=0.0)
    lineas = Column(JSON, nullable=False, default=list)
    lineas_pendientes = Column(JSON, nullable=False, default=list)
    titulos_grupo = Column(JSON, nullable=True, default=dict)       # ref → título de partida
    descripciones_grupo = Column(JSON, nullable=True, default=dict)  # ref → descripción comercial
    imagenes_grupo = Column(JSON, nullable=True, default=dict)       # ref → url del recorte del plano
    proyecto = Column(String, nullable=True)                         # calle + número del proyecto
    familias_faltantes = Column(JSON, nullable=True, default=list)   # familias sin tarifa detectadas
    partidas = Column(JSON, nullable=True, default=list)             # partidas detectadas (para corregir/recalcular)
    archivos_origen = Column(JSON, nullable=True, default=list)      # keys de los archivos ORIGINALES subidos
    correcciones = Column(JSON, nullable=True, default=list)         # historial de correcciones con IA
    archivos_keys = Column(JSON, nullable=True, default=list)  # R2/S3 object keys for all files
    status = Column(String, default="processing", nullable=False)
    holded_estimate_id = Column(String, nullable=True)
    # index: el listado hace ORDER BY created_at DESC LIMIT 100 en cada poll
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class LeccionModel(Base):
    """
    Lección aprendida de una corrección humana: regla GENERAL de lectura de
    planos ("las estanterías E## rotuladas así son baldas entre paredes…") que
    se inyecta en los siguientes análisis de visión.
    """
    __tablename__ = "lecciones"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    texto = Column(String, nullable=False)
    plano_id = Column(String, nullable=True)      # presupuesto que la originó
    cliente_id = Column(String, nullable=True)
    activo = Column(String, default="si", nullable=False, index=True)  # "si"/"no"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class JobLogModel(Base):
    __tablename__ = "job_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, nullable=False, index=True)
    nodo = Column(String, nullable=False)
    error_type = Column(String, nullable=True)
    mensaje = Column(String, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ComponentFeedbackModel(Base):
    __tablename__ = "component_feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    plano_id = Column(String, nullable=False, index=True)
    # index: get_recent_corrections filtra por cliente_id en CADA análisis
    cliente_id = Column(String, nullable=True, index=True)
    componentes_originales = Column(JSON, nullable=False, default=list)
    componentes_corregidos = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PriceFeedbackModel(Base):
    __tablename__ = "price_feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    plano_id = Column(String, nullable=False, index=True)
    cliente_id = Column(String, nullable=True)
    # [{codigo, descripcion, precio_original, precio_corregido, chroma_updated}]
    correcciones = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
