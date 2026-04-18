from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class PrecioCreate(BaseModel):
    id: str = Field(..., description="ID único para el precio")
    texto: str = Field(..., description="Descripción del precio/material")
    metadatos: Dict[str, Any] = Field(
        ..., 
        description="Metadatos obligatorios: material, cliente, precio_unitario, unidad, version, categoria"
    )

class PrecioUpdate(BaseModel):
    precio_unitario: Optional[float] = None
    version: Optional[str] = None
    activo: Optional[bool] = None

class PrecioResponse(BaseModel):
    id: str
    documento: str
    metadatos: Dict[str, Any]
