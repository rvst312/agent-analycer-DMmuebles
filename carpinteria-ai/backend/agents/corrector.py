"""
Corrector de partidas con IA.

Cuando el usuario ve algo mal en el presupuesto (medidas, tipo de puerta,
material, partidas que faltan…), escribe la corrección en texto libre y este
módulo EDITA las partidas detectadas (JSON estructurado) con una llamada de
texto —sin volver a mirar el plano— para que la calculadora recalcule al
instante. Rápido (~segundos) y barato comparado con re-analizar la imagen.
"""
import json
import logging
import os
from typing import List

import anthropic
from agents.vision_agent import GLOSARIO
from api.schemas.estimate import FAMILIAS, Partida

logger = logging.getLogger(__name__)

CORRECTOR_MODEL = os.getenv("CORRECTOR_MODEL", "claude-sonnet-5-5")


def corregir_partidas_con_ia(partidas: List[Partida], instruccion: str) -> List[Partida]:
    """
    Aplica `instruccion` (texto libre del usuario) sobre las partidas dadas y
    devuelve la lista corregida. Lanza ValueError si la respuesta no es parseable.
    """
    payload = json.dumps([p.model_dump() for p in partidas], ensure_ascii=False)

    prompt = f"""Eres el corrector de presupuestos de una carpintería a medida.
Te doy las PARTIDAS detectadas por visión en un plano (JSON) y una INSTRUCCIÓN de
corrección escrita por el presupuestador, que ha visto el plano y sabe la verdad.
Usa el glosario para interpretar rótulos, códigos, unidades y acabados.

<glosario_planos>
{GLOSARIO}
</glosario_planos>

<partidas_actuales>
{payload}
</partidas_actuales>

<instruccion>
{instruccion}
</instruccion>

Devuelve dentro de <output_format> un JSON {{"partidas": [...]}} con TODAS las
partidas recibidas, aplicando SOLO los cambios que pida la instrucción.

REGLAS ESTRICTAS:
- NO cambies el campo "ref" de ninguna partida existente (es su identificador).
- Mantén intactas las partidas que la instrucción no mencione.
- Puedes añadir partidas nuevas si la instrucción lo pide (dales un ref corto nuevo)
  y eliminar solo las que la instrucción pida eliminar explícitamente.
- Familias válidas: {", ".join(FAMILIAS)}.
- Medidas SIEMPRE en cm y como número. Rodapiés: ancho_cm = longitud total en cm
  (metros lineales × 100) y alto_cm = alto del perfil.
- La MELAMINA/laminado solo puede ser LISA (nunca plafonada/pantografiada).
- En armarios/vestidores mantén la estructura modulos/puertas/items_interiores y
  aplica ahí los cambios de medidas o tipos de puerta si procede.
- Conserva "pagina" y "bbox_pct" tal cual (no los inventes ni los borres).
Nada fuera de <output_format>.
"""

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=CORRECTOR_MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    text = "".join(b.text for b in response.content if b.type == "text")
    if "<output_format>" in text and "</output_format>" in text:
        text = text.split("<output_format>")[1].split("</output_format>")[0]
    start, end = text.find("{"), text.rfind("}") + 1
    if start == -1:
        raise ValueError("La IA no devolvió JSON de partidas")
    data = json.loads(text[start:end])

    corregidas: List[Partida] = []
    for p in data.get("partidas", []):
        try:
            corregidas.append(Partida(**p))
        except Exception as e:
            logger.warning(f"corrector: partida descartada por inválida: {e}")
    if not corregidas:
        raise ValueError("La corrección no produjo ninguna partida válida")
    logger.info(f"corrector: {len(partidas)} → {len(corregidas)} partidas tras corrección")
    return corregidas
