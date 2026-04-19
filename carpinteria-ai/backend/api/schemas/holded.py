from pydantic import BaseModel, Field, model_validator
from typing import Optional, List

class ContactoSchema(BaseModel):
    nombre: str
    nif: str
    email: Optional[str] = None
    telefono: Optional[str] = None

class HoldedItem(BaseModel):
    name: str
    units: float
    subtotal: float
    tax: int = 21

class HoldedEstimate(BaseModel):
    contactId: str
    date: int
    items: List[HoldedItem]

    @model_validator(mode='after')
    def check_items_not_empty(self) -> 'HoldedEstimate':
        if not self.items:
            raise ValueError('items cannot be empty')
        return self

    def model_dump_json_clean(self) -> str:
        return self.model_dump_json(exclude_none=True)
