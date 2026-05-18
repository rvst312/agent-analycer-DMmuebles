import logging
import os
from typing import Callable, List, Optional

from api.schemas.estimate import (
    AnalisisArmario, LineaPresupuesto, PlanoAnalizado, Presupuesto,
)
from rag.embeddings import query_precios

logger = logging.getLogger(__name__)


def get_k_labor(tipo: str) -> float:
    env_var_name = f"K_LABOR_{tipo.upper()}"
    k_labor_str = os.environ.get(env_var_name, "0.0")
    try:
        return float(k_labor_str)
    except ValueError:
        logger.warning(f"Valor inválido para {env_var_name}: {k_labor_str}. Usando 0.0")
        return 0.0


_TIPO_PREFIXES = {
    "tablero": "TAB", "puerta": "PTA", "cajon": "CAJ", "cajón": "CAJ",
    "herraje": "HER", "barra": "BAR", "estante": "EST", "armario": "ARM",
    "otro": "OTR",
    # armario-specific
    "modulo": "MOD", "puerta_armario": "PTA", "item": "ITM",
}


def _gen_codigo(tipo: str, counters: dict) -> str:
    prefix = _TIPO_PREFIXES.get(tipo.lower(), "OTR")
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{prefix}-{counters[prefix]:03d}"


def _rag_lookup(query_variants: List[str], cliente_id: str) -> tuple[float, bool, float]:
    """
    Returns (precio_unitario, precio_pendiente, best_distance).
    Tries each query variant against cliente and 'general' collections.
    """
    precio_unitario = 0.0
    precio_pendiente = True
    mejor_distancia = float("inf")

    for query_text in query_variants:
        for client_key in dict.fromkeys([cliente_id, "general"]):
            resultados = query_precios(query_text, client_key, n_results=5)
            for res in resultados:
                dist = res.get("distancia", float("inf"))
                if dist < mejor_distancia and dist < 1.8:
                    metadatos = res.get("metadatos", {})
                    if "precio_unitario" in metadatos:
                        try:
                            precio_unitario = float(metadatos["precio_unitario"])
                            mejor_distancia = dist
                            precio_pendiente = False
                        except (ValueError, TypeError):
                            pass
        if not precio_pendiente:
            break

    return precio_unitario, precio_pendiente, mejor_distancia


# ── Armario pricing ──────────────────────────────────────────────────────────

def _price_armarios(
    armarios: List[AnalisisArmario],
    plano_id: str,
    cliente_id: str,
    on_line_added: Optional[Callable] = None,
) -> tuple[List[LineaPresupuesto], float]:
    """Genera líneas de presupuesto para planos de tipo armario."""
    lineas: List[LineaPresupuesto] = []
    total = 0.0
    counters: dict = {}

    for armario in armarios:
        ref = armario.ref

        # 1. Módulos del cuerpo
        for mod in armario.modulos:
            queries = [
                f"módulo armario {mod.tipo} {mod.ancho_cm}x{mod.alto_cm}cm",
                f"módulo armario {mod.tipo} {mod.ancho_cm}cm",
                f"módulo armario {mod.ancho_cm}x{mod.alto_cm}cm",
                f"módulo {mod.tipo} armario",
                f"módulo armario {mod.tipo}",
            ]
            precio, pendiente, dist = _rag_lookup(queries, cliente_id)

            if not pendiente:
                logger.info(f"[MOD] {ref} '{mod.tipo}' {mod.ancho_cm}x{mod.alto_cm}cm → {precio:.2f}€ (dist={dist:.3f})")
            else:
                logger.info(f"[MOD] {ref} '{mod.tipo}' sin precio RAG")

            subtotal = precio * mod.cantidad
            if not pendiente:
                total += subtotal

            desc = f"Módulo {mod.tipo} {mod.ancho_cm}x{mod.alto_cm}cm"
            if mod.fondo_cm:
                desc += f" fondo {mod.fondo_cm}cm"
            if mod.notas:
                desc += f" — {mod.notas}"

            linea = LineaPresupuesto(
                codigo=_gen_codigo("modulo", counters),
                ref=ref,
                descripcion=desc,
                cantidad=mod.cantidad,
                precio_unitario=precio,
                subtotal=subtotal,
                precio_pendiente=pendiente,
            )
            lineas.append(linea)
            if on_line_added:
                on_line_added(linea.model_dump())

        # 2. Puertas
        for puerta in armario.puertas:
            queries = [
                f"puerta armario {puerta.tipo} {puerta.ancho_cm}x{puerta.alto_cm}cm {puerta.acabado}",
                f"puerta armario {puerta.tipo} {puerta.ancho_cm}x{puerta.alto_cm}cm",
                f"puerta armario {puerta.tipo} {puerta.acabado}",
                f"puerta armario {puerta.tipo}",
                f"puerta {puerta.tipo} armario",
            ]
            precio, pendiente, dist = _rag_lookup(queries, cliente_id)

            if not pendiente:
                logger.info(f"[PTA] {ref} puerta {puerta.tipo} {puerta.ancho_cm}x{puerta.alto_cm}cm → {precio:.2f}€ (dist={dist:.3f})")

            subtotal = precio * puerta.cantidad
            if not pendiente:
                total += subtotal

            desc = f"Puerta {puerta.tipo} {puerta.ancho_cm}x{puerta.alto_cm}cm {puerta.acabado}".strip()
            if puerta.notas:
                desc += f" — {puerta.notas}"

            linea = LineaPresupuesto(
                codigo=_gen_codigo("puerta_armario", counters),
                ref=ref,
                descripcion=desc,
                cantidad=puerta.cantidad,
                precio_unitario=precio,
                subtotal=subtotal,
                precio_pendiente=pendiente,
            )
            lineas.append(linea)
            if on_line_added:
                on_line_added(linea.model_dump())

        # 3. Items interiores
        for item in armario.items_interiores:
            queries = [
                f"{item.tipo} armario interior",
                f"{item.tipo} armario",
                f"{item.tipo}",
            ]
            precio, pendiente, dist = _rag_lookup(queries, cliente_id)

            if not pendiente:
                logger.info(f"[ITM] {ref} '{item.tipo}' → {precio:.2f}€ (dist={dist:.3f})")

            subtotal = precio * item.cantidad
            if not pendiente:
                total += subtotal

            desc = f"{item.tipo.capitalize()}"
            if item.notas:
                desc += f" — {item.notas}"

            linea = LineaPresupuesto(
                codigo=_gen_codigo("item", counters),
                ref=ref,
                descripcion=desc,
                cantidad=item.cantidad,
                precio_unitario=precio,
                subtotal=subtotal,
                precio_pendiente=pendiente,
            )
            lineas.append(linea)
            if on_line_added:
                on_line_added(linea.model_dump())

    return lineas, total


# ── Generic pricing (existing logic) ─────────────────────────────────────────

_AREA_TIPOS = {"tablero", "puerta", "estante", "armario", "cajon", "cajón"}

_TIPO_CATALOG = {
    "tablero": "módulo armario tablero",
    "puerta": "puerta armario",
    "cajon": "cajón bandeja extraíble armario",
    "cajón": "cajón bandeja extraíble armario",
    "estante": "balda estante armario",
    "herraje": "herraje accesorio",
    "barra": "barra perchero armario",
    "armario": "armario módulo",
}


def _price_generic(
    plano: PlanoAnalizado,
    cliente_id: str,
    on_line_added: Optional[Callable] = None,
) -> tuple[List[LineaPresupuesto], float]:
    lineas: List[LineaPresupuesto] = []
    total = 0.0
    tipo_counters: dict = {}

    for comp in plano.componentes:
        ancho_m = comp.ancho_cm / 100.0
        largo_m = comp.largo_cm / 100.0
        tipo_str = comp.tipo.value if hasattr(comp.tipo, "value") else str(comp.tipo)
        catalog_hint = _TIPO_CATALOG.get(tipo_str.lower(), tipo_str)

        query_variants = [
            f"{catalog_hint} {comp.material} {comp.acabado}",
            f"{catalog_hint} {comp.acabado}",
            f"{catalog_hint} {comp.material}",
            f"{tipo_str} {comp.material} {comp.acabado}",
            f"{comp.material} {comp.acabado}",
            f"{catalog_hint}",
        ]

        precio_unitario, precio_pendiente, mejor_distancia = _rag_lookup(query_variants, cliente_id)

        # Flag zero-dimension area components as pending
        requires_area = tipo_str.lower() in _AREA_TIPOS
        area_m2 = ancho_m * largo_m
        if requires_area and area_m2 == 0.0 and not precio_pendiente:
            precio_pendiente = True
            logger.info(f"Pendiente: '{tipo_str}' sin dimensiones ({comp.ancho_cm}x{comp.largo_cm}cm)")

        if not precio_pendiente:
            logger.info(f"Precio '{tipo_str}': {precio_unitario} (dist={mejor_distancia:.3f})")
        else:
            logger.info(f"Sin precio RAG para '{query_variants[0]}'")

        k_labor = get_k_labor(tipo_str)
        coste_unitario_total = area_m2 * precio_unitario + k_labor
        subtotal = coste_unitario_total * comp.cantidad
        if not precio_pendiente:
            total += subtotal

        descripcion = f"{tipo_str.capitalize()} de {comp.material} {comp.acabado} ({comp.ancho_cm}x{comp.largo_cm}cm)"
        if comp.notas:
            descripcion += f" - {comp.notas}"

        linea = LineaPresupuesto(
            codigo=_gen_codigo(tipo_str, tipo_counters),
            ref=getattr(comp, "ref", None),
            descripcion=descripcion,
            cantidad=comp.cantidad,
            precio_unitario=coste_unitario_total,
            subtotal=subtotal,
            precio_pendiente=precio_pendiente,
        )
        lineas.append(linea)
        if on_line_added:
            on_line_added(linea.model_dump())

    return lineas, total


# ── Public API ────────────────────────────────────────────────────────────────

def calculate_pricing(
    plano: PlanoAnalizado,
    cliente_id: str,
    on_line_added: Optional[Callable] = None,
) -> Presupuesto:
    """Enruta al pricing correcto según el tipo de plano."""
    if plano.tipo_plano == "armario" and plano.armarios:
        lineas, total = _price_armarios(
            plano.armarios, plano.plano_id, cliente_id, on_line_added
        )
    else:
        lineas, total = _price_generic(plano, cliente_id, on_line_added)

    return Presupuesto(plano_id=plano.plano_id, lineas=lineas, total=total)
