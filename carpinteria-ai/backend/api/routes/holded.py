import logging
import os

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/holded", tags=["holded"])
logger = logging.getLogger(__name__)

HOLDED_API_KEY = os.getenv("HOLDED_API_KEY", "")
HOLDED_BASE_URL = "https://api.holded.com/api/invoicing/v1"


def _headers() -> dict:
    return {"key": HOLDED_API_KEY, "Accept": "application/json"}


@router.get("/contacts")
async def get_contacts():
    """Return all Holded contacts as [{id, name}] for the frontend selector."""
    if not HOLDED_API_KEY:
        raise HTTPException(status_code=503, detail="HOLDED_API_KEY not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{HOLDED_BASE_URL}/contacts", headers=_headers())
            resp.raise_for_status()
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Timeout connecting to Holded")
        except httpx.HTTPStatusError as e:
            logger.error(f"Holded contacts HTTP error: {e.response.status_code} {e.response.text}")
            raise HTTPException(status_code=502, detail=f"Holded API returned {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching Holded contacts: {e}")
            raise HTTPException(status_code=500, detail="Error fetching contacts from Holded")

    contacts = resp.json()
    if not isinstance(contacts, list):
        logger.error(f"Unexpected Holded contacts response: {contacts}")
        raise HTTPException(status_code=502, detail="Unexpected response from Holded API")

    return [
        {"id": c.get("id"), "name": c.get("name") or "Sin nombre"}
        for c in contacts
        if c.get("id")
    ]
