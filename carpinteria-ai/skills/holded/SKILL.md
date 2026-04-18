# Holded Skill

Integrates with Holded's invoicing API to export approved estimates as draft documents.

## Purpose
Sends formatted estimate data to Holded (SaaS accounting platform) after human approval. Creates estimate/quote documents that can be sent to clients and converted to invoices.

## Holded Integration (backend/services/ or api/routes/estimates.py)

### API Endpoint
```
POST https://api.holded.com/api/invoicing/v1/documents/estimate
Authorization: Bearer {HOLDED_API_KEY}
```

### Request Payload (from pricing_agent output)
```json
{
  "contactId": "123456",        # Holded contact ID
  "date": 1713398400,           # UNIX timestamp
  "number": "EST-2025-001",     # Optional, Holded auto-generates
  "subject": "Presupuesto carpintería",
  "notes": "Documento generado por Carpintería AI",
  "items": [
    {
      "name": "Tablero Roble 100x50cm (acabado natural)",
      "description": "Material + Labor",
      "quantity": 1.0,
      "unitPrice": 48.50,       # price_material + costo_labor combined
      "tax": 21,                # VAT percentage (Spain default)
      "reference": "roble_tablero_natural_v1"
    }
  ]
}
```

### Response
```json
{
  "id": "est_abc123def456",
  "number": "EST-2025-001",
  "status": "draft",
  "url": "https://app.holded.com/documents/est_abc123def456",
  "contactId": "123456",
  "totalAmount": 1245.67,
  "totalTax": 261.59,
  "currency": "EUR"
}
```

## Implementation Pattern

**Holded Service Client** (recommended structure):
```python
# backend/services/holded_service.py
from httpx import AsyncClient
import os

class HolledService:
    def __init__(self):
        self.api_key = os.getenv("HOLDED_API_KEY")
        self.base_url = "https://api.holded.com/api/invoicing/v1"

    async def create_estimate(self, payload: dict) -> dict:
        """Send estimate to Holded and return document ID"""
        async with AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/documents/estimate",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            response.raise_for_status()
            return response.json()
```

**Integration in send_to_holded Node**:
```python
def send_to_holded(state: GraphState):
    """Convert estimate to Holded format and POST"""
    try:
        holded_payload = convert_estimate_to_holded_format(
            state["pricing_result"],
            client_id=state["input_data"]["client_id"]
        )
        
        holded_response = await holled_service.create_estimate(holled_payload)
        
        return {
            "status": "sent_to_holded",
            "holded_document_id": holled_response["id"],
            "holded_url": holled_response["url"]
        }
    except Exception as e:
        logger.error(f"Holded export failed: {e}")
        return {"status": "holded_failed", "error": str(e)}
```

## Data Transformation

**Pricing Output → Holded Items**:
```python
def convert_estimate_to_holded_format(pricing_result: dict, client_id: str) -> dict:
    """Transform pricing_agent output to Holded API format"""
    
    items = []
    for component in pricing_result["items"]:
        items.append({
            "name": f"{component['tipo']} {component['material']} ({component['acabado']})",
            "description": f"{component['dimensiones']} - Material + Labor",
            "quantity": component["cantidad"],
            "unitPrice": component["subtotal"],
            "tax": 21,  # Spain default, make configurable per client if needed
            "reference": f"{component['material']}_{component['tipo']}_v1"
        })
    
    return {
        "contactId": get_holded_contact_id(client_id),  # Lookup in DB
        "date": int(time.time()),
        "subject": f"Presupuesto - {client_id}",
        "notes": "Generado por Carpintería AI",
        "items": items
    }
```

## Contact Management

Holded requires a `contactId`. Map internal client IDs to Holded contact IDs:

**Lookup Strategy**:
1. Query local DB (api/schemas/) for client → holded_contact_id mapping
2. Cache mappings to avoid repeated API calls
3. Fallback: Create new contact in Holded if needed (requires Holded create endpoint)

```python
def get_holded_contact_id(client_id: str) -> str:
    """Map internal client_id to Holded contactId"""
    # Implement mapping in DB or config
    contact_map = {
        "acme_inc": "123456",
        "xyz_corp": "789012"
    }
    return contact_map.get(client_id, "")
```

## Error Handling

**Common Errors**:
- `401 Unauthorized`: HOLDED_API_KEY invalid or expired
- `404 Not Found`: contactId doesn't exist in Holded
- `400 Bad Request`: Payload format error (missing required field)
- `429 Too Many Requests`: Rate limiting (retry with backoff)

```python
try:
    response = await holded_client.post(...)
except HTTPStatusError as e:
    if e.response.status_code == 401:
        logger.error("Holded authentication failed")
    elif e.response.status_code == 404:
        logger.error(f"Holded contact {contactId} not found")
    else:
        logger.error(f"Holded API error: {e.response.text}")
```

## Integration Points

**Input:** pricing_result (from pricing_agent) in workflow state

**Output:** holded_document_id stored in workflow state, workflow continues to notify_team

**External:** Holded API (requires HOLDED_API_KEY env var)

**Related:** Client contact mapping (should be in local DB, not hardcoded)

## Common Tasks

**Test Holded Export** (requires real API key or mock)
```bash
pytest tests/test_holded_integration.py -v
# Use mocked responses to avoid real API calls in CI
```

**Create New Client in Holded**
```python
# Use Holded contacts API (POST /api/invoicing/v1/contacts)
# Store mapping in local DB for future lookups
```

**Debug Holded Payload**
```python
# Log the full JSON before POST
import json
logger.debug(json.dumps(holded_payload, indent=2))
```

**Handle Client Tax Variations**
- Store client-specific tax rates in DB
- Use during payload construction, don't hardcode 21%
- Fallback to 21% (Spain standard) if not specified

## Dependencies
- httpx (async HTTP client)
- pydantic (validation)
- python-dotenv (HOLDED_API_KEY)
