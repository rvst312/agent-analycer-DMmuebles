# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
Carpintería AI is an automated carpentry estimate system. It uses Claude 3.5 Sonnet + LangGraph to extract specifications from floor plans and compute pricing via a RAG-based knowledge base, with human approval before sending estimates to Holded.

## Architecture

**Two-Agent LangGraph Orchestration**
- `vision_agent`: Analyzes plan images/PDFs using Claude with Chain-of-Thought, outputs JSON of components (dimensions, materials, finishes, hardware)
- `pricing_agent`: Consults ChromaDB with metadata filters, calculates cost using formula: C_total = (A × L × P_unitario) + K_labor

**LangGraph Workflow (backend/graph/workflow.py)**
Sequential nodes: `receive_input` → `vision_analysis` → `extract_entities` → `rag_pricing` → `consolidate` → `human_approval` (interrupt) → `send_to_holded` → `notify_team`

The `human_approval` node uses `interrupt()` to pause execution and save state. The `/resume` endpoint resumes from the checkpoint after frontend approval.

**Backend Stack**
- FastAPI (main.py) with routes in `api/routes/` (estimates, workflow, knowledge)
- PostgreSQL: stores workflow checkpoints (configured via POSTGRES_URL and db/persistence.py)
- ChromaDB: vector DB for RAG pricing lookups (rag/chroma_client.py, rag/embeddings.py)
- Pydantic schemas in `api/schemas/` for request/response validation
- Services layer for external integrations (Holded, n8n, Slack)

**Frontend**
Next.js app (minimal setup, needs package.json and build config). Routes in `frontend/app/`: dashboard, estimates detail, knowledge base. Components in `frontend/components/` for UI (EstimateBreakdown, PriceTable, PlanViewer).

## Development

**Setup**
```bash
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your keys
```

**Common Commands**
```bash
# Backend (from backend/ dir)
uvicorn main:app --reload              # Dev server on :8000
pytest tests/ -v                       # All tests
pytest tests/test_vision_agent.py -v  # Single test file
pytest tests/ -v --cov=agents --cov-fail-under=80  # Coverage check (80% min in agents/)
pytest tests/test_pricing_agent.py::test_pricing_calculation -v  # Single test

# Full stack
cd .. && docker-compose up  # Starts backend, postgres, chromadb

# Frontend (once package.json is set up)
cd frontend && npm run dev
```

**Required Environment Variables** (.env)
```
ANTHROPIC_API_KEY=<your-key>
POSTGRES_URL=postgresql://user:password@localhost:5432/carpinteria
CHROMA_PERSIST_PATH=./chroma_data
HOLDED_API_KEY=<your-key>
N8N_WEBHOOK_URL=<webhook>
SLACK_WEBHOOK_URL=<webhook>
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Code Conventions

**Pydantic Models**
- All agent input/output schemas use Pydantic (api/schemas/)
- Schemas validate both directions (request → node → response)

**Claude Integration**
- JSON responses parsed with `json.loads()` in try/except blocks
- Detailed error logging on parse failure
- Prompts stored as constants (agents/prompts.py expected, use XML tags: `<instructions>`, `<input_data>`, `<output_format>`)

**LangGraph Nodes**
- Each node has try/except, updates `status` field before propagating errors
- State is GraphState (TypedDict in workflow.py)

**Testing**
- pytest with ≥80% coverage in `agents/` and `graph/`
- Use fixtures for mocking Claude/ChromaDB responses

## API Reference

**vision_agent Output Schema**
```json
{
  "plano_id": "string",
  "componentes": [
    {
      "tipo": "tablero | puerta | cajon | herraje | barra",
      "material": "string",
      "acabado": "string",
      "ancho_cm": 0.0,
      "largo_cm": 0.0,
      "cantidad": 1,
      "notas": "string"
    }
  ],
  "confidence_score": 0.0,
  "raw_reasoning": "string"
}
```

**Holded API (POST /invoicing/v1/documents/estimate)**
```json
{
  "contactId": "string",
  "date": "UNIX timestamp",
  "items": [
    {
      "name": "string",
      "units": 0.0,
      "subtotal": 0.0,
      "tax": 21
    }
  ]
}
```

## Key Files
- `backend/main.py` – FastAPI entry point
- `backend/graph/workflow.py` – LangGraph orchestration
- `backend/agents/{vision,pricing}_agent.py` – Agent implementations
- `backend/rag/chroma_client.py` – Vector DB access
- `backend/db/persistence.py` – Workflow checkpointing
