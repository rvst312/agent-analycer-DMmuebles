from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TipoComponente(str, Enum):
    TABLERO = "tablero"
    PUERTA = "puerta"
    CAJON = "cajon"
    CAJON_TILDE = "cajón"
    HERRAJE = "herraje"
    BARRA = "barra"
    ESTANTE = "estante"
    ARMARIO = "armario"
    OTRO = "otro"


class ComponenteArmario(BaseModel):
    tipo: TipoComponente
    material: str
    acabado: str
    ancho_cm: float = Field(..., ge=0)
    largo_cm: float = Field(..., ge=0)
    cantidad: int = Field(..., gt=0)
    notas: Optional[str] = None
    ref: Optional[str] = None


# ── Armario-specific models ──────────────────────────────────────────────────

class ModuloArmario(BaseModel):
    """Cuerpo estructural de un armario (ropa larga, zapatero, rinconero…)."""
    ref: str = ""
    tipo: str                   # e.g. "ropa larga", "zapatero", "rinconero"
    ancho_cm: float = 0.0
    alto_cm: float = 0.0
    fondo_cm: float = 0.0
    cantidad: int = 1
    notas: Optional[str] = None


class PuertaArmario(BaseModel):
    """Puerta del armario (corredera, abatible…)."""
    ref: str = ""
    tipo: str                   # e.g. "corredera", "abatible", "batiente"
    ancho_cm: float = 0.0
    alto_cm: float = 0.0
    acabado: str = ""
    cantidad: int = 1
    notas: Optional[str] = None


class ItemInteriorArmario(BaseModel):
    """Accesorio interior (cajón, barra, LED, espejo, bandeja…)."""
    ref: str = ""
    tipo: str
    cantidad: int = 1
    notas: Optional[str] = None


class AnalisisArmario(BaseModel):
    """Análisis completo de un armario identificado por su ref en el plano."""
    ref: str
    modulos: List[ModuloArmario] = []
    puertas: List[PuertaArmario] = []
    items_interiores: List[ItemInteriorArmario] = []


# ── PlanoAnalizado (unified) ─────────────────────────────────────────────────

class PlanoAnalizado(BaseModel):
    plano_id: str
    tipo_plano: str = "general"                     # "armario" | "general" | …
    componentes: List[ComponenteArmario] = []       # used for non-armario types
    armarios: Optional[List[AnalisisArmario]] = None  # used for armario type
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    raw_reasoning: str
    error: Optional[str] = None


# ── Presupuesto ──────────────────────────────────────────────────────────────

class LineaPresupuesto(BaseModel):
    codigo: str = ""
    ref: Optional[str] = None
    descripcion: str
    cantidad: int
    precio_unitario: float
    subtotal: float
    precio_pendiente: bool = False


class Presupuesto(BaseModel):
    plano_id: str
    lineas: List[LineaPresupuesto]
    total: float


class PresupuestoConsolidado(BaseModel):
    cliente_id: str
    plano_id: str
    lineas: List[LineaPresupuesto]
    subtotal: float
    iva: float
    total: float
    lineas_pendientes: List[LineaPresupuesto]
    status: str = "pending_review"
    descripciones_grupo: Optional[Dict[str, str]] = None
    titulo_proyecto: Optional[str] = None
