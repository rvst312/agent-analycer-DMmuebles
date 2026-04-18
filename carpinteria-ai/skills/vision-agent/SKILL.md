# Vision Agent Skill

Analyzes floor plans (images/PDFs) using Claude 3.5 Sonnet to extract carpentry specifications.

## Purpose
Processes architectural documents and outputs structured JSON with component specifications: dimensions, materials, finishes, hardware types.

## Implementation (backend/agents/vision_agent.py)

### Input
```python
{
  "plan_image": bytes,  # Image or PDF content
  "client_id": str,     # For context in prompts
  "notes": str          # Additional instructions (optional)
}
```

### Output (Pydantic model)
```python
{
  "plano_id": str,
  "componentes": [
    {
      "tipo": str,      # "tablero" | "puerta" | "cajon" | "herraje" | "barra"
      "material": str,
      "acabado": str,
      "ancho_cm": float,
      "largo_cm": float,
      "cantidad": int,
      "notas": str
    }
  ],
  "confidence_score": float,  # 0.0-1.0, higher = more confident
  "raw_reasoning": str        # Claude's chain-of-thought
}
```

## Key Patterns

**Claude Call with Chain-of-Thought**
- Always use Claude 3.5 Sonnet (langchain-anthropic integration)
- Include `<instructions>`, `<input_data>`, `<output_format>` XML tags in prompts
- Enable extended thinking for complex plans
- Parse response with `json.loads()` in try/except, log parse errors

**Error Handling**
```python
try:
    response = claude.parse_image_and_extract_json(...)
    result = json.loads(response)
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse vision_agent output: {e}")
    # Return fallback with confidence_score=0.0
except Exception as e:
    logger.error(f"Vision analysis failed: {e}")
    raise
```

## Integration Points

**Called by:** LangGraph node `vision_analysis` (workflow.py)

**Consumes:** Plan images (from `/estimates` endpoint)

**Produces:** Component JSON fed to `pricing_agent`

**Stores:** Raw output in workflow state for audit trail

## Common Tasks

**Test vision output parsing**
```bash
pytest tests/test_vision_agent.py -v
```

**Add a new component type**
- Update the `tipo` enum in output schema (api/schemas/estimate.py)
- Update Claude prompt in agents/prompts.py with example
- Add test case in tests/test_vision_agent.py

**Improve confidence scoring**
- Confidence reflects JSON parse success + component coverage (each extracted dimension)
- Low confidence (< 0.5) triggers human review in workflow

## Dependencies
- langchain-anthropic
- anthropic SDK (Claude 3.5 Sonnet)
- pdf2image (for PDF handling)
- base64 (for image encoding)
