from pydantic import BaseModel, Field
from typing import Optional

class ContactoSchema(BaseModel):
    nombre: str
    nif: str
    email: Optional[str] = None
    telefono: Optional[str] = None
