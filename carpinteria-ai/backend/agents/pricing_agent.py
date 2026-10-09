import logging
import math
import os
import re
from typing import Callable, List, Optional

from agents import tarifa
from api.schemas.estimate import (
    AnalisisArmario, LineaPresupuesto, PlanoAnalizado, Presupuesto,
)
from rag.embeddings import RAG_MAX_DISTANCE, query_precios

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


def _rag_lookup(query_variants: List[str], cliente_id: str) -> tuple[float, bool, float, str]:
    """
    Returns (precio_unitario, precio_pendiente, best_distance, kb_descripcion).
    kb_descripcion is the KB item's material + documento text when found, else "".
    """
    precio_unitario = 0.0
    precio_pendiente = True
    mejor_distancia = float("inf")
    kb_descripcion = ""

    for query_text in query_variants:
        for client_key in dict.fromkeys([cliente_id, "general"]):
            resultados = query_precios(query_text, client_key, n_results=5)
            for res in resultados:
                dist = res.get("distancia", float("inf"))
                if dist < mejor_distancia and dist < RAG_MAX_DISTANCE:
                    metadatos = res.get("metadatos", {})
                    if "precio_unitario" in metadatos:
                        try:
                            precio_unitario = float(metadatos["precio_unitario"])
                            mejor_distancia = dist
                            precio_pendiente = False
                            # Build description from KB item
                            material = metadatos.get("material", "")
                            documento = res.get("documento", "")
                            unidad = metadatos.get("unidad", "")
                            kb_descripcion = material or documento
                            if unidad:
                                kb_descripcion += f" ({unidad})"
                        except (ValueError, TypeError):
                            pass
        if not precio_pendiente:
            break

    return precio_unitario, precio_pendiente, mejor_distancia, kb_descripcion


# ── Título y descripción de partida (formato comercial) ──────────────────────

def _unir_y(partes: List[str]) -> str:
    """['a','b','c'] → 'a, b y c'."""
    partes = [p for p in partes if p]
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def titulo_partida(armario, tipo_mueble: str = "Armario") -> str:
    """P.ej. 'A06 - Armario Dormitorio 2' o 'V01 - Vestidor Dormitorio ppal'."""
    hab = (getattr(armario, "habitacion", "") or "").strip()
    return f"{armario.ref} - {tipo_mueble} {hab}".rstrip(" -") if hab else f"{armario.ref} - {tipo_mueble}"


def descripcion_partida(armario: AnalisisArmario) -> str:
    """Descripción comercial de la partida en el formato de 3 líneas."""
    puertas = armario.puertas
    n_puertas = int(sum(p.cantidad for p in puertas)) or len(puertas)

    aperturas = {"corredera" if "corredera" in (p.tipo or "").lower() else "abatible" for p in puertas}
    apertura = "abatibles" if aperturas == {"abatible"} else \
               ("correderas" if aperturas == {"corredera"} else "abatibles/correderas")

    # labrado: melamina/laminado ⇒ siempre lisa
    labrado = "lisas"
    for p in puertas:
        ac = (p.acabado or "").lower()
        es_melamina = "melamina" in ac or "laminad" in ac
        if not es_melamina and any(k in ac for k in ("plafon", "pantograf", "fresad", "moldura")):
            labrado = "plafonadas"
            break

    items = armario.items_interiores
    def _tiene(*claves):
        return any(any(c in (i.tipo or "").lower() for c in claves) for i in items)
    n_cajones = int(sum(i.cantidad for i in items if "caj" in (i.tipo or "").lower()))
    hay_accesorios = _tiene("acceso", "celdilla")
    hay_baldas = _tiene("balda", "estante", "maletero")
    hay_barra = _tiene("barra", "perchero")
    hay_zapatero = _tiene("zapatero")
    hay_bandeja = _tiene("bandeja")
    hay_espejo = _tiene("espejo")
    hay_led = _tiene("led", "ilumina")
    hay_tirador = _tiene("tirador", "pomo", "asa", "manija", "uñero")

    interior = []
    if n_cajones:
        caj = f"{n_cajones} cajones" if n_cajones != 1 else "1 cajón"
        if hay_accesorios:
            caj += " (uno con celdillas para accesorios)"
        interior.append(caj)
    if hay_bandeja:
        interior.append("bandejas extraíbles")
    if hay_zapatero:
        interior.append("zapatero")
    if hay_baldas:
        interior.append("baldas")
    if hay_barra:
        interior.append("barra de perchero")
    if hay_espejo:
        interior.append("espejo")
    if hay_led:
        interior.append("iluminación LED")

    if n_puertas > 0:
        l1 = f"Suministro e instalación de armario de {n_puertas} puertas {apertura} {labrado}"
    else:
        # vestidor / armario abierto: sin frase de puertas (ni de tiradores)
        l1 = "Suministro e instalación de vestidor abierto"
    if interior:
        l1 += f" con {_unir_y(interior)}"
    l1 += "."
    # Con puerta lisa los tiradores no se incluyen → siempre se indica.
    # (Los vestidores no llevan puertas → sin frase de tiradores.)
    if n_puertas > 0 and (labrado == "lisas" or hay_tirador):
        l1 += " No incluye tirador."

    # medidas: ancho total × alto × fondo. Si el plano no da medidas, se
    # presupuesta a los MÁXIMOS (alto hasta 3050mm, 600mm/puerta) y se indica.
    ancho_t, alto_t, fondo_t, _np, estimado = _dims_armario(armario)
    if estimado:
        l2 = f"Medidas máx. presupuestadas: {ancho_t:.0f}x{alto_t:.0f}x{fondo_t:.0f} (alto hasta {alto_t:.0f}cm)"
    else:
        l2 = f"Medidas aprox: {ancho_t:.0f}x{alto_t:.0f}x{fondo_t:.0f}"

    # materiales exterior (acabado de puerta) / interior
    ext = ""
    if puertas and puertas[0].acabado:
        ac = puertas[0].acabado.lower()
        if "melamina" in ac or "laminad" in ac:
            color = "blanca" if "blanc" in ac else ""
            ext = f"melamina {color}".strip()
        elif "laca" in ac:
            ext = puertas[0].acabado
        else:
            ext = puertas[0].acabado
    intr = (armario.material_interior or "").strip()
    if ext and intr:
        l3 = f"Material y terminación: exterior {ext}, interior {intr}"
    elif ext:
        l3 = f"Material y terminación: exterior {ext}"
    else:
        l3 = ""

    return "\n".join([x for x in (l1, l2, l3) if x])


# ── Armario pricing ──────────────────────────────────────────────────────────

def _price_armarios(
    armarios: List[AnalisisArmario],
    plano_id: str,
    cliente_id: str,
    on_line_added: Optional[Callable] = None,
) -> tuple[List[LineaPresupuesto], float]:
    """
    Genera líneas de presupuesto para planos de tipo armario usando la
    CALCULADORA PARAMÉTRICA (tarifa.py), no búsqueda por texto. Modelo:
    cuerpo (nº de módulos según ancho total) + puertas + accesorios interiores.
    """
    lineas: List[LineaPresupuesto] = []
    total = 0.0
    counters: dict = {}

    def _add(codigo_tipo: str, ref: str, descripcion: str, cantidad: int,
             precio: Optional[float], explicacion: Optional[str] = None) -> None:
        nonlocal total
        pendiente = precio is None
        pu = 0.0 if pendiente else precio
        subtotal = pu * cantidad
        if not pendiente:
            total += subtotal
        linea = LineaPresupuesto(
            codigo=_gen_codigo(codigo_tipo, counters), ref=ref,
            descripcion=descripcion, cantidad=cantidad, precio_unitario=pu,
            subtotal=subtotal, precio_pendiente=pendiente, explicacion=explicacion,
        )
        lineas.append(linea)
        if on_line_added:
            on_line_added(linea.model_dump())

    for armario in armarios:
        _precio_un_armario(armario, _add)

    return lineas, total


# Medidas MÁXIMAS de presupuestación cuando el plano no da medidas (regla de
# negocio): alto hasta 3050mm (lo más habitual), módulo hasta 1200mm de ancho
# (2 puertas) → cada puerta máx. 600mm → ancho total = nº puertas × 600mm;
# fondo 600mm de módulo (+~30mm de puerta ≈ 630mm en total).
_MAX_ALTO_CM = 305.0
_MAX_ANCHO_PUERTA_CM = 60.0
_FONDO_MODULO_CM = 60.0


def _dims_armario(armario) -> tuple:
    """
    Devuelve (ancho_total, alto, fondo, n_puertas, estimado).
    Fuentes por orden de fiabilidad:
      ancho: 1) ancho_cm de la propia partida (la visión da el TOTAL del armario)
             2) suma de anchos de puertas (las no medidas cuentan a 600mm máx.)
             3) zona más ancha del cuerpo
             4) máximos de negocio (nº puertas × 600mm)
      alto:  partida → máx(zonas/puertas) → 3050mm máx.
      fondo: partida → máx(zonas) → 600mm.
    """
    modulos = armario.modulos or []
    puertas = armario.puertas or []
    n_puertas = int(sum(p.cantidad or 1 for p in puertas)) or len(puertas)
    estimado = False

    # ── ancho total ──
    ancho_total = float(getattr(armario, "ancho_cm", 0) or 0)
    if ancho_total <= 0 and puertas:
        suma, alguna_sin_medida = 0.0, False
        for p in puertas:
            if p.ancho_cm:
                suma += p.ancho_cm * (p.cantidad or 1)
            else:
                suma += _MAX_ANCHO_PUERTA_CM * (p.cantidad or 1)
                alguna_sin_medida = True
        ancho_total = suma
        estimado = estimado or alguna_sin_medida
    if ancho_total <= 0:
        anchos = [m.ancho_cm for m in modulos if m.ancho_cm]
        ancho_total = max(anchos) if anchos else 0.0
    if ancho_total <= 0:
        ancho_total = max(n_puertas, 1) * _MAX_ANCHO_PUERTA_CM
        estimado = True

    # ── alto ──
    alto = float(getattr(armario, "alto_cm", 0) or 0)
    if alto <= 0:
        altos = [m.alto_cm for m in modulos if m.alto_cm] + [p.alto_cm for p in puertas if p.alto_cm]
        alto = max(altos) if altos else 0.0
    if alto <= 0:
        alto = _MAX_ALTO_CM   # sin medida de alto → presupuestamos hasta 3050mm
        estimado = True

    # ── fondo ──
    fondo = float(getattr(armario, "fondo_cm", 0) or 0)
    if fondo <= 0:
        fondos = [m.fondo_cm for m in modulos if m.fondo_cm]
        fondo = max(fondos) if fondos else _FONDO_MODULO_CM

    return ancho_total, alto, fondo, n_puertas, estimado


# Armario de "puertas simuladas" / solo frentes: no lleva cuerpo.
_RE_SOLO_FRENTES = re.compile(r"simulad|s[oó]lo\s+frentes?|sin\s+cuerpo")


def _precio_un_armario(armario, _add: Callable, es_vestidor: bool = False) -> None:
    """
    Precio de UN armario (o vestidor): cuerpo (nº de módulos según ancho total) +
    puertas + interior. El vestidor no lleva puertas y suma un remate por ml.
    `armario` puede ser un AnalisisArmario o una Partida (mismos campos).
    """
    ref = armario.ref or "SIN-REF"
    puertas = armario.puertas or []
    items = armario.items_interiores or []

    ancho_total, alto_c, fondo_c, n_puertas, estimado = _dims_armario(armario)
    nota_max = " (presupuestado a medidas máx.)" if estimado else ""

    # 1. Cuerpo — el acabado del interior afecta al precio (laca +100%,
    #    melamina especial +50%); por defecto melamina stock (0%).
    #    "Puertas simuladas" / "solo frentes" / "sin cuerpo" → NO se cobra el
    #    cuerpo (solo las puertas). AnalisisArmario no tiene descripcion/notas.
    texto_arm = f"{getattr(armario, 'descripcion', '') or ''} {getattr(armario, 'notas', '') or ''}".lower()
    if _RE_SOLO_FRENTES.search(texto_arm):
        _add("modulo", ref, "Solo frentes (sin cuerpo de armario)", 1, 0.0,
             "puertas simuladas / solo frentes: no lleva cuerpo de armario → solo se presupuestan las puertas")
    else:
        n_mod = max(1, math.ceil((ancho_total * 10) / 1200))
        acabado_interior = getattr(armario, "material_interior", "") or "melamina stock"
        precio, _, expl = tarifa.precio_modulo(ancho_total / n_mod, alto_c, fondo_c, acabado_interior)
        tipo_txt = "Cuerpo de vestidor" if es_vestidor else "Cuerpo de armario"
        if n_mod > 1:
            expl = f"ancho total {ancho_total:.0f}cm → {n_mod} módulos de {ancho_total / n_mod:.0f}cm · cada uno: " + expl
        _add("modulo", ref,
             f"{tipo_txt} · {n_mod} módulo(s) · ancho total {ancho_total:.0f}cm, alto hasta {alto_c:.0f}cm, fondo {fondo_c:.0f}cm{nota_max}",
             n_mod, precio, expl)

    # 2. Puertas (los vestidores no tienen). Sin medidas → máximos: 600mm de
    #    ancho por hoja y alto hasta 3050mm.
    if not es_vestidor:
        for puerta in puertas:
            p_ancho = puerta.ancho_cm or _MAX_ANCHO_PUERTA_CM
            p_alto = puerta.alto_cm or _MAX_ALTO_CM
            p_estimada = not (puerta.ancho_cm and puerta.alto_cm)
            precio, desc, expl = tarifa.precio_puerta_armario(
                p_ancho, p_alto, puerta.tipo, puerta.acabado or "laca blanca")
            etiqueta = desc + (f" {puerta.acabado}" if puerta.acabado else "") + \
                       (" (medidas máx.)" if p_estimada else "") + \
                       (f" ({puerta.notas})" if puerta.notas else "")
            _add("puerta_armario", ref, etiqueta, puerta.cantidad, precio, expl)

    # 3. Interior (tiradores → nota, no línea; LED → línea APARTE al final)
    tiradores = False
    tiras_led = 0
    for item in items:
        t = (item.tipo or "").lower()
        # Interior reutilizado (p.ej. "interior reutilizado") → sin coste, antes
        # que LED/tiradores para no cobrar una iluminación que ya existe.
        if "reutilizad" in t:
            _add("item", ref, f"{(item.tipo or '').strip().capitalize()} — sin coste", item.cantidad, 0.0,
                 "interior reutilizado — sin coste")
            continue
        if any(k in t for k in ("tirador", "pomo", "asa", "manija", "manilla", "uñero", "unero")):
            tiradores = True
            continue
        if "led" in t or "ilumina" in t:
            tiras_led += int(item.cantidad or 1)
            continue
        precio, desc, expl = tarifa.precio_interior(item.tipo)
        if precio == 0.0:
            etiqueta = desc  # incluido (maletero/altillo, hueco): la tarifa ya da el texto final
        else:
            etiqueta = f"{desc} — {item.tipo}" if desc.lower() not in t else (item.tipo or "").capitalize()
        if item.notas:
            etiqueta += f" ({item.notas})"
        _add("item", ref, etiqueta, item.cantidad, precio, expl)
    if tiradores and not es_vestidor:
        _add("item", ref, "Tiradores no incluidos", 1, 0.0,
             "con puerta lisa los tiradores no se incluyen en el presupuesto")

    # 4b. LED: SIEMPRE una línea propia debajo del armario. Mínimo por armario
    #     (250€ por defecto) y, por encima, por metro lineal. Los ml se estiman
    #     como ancho del armario × nº de tiras (editable al revisar).
    if tiras_led > 0:
        ml = round((ancho_total / 100.0) * tiras_led, 2)
        precio_led, desc_led, expl_led = tarifa.precio_led(ml)
        _add("item", ref, desc_led, 1, precio_led,
             f"ml estimados = ancho {ancho_total:.0f}cm × {tiras_led} tira(s) → " + expl_led)

    # 4. Vestidor: remate por metro lineal
    if es_vestidor:
        ml = round(ancho_total / 100.0, 2)
        remate_ml = tarifa.CFG.get("vestidor", {}).get("remate_ml", 45)
        _add("item", ref, f"Remates de vestidor ({ml:.2f} ml × {remate_ml}€/ml)", 1, round(remate_ml * ml, 2),
             f"remate de vestidor: {ml:.2f} ml (ancho del vestidor) × {remate_ml}€/ml de tarifa")


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

        precio_unitario, precio_pendiente, mejor_distancia, kb_desc = _rag_lookup(query_variants, cliente_id)

        # Flag zero-dimension area components as pending
        requires_area = tipo_str.lower() in _AREA_TIPOS
        area_m2 = ancho_m * largo_m
        if requires_area and area_m2 == 0.0 and not precio_pendiente:
            precio_pendiente = True
            kb_desc = ""
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

        if kb_desc:
            descripcion = kb_desc
            if comp.ancho_cm > 0 and comp.largo_cm > 0:
                descripcion += f" — {comp.ancho_cm}×{comp.largo_cm}cm"
        else:
            descripcion = f"{tipo_str.capitalize()} de {comp.material} {comp.acabado} ({comp.ancho_cm}x{comp.largo_cm}cm)"
        if comp.notas:
            descripcion += f" ({comp.notas})"

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


# ── Pricing por PARTIDAS (dispatch por familia) ──────────────────────────────

_FAMILIAS_SIN_TARIFA = {"cerramiento", "mueble_bano", "mueble_varios", "otro"}
_FAMILIA_LABEL = {
    "puerta_paso_abatible": "Puerta de paso abatible",
    "puerta_paso_corredera": "Puerta de paso corredera",
    "cerramiento": "Cerramiento",
    "rodapie": "Rodapié",
    "armario": "Armario",
    "vestidor": "Vestidor",
    "mueble_bano": "Mueble de baño",
    "mueble_varios": "Mueble",
    "balda_pared": "Balda a pared",
    "otro": "Partida",
}


def _medidas_txt(p) -> str:
    d = [f"{v:.0f}" for v in (p.ancho_cm, p.alto_cm, p.fondo_cm) if v]
    return ("×".join(d) + "cm") if d else ""


# ── Reglas de texto de partidas ──────────────────────────────────────────────
# Partida que NO se presupuesta (se reutiliza / se mantiene / va en otra partida).
# Ojo: "igualando al existente" NO es reutilizado → no se usa la palabra "existente".
_RE_REUTILIZADO = re.compile(
    r"\b(se\s+reutilizan?|reutilizad[oa]s?|se\s+mantienen?|se\s+conservan?|no\s+se\s+presupuesta"
    r"|incluido\s+en\s+(?:muebles\s+de\s+)?cocina)\b")
# Puerta oculta/rasomuro → su propia tarifa (base 720, no 370).
_RE_RASOMURO = re.compile(r"rasomuro|raso\s+muro|enrasad[ao]s?|puerta\s+oculta|hoja\s+oculta")
_RE_OCULTA = re.compile(r"\bocultas?\b")
# "bisagras/guías/carril… oculta(s)" se refiere al HERRAJE, no a la puerta.
_RE_HERRAJE = re.compile(
    r"\b(?:bisagras?|gu[ií]as?|carril(?:es)?|herrajes?|riel(?:es)?|tirador(?:es)?|cerraduras?|pernios?)\b")
# Acorazada/blindada → fuera de tarifa. "de seguridad"/"antirrobo" solo cuenta
# si va con puerta/hoja (una "cerradura de seguridad" es una puerta normal).
_RE_ACORAZADA = re.compile(r"acorazad|blindad|\b(?:puerta|hoja)s?\s+(?:de\s+seguridad|antirrobo)")
# Pista de puerta de medidas estándar (2030×725) cuando el plano no da el alto.
_RE_ESTANDAR = re.compile(r"est[aá]ndar|\bstd\b|\b2030?(?:\s*[cm]m)?\b")
# Extras de puerta de paso: (patrón, clave en tarifa_config «extras», texto descripción).
_EXTRAS_PASO_NORMAL = (
    # hasta 2 palabras en medio ("bisagras Tectus ocultas"), igual que la ventana de _es_rasomuro
    (re.compile(r"\bbisagras?(?:\s+\S+){0,2}?\s+ocultas?\b"), "bisagras_ocultas", "bisagras ocultas"),
    (re.compile(r"resbal[oó]n\s+magn[eé]tico"), "resbalon_magnetico", "resbalón magnético"),
    (re.compile(r"\bplintos?\b"), "plinto_por_puerta", "plintos"),
)
_EXTRAS_PASO_RASOMURO = (
    (re.compile(r"autocierre"), "autocierre_sin_manivela", "autocierre sin manivela"),
)


def _es_rasomuro(texto: str) -> bool:
    if _RE_RASOMURO.search(texto):
        return True
    # "oculta(s)" suelta → rasomuro, salvo que la preceda un herraje (≤3 palabras antes)
    for m in _RE_OCULTA.finditer(texto):
        previas = " ".join(texto[:m.start()].split()[-3:])
        if not _RE_HERRAJE.search(previas):
            return True
    return False


def _price_partidas(partidas, cliente_id, on_line_added=None):
    """Enruta cada partida a su familia. Devuelve (lineas, total, titulos,
    descripciones, familias_faltantes)."""
    lineas: List[LineaPresupuesto] = []
    total = 0.0
    counters: dict = {}
    familias_faltantes: set = set()
    titulos: dict = {}
    descripciones: dict = {}

    def _add(codigo_tipo, ref, descripcion, cantidad, precio, explicacion=None):
        nonlocal total
        pendiente = precio is None
        pu = 0.0 if pendiente else precio
        subtotal = pu * cantidad
        if not pendiente:
            total += subtotal
        linea = LineaPresupuesto(
            codigo=_gen_codigo(codigo_tipo, counters), ref=ref, descripcion=descripcion,
            cantidad=cantidad, precio_unitario=pu, subtotal=subtotal, precio_pendiente=pendiente,
            explicacion=explicacion)
        lineas.append(linea)
        if on_line_added:
            on_line_added(linea.model_dump())

    for i, partida in enumerate(partidas):
        fam = partida.familia or "otro"
        # Los refs llegan ya únicos desde el workflow (asignar_refs_unicos);
        # esto es solo un fallback defensivo.
        ref = partida.ref or f"P{i+1}"
        cant = partida.cantidad or 1
        label = _FAMILIA_LABEL.get(fam, "Partida")
        med = _medidas_txt(partida)
        desc_base = (partida.descripcion or label) + (f" — {med}" if med else "")
        if partida.material:
            desc_base += f" ({partida.material})"

        # Reutilizado / se mantiene / incluido en cocina → UNA línea a 0€ (no
        # pendiente), con el título y la descripción de grupo de siempre.
        if _RE_REUTILIZADO.search(f"{partida.descripcion} {partida.notas or ''}".lower()):
            _add("otro", ref, f"{desc_base} — no se presupuesta (reutilizado/existente)", cant, 0.0,
                 "la partida se reutiliza / se mantiene (o va incluida en otra) → no se presupuesta")
            if fam in ("armario", "vestidor"):
                titulos[ref] = titulo_partida(partida, "Vestidor" if fam == "vestidor" else "Armario")
                descripciones[ref] = descripcion_partida(partida)
            else:
                titulos[ref] = f"{ref} - {label}" + (f" {partida.habitacion}" if partida.habitacion else "")
                descripciones[ref] = desc_base
            continue

        # Armarios y vestidores: pricing detallado + título/descripción comercial.
        if fam in ("armario", "vestidor"):
            es_vest = (fam == "vestidor")
            _precio_un_armario(partida, _add, es_vestidor=es_vest)
            titulos[ref] = titulo_partida(partida, "Vestidor" if es_vest else "Armario")
            descripciones[ref] = descripcion_partida(partida)
            continue

        if fam in ("puerta_paso_abatible", "puerta_paso_corredera"):
            tipo_txt = f"{partida.acabado or 'lisa'}{' corredera' if fam.endswith('corredera') else ''}"
            texto_todo = f"{partida.descripcion} {partida.material} {partida.acabado} {partida.notas or ''}".lower()
            if _RE_ACORAZADA.search(texto_todo):
                _add("puerta_paso", ref, f"{desc_base} · acorazada/blindada (consultar)", cant, None,
                     "puerta acorazada/blindada: fuera de tarifa → consultar")
            else:
                es_rasomuro = _es_rasomuro(texto_todo)
                extras = [(clave, txt) for patron, clave, txt in
                          (_EXTRAS_PASO_RASOMURO if es_rasomuro else _EXTRAS_PASO_NORMAL)
                          if patron.search(texto_todo)]
                # Sin alto pero rotulada "estándar" → medidas estándar 2030×725.
                ancho_p, alto_p, nota_std = partida.ancho_cm, partida.alto_cm, ""
                if alto_p <= 0 and _RE_ESTANDAR.search(texto_todo):
                    alto_p = 203.0
                    if ancho_p <= 0:
                        ancho_p, nota_std = 72.5, " (medidas estándar 2030×725)"
                    else:
                        nota_std = " (alto estándar 2030)"
                # Alto acotado pero sin ancho (los planos de planta solo marcan la
                # puerta con un punto): hasta 825 mm el ancho no cambia el precio
                # (0 %), así que se presupuesta a 825 y se avisa para confirmar.
                elif alto_p > 0 and ancho_p <= 0:
                    ancho_p, nota_std = 82.5, " (ancho no acotado: presupuestado hasta 825mm, confirmar)"
                precio, _d, expl = tarifa.precio_puerta_paso(
                    ancho_p, alto_p, tipo_txt,
                    partida.material or partida.acabado or "laca blanca",
                    rasomuro=es_rasomuro, extras=[clave for clave, _t in extras])
                _add("puerta_paso", ref,
                     desc_base + (" · rasomuro" if es_rasomuro else "") +
                     "".join(f" · {txt}" for _c, txt in extras) + nota_std,
                     cant, precio, expl + nota_std)
        elif fam == "balda_pared":
            # Estantería entre paredes = N BALDAS del ancho del hueco.
            # largo de cada balda = ancho del hueco (partida.ancho_cm);
            # ancho de balda = profundidad (fondo_cm, 30cm por defecto);
            # el alto_cm del conjunto NO es una medida de balda.
            texto_b = f"{partida.notas or ''} {partida.descripcion} {partida.material} {partida.acabado}".lower()
            n_baldas = cant if cant > 1 else 0
            if n_baldas == 0:
                m = re.search(r"(\d+)\s*baldas?", texto_b)
                # sin "N baldas" en el texto → nº de baldas del interior detectado
                n_items = sum(int(i.cantidad or 0) for i in (partida.items_interiores or [])
                              if "balda" in (i.tipo or "").lower())
                n_baldas = int(m.group(1)) if m else (n_items if n_items > 0 else 1)
            largo_b = partida.ancho_cm
            ancho_b = partida.fondo_cm or 30.0
            grosor_mm = 30.0
            # "Grosor balda 40mm", "grosor de 4 cm"…: hasta 20 caracteres hasta el número
            g = re.search(r"grosor[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*(mm|cm)", texto_b)
            if g:
                v = float(g.group(1).replace(",", "."))
                grosor_mm = v * 10 if g.group(2) == "cm" else v
            precio, _d, expl = tarifa.precio_balda(ancho_b, largo_b, partida.material or "laca blanca", grosor_mm)
            _add("balda", ref,
                 f"{desc_base} — {n_baldas} balda(s) de {largo_b:.0f}cm (grosor {grosor_mm:.0f}mm)",
                 n_baldas, precio, f"{n_baldas} baldas × [{expl}]" if precio else expl)
        elif fam == "rodapie":
            # El rodapié se cobra por METRO LINEAL: la visión pone la longitud
            # total en ancho_cm (ml × 100) y el alto del perfil en alto_cm.
            alto = partida.alto_cm or 0
            ml = round((partida.ancho_cm or 0) / 100.0, 2)
            if alto <= 0:
                _add("rodapie", ref, desc_base + " · alto del rodapié no medido (consultar)", 1, None)
            else:
                queries = [f"rodapié {alto:.0f}cm {partida.acabado}".strip(),
                           f"rodapié {alto:.0f}cm"]
                precio, pendiente, _dist, kb_desc = _rag_lookup(queries, cliente_id)
                # El alto del perfil debe coincidir EXACTO con el ítem de la KB
                # (los embeddings confunden 10cm con 20cm): si no coincide → pendiente.
                if not pendiente and f"{alto:.0f}cm" not in (kb_desc or ""):
                    logger.info(f"rodapié {alto:.0f}cm: match KB '{kb_desc}' no coincide en alto → pendiente")
                    pendiente = True
                if pendiente:
                    _add("rodapie", ref, desc_base + " (por ml)", 1, None,
                         f"no hay rodapié de {alto:.0f}cm en la Base de Precios → pendiente")
                elif ml > 0:
                    _add("rodapie", ref, f"{desc_base} — {ml:.2f} ml × {precio:.2f}€/ml", ml, precio,
                         f"Base de Precios: «{kb_desc}» → {precio:.2f}€/ml × {ml:.2f} ml")
                else:
                    # €/ml conocido pero faltan los metros → pendiente para indicarlos
                    _add("rodapie", ref, f"{desc_base} — {precio:.2f}€/ml · indicar metros lineales", 1, None,
                         f"Base de Precios: «{kb_desc}» a {precio:.2f}€/ml, pero el plano no da los metros lineales")
        else:
            # cerramiento, mueble_bano, mueble_varios, otro → familia sin tarifa
            # (el aviso completo se muestra en el banner del presupuesto)
            familias_faltantes.add(fam)
            _add("otro", ref, f"{desc_base} · sin tarifa", cant, None,
                 f"la familia «{label}» no tiene tarifa todavía → pendiente de precio manual")

        # LED en CUALQUIER mueble (baño, varios, cerramiento…): línea aparte con
        # el mínimo por mueble. En armarios/vestidores ya lo añade su propio flujo.
        texto_led = f"{partida.descripcion} {partida.notas or ''} {partida.acabado}".lower()
        tiras = sum(int(i.cantidad or 1) for i in (partida.items_interiores or [])
                    if "led" in (i.tipo or "").lower() or "ilumina" in (i.tipo or "").lower())
        if tiras == 0 and ("led" in texto_led or "iluminaci" in texto_led):
            tiras = 1
        if tiras:
            # LED vertical en baldas → los ml van por el ALTO del conjunto.
            texto_items = " ".join(f"{i.tipo} {i.notas or ''}" for i in (partida.items_interiores or []))
            vertical = fam == "balda_pared" and "vertical" in f"{texto_led} {texto_items}".lower()
            medida = (partida.alto_cm if vertical else partida.ancho_cm) or 0
            ml = round(medida / 100.0 * tiras, 2)
            p_led, d_led, e_led = tarifa.precio_led(ml)
            if medida:
                e_led = f"ml estimados = {'alto' if vertical else 'ancho'} {medida:.0f}cm × {tiras} tira(s) → " + e_led
            _add("item", ref, d_led, 1, p_led, e_led)

        titulos[ref] = f"{ref} - {label}" + (f" {partida.habitacion}" if partida.habitacion else "")
        descripciones[ref] = desc_base

    return lineas, total, titulos, descripciones, familias_faltantes


# ── Public API ────────────────────────────────────────────────────────────────

def calculate_pricing(
    plano: PlanoAnalizado,
    cliente_id: str,
    on_line_added: Optional[Callable] = None,
) -> Presupuesto:
    """Enruta al pricing por partidas (o al legacy si no hay partidas)."""
    titulos_grupo = None
    descripciones_grupo = None
    familias_faltantes = None

    if plano.partidas:
        lineas, total, titulos_grupo, descripciones_grupo, faltantes = _price_partidas(
            plano.partidas, cliente_id, on_line_added)
        if faltantes:
            familias_faltantes = sorted(faltantes)
            logger.warning(f"Familias sin tarifa (crear en la tabla): {familias_faltantes}")
    elif plano.tipo_plano == "armario" and plano.armarios:
        lineas, total = _price_armarios(plano.armarios, plano.plano_id, cliente_id, on_line_added)
        titulos_grupo = {a.ref: titulo_partida(a) for a in plano.armarios}
        descripciones_grupo = {a.ref: descripcion_partida(a) for a in plano.armarios}
    else:
        lineas, total = _price_generic(plano, cliente_id, on_line_added)

    return Presupuesto(
        plano_id=plano.plano_id, lineas=lineas, total=total,
        titulos_grupo=titulos_grupo, descripciones_grupo=descripciones_grupo,
        familias_faltantes=familias_faltantes,
    )
