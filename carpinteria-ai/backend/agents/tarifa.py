"""
Motor de tarifas paramétrico.

Calcula precios a partir de las TABLAS de la tarifa (precio base + porcentajes
por dimensiones/material/acabado + extras fijos), en lugar de una lista plana
buscada por similitud de texto.

Fuente: TABLA_DE_PRECIOS_actualizada_Dani.pdf.

Convención (según la propia tarifa): "Los porcentajes que correspondan a los
elementos se suman entre sí y se aplican sumándolos a la tarifa base":

    precio = base * (1 + Σ porcentajes)   [+ extras en €]

Cuando una dimensión cae en un tramo "Consultar" (o el material/acabado es
"Consultar"), la función devuelve precio=None → la línea queda PENDIENTE
(mejor pendiente que un precio inventado).

Las medidas de la visión vienen en cm; la tarifa está en mm → se multiplican
por 10 al comparar los tramos.
"""
import json
import os
from typing import Optional, Tuple

# ── Configuración editable de la tarifa ──────────────────────────────────────
# Todos los números (precios base y porcentajes) viven en tarifa_config.json.
# En producción TARIFA_CONFIG_PATH apunta a un VOLUMEN persistente para que las
# ediciones desde la app sobrevivan a los redeploys; la primera vez se copia
# allí la tarifa que viene con el código.
_CONFIG_DEFAULT = os.path.join(os.path.dirname(__file__), "tarifa_config.json")
_CONFIG_PATH = os.getenv("TARIFA_CONFIG_PATH") or _CONFIG_DEFAULT
if _CONFIG_PATH != _CONFIG_DEFAULT and not os.path.exists(_CONFIG_PATH):
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    import shutil as _shutil
    _shutil.copyfile(_CONFIG_DEFAULT, _CONFIG_PATH)


def _merge_defaults(cfg: dict, defaults: dict) -> bool:
    """
    Añade a `cfg` las claves NUEVAS que traiga la tarifa del código (p.ej. un
    campo recién creado como tira_led_minimo) sin tocar los valores que el
    usuario ya editó. Devuelve True si añadió algo.
    """
    cambiado = False
    for k, v in defaults.items():
        if k not in cfg:
            cfg[k] = v
            cambiado = True
        elif isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cambiado = _merge_defaults(cfg[k], v) or cambiado
    return cambiado


with open(_CONFIG_PATH, encoding="utf-8") as _f:
    CFG = json.load(_f)
if _CONFIG_PATH != _CONFIG_DEFAULT:
    with open(_CONFIG_DEFAULT, encoding="utf-8") as _f:
        _defaults = json.load(_f)
    if _merge_defaults(CFG, _defaults):
        with open(_CONFIG_PATH, "w", encoding="utf-8") as _f:
            json.dump(CFG, _f, ensure_ascii=False, indent=2)

CONSULTAR = None  # sentinel: tramo sin precio → pendiente


def _pct_por_tramo(valor_mm: float, tramos) -> Optional[float]:
    """
    tramos: lista ordenada de (limite_mm, pct). Devuelve el pct del primer tramo
    cuyo límite >= valor. Si el valor supera todos los límites → None (Consultar).
    """
    for limite_mm, pct in tramos:
        if valor_mm <= limite_mm:
            return pct
    return CONSULTAR


def _norm(texto: Optional[str]) -> str:
    return (texto or "").strip().lower()


def _pct_por_clave(texto: str, tabla: dict, default: float = 0.0) -> float:
    """
    Busca en `texto` (libre, de la visión) la clave MÁS ESPECÍFICA (más larga)
    de `tabla` contenida en él. Normaliza el género (blanco→blanca, oscura→oscuro…)
    para tolerar cómo rotula cada plano. Si nada casa → default.
    """
    t = _norm(texto).replace("blanco", "blanca").replace("oscura", "oscuro").replace("clara", "claro")
    mejor, mejor_len = default, 0
    for k, pct in tabla.items():
        kl = k.lower()
        if kl in t and len(kl) > mejor_len:
            mejor, mejor_len = float(pct), len(kl)
    return mejor


def _explica(base: float, factores: list, total: float, extras: Optional[list] = None) -> str:
    """
    Desglose legible del cálculo: "Base 160€ +20% alto ≤3050mm +60% plafonada
    −25% melamina = 288€". `factores` = [(etiqueta, pct)], se muestran todos
    (también los 0% relevantes, para que se vea qué tramo aplicó).
    """
    partes = [f"Base {base:g}€"]
    for etiqueta, pct in factores:
        signo = "+" if pct >= 0 else "−"
        partes.append(f"{signo}{abs(pct) * 100:g}% {etiqueta}")
    txt = " ".join(partes)
    for e in (extras or []):
        txt += f" + {e}"
    return f"{txt} = {total:g}€"


def _material_puerta_desde_cfg(acabados: dict) -> list:
    """
    Deriva la lista de detección de material de puerta desde el config
    (clave, pct, es_melamina), más específica primero, con el alias
    'laminad' = melamina (los planos rotulan 'laminada').
    """
    items = [(k.lower(), float(pct), "melamina" in k.lower()) for k, pct in acabados.items()]
    pct_mel = float(acabados.get("melamina", acabados.get("melamina stock", 0.0)))
    items.append(("laminad", pct_mel, True))
    items.sort(key=lambda x: -len(x[0]))
    return items


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO + MALETERO  (cuerpo del armario)   ·  base 700 €
# ─────────────────────────────────────────────────────────────────────────────
_MOD_BASE = CFG["modulo"]["base"]
_MOD_ALTO = CFG["modulo"]["alto_mm"]
_MOD_ANCHO = CFG["modulo"]["ancho_mm"]
_MOD_FONDO = CFG["modulo"]["fondo_mm"]
_MOD_DESCUENTO_DIM_MAX = CFG["modulo"]["descuento_dimension_max"]
_MOD_ACABADO = CFG["modulo"]["acabado"]


def precio_modulo(ancho_cm: float, alto_cm: float, fondo_cm: float,
                  acabado: str = "melamina stock") -> Tuple[Optional[float], str, str]:
    p_alto = _pct_por_tramo(alto_cm * 10, _MOD_ALTO)
    p_ancho = _pct_por_tramo(ancho_cm * 10, _MOD_ANCHO)
    p_fondo = _pct_por_tramo(fondo_cm * 10, _MOD_FONDO)
    # match por substring: "melamina textil cactus" → melamina (0%), "laca blanca" → +100%
    p_acab = _pct_por_clave(acabado, _MOD_ACABADO, default=0.0)
    if None in (p_alto, p_ancho, p_fondo):
        return CONSULTAR, "módulo fuera de tarifa (consultar)", "alguna medida supera el último tramo de la tarifa → consultar"
    dim = max(p_alto + p_ancho + p_fondo, _MOD_DESCUENTO_DIM_MAX)  # tope -50 %
    precio = round(_MOD_BASE * (1 + dim + p_acab), 2)
    tope = " (tope −50% aplicado)" if (p_alto + p_ancho + p_fondo) < _MOD_DESCUENTO_DIM_MAX else ""
    detalle = _explica(_MOD_BASE, [
        (f"alto {alto_cm:.0f}cm", p_alto), (f"ancho {ancho_cm:.0f}cm", p_ancho),
        (f"fondo {fondo_cm:.0f}cm", p_fondo), (f"acabado {acabado or 'melamina'}", p_acab),
    ], precio) + tope
    return precio, f"Módulo {ancho_cm:.0f}×{alto_cm:.0f}×f{fondo_cm:.0f}cm", detalle


# ─────────────────────────────────────────────────────────────────────────────
# PUERTA DE ARMARIO   ·  base 160 €  (lisa lacada blanca abatible)
# ─────────────────────────────────────────────────────────────────────────────
_PARM_BASE = CFG["puerta_armario"]["base"]
_PARM_ALTO = CFG["puerta_armario"]["alto_mm"]
_PARM_ANCHO = CFG["puerta_armario"]["ancho_mm"]
_PARM_CORREDERA_ANCHO = CFG["puerta_armario"]["corredera_ancho_mm"]


# Detección de MATERIAL de la puerta: derivada del CONFIG (editable en la app).
_MATERIAL_PUERTA = _material_puerta_desde_cfg(CFG["puerta_armario"]["acabado"])
def _labrado_pct(texto: str) -> float:
    """Recargo por labrado detectado en texto libre. Usa raíces para tolerar
    variaciones (plafonado/plafonada, pantografiado/pantografiada…)."""
    complejo = "complej" in texto
    if "vitrina" in texto or "metalic" in texto:
        return 1.80
    if "pantograf" in texto and ("plafon" in texto or "moldura" in texto):
        return 0.90
    if "plafon" in texto or "moldura" in texto:
        return 0.70 if complejo else 0.60
    if "pantograf" in texto:
        return 0.42 if complejo else 0.35
    if "fresad" in texto:
        return 0.25
    if "uñero" in texto or "unero" in texto:
        return 0.25
    return 0.0


def precio_puerta_armario(ancho_cm: float, alto_cm: float, tipo: str = "",
                          acabado: str = "laca blanca",
                          costado_visto: bool = False) -> Tuple[Optional[float], str]:
    if ancho_cm <= 0 or alto_cm <= 0:
        return CONSULTAR, "puerta de armario sin medidas (consultar)"
    texto = f"{_norm(tipo)} {_norm(acabado)}"
    es_corredera = "corredera" in texto
    p_alto = _pct_por_tramo(alto_cm * 10, _PARM_ALTO)
    if es_corredera:
        # Las correderas usan su propia tabla de % por ancho.
        p_ancho = _pct_por_tramo(ancho_cm * 10, _PARM_CORREDERA_ANCHO)
    else:
        p_ancho = _pct_por_tramo(ancho_cm * 10, _PARM_ANCHO)
    if None in (p_alto, p_ancho):
        return CONSULTAR, "puerta de armario fuera de tarifa (consultar)", \
               f"ancho {ancho_cm:.0f}cm o alto {alto_cm:.0f}cm superan el último tramo de la tarifa → consultar"

    # material (acabado)
    p_acab, es_melamina = 0.0, False
    material_txt = "laca blanca"
    for clave, pct, melam in _MATERIAL_PUERTA:
        if clave in texto:
            p_acab, es_melamina, material_txt = pct, melam, clave
            break
    # labrado (tipo de puerta)
    p_labrado = _labrado_pct(texto)
    nota_melamina = ""
    # REGLA: la melamina no admite labrado (plafón, pantografiado…) → lisa.
    if es_melamina and p_labrado > 0:
        p_labrado = 0.0
        nota_melamina = " (melamina siempre lisa: labrado ignorado)"

    precio = _PARM_BASE * (1 + p_alto + p_ancho + p_labrado + p_acab)
    extras = []
    if costado_visto:
        cv = float(CFG["puerta_armario"].get("costado_visto", 120))
        precio += cv
        extras.append(f"{cv:g}€ costado visto")
    apertura = "corredera" if es_corredera else "abatible"
    labr = " plafonada/labrada" if p_labrado > 0 else ""
    precio = round(precio, 2)
    factores = [(f"alto {alto_cm:.0f}cm", p_alto),
                (f"ancho {ancho_cm:.0f}cm ({'corredera' if es_corredera else 'abatible'})", p_ancho)]
    if p_labrado:
        factores.append(("labrado (plafón/pantografiado…)", p_labrado))
    factores.append((f"material {material_txt}", p_acab))
    detalle = _explica(_PARM_BASE, factores, precio, extras) + nota_melamina
    return precio, f"Puerta armario {apertura}{labr} {ancho_cm:.0f}×{alto_cm:.0f}cm", detalle


# ─────────────────────────────────────────────────────────────────────────────
# INTERIORES DE ARMARIO   ·  precios (mayormente) fijos por unidad
# ─────────────────────────────────────────────────────────────────────────────
_INT = CFG["interiores"]
_CAJON_CAJONERA = _INT["cajon_cajonera_mm"]      # por alto (mm)
_CAJON_SUELTO = _INT["cajon_suelto_mm"]          # bandeja/cajón suelto
_INTERIOR_FIJOS = [  # (palabras_clave, precio, etiqueta)
    (("balda", "estante"), _INT["balda"], "Balda de interior"),
    (("barra", "perchero"), _INT["barra_perchero"], "Barra perchero"),
    (("sensor",), _INT["sensor"], "Sensor de puerta"),
    (("led",), _INT["tira_led_ml"], "Tira LED 2700k (por ml)"),  # "led" no matchea "tirador"
]


def precio_led(ml: float = 0.0) -> Tuple[float, str]:
    """
    Iluminación LED: se presupuesta APARTE, una línea por MUEBLE (armario,
    vestidor, mueble de baño, mueble varios…). No se pone LED en ningún mueble
    por menos del mínimo (tira_led_minimo, 250€ por defecto); por encima del
    mínimo se cobra por metro lineal (tira_led_ml).
    """
    tarifa_ml = float(CFG["interiores"].get("tira_led_ml", 45))
    minimo = float(CFG["interiores"].get("tira_led_minimo", 250))
    if ml and ml > 0:
        por_ml = round(tarifa_ml * ml, 2)
        if por_ml > minimo:
            return por_ml, f"Iluminación LED — {ml:.2f} ml × {tarifa_ml:g}€/ml", \
                   f"{ml:.2f} ml × {tarifa_ml:g}€/ml = {por_ml:g}€ (supera el mínimo de {minimo:g}€)"
        return minimo, f"Iluminación LED — mínimo por mueble ({minimo:g}€; {ml:.2f} ml)", \
               f"{ml:.2f} ml × {tarifa_ml:g}€/ml = {por_ml:g}€ < mínimo por mueble → se cobra el mínimo {minimo:g}€"
    return minimo, f"Iluminación LED — mínimo por mueble ({minimo:g}€)", \
           f"sin metros medidos → mínimo por mueble {minimo:g}€"


def precio_interior(tipo: str, alto_mm: Optional[float] = None) -> Tuple[Optional[float], str, str]:
    t = _norm(tipo)
    # Incluidos (0€, NO pendientes): la etiqueta devuelta es ya la descripción final.
    if "maletero" in t or "altillo" in t:
        return 0.0, "Maletero/altillo — incluido en el módulo", \
               "la tarifa 'Módulo + maletero' ya incluye el altillo"
    if "hueco" in t or "espacio abierto" in t or "espacio para" in t:
        return 0.0, f"{(tipo or '').strip().capitalize()} — hueco sin coste", "hueco sin coste"
    if "bandeja" in t or "cajón suelto" in t or "cajon suelto" in t:
        precio = _pct_por_tramo(alto_mm or 160, _CAJON_SUELTO) if alto_mm else _CAJON_SUELTO[0][1]
        if precio:
            return precio, "Bandeja extraíble / cajón suelto", f"precio fijo de tarifa (bandeja/cajón suelto): {precio:g}€/ud"
        return CONSULTAR, "bandeja (consultar)", "alto fuera de los tramos de la tarifa"
    if "caj" in t:  # cajón / cajones / cajonera
        precio = _pct_por_tramo(alto_mm or 160, _CAJON_CAJONERA) if alto_mm else _CAJON_CAJONERA[0][1]
        if precio:
            return precio, "Cajón (cajonera)", f"precio fijo de tarifa (cajón en cajonera): {precio:g}€/ud"
        return CONSULTAR, "cajón (consultar)", "alto fuera de los tramos de la tarifa"
    # Zapatero de baldas (no extraíble) = balda de interior por unidad.
    if ("zapatero" in t or "zapatos" in t) and "extraíble" not in t and "extraible" not in t:
        precio = _INT["balda"]
        return precio, "Balda zapatero", f"zapatero de baldas = precio de balda de interior: {precio:g}€/ud"
    for claves, precio, etiqueta in _INTERIOR_FIJOS:
        if any(c in t for c in claves):
            return precio, etiqueta, f"precio fijo de tarifa ({etiqueta.lower()}): {precio:g}€/ud"
    return CONSULTAR, f"interior '{tipo}' fuera de tarifa (consultar)", \
           f"'{tipo}' no está en la tarifa de interiores → pendiente"


# ─────────────────────────────────────────────────────────────────────────────
# BALDAS ENTRE PAREDES   ·  tabla base ancho×largo + % material + % grosor
# ─────────────────────────────────────────────────────────────────────────────
# base[tramo_ancho][tramo_largo]
_BAL = CFG["balda_pared"]
_BALDA_LARGO_TRAMOS = _BAL["largo_tramos_mm"]  # >último consultar
_BALDA_BASE = {int(a): {int(l): v for l, v in cols.items()} for a, cols in _BAL["base"].items()}
_BALDA_MATERIAL = _BAL["material"]
_BALDA_GROSOR = _BAL["grosor_mm"]


def precio_balda(ancho_cm: float, largo_cm: float, material: str = "laca blanca",
                 grosor_mm: float = 30) -> Tuple[Optional[float], str, str]:
    if ancho_cm <= 0 or largo_cm <= 0:
        return CONSULTAR, "balda sin medidas (consultar)", "faltan medidas de la balda"
    ancho_mm, largo_mm = ancho_cm * 10, largo_cm * 10
    tramo_ancho = 300 if ancho_mm <= 300 else (600 if ancho_mm <= 600 else None)
    tramo_largo = next((t for t in _BALDA_LARGO_TRAMOS if largo_mm <= t), None)
    if tramo_ancho is None or tramo_largo is None:
        return CONSULTAR, "balda fuera de tarifa (consultar)", \
               f"profundidad {ancho_cm:.0f}cm o largo {largo_cm:.0f}cm superan los tramos de la tabla → consultar"
    base = _BALDA_BASE[tramo_ancho][tramo_largo]
    # match por substring + alias laminado=melamina ("Laminado Olmo Caramelo")
    mat_texto = _norm(material)
    if "laminad" in mat_texto:
        p_mat = float(_BALDA_MATERIAL.get("melamina", _BALDA_MATERIAL.get("melamina stock", 0.0)))
        mat_label = "laminado (=melamina)"
    else:
        p_mat = _pct_por_clave(mat_texto, _BALDA_MATERIAL, default=0.0)
        mat_label = material or "laca blanca"
    p_gros = _pct_por_tramo(grosor_mm, _BALDA_GROSOR)
    if p_gros is None:
        return CONSULTAR, "balda (grosor consultar)", f"grosor {grosor_mm:.0f}mm supera el último tramo → consultar"
    precio = round(base * (1 + p_mat + p_gros), 2)
    detalle = _explica(base, [(f"material {mat_label}", p_mat), (f"grosor {grosor_mm:.0f}mm", p_gros)], precio)
    detalle = f"tabla prof.≤{tramo_ancho}mm × largo≤{tramo_largo}mm → " + detalle
    return precio, f"Balda {ancho_cm:.0f}×{largo_cm:.0f}cm", detalle


# ─────────────────────────────────────────────────────────────────────────────
# PUERTAS DE PASO   ·  normal (base 370 €) y rasomuro/oculta (base 720 €)
# ─────────────────────────────────────────────────────────────────────────────
def _labrado_paso_pct(texto: str) -> float:
    """
    Recargo por tipo de puerta DE PASO detectado en texto libre (raíces para
    tolerar plafonada/plafonado, fresada/fresado…). Porcentajes de la tarifa
    de puerta de paso (distintos de los de puerta de armario).
    """
    t = texto
    if "pantograf" in t and ("plafon" in t or "moldura" in t):
        return 0.90
    if "plafon" in t or "moldura" in t:
        return 0.70 if "complej" in t else 0.60
    if "fresad" in t:
        return 0.60 if "3d" in t else (0.42 if "complej" in t else 0.30)
    if "pantograf" in t:
        return 0.15 if "sencill" in t else 0.25
    return 0.0

def _paso_tabla(cfg: dict) -> dict:
    # "extras" es OPCIONAL (tarifas guardadas antes de existir): € fijos por puerta.
    return {"base": cfg["base"], "alto": cfg["alto_mm"], "ancho": cfg["ancho_mm"],
            "grosor": cfg["grosor_mm"], "acabado": cfg["acabado"], "corredera": cfg["corredera"],
            "extras": cfg.get("extras") or {}}


_PASO_NORMAL = _paso_tabla(CFG["puerta_paso_normal"])
_PASO_RASOMURO = _paso_tabla(CFG["puerta_paso_rasomuro"])


def precio_puerta_paso(ancho_cm: float, alto_cm: float, tipo: str = "lisa",
                       acabado: str = "laca blanca", grosor_mm: float = 40,
                       rasomuro: bool = False,
                       extras: Optional[list[str]] = None) -> Tuple[Optional[float], str, str]:
    """`extras`: claves de tabla["extras"] (p.ej. "bisagras_ocultas") que se
    suman en € por puerta tras aplicar los porcentajes."""
    if ancho_cm <= 0 or alto_cm <= 0:
        return CONSULTAR, "puerta de paso sin medidas (consultar)", "faltan medidas de la puerta"
    tabla = _PASO_RASOMURO if rasomuro else _PASO_NORMAL
    # tipo + acabado juntos: la visión mezcla el labrado en cualquiera de los dos
    texto = f"{_norm(tipo)} {_norm(acabado)}"
    p_alto = _pct_por_tramo(alto_cm * 10, tabla["alto"])
    p_ancho = _pct_por_tramo(ancho_cm * 10, tabla["ancho"])
    if None in (p_alto, p_ancho):
        return CONSULTAR, "puerta de paso fuera de tarifa (consultar)", \
               f"ancho {ancho_cm:.0f}cm o alto {alto_cm:.0f}cm superan el último tramo → consultar"
    p_gros = 0.0
    if tabla["grosor"] is not None:
        p_gros = _pct_por_tramo(grosor_mm, tabla["grosor"])
        if p_gros is None:
            return CONSULTAR, "puerta de paso (grosor consultar)", f"grosor {grosor_mm:.0f}mm fuera de tramos → consultar"
    p_tipo = _labrado_paso_pct(texto)             # raíces: plafonada/fresada/pantografiada…
    p_acab = _pct_por_clave(texto, tabla["acabado"])  # substring + género normalizado
    p_corr = tabla["corredera"] if (tabla["corredera"] and "corredera" in texto) else 0.0
    precio = tabla["base"] * (1 + p_alto + p_ancho + p_gros + p_tipo + p_acab + p_corr)
    extras_txt, sin_precio = [], []
    for clave in (extras or []):
        if clave in tabla["extras"]:
            v = float(tabla["extras"][clave])
            precio += v
            extras_txt.append(f"{v:g}€ {clave.replace('_', ' ')}")
        else:
            sin_precio.append(clave.replace("_", " "))
    precio = round(precio, 2)
    etiqueta = "rasomuro" if rasomuro else "normal"
    factores = [(f"alto {alto_cm:.0f}cm", p_alto), (f"ancho {ancho_cm:.0f}cm", p_ancho)]
    if tabla["grosor"] is not None:
        factores.append((f"grosor {grosor_mm:.0f}mm", p_gros))
    if p_tipo:
        factores.append(("tipo de puerta (labrado)", p_tipo))
    factores.append(("acabado", p_acab))
    if p_corr:
        factores.append(("corredera", p_corr))
    detalle = f"tarifa puerta de paso {etiqueta} → " + _explica(tabla["base"], factores, precio, extras_txt)
    if sin_precio:
        detalle += f" (extra sin precio en la tarifa {etiqueta}, no incluido: {', '.join(sin_precio)})"
    return precio, f"Puerta de paso {etiqueta} {ancho_cm:.0f}×{alto_cm:.0f}cm", detalle

# ─────────────────────────────────────────────────────────────────────────────
# RECARGA EN CALIENTE
# ─────────────────────────────────────────────────────────────────────────────

def _es_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_tramos(nombre: str, tramos) -> None:
    """Tramos = lista no vacía de [límite_mm, pct] numéricos, límites ascendentes."""
    if not isinstance(tramos, list) or not tramos:
        raise ValueError(f"«{nombre}»: la lista de tramos no puede estar vacía")
    prev = None
    for t in tramos:
        if not (isinstance(t, list) and len(t) == 2 and _es_num(t[0]) and _es_num(t[1])):
            raise ValueError(f"«{nombre}»: cada tramo debe ser [límite_mm, porcentaje] numéricos")
        if t[0] <= 0:
            raise ValueError(f"«{nombre}»: el límite de tramo debe ser > 0 (hay un {t[0]})")
        if prev is not None and t[0] <= prev:
            raise ValueError(f"«{nombre}»: los límites deben ir en orden ascendente ({prev} → {t[0]})")
        prev = t[0]


def _check_num(nombre: str, v) -> None:
    if not _es_num(v):
        raise ValueError(f"«{nombre}» debe ser un número (recibido: {v!r})")


def _check_dict_num(nombre: str, d) -> None:
    if not isinstance(d, dict) or not d:
        raise ValueError(f"«{nombre}» debe ser un diccionario no vacío")
    for k, v in d.items():
        if not _es_num(v):
            raise ValueError(f"«{nombre}.{k}» debe ser un número (recibido: {v!r})")


def _build_tables(cfg: dict) -> dict:
    """
    VALIDA el config en profundidad y construye todas las tablas del módulo.
    Lanza ValueError con mensaje claro si algo está mal — sin efectos laterales.
    """
    requeridas = {"modulo", "puerta_armario", "interiores", "balda_pared",
                  "puerta_paso_normal", "puerta_paso_rasomuro", "vestidor"}
    faltan = requeridas - set(cfg.keys())
    if faltan:
        raise ValueError(f"Faltan secciones en la tarifa: {sorted(faltan)}")
    for s in requeridas:
        if not isinstance(cfg[s], dict):
            raise ValueError(f"La sección «{s}» debe ser un objeto con sus claves, no {cfg[s]!r}")

    try:
        mod, parm, _int, bal = cfg["modulo"], cfg["puerta_armario"], cfg["interiores"], cfg["balda_pared"]
    except KeyError as e:  # defensivo; ya validado arriba
        raise ValueError(f"Falta la sección {e}")
    _check_num("modulo.base", mod["base"])
    _check_tramos("modulo.alto_mm", mod["alto_mm"])
    _check_tramos("modulo.ancho_mm", mod["ancho_mm"])
    _check_tramos("modulo.fondo_mm", mod["fondo_mm"])
    _check_num("modulo.descuento_dimension_max", mod["descuento_dimension_max"])
    _check_dict_num("modulo.acabado", mod["acabado"])
    _check_num("puerta_armario.base", parm["base"])
    _check_tramos("puerta_armario.alto_mm", parm["alto_mm"])
    _check_tramos("puerta_armario.ancho_mm", parm["ancho_mm"])
    _check_tramos("puerta_armario.corredera_ancho_mm", parm["corredera_ancho_mm"])
    _check_dict_num("puerta_armario.acabado", parm["acabado"])
    _check_num("puerta_armario.costado_visto", parm.get("costado_visto", 120))
    _check_tramos("interiores.cajon_cajonera_mm", _int["cajon_cajonera_mm"])
    _check_tramos("interiores.cajon_suelto_mm", _int["cajon_suelto_mm"])
    for k in ("balda", "barra_perchero", "sensor", "tira_led_ml"):
        _check_num(f"interiores.{k}", _int[k])
    _check_num("interiores.tira_led_minimo", _int.get("tira_led_minimo", 250))
    _check_dict_num("balda_pared.material", bal["material"])
    _check_tramos("balda_pared.grosor_mm", bal["grosor_mm"])
    balda_base = {int(a): {int(l): v for l, v in cols.items()} for a, cols in bal["base"].items()}
    for a, cols in balda_base.items():
        for l, v in cols.items():
            _check_num(f"balda_pared.base[{a}][{l}]", v)
    for seccion in ("puerta_paso_normal", "puerta_paso_rasomuro"):
        pp = cfg[seccion]
        _check_num(f"{seccion}.base", pp["base"])
        _check_tramos(f"{seccion}.alto_mm", pp["alto_mm"])
        _check_tramos(f"{seccion}.ancho_mm", pp["ancho_mm"])
        if pp.get("grosor_mm") is not None:
            _check_tramos(f"{seccion}.grosor_mm", pp["grosor_mm"])
        if pp.get("corredera") is not None:
            _check_num(f"{seccion}.corredera", pp["corredera"])
        _check_dict_num(f"{seccion}.acabado", pp["acabado"])
        if pp.get("extras") not in (None, {}):  # opcional (null/{} = sin extras); si no, € numéricos
            _check_dict_num(f"{seccion}.extras", pp["extras"])
    _check_num("vestidor.remate_ml", cfg["vestidor"]["remate_ml"])

    return {
        "CFG": cfg,
        "_MOD_BASE": mod["base"], "_MOD_ALTO": mod["alto_mm"],
        "_MOD_ANCHO": mod["ancho_mm"], "_MOD_FONDO": mod["fondo_mm"],
        "_MOD_DESCUENTO_DIM_MAX": mod["descuento_dimension_max"],
        "_MOD_ACABADO": mod["acabado"],
        "_PARM_BASE": parm["base"], "_PARM_ALTO": parm["alto_mm"],
        "_PARM_ANCHO": parm["ancho_mm"], "_PARM_CORREDERA_ANCHO": parm["corredera_ancho_mm"],
        "_MATERIAL_PUERTA": _material_puerta_desde_cfg(parm["acabado"]),
        "_INT": _int,
        "_CAJON_CAJONERA": _int["cajon_cajonera_mm"],
        "_CAJON_SUELTO": _int["cajon_suelto_mm"],
        "_INTERIOR_FIJOS": [
            (("balda", "estante"), _int["balda"], "Balda de interior"),
            (("barra", "perchero"), _int["barra_perchero"], "Barra perchero"),
            (("sensor",), _int["sensor"], "Sensor de puerta"),
            (("led",), _int["tira_led_ml"], "Tira LED 2700k (por ml)"),
        ],
        "_BAL": bal,
        "_BALDA_LARGO_TRAMOS": bal["largo_tramos_mm"],
        "_BALDA_BASE": balda_base,
        "_BALDA_MATERIAL": bal["material"],
        "_BALDA_GROSOR": bal["grosor_mm"],
        "_PASO_NORMAL": _paso_tabla(cfg["puerta_paso_normal"]),
        "_PASO_RASOMURO": _paso_tabla(cfg["puerta_paso_rasomuro"]),
    }


def reload() -> dict:
    """
    Relee tarifa_config.json, lo valida y reaplica todos los valores SIN
    reiniciar el servidor. Si el archivo es inválido, lanza ValueError y NO
    toca el estado en memoria (se sigue calculando con la tarifa anterior).
    """
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        nuevo = json.load(f)
    try:
        tablas = _build_tables(nuevo)   # valida TODO antes de tocar nada
    except KeyError as e:
        raise ValueError(f"Falta la clave {e} en la tarifa")
    globals().update(tablas)        # aplicación en un solo paso
    return nuevo


def save_config(nuevo_cfg: dict) -> dict:
    """
    Valida en profundidad, persiste ATÓMICAMENTE (tmp + os.replace) y recarga
    en caliente. Si la validación falla, ni el disco ni la memoria cambian.
    """
    import tempfile

    try:
        tablas = _build_tables(nuevo_cfg)  # ← valida ANTES de escribir
    except KeyError as e:
        raise ValueError(f"Falta la clave {e} en la tarifa")

    # Escritura atómica: nunca queda un JSON a medias en disco.
    dir_cfg = os.path.dirname(_CONFIG_PATH)
    fd, tmp_path = tempfile.mkstemp(dir=dir_cfg, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(nuevo_cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, _CONFIG_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    globals().update(tablas)
    return nuevo_cfg
