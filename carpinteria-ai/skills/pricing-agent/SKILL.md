# Pricing Agent Skill

Consults ChromaDB knowledge base to calculate labor + material costs for carpentry components.

## Purpose
Converts vision_agent component JSON into itemized estimate with unit prices and labor hours using RAG lookup.

## Implementation (backend/agents/pricing_agent.py)

### Input (from vision_agent output)
```python
{
  "plano_id": str,
  "componentes": [
    {
      "tipo": str,
      "material": str,
      "acabado": str,
      "ancho_cm": float,
      "largo_cm": float,
      "cantidad": int,
      "notas": str
    }
  ],
  "confidence_score": float,
  "raw_reasoning": str
}
```

### Output
```python
{
  "plano_id": str,
  "items": [
    {
      "componente_id": str,
      "tipo": str,
      "material": str,
      "acabado": str,
      "dimensiones": str,
      "cantidad": int,
      "precio_unitario": float,
      "precio_material": float,
      "horas_labor": float,
      "costo_labor": float,
      "subtotal": float
    }
  ],
  "total_material": float,
  "total_labor": float,
  "grand_total": float,
  "moneda": str  # "EUR" or "USD"
}
```

## Cost Calculation Formula

For each component:
```
precio_unitario = ChromaDB lookup (material × tipo × acabado)
precio_material = precio_unitario × ancho_cm × largo_cm × cantidad
horas_labor = (ancho_cm × largo_cm × cantidad) / labor_rate (from DB)
costo_labor = horas_labor × hourly_rate (from DB)
subtotal = precio_material + costo_labor
```

## ChromaDB Query Pattern

**Metadata filters applied in query:**
```python
{
  "material": component["material"],
  "tipo": component["tipo"],
  "acabado": component["acabado"],
  "cliente": client_id,  # Optional: client-specific pricing
  "version": "active"    # Query only active pricing
}
```

Client-specific pricing overrides default pricing if found.

## Key Patterns

**RAG Integration** (rag/chroma_client.py)
- Query ChromaDB with component metadata
- Returns price and labor rate vectors
- Falls back to default pricing if no match (low confidence)

**Error Handling**
```python
try:
    pricing_data = chroma_client.query_pricing(
        material=tipo,
        acabado=acabado,
        cliente=client_id
    )
    if not pricing_data:
        logger.warning(f"No pricing for {material}/{acabado}, using defaults")
except Exception as e:
    logger.error(f"ChromaDB query failed: {e}")
    raise  # Pricing failure blocks workflow
```

## Integration Points

**Called by:** LangGraph node `rag_pricing` (workflow.py)

**Consumes:** vision_agent output from workflow state

**Produces:** Pricing data → `consolidate` node → workflow state

**External:** ChromaDB service (docker-compose.yml, port 8001)

## Common Tasks

**Test pricing calculation**
```bash
pytest tests/test_pricing_agent.py -v
```

**Add new pricing data to ChromaDB**
```python
from rag.chroma_client import ChromaClient

client = ChromaClient()
client.add_pricing_document(
    material="roble",
    tipo="tablero",
    acabado="natural",
    price_per_sqm=45.50,
    labor_hours_per_sqm=0.3,
    cliente="cliente_default",
    metadata={"version": "active"}
)
```

**Query existing pricing**
```bash
curl -X GET "http://localhost:8001/api/v1/collections"  # ChromaDB API
```

**Update labor rates by client**
- Store in ChromaDB metadata under `cliente` field
- Query with client filter to get client-specific rates
- Document rates in knowledge base (RAG documents)

## Dependencies
- chromadb
- numpy (embeddings)
- langchain (vector store integration)
- pydantic (output validation)
