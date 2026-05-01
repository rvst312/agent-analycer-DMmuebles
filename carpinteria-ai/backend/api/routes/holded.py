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
    """Return ALL Holded contacts as [{id, name}], paginating through every page."""
    if not HOLDED_API_KEY:
        raise HTTPException(status_code=503, detail="HOLDED_API_KEY not configured")

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

    return sorted(
        [
            {"id": c.get("id"), "name": c.get("name") or "Sin nombre"}
            for c in all_contacts
            if c.get("id") and c.get("type") == "client"
        ],
        key=lambda x: x["name"].lower(),
    )
