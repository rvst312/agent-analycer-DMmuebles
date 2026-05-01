import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import anthropic
from api.schemas.estimate import (ComponenteArmario, PlanoAnalizado,
                                  TipoComponente)

logger = logging.getLogger(__name__)

def _repair_truncated_json(json_content: str, plano_id: str, original_error: Exception) -> dict:
    """
    Attempts to recover a truncated JSON by finding the last complete component object.
    Iterates backwards through `}` positions and tries closing the array at each one.
    """
    closers = [
        '], "confidence_score": 0.5}',
        '}], "confidence_score": 0.5}',
    ]
    for i in range(len(json_content) - 1, -1, -1):
        if json_content[i] != '}':
            continue
        candidate_base = json_content[:i + 1]
        for closer in closers:
            try:
                result = json.loads(candidate_base + closer)
                logger.warning(f"JSON truncado reparado para plano {plano_id} (recuperados hasta char {i})")
                return result
            except json.JSONDecodeError:
                continue

    _log_error(plano_id, "JSONDecodeError", original_error, raw_text=json_content)
    return {
        "plano_id": plano_id,
        "componentes": [],
        "confidence_score": 0.0,
        "error": f"JSON parse error: {str(original_error)}"
    }

def _log_error(plano_id: str, error_type: str, details: Any, raw_text: Optional[str] = None):
    log_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plano_id": plano_id,
        "error_type": error_type,
        "details": str(details)
    }
    if raw_text:
        log_data["raw_text"] = raw_text
    logger.error(json.dumps(log_data))

SYSTEM_PROMPT = """Eres un experto analista de planos arquitectónicos de carpintería.
Tu objetivo es extraer información detallada sobre los componentes de madera, herrajes, y dimensiones exactas a partir de imágenes de planos o diagramas.

Sigue las instrucciones cuidadosamente y utiliza el formato especificado.
"""


def _build_examples_section(examples: List[List[Dict[str, Any]]]) -> str:
    """Format corrected components as a few-shot block to inject into the prompt."""
    if not examples:
        return ""
    lines = [
        "<learned_examples>",
        "Los siguientes ejemplos muestran cómo se han identificado y corregido componentes en planos anteriores de este cliente.",
        "Usa el mismo vocabulario de materiales, acabados y tipos de componentes:",
        "",
    ]
    for i, comps in enumerate(examples, 1):
        compact = json.dumps(comps, ensure_ascii=False, separators=(",", ":"))
        lines.append(f"<example index=\"{i}\">")
        lines.append(compact)
        lines.append("</example>")
    lines.append("</learned_examples>")
    return "\n".join(lines) + "\n\n"


def analyze_plan(
    image_base64: str,
    media_type: str = "image/jpeg",
    notes: Optional[str] = None,
    plano_id: str = "unknown",
    few_shot_examples: Optional[List[List[Dict[str, Any]]]] = None,
) -> PlanoAnalizado:
    """
    Analiza una imagen en base64 usando Claude 3.5 Sonnet y devuelve el modelo Pydantic PlanoAnalizado con los componentes.
    """
    # Validar imagen base64
    try:
        base64.b64decode(image_base64, validate=True)
    except Exception as e:
        _log_error(plano_id, "CorruptImageError", e)
        return PlanoAnalizado(
            plano_id=plano_id,
            componentes=[],
            confidence_score=0.0,
            raw_reasoning="",
            error=f"Corrupt or invalid base64 image: {str(e)}"
        )

    client = anthropic.Anthropic()

    examples_block = _build_examples_section(few_shot_examples or [])

    prompt_content = f"""
<instructions>
Analiza la imagen proporcionada paso a paso. Primero, utiliza un bloque <raw_reasoning> para razonar sobre lo que ves en el plano: dimensiones, materiales, tipos de componentes y acabados.
MANTÉN EL RAZONAMIENTO MUY BREVE Y CONCISO (máximo 50 palabras).
Después de tu razonamiento, proporciona estrictamente un bloque JSON dentro de <output_format> con la siguiente estructura:
{{
  "plano_id": "generado_o_extraido",
  "componentes": [
    {{
      "tipo": "tablero|puerta|cajon|herraje|barra|estante|armario|otro",
      "material": "string (máx. 4 palabras)",
      "acabado": "string (máx. 4 palabras)",
      "ancho_cm": 0.0,
      "largo_cm": 0.0,
      "cantidad": 1,
      "notas": "string (máx. 10 palabras)"
    }}
  ],
  "confidence_score": 0.9
}}
MUY IMPORTANTE REGLA JSON: Para "ancho_cm", "largo_cm" y "cantidad" debes devolver SIEMPRE un número (ej. 120.5 o 1). ¡NUNCA devuelvas texto sin comillas como la palabra 'variable' porque rompes el JSON! Si no conoces la medida exacta o la cantidad, usa obligatoriamente el número 0.0 o 1.
CRÍTICO: Los campos "material", "acabado" y "notas" deben ser MUY CORTOS (ver límites arriba). Respuestas largas causan truncamiento del JSON y fallo total del análisis.
No incluyas texto fuera del bloque <raw_reasoning> y el JSON en <output_format>.
</instructions>

{examples_block}<input_data>
Notas adicionales del cliente: {notes if notes else "Ninguna"}
</input_data>
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt_content
                        }
                    ],
                }
            ],
        )

        # Extraer el texto de la respuesta
        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text += block.text

        # Extraer raw_reasoning
        raw_reasoning = ""
        if "<raw_reasoning>" in response_text and "</raw_reasoning>" in response_text:
            raw_reasoning = response_text.split("<raw_reasoning>")[1].split("</raw_reasoning>")[0].strip()
        
        # Extraer JSON
        json_content = ""
        if "{" in response_text and "}" in response_text:
            if "<output_format>" in response_text and "</output_format>" in response_text:
                json_content = response_text.split("<output_format>")[1].split("</output_format>")[0].strip()
            
            if json_content.startswith("```json"):
                json_content = json_content[7:]
            if json_content.endswith("```"):
                json_content = json_content[:-3]
            json_content = json_content.strip()
            
            if not json_content:
                start_idx = response_text.find("{")
                end_idx = response_text.rfind("}") + 1
                json_content = response_text[start_idx:end_idx]

        try:
            result = json.loads(json_content)
        except json.JSONDecodeError as e:
            # Intentar reparar un JSON truncado buscando el último objeto completo
            result = _repair_truncated_json(json_content, plano_id, e)

        # Always override Claude's generated plano_id with the actual estimate_id
        # so the DB upsert in consolidation_agent finds the correct record.
        result["plano_id"] = plano_id
        result["raw_reasoning"] = raw_reasoning
        
        # Validar con Pydantic
        try:
            # Convertimos el resultado a diccionario puro para evitar problemas
            # de serialización de Enums (TipoComponente) en LangGraph
            model = PlanoAnalizado(**result)
            # Volvemos a parsear desde json para que los Enums se conviertan a str
            return PlanoAnalizado(**json.loads(model.model_dump_json()))
        except Exception as e:
            _log_error(plano_id, "PydanticValidationError", e)
            return PlanoAnalizado(
                plano_id=plano_id,
                componentes=[],
                confidence_score=0.0,
                raw_reasoning=raw_reasoning,
                error=f"Validation error: {str(e)}"
            )

    except anthropic.APITimeoutError as e:
        _log_error(plano_id, "AnthropicAPITimeoutError", e)
        return PlanoAnalizado(
            plano_id=plano_id,
            componentes=[],
            confidence_score=0.0,
            raw_reasoning="",
            error=f"API Timeout: {str(e)}"
        )
    except anthropic.APIStatusError as e:
        _log_error(plano_id, "AnthropicAPIStatusError", f"Status code: {e.status_code}, Message: {str(e)}")
        return PlanoAnalizado(
            plano_id=plano_id,
            componentes=[],
            confidence_score=0.0,
            raw_reasoning="",
            error=f"API Status Error: {str(e)}"
        )
    except Exception as e:
        _log_error(plano_id, "AnthropicGeneralError", e)
        return PlanoAnalizado(
            plano_id=plano_id,
            componentes=[],
            confidence_score=0.0,
            raw_reasoning="",
            error=str(e)
        )
