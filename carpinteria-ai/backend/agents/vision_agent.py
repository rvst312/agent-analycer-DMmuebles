import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import anthropic
from api.schemas.estimate import (
    AnalisisArmario, ComponenteArmario, ItemInteriorArmario,
    ModuloArmario, PlanoAnalizado, PuertaArmario, TipoComponente,
)

logger = logging.getLogger(__name__)

PLAN_TYPES = {"armario", "puerta_paso", "rodapie", "mueble_banio", "panelado", "mueble_general"}


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


def _extract_json_block(response_text: str) -> str:
    """Extract JSON from <output_format> tags or fall back to first {} block."""
    if "<output_format>" in response_text and "</output_format>" in response_text:
        block = response_text.split("<output_format>")[1].split("</output_format>")[0].strip()
    else:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        block = response_text[start:end] if start != -1 else ""
    if block.startswith("```json"):
        block = block[7:]
    if block.endswith("```"):
        block = block[:-3]
    return block.strip()


SYSTEM_PROMPT = """Eres un experto analista de planos técnicos de carpintería a medida (armarios, muebles de cocina, vestidores).

Los planos que recibes son planos de despiece con múltiples ALZADOS o VISTAS. Cada alzado tiene un CÓDIGO DE VISTA —etiqueta alfanumérica (A01, A02, B01, etc.)— situado en la parte superior de cada sección del dibujo.

Tu objetivo: extraer cada componente con sus dimensiones, material, acabado y el código de vista al que pertenece.
"""


def _make_file_block(image_base64: str, media_type: str) -> dict:
    """Returns the correct API content block for images or PDFs."""
    if media_type == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": image_base64},
        }
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": image_base64},
    }


def _detect_view_codes(
    client: anthropic.Anthropic,
    image_base64: str,
    media_type: str,
    plano_id: str,
) -> List[str]:
    """Primera pasada: extrae SOLO los códigos de vista del plano."""
    pdf_ctx = "Este archivo PDF puede tener VARIAS PÁGINAS. Revisa TODAS las páginas antes de responder.\n\n" if media_type == "application/pdf" else ""

    prompt = f"""{pdf_ctx}Mira este plano técnico de carpintería.

Busca los CÓDIGOS DE REFERENCIA de cada armario, mueble o sección. Pueden aparecer en cualquier parte del plano:
1. Al final del título de sección: "ARMARIO DORMITORIO 1 — A03"  →  código: A03
2. Como etiqueta corta sobre un alzado: "A05", "B02"
3. En el cajetín o leyenda del plano
4. Sobre o junto a la propia vista dibujada

El formato más habitual es letra(s) mayúscula(s) seguida de número(s), pero acepta cualquier variante que identifique claramente una vista o mueble: A03, A-03, B01, C02, ARM-1, VEST2, etc.

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
                    _make_file_block(image_base64, media_type),
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        raw = response.content[0].text.strip() if response.content else ""
        logger.info(f"[PASS-1] Códigos de vista para plano {plano_id!r}: {raw!r}")

        if not raw or raw.upper() == "NINGUNO":
            return []
        return [c.strip() for c in raw.split(",") if c.strip()]

    except Exception as e:
        logger.warning(f"[PASS-1] Error detectando códigos de vista: {e}")
        return []


_TYPE_INSTRUCTIONS: dict = {
    "puerta_paso": """\
TIPO: Puertas de paso. Para cada puerta extrae:
- tipo de hoja: "blindada" | "hueca" | "maciza" | "vidriada"
- material y acabado de hoja y marco
- ancho_cm × largo_cm (largo_cm = altura de la puerta)
- herrajes (manilla, cerradura, bisagras) como componentes tipo="herraje"
- premarco o marco como tipo="otro" con notas="premarco" o "marco"
- cantidad por estancia si hay varias""",

    "rodapie": """\
TIPO: Rodapiés. Para cada zona/estancia extrae:
- tipo="tablero" con material y acabado del rodapié
- ancho_cm = altura del rodapié en cm (ej: 10cm)
- largo_cm = metros lineales × 100 (ej: 5,2m → 520cm)
- notas = nombre de la estancia o zona""",

    "mueble_banio": """\
TIPO: Muebles de baño. Extrae cada pieza por separado:
- mueble bajo / módulo: tipo="tablero" con sus dimensiones
- encimera / lavabo integrado: tipo="tablero", notas="encimera"
- espejo o botiquín: tipo="otro", notas="espejo" o "botiquín"
- iluminación LED: tipo="herraje", notas="LED"
- acabado y color siempre""",

    "panelado": """\
TIPO: Panelados de pared. Extrae por zona/pared:
- tipo="tablero" con material y acabado del panel
- ancho_cm × largo_cm = dimensiones del panel o superficie total de la zona
- notas = nombre de la pared o zona (ej: "pared norte")""",

    "mueble_general": """\
TIPO: Mueble a medida. Extrae cada módulo o cuerpo por separado:
- baldas como tipo="estante"
- cajones como tipo="cajon"
- puertas como tipo="puerta"
- barras como tipo="barra"
- herrajes como tipo="herraje"
Incluye siempre dimensiones y acabado.""",
}


def _classify_plan_type(
    client: anthropic.Anthropic,
    image_base64: str,
    media_type: str,
    plano_id: str,
) -> str:
    """Segunda pasada: clasifica el tipo de plano."""
    pdf_ctx = "Este PDF puede tener varias páginas. Analiza el contenido general de todas ellas.\n\n" if media_type == "application/pdf" else ""

    prompt = f"""{pdf_ctx}Clasifica este plano técnico de carpintería en UNA de estas categorías:

armario        → armario empotrado, vestidor, armario a medida
puerta_paso    → puertas de paso, puertas interiores
rodapie        → rodapiés, zócalos
mueble_banio   → mueble de baño, lavabo a medida
panelado       → panelados de pared, revestimientos
mueble_general → otros muebles (cocina, librería, TV, etc.)

Responde ÚNICAMENTE con la palabra clave exacta (ej: armario), sin texto adicional."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=32,
            messages=[{
                "role": "user",
                "content": [
                    _make_file_block(image_base64, media_type),
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        raw = response.content[0].text.strip().lower() if response.content else ""
        tipo = raw if raw in PLAN_TYPES else "mueble_general"
        logger.info(f"[PASS-2] Tipo de plano para {plano_id!r}: {tipo!r} (raw={raw!r})")
        return tipo

    except Exception as e:
        logger.warning(f"[PASS-2] Error clasificando plano: {e}")
        return "mueble_general"


def _analyze_armario_plan(
    client: anthropic.Anthropic,
    image_base64: str,
    media_type: str,
    view_codes: List[str],
    plano_id: str,
    few_shot_examples: Optional[List] = None,
) -> PlanoAnalizado:
    """Pasada específica para planos de armario: extrae módulos, puertas e items interiores."""

    if view_codes:
        codes_ctx = (
            f"Las referencias de armario en este plano son: {', '.join(view_codes)}.\n"
            "Analiza CADA referencia por separado."
        )
    else:
        codes_ctx = "No se detectaron referencias. Analiza todo el plano como un único armario con ref 'SIN-REF'."

    pdf_ctx = (
        "IMPORTANTE: Este PDF tiene varias páginas. Analiza TODAS las páginas "
        "y extrae los armarios de cada una.\n\n"
    ) if media_type == "application/pdf" else ""

    prompt = f"""<instructions>
{pdf_ctx}{codes_ctx}

Para CADA referencia/armario extrae en JSON dentro de <output_format>:
{{
  "tipo_plano": "armario",
  "armarios": [
    {{
      "ref": "A01",
      "modulos": [
        {{
          "tipo": "ropa larga",
          "ancho_cm": 60.0,
          "alto_cm": 240.0,
          "fondo_cm": 60.0,
          "cantidad": 1,
          "notas": ""
        }}
      ],
      "puertas": [
        {{
          "tipo": "corredera",
          "ancho_cm": 120.0,
          "alto_cm": 240.0,
          "acabado": "blanco mate",
          "cantidad": 1,
          "notas": ""
        }}
      ],
      "items_interiores": [
        {{"tipo": "cajón suave cierre", "cantidad": 3, "notas": ""}},
        {{"tipo": "barra perchero", "cantidad": 1, "notas": ""}}
      ]
    }}
  ],
  "confidence_score": 0.9
}}

REGLAS:
- "modulos": las partes del cuerpo del armario (ropa larga, zapatero, rinconero, baldas, cajones integrados…). Incluye SIEMPRE ancho y alto en cm.
- "puertas": todas las puertas visibles. Incluye tipo (corredera/abatible/batiente), dimensiones y acabado.
- "items_interiores": accesorios (cajón, barra, LED, espejo, bandeja, zapatero extraíble…). Si no hay, lista vacía.
- Dimensiones SIEMPRE como número. Si no se ve claramente: 0.0.
- "notas" → máx. 5 palabras o cadena vacía.
- Nada fuera de <raw_reasoning> y <output_format>.

Antes del JSON escribe en <raw_reasoning> qué ves en cada sección (máx. 60 palabras).
</instructions>
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    _make_file_block(image_base64, media_type),
                    {"type": "text", "text": prompt},
                ],
            }],
        )

        response_text = "".join(b.text for b in response.content if b.type == "text")
        logger.debug(f"[ARMARIO] Respuesta {plano_id!r}:\n{response_text[:800]}")

        raw_reasoning = ""
        if "<raw_reasoning>" in response_text and "</raw_reasoning>" in response_text:
            raw_reasoning = response_text.split("<raw_reasoning>")[1].split("</raw_reasoning>")[0].strip()

        json_block = _extract_json_block(response_text)

        try:
            data = json.loads(json_block)
        except json.JSONDecodeError as e:
            _log_error(plano_id, "JSONDecodeError_armario", e, raw_text=json_block)
            return PlanoAnalizado(
                plano_id=plano_id, tipo_plano="armario",
                armarios=[], confidence_score=0.0,
                raw_reasoning=raw_reasoning,
                error=f"JSON parse error: {e}"
            )

        armarios_raw = data.get("armarios", [])
        armarios: List[AnalisisArmario] = []
        for a in armarios_raw:
            ref = a.get("ref", "SIN-REF")
            modulos = [
                ModuloArmario(ref=ref, **{k: v for k, v in m.items() if k != "ref"})
                for m in a.get("modulos", [])
            ]
            puertas = [
                PuertaArmario(ref=ref, **{k: v for k, v in p.items() if k != "ref"})
                for p in a.get("puertas", [])
            ]
            items = [
                ItemInteriorArmario(ref=ref, **{k: v for k, v in i.items() if k != "ref"})
                for i in a.get("items_interiores", [])
            ]
            armarios.append(AnalisisArmario(ref=ref, modulos=modulos, puertas=puertas, items_interiores=items))

        logger.info(f"[ARMARIO] {plano_id!r}: {len(armarios)} armarios, "
                    f"{sum(len(a.modulos) for a in armarios)} módulos, "
                    f"{sum(len(a.puertas) for a in armarios)} puertas, "
                    f"{sum(len(a.items_interiores) for a in armarios)} items")

        return PlanoAnalizado(
            plano_id=plano_id,
            tipo_plano="armario",
            armarios=armarios,
            confidence_score=float(data.get("confidence_score", 0.8)),
            raw_reasoning=raw_reasoning,
        )

    except anthropic.APIStatusError as e:
        _log_error(plano_id, "AnthropicAPIStatusError", e)
        return PlanoAnalizado(plano_id=plano_id, tipo_plano="armario", armarios=[], confidence_score=0.0, raw_reasoning="", error=str(e))
    except Exception as e:
        _log_error(plano_id, "AnthropicGeneralError_armario", e)
        return PlanoAnalizado(plano_id=plano_id, tipo_plano="armario", armarios=[], confidence_score=0.0, raw_reasoning="", error=str(e))


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
    file_index: int = 1,
    file_total: int = 1,
) -> PlanoAnalizado:
    """
    Analiza un plano de carpintería en tres pasadas:
      1. Detecta códigos de vista.
      2. Clasifica el tipo de plano (armario vs. otros).
      3a. Si armario: extrae módulos, puertas e items interiores.
      3b. Si otro tipo: extrae componentes genéricos.
    """
    try:
        base64.b64decode(image_base64, validate=True)
    except Exception as e:
        _log_error(plano_id, "CorruptImageError", e)
        return PlanoAnalizado(
            plano_id=plano_id, componentes=[], confidence_score=0.0,
            raw_reasoning="", error=f"Corrupt or invalid base64: {str(e)}"
        )

    client = anthropic.Anthropic()

    # ── PASADA 1: códigos de vista ────────────────────────────────────────────
    view_codes = _detect_view_codes(client, image_base64, media_type, plano_id)

    # ── PASADA 2: clasificar tipo de plano ────────────────────────────────────
    tipo_plano = _classify_plan_type(client, image_base64, media_type, plano_id)

    # ── PASADA 3: extracción específica ───────────────────────────────────────
    if tipo_plano == "armario":
        return _analyze_armario_plan(client, image_base64, media_type, view_codes, plano_id, few_shot_examples)

    # ── PASADA 3 (generic): extracción genérica ───────────────────────────────
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

    examples_block = _build_examples_section(few_shot_examples or [])
    type_instructions = _TYPE_INSTRUCTIONS.get(tipo_plano, _TYPE_INSTRUCTIONS["mueble_general"])

    if media_type == "application/pdf":
        scope_ctx = (
            "IMPORTANTE: Este PDF puede contener VARIAS PÁGINAS/HOJAS. "
            "Analiza CADA PÁGINA por separado y extrae TODOS los componentes visibles en TODAS las hojas. "
            "No omitas ningún mueble ni pieza aunque aparezca en páginas distintas."
        )
    elif file_total > 1:
        scope_ctx = f"Esta es la hoja {file_index} de {file_total}. Extrae todos los componentes visibles en esta imagen."
    else:
        scope_ctx = "Extrae todos los componentes visibles en el plano."

    prompt_content = f"""
<instructions>
{codes_context}

{type_instructions}

{scope_ctx}

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
            messages=[{
                "role": "user",
                "content": [
                    _make_file_block(image_base64, media_type),
                    {"type": "text", "text": prompt_content},
                ],
            }],
        )

        response_text = "".join(b.text for b in response.content if b.type == "text")
        logger.debug(f"[PASS-3] Respuesta {plano_id!r}:\n{response_text[:1000]}")

        raw_reasoning = ""
        if "<raw_reasoning>" in response_text and "</raw_reasoning>" in response_text:
            raw_reasoning = response_text.split("<raw_reasoning>")[1].split("</raw_reasoning>")[0].strip()

        json_block = _extract_json_block(response_text)

        try:
            result = json.loads(json_block)
        except json.JSONDecodeError as e:
            result = _repair_truncated_json(json_block, plano_id, e)

        result["plano_id"] = plano_id
        result["tipo_plano"] = tipo_plano
        result["raw_reasoning"] = raw_reasoning

        try:
            model = PlanoAnalizado(**result)
            return PlanoAnalizado(**json.loads(model.model_dump_json()))
        except Exception as e:
            _log_error(plano_id, "PydanticValidationError", e)
            return PlanoAnalizado(
                plano_id=plano_id, tipo_plano=tipo_plano,
                componentes=[], confidence_score=0.0,
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
