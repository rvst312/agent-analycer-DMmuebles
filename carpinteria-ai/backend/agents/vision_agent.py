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


SYSTEM_PROMPT = """Eres un experto analista de planos técnicos de carpintería a medida (armarios, muebles de cocina, vestidores).

Los planos que recibes son planos de despiece con múltiples ALZADOS o VISTAS. Cada alzado tiene un CÓDIGO DE VISTA —etiqueta alfanumérica (A01, A02, B01, etc.)— situado en la parte superior de cada sección del dibujo.

Tu objetivo: extraer cada componente con sus dimensiones, material, acabado y el código de vista al que pertenece.
"""


def _detect_view_codes(
    client: anthropic.Anthropic,
    image_base64: str,
    media_type: str,
    plano_id: str,
) -> List[str]:
    """
    Primera pasada: extrae SOLO los códigos de vista del plano.
    Tarea única y simple para maximizar precisión.
    """
    prompt = """Mira este plano técnico de carpintería.

Busca los CÓDIGOS DE REFERENCIA de cada armario o sección. Aparecen de dos formas:
1. Al final del título de sección, tras un guión: "ARMARIO DORMITORIO 1 — A03"  →  código: A03
2. Como etiqueta corta directamente sobre una vista: "A05", "A06"

El formato es siempre: una letra mayúscula seguida de dos dígitos (A03, A04, A05, A06...).

Devuelve ÚNICAMENTE los códigos encontrados, separados por comas, sin ningún otro texto.
Ejemplo de respuesta válida: A03,A04,A05,A06

Si no encuentras ninguno, responde exactamente: NINGUNO"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=128,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": image_base64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        raw = response.content[0].text.strip() if response.content else ""
        logger.info(f"[PASS-1] Respuesta códigos de vista para plano {plano_id!r}: {raw!r}")

        if not raw or raw.upper() == "NINGUNO":
            return []

        # Limpiar y normalizar: quitar espacios, split por coma
        codes = [c.strip() for c in raw.split(",") if c.strip()]
        return codes

    except Exception as e:
        logger.warning(f"[PASS-1] Error detectando códigos de vista: {e}")
        return []


def _build_examples_section(examples: List[List[Dict[str, Any]]]) -> str:
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
    Analiza una imagen de plano carpintería en dos pasadas:
      1. Detecta los códigos de vista (A01, B02…) del plano.
      2. Extrae componentes asignando cada uno a su código de vista.
    """
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

    # ── PASADA 1: detectar códigos de vista ──────────────────────────────────
    view_codes = _detect_view_codes(client, image_base64, media_type, plano_id)

    if view_codes:
        codes_context = (
            f"Los códigos de vista que hay en este plano son: {', '.join(view_codes)}.\n"
            f"Asigna exactamente uno de estos códigos en el campo \"ref\" de cada componente "
            f"según la sección del plano donde está dibujado."
        )
        ref_rule = f"uno de: {', '.join(view_codes)}"
    else:
        codes_context = "No se han detectado códigos de vista en el plano. Usa \"SIN-REF\" en todos los componentes."
        ref_rule = "SIN-REF"

    # ── PASADA 2: extraer componentes ────────────────────────────────────────
    examples_block = _build_examples_section(few_shot_examples or [])

    prompt_content = f"""
<instructions>
{codes_context}

Extrae todos los componentes del plano con el siguiente JSON estricto dentro de <output_format>:
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
      "notas": "string (máx. 10 palabras)",
      "ref": "{ref_rule}"
    }}
  ],
  "confidence_score": 0.9
}}

Antes del JSON, en <raw_reasoning> describe brevemente qué ves en cada sección (máx. 80 palabras).

REGLAS JSON CRÍTICAS:
- "ancho_cm", "largo_cm", "cantidad" → SIEMPRE número. Si no sabes: 0.0 o 1.
- "ref" → solo el código exacto ({ref_rule}). Sin texto adicional.
- "material", "acabado", "notas" → MUY CORTOS o el JSON se trunca.
- Nada fuera de <raw_reasoning> y <output_format>.
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
                        {"type": "text", "text": prompt_content},
                    ],
                }
            ],
        )

        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text += block.text

        logger.debug(f"[PASS-2] Respuesta completa plano {plano_id!r}:\n{response_text[:1000]}")

        raw_reasoning = ""
        if "<raw_reasoning>" in response_text and "</raw_reasoning>" in response_text:
            raw_reasoning = response_text.split("<raw_reasoning>")[1].split("</raw_reasoning>")[0].strip()

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
            result = _repair_truncated_json(json_content, plano_id, e)

        result["plano_id"] = plano_id
        result["raw_reasoning"] = raw_reasoning

        try:
            model = PlanoAnalizado(**result)
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
        return PlanoAnalizado(plano_id=plano_id, componentes=[], confidence_score=0.0, raw_reasoning="", error=f"API Timeout: {str(e)}")
    except anthropic.APIStatusError as e:
        _log_error(plano_id, "AnthropicAPIStatusError", f"Status code: {e.status_code}, Message: {str(e)}")
        return PlanoAnalizado(plano_id=plano_id, componentes=[], confidence_score=0.0, raw_reasoning="", error=f"API Status Error: {str(e)}")
    except Exception as e:
        _log_error(plano_id, "AnthropicGeneralError", e)
        return PlanoAnalizado(plano_id=plano_id, componentes=[], confidence_score=0.0, raw_reasoning="", error=str(e))
