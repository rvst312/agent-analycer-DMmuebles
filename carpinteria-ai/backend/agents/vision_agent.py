import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import anthropic
from api.schemas.estimate import (
    AnalisisArmario, ComponenteArmario, ItemInteriorArmario,
    ModuloArmario, PlanoAnalizado, PuertaArmario, TipoComponente,
)

logger = logging.getLogger(__name__)

# Modelos configurables por entorno. VISION_MODEL hace la lectura fina del plano
# (pasada de partidas y la legacy de armario); VISION_FAST_MODEL, las pasadas
# cortas y baratas (códigos de vista y clasificación del tipo de plano).
VISION_MODEL = os.getenv("VISION_MODEL", "claude-opus-5-5")
VISION_FAST_MODEL = os.getenv("VISION_FAST_MODEL", "claude-haiku-5-5")
VISION_EFFORT = os.getenv("VISION_EFFORT", "medium")  # low | medium | high | xhigh | max

# "Lenguaje de planos" (rótulos, códigos, unidades, acabados) que la visión debe
# conocer. Se lee una vez al importar; si falta el archivo se sigue sin él.
_GLOSARIO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glosario_planos.md")
try:
    with open(_GLOSARIO_PATH, encoding="utf-8") as _f:
        GLOSARIO = _f.read().strip()
except OSError as _e:
    logger.warning(f"Glosario de planos no disponible ({_GLOSARIO_PATH}): {_e} — se analiza sin él")
    GLOSARIO = ""

# Tope de caracteres de la capa de texto del PDF que se envía a la visión.
_MAX_TEXTO_PDF = 60_000

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


def _extraer_resumen(response_text: str) -> str:
    """Resumen de lectura que la visión escribe antes del JSON (<resumen_lectura>;
    <raw_reasoning> se acepta por compatibilidad con respuestas antiguas)."""
    for tag in ("resumen_lectura", "raw_reasoning"):
        a, b = f"<{tag}>", f"</{tag}>"
        if a in response_text and b in response_text:
            return response_text.split(a)[1].split(b)[0].strip()
    return ""


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


def _jpeg_block(img: bytes) -> dict:
    """Bloque de imagen para una página JPEG ya renderizada y orientada."""
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(img).decode("utf-8")}}


def _detect_view_codes(
    client: anthropic.Anthropic,
    image_base64: str,
    media_type: str,
    plano_id: str,
    page_images: Optional[List[bytes]] = None,  # páginas JPEG ya orientadas
) -> List[str]:
    """Primera pasada: extrae SOLO los códigos de vista del plano."""
    pdf_ctx = "Este archivo PDF puede tener VARIAS PÁGINAS. Revisa TODAS las páginas antes de responder.\n\n" if media_type == "application/pdf" else ""
    if page_images:
        pdf_ctx = (f"Recibes el plano como {len(page_images)} IMÁGENES (una por página). "
                   "Revisa TODAS antes de responder.\n\n")

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

    # Con las páginas ya renderizadas se envían como JPEG reducidos: el PDF crudo
    # puede pesar 8 MB en una llamada no-stream.
    if page_images:
        file_blocks = [_jpeg_block(img) for img in page_images]
    else:
        file_blocks = [_make_file_block(image_base64, media_type)]

    try:
        response = client.messages.create(
            model=VISION_FAST_MODEL,
            max_tokens=1024,  # sitio para el razonamiento adaptativo + la lista corta
            output_config={"effort": "low"},
            messages=[{
                "role": "user",
                "content": file_blocks + [{"type": "text", "text": prompt}],
            }],
        )
        # Leer por tipo: la respuesta puede empezar con bloques "thinking".
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
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
            model=VISION_FAST_MODEL,
            max_tokens=1024,  # sitio para el razonamiento adaptativo + la palabra clave
            output_config={"effort": "low"},
            messages=[{
                "role": "user",
                "content": [
                    _make_file_block(image_base64, media_type),
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip().lower()
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
    notes: Optional[str] = None,
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

    notes_ctx = f"\n<contexto_cliente>\n{notes}\n</contexto_cliente>\n" if notes else ""

    prompt = f"""<instructions>
{pdf_ctx}{codes_ctx}{notes_ctx}

Para CADA referencia/armario extrae en JSON dentro de <output_format>:
{{
  "tipo_plano": "armario",
  "armarios": [
    {{
      "ref": "A01",
      "habitacion": "Dormitorio 2",
      "material_interior": "melamina textil",
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
          "tipo": "abatible",
          "ancho_cm": 60.0,
          "alto_cm": 240.0,
          "acabado": "melamina blanca lisa",
          "cantidad": 2,
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
- "habitacion": la estancia a la que pertenece el armario, del título/rótulo del plano (p.ej. "Dormitorio 2", "Dormitorio principal", "Vestíbulo"). Si no se indica, "".
- "material_interior": material del interior del armario, del apartado de acabados (p.ej. "melamina textil", "melamina blanca"). Suele ser distinto del exterior. Si no se indica, "".
- "modulos": las partes del cuerpo del armario (ropa larga, zapatero, rinconero, baldas, cajones integrados…). Incluye SIEMPRE ancho y alto en cm.
- "puertas": todas las puertas visibles. "tipo" = SOLO el tipo de apertura: "abatible" o "corredera".
  · REGLA VISUAL (míralo con atención, es un error común):
    → ABATIBLE: líneas DISCONTINUAS en DIAGONAL sobre la hoja que forman ASPAS,
      TRIÁNGULOS o CUÑAS y convergen hacia el canto donde está el TIRADOR. Es la
      forma estándar de indicar el giro de apertura. La GRAN MAYORÍA de armarios
      son abatibles.
    → CORREDERA: SOLO si ves FLECHAS HORIZONTALES (↔, →, ←) de desplazamiento
      lateral, o un carril/guía dibujado arriba y abajo. Sin flechas ⇒ NO es corredera.
    → Si ves aspas/diagonales discontinuas y NINGUNA flecha horizontal ⇒ ABATIBLE.
    → Ante cualquier duda ⇒ "abatible".
- "acabado" de la puerta: material + labrado, p.ej. "melamina blanca lisa", "laca blanca plafonada", "roble barnizado". REGLAS:
  · Copia el MATERIAL tal como lo rotula el plano. Si pone "laminada" o "melamina",
    el material es MELAMINA (no lo cambies a "laca" para cuadrar nada).
  · La MELAMINA (laminado) solo puede ser LISA. Si el plano rotula "laminada/melamina"
    y ADEMÁS "plafonada/pantografiada" (combinación imposible de fabricar), ignora el
    labrado y escríbelo como "melamina <color> lisa". La melamina NUNCA lleva labrado.
  · Los labrados (plafonado, pantografiado, fresado, moldura) solo existen en LACADO o
    MADERA. No inventes labrados que no estén dibujados; si la hoja se ve lisa, "lisa".
- "items_interiores": accesorios (cajón, barra, LED, espejo, bandeja, zapatero extraíble…). Si no hay, lista vacía.
- Dimensiones SIEMPRE como número. Si no se ve claramente: 0.0.
- "notas" → máx. 5 palabras o cadena vacía.
- Nada fuera de <resumen_lectura> y <output_format>.

Antes del JSON escribe en <resumen_lectura> qué hay en cada sección (máx. 80 palabras).
OBLIGATORIO en <resumen_lectura>: para las puertas de CADA armario, indica
si ves "flechas de desplazamiento" (→ corredera) o "aspas/diagonales discontinuas"
(→ abatible), y decide el tipo en consecuencia. No decidas "corredera" sin flechas.
</instructions>
"""

    try:
        response = client.messages.create(
            model=VISION_MODEL,
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

        raw_reasoning = _extraer_resumen(response_text)

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
            armarios.append(AnalisisArmario(
                ref=ref,
                habitacion=a.get("habitacion", ""),
                material_interior=a.get("material_interior", ""),
                modulos=modulos, puertas=puertas, items_interiores=items,
            ))

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


_FAMILIAS_DOC = """FAMILIAS válidas (asigna a CADA partida la que corresponda):
- "puerta_paso_abatible": puerta de paso/interior de bisagra. En el plano: líneas
  DISCONTINUAS en arco/aspa que indican el giro; SIN flechas de desplazamiento.
- "puerta_paso_corredera": puerta de paso corredera. En el plano: FLECHAS
  horizontales de desplazamiento, o rótulo "corredera"/"con dedal".
- "cerramiento": particiones/cerramientos acristalados o mixtos (vidrio + DM/madera),
  tipo mampara o separación entre ambientes (p.ej. paso a cocina).
- "rodapie": rodapiés/zócalos perimetrales. Se cobra por METRO LINEAL:
  · alto_cm = alto del PERFIL en cm (7, 9, 10, 12, 15, 20…).
  · ancho_cm = LONGITUD TOTAL a instalar en cm (metros lineales × 100), sumando
    las estancias que cubra. Si el plano no permite medirla, 0.
- "armario": armario CON puertas (cuerpo + puertas + interior).
- "vestidor": armario SIN puertas (abierto). Igual que armario pero sin puertas.
- "mueble_bano": muebles de baño (bajo lavabo, columnas, espejo de baño).
- "mueble_varios": otros muebles a medida (aparador, mueble TV, recibidor, librería…).
- "balda_pared": baldas/estantes fijados entre paredes (estanterías de obra en un hueco).
  · cantidad = NÚMERO DE BALDAS (cuéntalas en el alzado; se cobra por balda).
  · ancho_cm = ancho del HUECO entre paredes (= largo de cada balda).
  · fondo_cm = profundidad de la balda si se ve; alto_cm = alto total del conjunto.
  · Si se rotula el GROSOR de la balda, inclúyelo en "notas" (p.ej. "grosor 40mm").
- "otro": lo que no encaje en ninguna de las anteriores.

REGLAS:
- Detecta CADA partida del plano y clasifícala en una familia. NO clasifiques el
  plano entero como una sola cosa: un mismo plano puede tener puertas de paso,
  rodapiés, armarios, cerramientos… a la vez.
- UNA partida = UNA sola familia. NUNCA mezcles elementos de familias distintas
  en la misma partida (p.ej. rodapié y puertas de paso deben ser partidas SEPARADAS,
  cada una con su ref distinto).
- "armario" y "vestidor" son SOLO muebles con CUERPO (módulos) e interior. Una
  puerta suelta (de entrada o de paso) NUNCA es armario: va en "puerta_paso_*".
  La puerta de ENTRADA a la vivienda es "puerta_paso_abatible".
- AGRUPA en UNA partida las idénticas (misma familia + medidas + material + acabado)
  y pon la "cantidad". Ej.: 3 puertas abatibles iguales → 1 partida con cantidad 3.
  La "cantidad" es SIEMPRE un entero >= 1 (nunca 0).
- Puertas: distingue abatible (arco discontinuo, sin flechas) de corredera (flechas).
  Ante la duda, abatible. Pon la apertura en "apertura".
- Material/acabado: cópialos del plano. La MELAMINA/laminado solo puede ser LISA
  (nunca plafonada/pantografiada, es imposible). Para armario/vestidor separa
  material exterior ("material") e interior ("material_interior").
- "habitacion": la estancia del rótulo (p.ej. "Dormitorio 2", "Cocina"). Si no, "".
- Medidas SIEMPRE en cm y como número. Esfuérzate en leerlas del plano.
- Para armario/vestidor: en CADA puerta de "puertas" incluye SIEMPRE ancho_cm y
  alto_cm (mide cada hoja); si de verdad no se ve, no la pongas.
- Solo armario/vestidor llevan modulos/puertas/items_interiores; el resto los deja [].
- "proyecto" (campo de nivel superior): el NOMBRE DEL PROYECTO, que es siempre la
  CALLE y el NÚMERO de la obra. Búscalo en el cajetín, título o pie del plano
  (p.ej. "GOYA 23", "Zurbano 93"). Si de verdad no aparece, "".
- LOCALIZACIÓN EN EL PLANO (obligatorio en cada partida):
  · "pagina": número de página del PDF donde está dibujada la partida (1 = primera).
  · "bbox_pct": [x0, y0, x1, y1] — el recuadro que encierra el DIBUJO de la partida
    en esa página, en PORCENTAJE del ancho/alto de la página (0-100, origen arriba-izq).
  · REGLAS DEL RECUADRO (importante, se usa para recortar la imagen):
    → Debe contener TODAS las vistas de la partida en esa página: alzado, planta o
      sección, distribución interior, cotas, rótulos y cuadro de acabados. NUNCA
      cortes el dibujo por la mitad: ante la duda, recuadro MÁS GRANDE.
    → Si la página entera está dedicada a esa única partida (muy habitual: un
      armario por hoja con toda su información), usa la página completa:
      "bbox_pct": [0, 0, 100, 100].
    → Un mismo armario (misma ref) presentado en varias vistas o zonas de la página
      es UNA sola partida, con UN único recuadro que abarque todas sus vistas.
      Créalo por zonas SOLO si el plano lo presenta como partidas separadas
      (refs/rotulaciones distintas)."""


def _analyze_partidas_plan(
    client,
    image_base64: str,
    media_type: str,
    view_codes: List[str],
    plano_id: str,
    notes: Optional[str] = None,
    page_images: Optional[List[bytes]] = None,  # páginas JPEG ya orientadas (mismo eje que el visor)
    lecciones: Optional[List[str]] = None,      # reglas aprendidas de correcciones anteriores
    pdf_text_pages: Optional[List[str]] = None,  # capa de texto del PDF, una entrada por página
) -> PlanoAnalizado:
    """Pasada por PARTIDAS: detecta cada partida del plano y su familia."""
    from api.schemas.estimate import Partida

    pdf_ctx = (
        "IMPORTANTE: este PDF tiene VARIAS páginas. Analízalas TODAS y extrae las "
        "partidas de cada una.\n\n"
    ) if media_type == "application/pdf" else ""
    if page_images:
        pdf_ctx = (
            f"Recibes el plano como {len(page_images)} IMÁGENES: la imagen k es la "
            "PÁGINA k del plano (usa ese número en el campo 'pagina'). Analízalas TODAS.\n\n"
        )
    codes_ctx = (
        f"Códigos/referencias de vista del plano: {', '.join(view_codes)}. Usa el que "
        "corresponda en 'ref'.\n" if view_codes else "Si no hay código de vista, usa 'SIN-REF'.\n"
    )
    notes_ctx = f"\n<contexto_cliente>\n{notes}\n</contexto_cliente>\n" if notes else ""
    lecciones_ctx = ""
    if lecciones:
        reglas = "\n".join(f"- {l}" for l in lecciones)
        lecciones_ctx = (
            "\n<lecciones_aprendidas>\nReglas aprendidas de correcciones humanas "
            "en planos anteriores — APLÍCALAS SIEMPRE:\n" + reglas + "\n</lecciones_aprendidas>\n"
        )

    # Capa de texto del PDF (exacta): bloque propio entre las imágenes y las
    # instrucciones. Solo las páginas con texto; tope total para acotar tokens.
    texto_pdf_block = None
    partes_texto = [f"— página {i} —\n{t.strip()}"
                    for i, t in enumerate(pdf_text_pages or [], 1) if (t or "").strip()]
    if partes_texto:
        cuerpo = "\n".join(partes_texto)
        if len(cuerpo) > _MAX_TEXTO_PDF:
            cuerpo = cuerpo[:_MAX_TEXTO_PDF].rstrip() + "\n[texto truncado]"
        texto_pdf_block = {"type": "text", "text": (
            "<texto_del_pdf>\n"
            "Texto extraído de la capa de texto del PDF (EXACTO: cotas, rótulos, acabados y "
            "cantidades aquí NO tienen errores de lectura; úsalo con prioridad sobre lo que "
            "leas en la imagen; la imagen sirve para la geometría, qué es cada cosa y dónde está).\n"
            "Si el texto de una página es una MEDICIÓN del cliente (formato Presto: \"Partida ud …\", "
            "\"CanPres\"), sus cantidades mandan y sus códigos (PL, PM, A1…) se unifican con los "
            "dibujos de la misma referencia: UNA sola partida por código, nunca duplicada.\n"
            + cuerpo + "\n</texto_del_pdf>"
        )}

    # Las FAMILIAS/REGLAS y el glosario (estables) van en el system con caché;
    # aquí solo lo que cambia por plano.
    prompt = f"""<instructions>
{pdf_ctx}{codes_ctx}{notes_ctx}{lecciones_ctx}
Eres un presupuestador de carpintería a medida. Recorre el plano y detecta TODAS
las partidas, clasificando cada una en una de las FAMILIAS válidas del sistema y
cumpliendo sus REGLAS.
Aplica el <glosario_planos> del sistema para interpretar rótulos, códigos, unidades y acabados.

Devuelve el JSON dentro de <output_format> con esta forma:
{{
  "proyecto": "Goya 23",
  "partidas": [
    {{
      "familia": "puerta_paso_corredera",
      "descripcion": "Puerta de paso corredera con dedal",
      "habitacion": "Baño 1",
      "ancho_cm": 82.0, "alto_cm": 276.0, "fondo_cm": 0.0,
      "material": "DM lacado blanco", "material_interior": "", "acabado": "lisa",
      "apertura": "corredera", "cantidad": 3, "ref": "P3", "notas": "",
      "pagina": 3, "bbox_pct": [8, 25, 45, 80],
      "modulos": [], "puertas": [], "items_interiores": []
    }},
    {{
      "familia": "armario",
      "descripcion": "Armario 6 puertas abatibles",
      "habitacion": "Dormitorio 2",
      "ancho_cm": 310.0, "alto_cm": 240.0, "fondo_cm": 60.0,
      "material": "melamina blanca", "material_interior": "melamina textil", "acabado": "lisa",
      "apertura": "abatible", "cantidad": 1, "ref": "A06", "notas": "",
      "pagina": 1, "bbox_pct": [30, 8, 70, 60],
      "modulos": [{{"tipo": "cuerpo", "ancho_cm": 103.0, "alto_cm": 240.0, "fondo_cm": 60.0, "cantidad": 3}}],
      "puertas": [{{"tipo": "abatible", "ancho_cm": 51.0, "alto_cm": 240.0, "acabado": "melamina blanca lisa", "cantidad": 6}}],
      "items_interiores": [{{"tipo": "barra perchero", "cantidad": 2}}, {{"tipo": "cajón", "cantidad": 4}}, {{"tipo": "balda", "cantidad": 6}}]
    }}
  ],
  "confidence_score": 0.9
}}

Antes del JSON, escribe en <resumen_lectura> (máx. 100 palabras) un resumen para el
presupuestador: qué partidas hay en el plano y, para las puertas, si el dibujo muestra
arco/diagonales discontinuas o flechas de desplazamiento.
Nada fuera de <resumen_lectura> y <output_format>.
</instructions>"""

    # Contenido: páginas como imágenes orientadas (mismo eje que el visor → los
    # bbox de recorte cuadran exactos) o, si no hay, el archivo original.
    if page_images:
        content = [_jpeg_block(img) for img in page_images]
    else:
        content = [_make_file_block(image_base64, media_type)]
    if texto_pdf_block:
        content.append(texto_pdf_block)
    content.append({"type": "text", "text": prompt})

    params = dict(
        model=VISION_MODEL,
        # 15-20 partidas con sub-estructuras superan 8k con facilidad, y el
        # razonamiento (thinking) también cuenta contra max_tokens.
        max_tokens=64000,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT + "\n\n" + _FAMILIAS_DOC
                    + "\n\n<glosario_planos>\n" + GLOSARIO + "\n</glosario_planos>",
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": content}],
    )
    # display "summarized": el stream envía el resumen del razonamiento mientras
    # piensa. Con el valor por defecto ("omitted") y effort alto, Opus 5.5 pasaba
    # >10 min sin enviar ni un byte → timeout de lectura + 2 reintentos (27 min,
    # sin resultado). Con medium + summarized: ~80 s y huecos de ≤5 s (CARACAS 11).
    razonamiento = {"thinking": {"type": "adaptive", "display": "summarized"},
                    "output_config": {"effort": VISION_EFFORT}}

    try:
        # max_tokens alto exige streaming en el SDK; el resultado final es el mismo.
        # thinking/output_config: si la versión instalada del SDK no conoce esos
        # kwargs (TypeError al construir la llamada), se mandan en el cuerpo vía
        # extra_body; la API los acepta igual.
        try:
            gestor = client.messages.stream(**params, **razonamiento)
        except TypeError:
            gestor = client.messages.stream(**params, extra_body=razonamiento)
        with gestor as _stream:
            response = _stream.get_final_message()
        if getattr(response, "stop_reason", None) == "refusal":
            logger.warning(f"[PARTIDAS] {plano_id}: la visión rechazó el análisis (refusal) — "
                           f"{getattr(response, 'stop_details', None)}")
            return PlanoAnalizado(plano_id=plano_id, tipo_plano="partidas", partidas=[],
                                  confidence_score=0.0, raw_reasoning="",
                                  error="La visión rechazó el análisis (refusal)")
        # Señal fiable de truncado: si se agotó max_tokens, el JSON está cortado.
        truncado = getattr(response, "stop_reason", None) == "max_tokens"
        if truncado:
            logger.warning(f"[PARTIDAS] {plano_id}: respuesta TRUNCADA (max_tokens) — puede faltar contenido")

        # Solo los bloques "text": los bloques "thinking" se ignoran.
        response_text = "".join(b.text for b in response.content if b.type == "text")
        raw_reasoning = _extraer_resumen(response_text)

        json_block = _extract_json_block(response_text)
        reparado = False
        try:
            data = json.loads(json_block)
        except json.JSONDecodeError as e:
            data = _repair_truncated_json(json_block, plano_id, e)
            reparado = True
            if "partidas" not in data:
                # el fallback del reparador es del esquema viejo (componentes)
                data["partidas"] = []

        partidas: List[Partida] = []
        for p in data.get("partidas", []):
            try:
                ref = p.get("ref") or "SIN-REF"
                modulos = [ModuloArmario(ref=ref, **{k: v for k, v in m.items() if k != "ref"})
                           for m in p.get("modulos", [])]
                puertas = [PuertaArmario(ref=ref, **{k: v for k, v in d.items() if k != "ref"})
                           for d in p.get("puertas", [])]
                items = [ItemInteriorArmario(ref=ref, **{k: v for k, v in i.items() if k != "ref"})
                         for i in p.get("items_interiores", [])]
                partidas.append(Partida(
                    familia=p.get("familia", "otro"),
                    descripcion=p.get("descripcion", ""),
                    habitacion=p.get("habitacion", ""),
                    ancho_cm=float(p.get("ancho_cm", 0) or 0),
                    alto_cm=float(p.get("alto_cm", 0) or 0),
                    fondo_cm=float(p.get("fondo_cm", 0) or 0),
                    material=p.get("material", ""),
                    material_interior=p.get("material_interior", ""),
                    acabado=p.get("acabado", ""),
                    apertura=p.get("apertura", ""),
                    cantidad=int(p.get("cantidad", 1) or 1),
                    notas=p.get("notas") or None,
                    ref=ref,
                    pagina=int(p.get("pagina", 0) or 0),
                    bbox_pct=[float(v) for v in (p.get("bbox_pct") or [])][:4],
                    modulos=modulos, puertas=puertas, items_interiores=items,
                ))
            except Exception as pe:
                logger.warning(f"[PARTIDAS] {plano_id}: partida ignorada por error: {pe}")

        logger.info(f"[PARTIDAS] {plano_id}: {len(partidas)} partidas detectadas"
                    + (" (TRUNCADO/REPARADO: puede faltar contenido)" if (truncado or reparado) else ""))

        # Truncado/reparación: avisar SIEMPRE, nunca en silencio.
        if (truncado or reparado) and partidas:
            raw_reasoning = ("⚠ RESPUESTA TRUNCADA/REPARADA: pueden faltar partidas del plano. "
                             "Revisa que estén todas. | ") + raw_reasoning
        if not partidas and (truncado or reparado or data.get("error")):
            return PlanoAnalizado(
                plano_id=plano_id, tipo_plano="partidas", partidas=[],
                confidence_score=0.0, raw_reasoning=raw_reasoning,
                error=data.get("error") or "Respuesta de visión truncada: sin partidas parseables",
            )

        return PlanoAnalizado(
            plano_id=plano_id, tipo_plano="partidas", partidas=partidas,
            proyecto=(data.get("proyecto") or "").strip(),
            confidence_score=float(data.get("confidence_score", 0.8)) * (0.7 if (truncado or reparado) else 1.0),
            raw_reasoning=raw_reasoning,
        )
    except Exception as e:
        _log_error(plano_id, "PartidasError", e)
        return PlanoAnalizado(plano_id=plano_id, tipo_plano="partidas", partidas=[],
                              confidence_score=0.0, raw_reasoning="", error=str(e))


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
    page_images: Optional[List[bytes]] = None,
    lecciones: Optional[List[str]] = None,
    pdf_text_pages: Optional[List[str]] = None,
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

    # Lectura máx. 5 min sin datos y sin reintentos automáticos: un plano colgado
    # debe fallar rápido, no multiplicar la espera ×3.
    client = anthropic.Anthropic(timeout=anthropic.Timeout(1200, read=300), max_retries=1)

    # ── PASADA 1: códigos de vista ────────────────────────────────────────────
    view_codes = _detect_view_codes(client, image_base64, media_type, plano_id, page_images=page_images)

    # ── PASADA 2: detección de PARTIDAS por familia ───────────────────────────
    # Un plano puede tener varias familias a la vez (puertas, rodapiés, armarios…),
    # así que ya NO se clasifica el plano entero: se detecta cada partida.
    return _analyze_partidas_plan(client, image_base64, media_type, view_codes, plano_id, notes,
                                  page_images, lecciones, pdf_text_pages=pdf_text_pages)

    # (código antiguo por tipo de plano — inalcanzable, se mantiene de referencia)
    tipo_plano = _classify_plan_type(client, image_base64, media_type, plano_id)
    if tipo_plano == "armario":
        return _analyze_armario_plan(client, image_base64, media_type, view_codes, plano_id, few_shot_examples, notes)

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

Antes del JSON, en <resumen_lectura> resume brevemente qué hay en cada sección (máx. 80 palabras).

REGLAS JSON CRÍTICAS:
- "ancho_cm", "largo_cm", "cantidad" → SIEMPRE número. Si no sabes: 0.0 o 1.
- "ref" → solo el código exacto ({ref_rule}). Sin texto adicional.
- "material", "acabado", "notas" → MUY CORTOS o el JSON se trunca.
- Nada fuera de <resumen_lectura> y <output_format>.
</instructions>

{examples_block}<input_data>
Notas adicionales del cliente: {notes if notes else "Ninguna"}
</input_data>
"""

    try:
        response = client.messages.create(
            model=VISION_MODEL,
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

        raw_reasoning = _extraer_resumen(response_text)

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
