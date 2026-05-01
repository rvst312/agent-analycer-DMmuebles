from enum import Enum
from typing import List, Optional

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

class PlanoAnalizado(BaseModel):
    plano_id: str
    componentes: List[ComponenteArmario]
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    raw_reasoning: str
    error: Optional[str] = None

class LineaPresupuesto(BaseModel):
    descripcion: str
    cantidad: int
    precio_unitario: float
    subtotal: float
    precio_pendiente: bool = False
    
class Presupuesto(BaseModel):
    plano_id: str
    lineas: List[LineaPresupuesto]
    total: float

class ResumenModulo(BaseModel):
    nombre: str
    descripcion: str
    subtotal: float
    total_con_iva: float

class PresupuestoConsolidado(BaseModel):
    cliente_id: str
    plano_id: str
    lineas: List[LineaPresupuesto]
    subtotal: float
    iva: float
    total: float
    lineas_pendientes: List[LineaPresupuesto]
    status: str = "pending_review"
    resumen: Optional[ResumenModulo] = None
    nombre_modulo: Optional[str] = None
