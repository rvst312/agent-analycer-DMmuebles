import uuid
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class PrecioCreate(BaseModel):
    id: Optional[str] = Field(default=None, description="ID único para el precio (se genera si se omite)")
    documento: str = Field(..., description="Descripción del precio/material")
    metadatos: Dict[str, Any] = Field(
        ...,
        description="Metadatos obligatorios: material, cliente, precio_unitario, unidad, version, categoria"
    )

    def resolved_id(self) -> str:
        return self.id or str(uuid.uuid4())

class PrecioUpdate(BaseModel):
    precio_unitario: Optional[float] = None
    version: Optional[str] = None
    activo: Optional[bool] = None

class PrecioResponse(BaseModel):
    id: str
    documento: str
    metadatos: Dict[str, Any]
