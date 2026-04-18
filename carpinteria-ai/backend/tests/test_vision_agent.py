import pytest
from unittest.mock import patch, MagicMock
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
    assert result["plano_id"] == "escritorio_001"
    assert len(result["componentes"]) == 1
    assert result["componentes"][0]["tipo"] == "tablero"
    assert result["confidence_score"] == 0.95
    assert "Veo un plano de un escritorio" in result["raw_reasoning"]
    
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

    result = analyze_plan("dummy")
    
    assert result["confidence_score"] == 0.0
    assert result["error"] == "JSON parse error"
    assert result["raw_reasoning"] == "test"
