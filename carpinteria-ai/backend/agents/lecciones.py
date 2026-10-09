"""
Aprendizaje continuo a partir de correcciones humanas.

Cada vez que el presupuestador corrige algo con IA, se DESTILA la corrección en
una regla GENERAL de lectura de planos (o se descarta si es un dato puntual de
ese proyecto). Las lecciones activas se inyectan en el prompt de la visión de
los siguientes análisis → la app "lee mejor" con cada corrección.
"""
import json
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

MAX_LECCIONES_PROMPT = 20   # nº máx. de lecciones inyectadas en cada análisis
LECCIONES_MODEL = os.getenv("LECCIONES_MODEL", "claude-haiku-5-5")


def destilar_leccion(instruccion: str, antes: list, despues: list) -> Optional[str]:
    """
    Convierte una corrección (instrucción + partidas antes/después) en una regla
    GENERAL de lectura de planos, o devuelve None si es un dato puntual (medidas
    concretas de un proyecto) que no sirve para el futuro. Llamada síncrona.
    """
    import anthropic

    resumen_antes = json.dumps([{k: p.get(k) for k in ("ref", "familia", "descripcion", "material", "acabado")}
                                for p in antes[:6]], ensure_ascii=False)
    resumen_despues = json.dumps([{k: p.get(k) for k in ("ref", "familia", "descripcion", "material", "acabado")}
                                  for p in despues[:6]], ensure_ascii=False)

    prompt = f"""Un presupuestador de carpintería ha corregido la lectura que hizo la IA de un plano.

CORRECCIÓN QUE ESCRIBIÓ: {instruccion}
PARTIDAS ANTES: {resumen_antes}
PARTIDAS DESPUÉS: {resumen_despues}

Si de esta corrección se puede extraer una REGLA GENERAL para leer mejor los
próximos planos (sobre cómo interpretar rótulos, materiales, tipos de apertura,
familias de partida, unidades…), escríbela en UNA sola frase imperativa y
concreta (máx. 30 palabras). Ejemplos de buenas reglas:
- "Los rótulos 'laminada' o 'laminado' indican melamina, nunca laca."
- "Las estanterías rotuladas E## con baldas en un hueco son familia balda_pared, una unidad por balda."

Si la corrección es SOLO un dato puntual de este proyecto (una medida concreta,
una cantidad específica) sin valor general, responde exactamente: NO

Responde SOLO la regla o NO, sin explicaciones."""

    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=LECCIONES_MODEL,
            max_tokens=1024,  # sitio para el razonamiento adaptativo + la frase
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
        )
        texto = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not texto or texto.upper().startswith("NO"):
            return None
        return texto.strip('" ')
    except Exception as e:
        logger.warning(f"lecciones: no se pudo destilar: {e}")
        return None


async def guardar_leccion(texto: str, plano_id: str = "", cliente_id: str = "") -> None:
    """Guarda la lección si no existe una casi igual (dedupe simple por texto)."""
    from db.models import LeccionModel
    from db.persistence import async_session_maker
    from sqlalchemy import select

    async with async_session_maker() as session:
        result = await session.execute(select(LeccionModel).where(LeccionModel.activo == "si"))
        existentes = {(l.texto or "").strip().lower() for l in result.scalars().all()}
        if texto.strip().lower() in existentes:
            return
        session.add(LeccionModel(texto=texto, plano_id=plano_id or None, cliente_id=cliente_id or None))
        await session.commit()
        logger.info(f"lecciones: nueva regla aprendida → {texto!r}")


async def cargar_lecciones(limit: int = MAX_LECCIONES_PROMPT) -> List[str]:
    """Lecciones activas más recientes, para inyectar en el prompt de visión."""
    from db.models import LeccionModel
    from db.persistence import async_session_maker
    from sqlalchemy import select

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(LeccionModel).where(LeccionModel.activo == "si")
                .order_by(LeccionModel.created_at.desc()).limit(limit)
            )
            return [l.texto for l in result.scalars().all()]
    except Exception as e:
        logger.warning(f"lecciones: no se pudieron cargar: {e}")
        return []
