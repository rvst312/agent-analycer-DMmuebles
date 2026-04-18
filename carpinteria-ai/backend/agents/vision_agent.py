import json
import logging
from typing import Dict, Any, Optional
import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un experto analista de planos arquitectónicos de carpintería.
Tu objetivo es extraer información detallada sobre los componentes de madera, herrajes, y dimensiones exactas a partir de imágenes de planos o diagramas.

Sigue las instrucciones cuidadosamente y utiliza el formato especificado.
"""

def analyze_plan(image_base64: str, media_type: str = "image/jpeg", notes: Optional[str] = None) -> Dict[str, Any]:
    """
    Analiza una imagen en base64 usando Claude 3.5 Sonnet y devuelve un diccionario con los componentes.
    """
    client = anthropic.Anthropic()

    prompt_content = f"""
<instructions>
Analiza la imagen proporcionada paso a paso. Primero, utiliza un bloque <raw_reasoning> para razonar sobre lo que ves en el plano: dimensiones, materiales, tipos de componentes y acabados.
Después de tu razonamiento, proporciona estrictamente un bloque JSON dentro de <output_format> con la siguiente estructura:
{{
  "plano_id": "generado_o_extraido",
  "componentes": [
    {{
      "tipo": "tablero|puerta|cajon|herraje|barra",
      "material": "string",
      "acabado": "string",
      "ancho_cm": float,
      "largo_cm": float,
      "cantidad": int,
      "notas": "string"
    }}
  ],
  "confidence_score": float (0.0 a 1.0)
}}
No incluyas texto fuera del bloque <raw_reasoning> y el JSON en <output_format>.
</instructions>

<input_data>
Notas adicionales del cliente: {notes if notes else "Ninguna"}
</input_data>

<output_format>
</output_format>
"""

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096,
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
            logger.error(f"Failed to parse vision_agent output: {e}")
            result = {
                "plano_id": "error",
                "componentes": [],
                "confidence_score": 0.0,
                "error": "JSON parse error"
            }
        
        # Guardar el razonamiento bruto para auditoría en el grafo
        result["raw_reasoning"] = raw_reasoning
        return result

    except Exception as e:
        logger.error(f"Vision analysis failed: {e}")
        return {
            "plano_id": "error",
            "componentes": [],
            "confidence_score": 0.0,
            "raw_reasoning": "",
            "error": str(e)
        }
