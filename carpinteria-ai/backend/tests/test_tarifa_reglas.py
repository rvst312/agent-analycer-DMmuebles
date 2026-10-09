"""
Reglas de negocio de la tarifa (pricing por partidas). Cada test reproduce un
caso real que el motor presupuestaba mal y fija el precio EXACTO esperado con
la tarifa por defecto (agents/tarifa_config.json).
"""
import copy

import pytest

from agents import pricing_agent, tarifa
from agents.pricing_agent import _price_partidas
from api.schemas.estimate import ItemInteriorArmario, Partida, PuertaArmario


@pytest.fixture(autouse=True)
def _sin_rag(monkeypatch):
    """Ninguna de estas reglas debe consultar la Base de Precios (Chroma)."""
    def _no_rag(*_a, **_k):
        raise AssertionError("_rag_lookup no debería llamarse en estas reglas")
    monkeypatch.setattr(pricing_agent, "_rag_lookup", _no_rag)


def _precios(*partidas):
    lineas, total, titulos, descripciones, _faltan = _price_partidas(list(partidas), "general")
    return lineas, total, titulos, descripciones


def _puerta_paso(**kw):
    datos = dict(familia="puerta_paso_abatible", ref="P1", ancho_cm=82, alto_cm=203)
    datos.update(kw)
    return Partida(**datos)


def _armario(**kw):
    datos = dict(familia="armario", ref="A1", habitacion="Dormitorio 1",
                 ancho_cm=120, alto_cm=240, fondo_cm=60,
                 puertas=[PuertaArmario(tipo="abatible", ancho_cm=60, alto_cm=240,
                                        acabado="laca blanca", cantidad=2)])
    datos.update(kw)
    return Partida(**datos)


# ── 1) "bisagras ocultas" es un EXTRA de 150€, no una puerta rasomuro ───────

def test_1_bisagras_ocultas_es_extra_no_rasomuro():
    lineas, total, _t, _d = _precios(_puerta_paso(
        descripcion="Puerta pantografiada", ancho_cm=82, alto_cm=240,
        acabado="pantografiada", notas="Bisagras ocultas", cantidad=2))
    assert len(lineas) == 1
    l = lineas[0]
    # 370 × (1 + 0.30 alto ≤2400 + 0.25 pantografiado) = 573.50 + 150 bisagras ocultas
    assert l.precio_unitario == 723.5
    assert l.cantidad == 2 and l.subtotal == 1447.0 and total == 1447.0
    assert l.precio_pendiente is False
    assert "rasomuro" not in l.descripcion
    assert "· bisagras ocultas" in l.descripcion
    assert "150€ bisagras ocultas" in l.explicacion


@pytest.mark.parametrize("notas", ["con guías ocultas", "herrajes ocultos y bisagras tipo cazoleta ocultas",
                                   "tirador oculto", "cerradura oculta"])
def test_1_oculta_de_herraje_no_es_rasomuro(notas):
    lineas, _total, _t, _d = _precios(_puerta_paso(descripcion="Puerta lisa", notas=notas))
    assert "tarifa puerta de paso normal" in lineas[0].explicacion


@pytest.mark.parametrize("descripcion", ["Puerta oculta", "Puerta enrasada", "Hoja oculta lacada",
                                         "Puerta rasomuro", "Puerta raso muro", "Puertas ocultas en pasillo"])
def test_1_puerta_oculta_si_es_rasomuro(descripcion):
    lineas, _total, _t, _d = _precios(_puerta_paso(descripcion=descripcion))
    assert lineas[0].precio_unitario == 720.0
    assert "· rasomuro" in lineas[0].descripcion


def test_1_bisagras_ocultas_con_palabras_en_medio():
    lineas, _total, _t, _d = _precios(_puerta_paso(descripcion="Puerta lisa",
                                                  notas="bisagras Tectus ocultas"))
    assert "tarifa puerta de paso normal" in lineas[0].explicacion
    assert lineas[0].precio_unitario == 370 + 150


def test_1_extras_resbalon_plintos_y_autocierre():
    normal, rasomuro = _precios(
        _puerta_paso(ref="P1", descripcion="Puerta lisa", notas="resbalón magnético y plintos"),
        _puerta_paso(ref="P2", descripcion="Puerta rasomuro", notas="autocierre sin manivela"),
    )[0]
    assert normal.precio_unitario == 370 + 30 + 80
    assert "· resbalón magnético" in normal.descripcion and "· plintos" in normal.descripcion
    assert rasomuro.precio_unitario == 720 + 150
    assert "· autocierre sin manivela" in rasomuro.descripcion


def test_1_extras_opcionales_y_validados_en_config():
    sin_extras = copy.deepcopy(tarifa.CFG)
    del sin_extras["puerta_paso_normal"]["extras"]
    tablas = tarifa._build_tables(sin_extras)          # tarifa antigua sin «extras» → válida
    assert tablas["_PASO_NORMAL"]["extras"] == {}
    roto = copy.deepcopy(tarifa.CFG)
    roto["puerta_paso_normal"]["extras"]["bisagras_ocultas"] = "150€"
    with pytest.raises(ValueError, match="extras.bisagras_ocultas"):
        tarifa._build_tables(roto)
    nulo = copy.deepcopy(tarifa.CFG)
    nulo["puerta_paso_normal"]["extras"] = None        # null = sin extras → válido
    assert tarifa._build_tables(nulo)["_PASO_NORMAL"]["extras"] == {}
    for malo in (False, 0, [], "150"):
        cfg = copy.deepcopy(tarifa.CFG)
        cfg["puerta_paso_normal"]["extras"] = malo
        with pytest.raises(ValueError, match="puerta_paso_normal.extras"):
            tarifa._build_tables(cfg)


# ── 2) Grosor de balda y nº de baldas ────────────────────────────────────────

def test_2_grosor_balda_40mm():
    lineas, total, _t, _d = _precios(Partida(
        familia="balda_pared", ref="B1", descripcion="Estantería", ancho_cm=60, fondo_cm=30,
        material="Laminado Olmo Caramelo", notas="Grosor balda 40mm", cantidad=6))
    l = lineas[0]
    # base 85 (prof.≤300 × largo≤600) × (1 − 0.20 laminado + 0.20 grosor 40mm)
    assert l.precio_unitario == 85.0
    assert l.cantidad == 6 and total == 510.0
    assert "grosor 40mm" in l.descripcion


def test_2_grosor_en_acabado_y_en_cm():
    lineas, _total, _t, _d = _precios(Partida(
        familia="balda_pared", ref="B1", descripcion="Balda", ancho_cm=60, fondo_cm=30,
        material="laca blanca", acabado="lacada mate, grosor de la balda 4cm"))
    assert lineas[0].precio_unitario == 102.0      # 85 × (1 + 0.20 grosor 40mm)


def test_2_numero_de_baldas_desde_items_interiores():
    lineas, _total, _t, _d = _precios(Partida(
        familia="balda_pared", ref="B1", descripcion="Estantería", ancho_cm=60, fondo_cm=30,
        material="laca blanca", cantidad=1,
        items_interiores=[ItemInteriorArmario(tipo="balda", cantidad=4)]))
    assert lineas[0].cantidad == 4
    assert lineas[0].subtotal == 4 * 85.0


def test_2_led_vertical_usa_el_alto():
    lineas, _total, _t, _d = _precios(Partida(
        familia="balda_pared", ref="B1", descripcion="Estantería con LED vertical",
        ancho_cm=60, alto_cm=240, fondo_cm=30, material="laca blanca",
        items_interiores=[ItemInteriorArmario(tipo="tira LED", cantidad=3)]))
    led = [l for l in lineas if l.descripcion.startswith("Iluminación LED")]
    assert len(led) == 1
    # alto 240cm × 3 tiras = 7.2 ml × 45€ = 324€ (con el ancho saldría el mínimo de 250€)
    assert led[0].precio_unitario == 324.0
    assert "alto 240cm" in led[0].explicacion


def test_2_led_vertical_indicado_en_el_item():
    lineas, _total, _t, _d = _precios(Partida(
        familia="balda_pared", ref="B1", descripcion="Estantería", ancho_cm=60, alto_cm=240,
        fondo_cm=30, material="laca blanca",
        items_interiores=[ItemInteriorArmario(tipo="tira LED vertical", cantidad=3)]))
    led = [l for l in lineas if l.descripcion.startswith("Iluminación LED")]
    assert len(led) == 1 and led[0].precio_unitario == 324.0


# ── 3) Maletero/altillo incluido, huecos sin coste, zapatero = balda ─────────

def test_3_maletero_altillo_hueco_y_zapatero():
    lineas, total, _t, _d = _precios(_armario(items_interiores=[
        ItemInteriorArmario(tipo="maletero", cantidad=1),
        ItemInteriorArmario(tipo="Altillo", cantidad=2),
        ItemInteriorArmario(tipo="hueco libre", cantidad=1),
        ItemInteriorArmario(tipo="espacio abierto", cantidad=1),
        ItemInteriorArmario(tipo="zapatero", cantidad=3),
        ItemInteriorArmario(tipo="baldas zapatos", cantidad=2),
        ItemInteriorArmario(tipo="zapatero extraíble", cantidad=1),
    ]))
    maleteros = [l for l in lineas if l.descripcion == "Maletero/altillo — incluido en el módulo"]
    assert len(maleteros) == 2
    assert all(l.precio_unitario == 0.0 and l.precio_pendiente is False for l in maleteros)
    assert "Módulo + maletero" in maleteros[0].explicacion

    huecos = [l for l in lineas if "hueco sin coste" in l.descripcion]
    assert len(huecos) == 2
    assert all(l.precio_unitario == 0.0 and l.precio_pendiente is False for l in huecos)

    zapateros = [l for l in lineas if l.descripcion.startswith("Balda zapatero")]
    assert [(l.cantidad, l.precio_unitario) for l in zapateros] == [(3, 20.0), (2, 20.0)]
    assert all(l.precio_pendiente is False for l in zapateros)

    extraible = [l for l in lineas if "zapatero extraíble" in l.descripcion]
    assert len(extraible) == 1 and extraible[0].precio_pendiente is True

    # cuerpo 700 + 2 puertas × 160 + 5 baldas zapatero × 20
    assert total == 700 + 320 + 100


# ── 4) Puerta acorazada/blindada → consultar ─────────────────────────────────

@pytest.mark.parametrize("descripcion", ["Puerta acorazada de entrada", "Puerta blindada",
                                         "Puerta de seguridad", "Hoja antirrobo"])
def test_4_acorazada_queda_pendiente(descripcion):
    lineas, total, _t, _d = _precios(_puerta_paso(descripcion=descripcion))
    assert len(lineas) == 1
    assert lineas[0].precio_pendiente is True
    assert lineas[0].explicacion == "puerta acorazada/blindada: fuera de tarifa → consultar"
    assert total == 0.0


def test_4_cerradura_de_seguridad_es_puerta_normal():
    lineas, total, _t, _d = _precios(_puerta_paso(descripcion="Puerta lisa",
                                                  notas="con cerradura de seguridad"))
    assert lineas[0].precio_pendiente is False
    assert lineas[0].precio_unitario == 370.0 and total == 370.0


# ── 5) Reutilizado / se mantiene → no se presupuesta ─────────────────────────

def test_5_reutilizado_no_se_presupuesta():
    lineas, total, titulos, descripciones = _precios(
        _puerta_paso(ref="P1", descripcion="Puerta de paso", habitacion="Baño", notas="Se reutiliza"),
        _armario(ref="A1", descripcion="Armario existente, se mantiene"),
    )
    assert len(lineas) == 2                     # una sola línea por partida (el armario no se desglosa)
    puerta, armario = lineas
    assert puerta.descripcion == "Puerta de paso — 82×203cm — no se presupuesta (reutilizado/existente)"
    assert armario.descripcion.endswith("— no se presupuesta (reutilizado/existente)")
    assert all(l.precio_unitario == 0.0 and l.precio_pendiente is False for l in lineas)
    assert total == 0.0
    assert titulos["P1"] == "P1 - Puerta de paso abatible Baño"
    assert titulos["A1"] == "A1 - Armario Dormitorio 1"
    assert descripciones["A1"].startswith("Suministro e instalación de armario")


@pytest.mark.parametrize("notas", ["se reutilizan las hojas", "Se conservan", "reutilizada",
                                   "No se presupuesta", "incluido en muebles de cocina"])
def test_5_variantes_de_reutilizado(notas):
    lineas, total, _t, _d = _precios(_puerta_paso(descripcion="Puerta", notas=notas))
    assert len(lineas) == 1 and lineas[0].precio_pendiente is False and total == 0.0


def test_5_igualando_al_existente_si_se_presupuesta():
    lineas, total, _t, _d = _precios(_puerta_paso(descripcion="Puerta lisa",
                                                  notas="lacada igualando al existente"))
    assert lineas[0].precio_unitario == 370.0 and total == 370.0


def test_5_interior_reutilizado_sin_coste():
    lineas, total, _t, _d = _precios(_armario(items_interiores=[
        ItemInteriorArmario(tipo="interior reutilizado", cantidad=1)]))
    reut = [l for l in lineas if "reutilizado" in l.descripcion.lower()]
    assert len(reut) == 1
    assert reut[0].descripcion == "Interior reutilizado — sin coste"
    assert reut[0].precio_unitario == 0.0 and reut[0].precio_pendiente is False
    assert total == 700 + 320


# ── 6) Puertas simuladas / solo frentes → sin cuerpo ─────────────────────────

@pytest.mark.parametrize("descripcion", ["Puertas simuladas", "Armario solo frentes", "Frente sin cuerpo"])
def test_6_puertas_simuladas_sin_cuerpo(descripcion):
    lineas, total, _t, _d = _precios(_armario(descripcion=descripcion))
    assert not any(l.descripcion.startswith("Cuerpo de armario") for l in lineas)
    solo = [l for l in lineas if l.descripcion == "Solo frentes (sin cuerpo de armario)"]
    assert len(solo) == 1 and solo[0].precio_unitario == 0.0 and solo[0].precio_pendiente is False
    puertas = [l for l in lineas if l.descripcion.startswith("Puerta armario")]
    assert len(puertas) == 1 and puertas[0].cantidad == 2 and puertas[0].precio_unitario == 160.0
    assert total == 320.0


# ── 7) Puerta de paso "estándar" sin alto → 2030×725 ─────────────────────────

def test_7_puerta_estandar_sin_medidas():
    lineas, total, _t, _d = _precios(_puerta_paso(descripcion="Puerta de paso estándar",
                                                  ancho_cm=0, alto_cm=0))
    l = lineas[0]
    assert l.precio_pendiente is False and l.precio_unitario == 370.0 and total == 370.0
    assert "(medidas estándar 2030×725)" in l.descripcion
    assert "(medidas estándar 2030×725)" in l.explicacion


def test_7_sin_pista_de_estandar_sigue_pendiente():
    lineas, total, _t, _d = _precios(_puerta_paso(descripcion="Puerta de paso", ancho_cm=0, alto_cm=0))
    assert lineas[0].precio_pendiente is True and total == 0.0


# ── Regla existente: la melamina siempre es lisa ─────────────────────────────

def test_melamina_siempre_lisa():
    precio, _desc, expl = tarifa.precio_puerta_armario(60, 240, "abatible", "melamina plafonada")
    assert precio == 120.0                       # 160 × (1 − 0.25 melamina), sin +60% plafón
    assert "labrado ignorado" in expl


def test_puerta_paso_con_alto_y_sin_ancho_se_presupuesta_hasta_825():
    """CARACAS 11: la planta marca las puertas con puntos (alto 240/270, sin ancho)."""
    from agents.pricing_agent import _price_partidas
    from api.schemas.estimate import Partida
    lineas, *_ = _price_partidas([Partida(
        familia="puerta_paso_abatible", descripcion="Puerta de paso abatible pantografiada blanca, altura especial 240 cm",
        ancho_cm=0, alto_cm=240, material="DM lacado blanco", acabado="pantografiada blanca", cantidad=5, ref="PA12")], "general")
    l = lineas[0]
    assert not l.precio_pendiente
    assert l.precio_unitario == 573.5  # 370 × (1 + 0.30 alto ≤2400 + 0.25 pantografiado)
    assert "ancho no acotado" in l.descripcion
