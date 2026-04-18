# Testing Skill

Patterns and utilities for testing the Carpintería AI system with pytest.

## Test Structure

```
backend/tests/
├── test_vision_agent.py       # vision_agent mocking/parsing
├── test_pricing_agent.py      # pricing calculation with RAG mocks
├── test_workflow.py           # Full workflow orchestration
├── conftest.py               # Shared fixtures (optional)
└── fixtures/
    ├── sample_plans/         # Sample images for vision tests
    └── pricing_data.json     # Mock ChromaDB data
```

## Coverage Requirements

Minimum **80% coverage** in:
- `agents/` (vision_agent.py, pricing_agent.py)
- `graph/` (workflow.py)

Run coverage check:
```bash
pytest tests/ -v --cov=agents --cov=graph --cov-fail-under=80
```

## Common Fixtures

**Mock Claude Response**
```python
import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def mock_claude_vision():
    """Mock Claude 3.5 Sonnet vision response"""
    return {
        "plano_id": "test_plan_001",
        "componentes": [
            {
                "tipo": "tablero",
                "material": "roble",
                "acabado": "natural",
                "ancho_cm": 100.0,
                "largo_cm": 50.0,
                "cantidad": 2,
                "notas": "Test component"
            }
        ],
        "confidence_score": 0.95,
        "raw_reasoning": "Extracted from floor plan..."
    }

@pytest.fixture
def mock_vision_agent(mock_claude_vision):
    with patch('agents.vision_agent.claude_client') as mock:
        mock.parse_and_extract_json.return_value = mock_claude_vision
        yield mock
```

**Mock ChromaDB**
```python
@pytest.fixture
def mock_chroma_client():
    """Mock ChromaDB queries for pricing"""
    with patch('rag.chroma_client.ChromaClient') as mock:
        mock.query.return_value = {
            "metadata": {
                "price_per_sqm": 45.50,
                "labor_hours_per_sqm": 0.3
            },
            "distance": 0.05
        }
        yield mock
```

**Mock Holded API**
```python
@pytest.fixture
def mock_holded_api():
    """Mock Holded POST response"""
    with patch('services.holded_service.HolledService.create_estimate') as mock:
        mock.return_value = {
            "id": "est_mock_123",
            "number": "EST-2025-001",
            "status": "draft",
            "url": "https://app.holded.com/documents/est_mock_123"
        }
        yield mock
```

## Unit Test Patterns

**Test vision_agent JSON Parsing**
```python
def test_vision_agent_parses_valid_json(mock_vision_agent, mock_claude_vision):
    from agents.vision_agent import analyze_plan
    
    result = analyze_plan(
        plan_image=b"fake_image_bytes",
        client_id="test_client"
    )
    
    assert result["plano_id"] == "test_plan_001"
    assert len(result["componentes"]) == 1
    assert result["componentes"][0]["tipo"] == "tablero"
    assert result["confidence_score"] == 0.95
```

**Test pricing Calculation**
```python
def test_pricing_agent_calculates_totals(mock_chroma_client):
    from agents.pricing_agent import calculate_pricing
    
    vision_result = {
        "plano_id": "test_plan_001",
        "componentes": [
            {
                "tipo": "tablero",
                "material": "roble",
                "acabado": "natural",
                "ancho_cm": 100.0,
                "largo_cm": 50.0,
                "cantidad": 1
            }
        ]
    }
    
    result = calculate_pricing(vision_result)
    
    expected_sqm = 5.0  # 100 * 50 / 1000
    expected_material = 45.50 * expected_sqm  # 227.50
    expected_labor = 0.3 * expected_sqm * 25  # $37.50 (assuming $25/hr)
    
    assert result["items"][0]["precio_material"] == pytest.approx(227.50, rel=0.01)
    assert result["total_material"] > 0
    assert result["grand_total"] > 0
```

**Test Workflow Orchestration**
```python
def test_workflow_full_pipeline(mock_vision_agent, mock_chroma_client, mock_holded_api):
    from graph.workflow import app_workflow
    
    initial_state = {
        "input_data": {
            "client_id": "test_client",
            "plan": b"fake_plan"
        },
        "status": "initialized"
    }
    
    result = app_workflow.invoke(initial_state)
    
    assert result["status"] == "pending_approval"  # Pauses at human_approval
    assert "vision_result" in result
    assert "pricing_result" in result
    assert result["estimate_id"] is not None
```

## Integration Test Patterns

**Test with Real ChromaDB** (requires docker-compose up)
```python
def test_pricing_with_real_chroma():
    """Integration test hitting actual ChromaDB"""
    from rag.chroma_client import ChromaClient
    import os
    
    if not os.getenv("RUN_INTEGRATION_TESTS"):
        pytest.skip("Integration tests disabled")
    
    client = ChromaClient(host="localhost", port=8001)
    result = client.query(
        collection="pricing_materials",
        filters={"material": "roble", "tipo": "tablero"}
    )
    
    assert len(result) > 0
    assert "metadata" in result[0]
```

**Test Workflow Resumption** (human_approval → /resume)
```python
@pytest.mark.asyncio
async def test_workflow_resume_from_approval(mock_vision_agent, mock_chroma_client, mock_holded_api):
    from api.routes.workflow import resume_workflow
    
    # Run workflow to approval
    initial_state = {...}
    # Get checkpoint ID from workflow state
    
    # Call resume with approval
    result = await resume_workflow(
        estimate_id="est_123",
        approved=True,
        notes="Looks good, send it!"
    )
    
    assert result["status"] == "completed"
    assert result["holded_document_id"] is not None
```

## Error Case Testing

**Test Vision Failure (JSON parse error)**
```python
def test_vision_agent_handles_parse_error(mock_claude_vision):
    with patch('agents.vision_agent.json.loads', side_effect=json.JSONDecodeError(...)):
        result = analyze_plan(b"fake_image")
        
        assert result["confidence_score"] == 0.0
        assert "error" in result
```

**Test Missing ChromaDB Data**
```python
def test_pricing_uses_default_when_no_match(mock_chroma_client):
    mock_chroma_client.query.return_value = None
    
    result = calculate_pricing(vision_result)
    
    # Should use fallback pricing, not crash
    assert result["grand_total"] > 0
    assert "warning_no_match" in result or result["confidence"] < 1.0
```

**Test Holled API Failure**
```python
def test_workflow_handles_holded_failure(mock_vision_agent, mock_chroma_client):
    with patch('services.holded_service.HolledService.create_estimate', 
               side_effect=Exception("Holled 500 error")):
        
        result = app_workflow.invoke(initial_state)
        
        assert result["status"] == "holded_failed"
        assert "error" in result
```

## Running Tests

**All tests**
```bash
pytest tests/ -v
```

**Single file**
```bash
pytest tests/test_vision_agent.py -v
```

**Single test**
```bash
pytest tests/test_pricing_agent.py::test_pricing_calculates_totals -v
```

**With coverage**
```bash
pytest tests/ -v --cov=agents --cov=graph --cov-report=html
# Open htmlcov/index.html to view coverage report
```

**Markers** (if defined):
```bash
pytest -m integration -v  # Run integration tests only
pytest -m "not integration" -v  # Skip integration tests
```

## Test Data Management

**Sample Plans**
Store small test images/PDFs in `tests/fixtures/sample_plans/`:
- `simple_square.pdf` – Single 100x100 component
- `complex_cabinet.pdf` – Multi-component cabinet
- `unclear_plan.pdf` – Low confidence (tests fallback)

**Mock Pricing Data** (tests/fixtures/pricing_data.json):
```json
{
  "materials": [
    {
      "id": "roble_tablero_natural",
      "material": "roble",
      "tipo": "tablero",
      "acabado": "natural",
      "price_per_sqm": 45.50,
      "labor_hours_per_sqm": 0.3
    }
  ]
}
```

**Seed ChromaDB** (for integration tests):
```python
# tests/conftest.py (optional)
@pytest.fixture(scope="session", autouse=True)
def seed_chroma():
    if os.getenv("RUN_INTEGRATION_TESTS"):
        from rag.chroma_client import ChromaClient
        client = ChromaClient()
        client.add_documents(...)
```

## Dependencies
- pytest
- pytest-asyncio (async test support)
- pytest-cov (coverage)
- unittest.mock (built-in)
- httpx (for mocking HTTP)
