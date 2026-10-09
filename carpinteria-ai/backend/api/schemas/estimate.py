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
    habitacion: str = ""            # p.ej. "Dormitorio 2" (para el título de partida)
    material_interior: str = ""     # p.ej. "melamina textil" (para la descripción)
    modulos: List[ModuloArmario] = []
    puertas: List[PuertaArmario] = []
    items_interiores: List[ItemInteriorArmario] = []


# ── Partidas por familia ─────────────────────────────────────────────────────

# Familias de partida que la visión debe reconocer. Cada una se enruta a un
# método de cálculo; las que no tienen tarifa quedan pendientes con aviso.
FAMILIAS = (
    "puerta_paso_abatible",
    "puerta_paso_corredera",
    "cerramiento",
    "rodapie",
    "armario",
    "vestidor",
    "mueble_bano",
    "mueble_varios",
    "balda_pared",
    "otro",
)


class Partida(BaseModel):
    """Una partida detectada en el plano, con su familia y atributos."""
    familia: str
    descripcion: str = ""              # qué es, en corto
    habitacion: str = ""
    ancho_cm: float = 0.0
    alto_cm: float = 0.0
    fondo_cm: float = 0.0
    material: str = ""                 # material/acabado exterior o principal
    material_interior: str = ""        # solo armario/vestidor
    acabado: str = ""
    apertura: str = ""                 # "abatible" | "corredera" (puertas)
    cantidad: int = 1                  # unidades idénticas agrupadas
    notas: Optional[str] = None
    ref: Optional[str] = None
    # Localización en el plano (para recortar el dibujo de la partida):
    pagina: int = 0                    # nº de página del PDF (1-based; 0 = desconocida)
    bbox_pct: List[float] = []         # [x0, y0, x1, y1] en % del ancho/alto de la página
    archivo_idx: int = 0               # índice del archivo subido (lo fija el workflow)
    # Sub-estructura (solo armario/vestidor):
    modulos: List[ModuloArmario] = []
    puertas: List[PuertaArmario] = []
    items_interiores: List[ItemInteriorArmario] = []


# ── PlanoAnalizado (unified) ─────────────────────────────────────────────────

class PlanoAnalizado(BaseModel):
    plano_id: str
    tipo_plano: str = "general"                     # "armario" | "general" | …
    proyecto: str = ""                              # calle + número (p.ej. "Goya 23")
    partidas: List[Partida] = []                    # NUEVO: partidas por familia
    componentes: List[ComponenteArmario] = []       # (legacy) non-armario types
    armarios: Optional[List[AnalisisArmario]] = None  # (legacy) armario type
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    raw_reasoning: str
    error: Optional[str] = None


# ── Presupuesto ──────────────────────────────────────────────────────────────

class LineaPresupuesto(BaseModel):
    codigo: str = ""
    ref: Optional[str] = None
    descripcion: str
    cantidad: float  # float: los rodapiés van por metros lineales (p.ej. 40.5)
    precio_unitario: float
    subtotal: float
    precio_pendiente: bool = False
    explicacion: Optional[str] = None  # desglose de cómo se calculó el precio


class Presupuesto(BaseModel):
    plano_id: str
    lineas: List[LineaPresupuesto]
    total: float
    titulos_grupo: Optional[Dict[str, str]] = None       # ref → "A06 - Armario Dormitorio 2"
    descripciones_grupo: Optional[Dict[str, str]] = None  # ref → descripción comercial
    familias_faltantes: Optional[List[str]] = None        # familias sin tarifa detectadas


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
    titulos_grupo: Optional[Dict[str, str]] = None
    familias_faltantes: Optional[List[str]] = None
    descuentos_grupo: Optional[Dict[str, float]] = None  # ref → % descuento (p.ej. 10)
    titulo_proyecto: Optional[str] = None
