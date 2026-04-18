from unittest.mock import MagicMock, patch

import pytest
from agents.vision_agent import analyze_plan


@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_success(mock_anthropic):
    # Setup mock
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = """<raw_reasoning>
Veo un plano de un escritorio. Tiene un tablero principal de 120x60cm de melamina blanca.
También tiene dos cajones.
</raw_reasoning>
<output_format>
{
  "plano_id": "escritorio_001",
  "componentes": [
    {
      "tipo": "tablero",
      "material": "melamina",
      "acabado": "blanco",
      "ancho_cm": 60.0,
      "largo_cm": 120.0,
      "cantidad": 1,
      "notas": "tablero principal"
    }
  ],
  "confidence_score": 0.95
}
</output_format>"""
    mock_response.content = [mock_block]
    mock_client.messages.create.return_value = mock_response

    # Call the function
    dummy_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    result = analyze_plan(dummy_base64)

    # Verify
    assert result.plano_id == "escritorio_001"
    assert len(result.componentes) == 1
    assert result.componentes[0].tipo == "tablero"
    assert result.confidence_score == 0.95
    assert "Veo un plano de un escritorio" in result.raw_reasoning
    
    # Verify the call parameters
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-3-5-sonnet-20241022"
    assert call_kwargs["max_tokens"] == 4096
    assert call_kwargs["system"].startswith("Eres un experto analista")
    
    user_message = call_kwargs["messages"][0]["content"]
    assert user_message[0]["type"] == "image"
    assert user_message[0]["source"]["data"] == dummy_base64
    assert "<instructions>" in user_message[1]["text"]

@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_json_error(mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    # Provide invalid JSON
    mock_block.text = """<raw_reasoning>test</raw_reasoning>
<output_format>
{
  "plano_id": "error",
  invalid json
}
</output_format>"""
    mock_response.content = [mock_block]
    mock_client.messages.create.return_value = mock_response

    dummy_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    result = analyze_plan(dummy_base64)
    
    assert result.confidence_score == 0.0
    assert result.error is not None and "JSON parse error" in result.error
    assert result.raw_reasoning == "test"

@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_pydantic_error(mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    # Provide valid JSON but invalid schema (missing required fields)
    mock_block.text = """<raw_reasoning>test validation</raw_reasoning>
<output_format>
{
  "plano_id": "error",
  "componentes": [
    {
      "tipo": "tablero_invalido"
    }
  ],
  "confidence_score": 0.5
}
</output_format>"""
    mock_response.content = [mock_block]
    mock_client.messages.create.return_value = mock_response

    dummy_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    result = analyze_plan(dummy_base64)
    
    assert result.confidence_score == 0.0
    assert result.error is not None and "Validation error" in result.error
    assert result.raw_reasoning == "test validation"

def test_analyze_plan_corrupt_base64():
    # Provide an invalid base64 string
    invalid_base64 = "not-a-valid-base64-string!@#"
    result = analyze_plan(invalid_base64)
    
    assert result.confidence_score == 0.0
    assert result.error is not None and "Corrupt or invalid base64 image" in result.error

@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_markdown_json(mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    # Provide valid JSON inside markdown block
    mock_block.text = """<raw_reasoning>test markdown json</raw_reasoning>
<output_format>
```json
{
  "plano_id": "test_md",
  "componentes": [],
  "confidence_score": 0.8
}
```
</output_format>"""
    mock_response.content = [mock_block]
    mock_client.messages.create.return_value = mock_response

    dummy_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    result = analyze_plan(dummy_base64)
    
    assert result.plano_id == "test_md"
    assert result.confidence_score == 0.8
    assert result.error is None
    assert result.raw_reasoning == "test markdown json"

@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_missing_tags(mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    # Provide JSON without <output_format> tags
    mock_block.text = """Here is the result:
{
  "plano_id": "test_no_tags",
  "componentes": [],
  "confidence_score": 0.7
}"""
    mock_response.content = [mock_block]
    mock_client.messages.create.return_value = mock_response

    dummy_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    result = analyze_plan(dummy_base64)
    
    assert result.plano_id == "test_no_tags"
    assert result.confidence_score == 0.7
    assert result.error is None
    assert result.raw_reasoning == ""

@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_api_timeout_error(mock_anthropic):
    import anthropic
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    # Simulate APITimeoutError
    request = MagicMock()
    mock_client.messages.create.side_effect = anthropic.APITimeoutError(request=request)

    dummy_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    result = analyze_plan(dummy_base64)
    
    assert result.confidence_score == 0.0
    assert result.error is not None and "API Timeout" in result.error

@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_api_status_error(mock_anthropic):
    import anthropic
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    # Simulate APIStatusError
    response = MagicMock()
    response.status_code = 500
    mock_client.messages.create.side_effect = anthropic.APIStatusError("Internal Server Error", response=response, body=None)

    dummy_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    result = analyze_plan(dummy_base64)
    
    assert result.confidence_score == 0.0
    assert result.error is not None and "API Status Error" in result.error

@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_general_error(mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    # Simulate general Exception
    mock_client.messages.create.side_effect = Exception("Unexpected Error")

    dummy_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    result = analyze_plan(dummy_base64)
    
    assert result.confidence_score == 0.0
    assert result.error is not None and "Unexpected Error" in result.error
