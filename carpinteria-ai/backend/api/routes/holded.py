import logging
import os
from typing import Optional

import httpx
from api.auth import verify_jefe_obra_token
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(
    prefix="/holded",
    tags=["holded"],
    dependencies=[Depends(verify_jefe_obra_token)],
)
logger = logging.getLogger(__name__)

HOLDED_API_KEY = os.getenv("HOLDED_API_KEY", "")
HOLDED_BASE_URL = "https://api.holded.com/api/invoicing/v1"


def _headers() -> dict:
    return {"key": HOLDED_API_KEY, "Accept": "application/json", "Content-Type": "application/json"}


class CreateContactBody(BaseModel):
    nombre: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    nif: Optional[str] = None


# ── Caché de contactos ────────────────────────────────────────────────────────
# La lista de Holded (~400 contactos, varias páginas de su API) se pedía a
# Holded en CADA carga del formulario. TTL de 10 min + invalidación al crear
# un contacto; ?refresh=1 fuerza recarga.
_CONTACTS_TTL = 600.0
_contacts_cache: dict = {"data": None, "ts": 0.0}


def invalidar_cache_contactos() -> None:
    _contacts_cache["data"] = None
    _contacts_cache["ts"] = 0.0


@router.get("/contacts")
async def get_contacts(refresh: bool = False):
    """Return ALL Holded contacts as [{id, name}] (cacheado 10 min)."""
    import time as _time

    if not HOLDED_API_KEY:
        raise HTTPException(status_code=503, detail="HOLDED_API_KEY not configured")

    if (not refresh and _contacts_cache["data"] is not None
            and _time.monotonic() - _contacts_cache["ts"] < _CONTACTS_TTL):
        return _contacts_cache["data"]

    all_contacts: list = []
    page = 1

    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            try:
                resp = await client.get(
                    f"{HOLDED_BASE_URL}/contacts",
                    headers=_headers(),
                    params={"page": page},
                )
                resp.raise_for_status()
            except httpx.TimeoutException:
                raise HTTPException(status_code=504, detail="Timeout connecting to Holded")
            except httpx.HTTPStatusError as e:
                logger.error(f"Holded contacts HTTP error: {e.response.status_code}")
                raise HTTPException(status_code=502, detail=f"Holded API returned {e.response.status_code}")
            except Exception as e:
                logger.error(f"Error fetching Holded contacts page {page}: {e}")
                raise HTTPException(status_code=500, detail="Error fetching contacts from Holded")

            batch = resp.json()
            if not isinstance(batch, list):
                logger.error(f"Unexpected Holded response on page {page}: {batch}")
                break

            all_contacts.extend(batch)
            logger.info(f"Holded contacts: fetched page {page} ({len(batch)} items, total {len(all_contacts)})")

            # Holded returns up to 500 per page; fewer means last page
            if len(batch) < 500:
                break
            page += 1

    resultado = sorted(
        [
            {"id": c.get("id"), "name": c.get("name") or "Sin nombre"}
            for c in all_contacts
            if c.get("id") and c.get("type") == "client"
        ],
        key=lambda x: x["name"].lower(),
    )
    import time as _time
    _contacts_cache["data"] = resultado
    _contacts_cache["ts"] = _time.monotonic()
    return resultado


@router.post("/contacts", status_code=201)
async def create_contact(body: CreateContactBody):
    """Create a new client contact in Holded and return {id, name}."""
    if not HOLDED_API_KEY:
        raise HTTPException(status_code=503, detail="HOLDED_API_KEY not configured")

    nombre = body.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")

    payload: dict = {"name": nombre, "type": "client"}
    if body.nif:
        payload["code"] = body.nif.strip()
    if body.email:
        payload["email"] = body.email.strip()
    if body.telefono:
        payload["phone"] = body.telefono.strip()

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{HOLDED_BASE_URL}/contacts",
                headers=_headers(),
                json=payload,
            )
            resp.raise_for_status()
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Timeout conectando con Holded")
        except httpx.HTTPStatusError as e:
            logger.error(f"Holded create contact HTTP error: {e.response.status_code} — {e.response.text}")
            raise HTTPException(status_code=502, detail=f"Holded devolvió {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error creating Holded contact: {e}")
            raise HTTPException(status_code=500, detail="Error creando contacto en Holded")

    result = resp.json()
    contact_id = result.get("id")
    if not contact_id or result.get("status") == 0:
        logger.error(f"Holded rejected contact creation: {result}")
        raise HTTPException(status_code=502, detail="Holded no pudo crear el contacto")

    logger.info(f"Created Holded contact: {contact_id} ({nombre})")
    invalidar_cache_contactos()  # que el nuevo cliente aparezca al instante
    return {"id": contact_id, "name": nombre}
