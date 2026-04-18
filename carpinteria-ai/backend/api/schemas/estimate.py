from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TipoComponente(str, Enum):
    TABLERO = "tablero"
    PUERTA = "puerta"
    CAJON = "cajon"
    HERRAJE = "herraje"
    BARRA = "barra"

class ComponenteArmario(BaseModel):
    tipo: TipoComponente
    material: str
    acabado: str
    ancho_cm: float = Field(..., gt=0)
    largo_cm: float = Field(..., gt=0)
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
