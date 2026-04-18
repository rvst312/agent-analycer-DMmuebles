# RAG Skill

Manages vector embeddings and ChromaDB retrieval for pricing lookups.

## Purpose
Stores and queries carpentry pricing data (materials, labor rates, finishes) as vectors. pricing_agent uses RAG to find matching prices without hardcoding them.

## Components

### ChromaDB Client (backend/rag/chroma_client.py)
Wraps ChromaDB HTTP API for embedding and retrieval.

```python
from rag.chroma_client import ChromaClient

client = ChromaClient(
    host="localhost",
    port=8001,
    persist_path="./chroma_data"
)

# Collections partition pricing by category
# "pricing_materials", "pricing_labor", "pricing_finishes"
```

### Embeddings Generator (backend/rag/embeddings.py)
Creates vector representations of pricing documents.

```python
from rag.embeddings import EmbeddingModel

embedder = EmbeddingModel()
embedding = embedder.embed("roble material for furniture")
# Returns: [0.123, -0.456, ...]
```

## Data Model

**Pricing Document Structure**
```json
{
  "id": "pricing_roble_tablero_natural_v1",
  "text": "Roble tablero acabado natural, precio 45.50 EUR/m2, labor 0.3h/m2",
  "metadata": {
    "material": "roble",
    "tipo": "tablero",
    "acabado": "natural",
    "price_per_sqm": 45.50,
    "labor_hours_per_sqm": 0.3,
    "currency": "EUR",
    "cliente": "default",
    "version": "active",
    "effective_date": "2025-01-01"
  }
}
```

Metadata filters enable precise queries without vector search alone.

## Common Operations

**Initialize ChromaDB Collection**
```python
from rag.chroma_client import ChromaClient

client = ChromaClient()

# Create collection
client.create_collection("pricing_materials")

# Add pricing documents
client.add_documents(
    collection="pricing_materials",
    documents=[
        {
            "id": "roble_1",
            "text": "Roble tablero acabado natural",
            "metadata": {
                "material": "roble",
                "tipo": "tablero",
                "acabado": "natural",
                "price_per_sqm": 45.50,
                "labor_hours_per_sqm": 0.3
            }
        },
        # ... more documents
    ]
)
```

**Query Pricing with Metadata Filters**
```python
results = client.query(
    collection="pricing_materials",
    query_text="roble tablero natural",
    filters={
        "material": "roble",
        "tipo": "tablero",
        "acabado": "natural",
        "cliente": "acme_inc",  # Client-specific override
        "version": "active"
    },
    top_k=1  # Return best match
)
# results[0] = {"id": "...", "metadata": {...}, "distance": 0.05}
```

**Add Client-Specific Pricing**
```python
client.add_documents(
    collection="pricing_materials",
    documents=[{
        "id": "roble_acme_override",
        "text": "Roble tablero acabado natural for ACME special rate",
        "metadata": {
            "material": "roble",
            "tipo": "tablero",
            "acabado": "natural",
            "price_per_sqm": 40.00,  # Override default 45.50
            "labor_hours_per_sqm": 0.25,
            "cliente": "acme_inc",  # Specific to ACME
            "version": "active"
        }
    }]
)
# Query will find this when cliente="acme_inc"
```

## ChromaDB Service

**Docker Setup** (docker-compose.yml)
```yaml
chroma:
  image: chromadb/chroma:latest
  ports:
    - "8001:8000"
```

**Health Check**
```bash
curl http://localhost:8001/api/v1/heartbeat
# Response: {"heartbeat": 5}
```

**Collections API**
```bash
curl http://localhost:8001/api/v1/collections
# Lists all collections
```

## Query Precedence

1. **Metadata filter match** (material + tipo + acabado + cliente)
2. **Vector similarity** (if metadata alone insufficient)
3. **Default pricing** (fallback, logged as warning)

Client filters (`cliente="acme_inc"`) override generic (`cliente="default"`).

## Integration with pricing_agent

pricing_agent calls ChromaDB for each component:
```python
def calculate(vision_result, client_id="default"):
    for comp in vision_result["componentes"]:
        pricing_data = chroma_client.query(
            filters={
                "material": comp["material"],
                "tipo": comp["tipo"],
                "acabado": comp["acabado"],
                "cliente": client_id,
                "version": "active"
            }
        )
        # Extract price and labor from pricing_data
```

## Common Tasks

**Bulk Import Pricing from CSV**
```python
import csv
from rag.chroma_client import ChromaClient

client = ChromaClient()
documents = []

with open("pricing_catalog.csv") as f:
    for row in csv.DictReader(f):
        documents.append({
            "id": f"{row['material']}_{row['tipo']}_{row['acabado']}",
            "text": f"{row['material']} {row['tipo']} {row['acabado']}",
            "metadata": {
                "material": row["material"],
                "tipo": row["tipo"],
                "acabado": row["acabado"],
                "price_per_sqm": float(row["price"]),
                "labor_hours_per_sqm": float(row["labor_hours"]),
                "cliente": "default",
                "version": "active"
            }
        })

client.add_documents(collection="pricing_materials", documents=documents)
```

**Update Pricing Version**
Mark old pricing inactive and add new version:
```python
# New documents with version="active"
# Old documents keep version="inactive" (or delete if no audit needed)
```

**Test RAG Queries**
```bash
pytest tests/test_rag.py -v  # If test file exists
```

## Dependencies
- chromadb
- sentence-transformers (or OpenAI embeddings if configured)
- numpy
- requests (HTTP to ChromaDB)
