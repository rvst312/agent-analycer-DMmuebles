"""
Tests del agente de visión (pasada de códigos de vista + pasada de PARTIDAS).

Se mockea `anthropic.Anthropic`: `messages.create` atiende la pasada rápida de
códigos de vista y `messages.stream` (context manager) la pasada de partidas.
"""
import os
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from agents import vision_agent
from agents.vision_agent import (GLOSARIO, VISION_FAST_MODEL, VISION_MODEL,
                                 _detect_view_codes, analyze_plan)
from core.plan_images import extract_pdf_text_pages

DUMMY_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
PDF_ROSALES = os.path.join(os.path.dirname(__file__), "..", "uploads",
                           "c55820d5-38d1-4848-bf98-43118e493900_1.pdf")

PARTIDAS_OK = """<raw_reasoning>
Veo un armario de dos puertas abatibles en el Dormitorio 2.
</raw_reasoning>
<output_format>
{
  "proyecto": "Rosales 12",
  "partidas": [
    {
      "familia": "armario", "descripcion": "Armario 2 puertas", "habitacion": "Dormitorio 2",
      "ancho_cm": 120.0, "alto_cm": 240.0, "fondo_cm": 60.0,
      "material": "melamina blanca", "material_interior": "melamina textil", "acabado": "lisa",
      "apertura": "abatible", "cantidad": 1, "ref": "A01", "notas": "",
      "pagina": 1, "bbox_pct": [0, 0, 100, 100],
      "modulos": [], "puertas": [], "items_interiores": []
    }
  ],
  "confidence_score": 0.9
}
</output_format>"""


def _block(tipo: str, text: str = "") -> MagicMock:
    b = MagicMock()
    b.type = tipo
    if tipo == "text":
        b.text = text
    else:
        b.thinking = ""  # el thinking llega vacío (display "omitted")
    return b


def _response(text: str, stop_reason: str = "end_turn", con_thinking: bool = True) -> MagicMock:
    r = MagicMock()
    r.stop_reason = stop_reason
    r.content = ([_block("thinking")] if con_thinking else []) + [_block("text", text)]
    return r


def _cliente(mock_anthropic, partidas_text: str = PARTIDAS_OK, codigos: str = "A01",
             stop_reason: str = "end_turn") -> MagicMock:
    """Cliente mock: create → códigos de vista; stream → partidas."""
    client = MagicMock()
    mock_anthropic.return_value = client
    client.messages.create.return_value = _response(codigos)
    final = client.messages.stream.return_value.__enter__.return_value
    final.get_final_message.return_value = _response(partidas_text, stop_reason)
    return client


def _stream_kwargs(client) -> dict:
    client.messages.stream.assert_called_once()
    return client.messages.stream.call_args.kwargs


# ── pasada de partidas ──────────────────────────────────────────────────────

@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_success(mock_anthropic):
    client = _cliente(mock_anthropic)

    result = analyze_plan(DUMMY_B64, plano_id="p1")

    assert result.error is None
    assert result.tipo_plano == "partidas"
    assert result.proyecto == "Rosales 12"
    assert len(result.partidas) == 1
    p = result.partidas[0]
    assert (p.familia, p.ref, p.ancho_cm, p.apertura) == ("armario", "A01", 120.0, "abatible")
    assert result.confidence_score == 0.9
    assert "armario de dos puertas" in result.raw_reasoning  # el bloque thinking se ignora

    kw = _stream_kwargs(client)
    assert kw["model"] == VISION_MODEL
    assert kw["max_tokens"] == 64000
    # display "summarized" mantiene vivo el stream mientras piensa (sin él, cuelgue de >10 min)
    assert kw["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert kw["output_config"] == {"effort": "medium"}
    content = kw["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["data"] == DUMMY_B64
    assert "<instructions>" in content[-1]["text"]


@patch("agents.vision_agent.anthropic.Anthropic")
def test_glosario_y_familias_en_system_con_cache(mock_anthropic):
    client = _cliente(mock_anthropic)

    analyze_plan(DUMMY_B64, plano_id="p1")

    assert GLOSARIO, "agents/glosario_planos.md debe cargarse al importar"
    system = _stream_kwargs(client)["system"]
    assert isinstance(system, list) and len(system) == 1
    assert system[0]["type"] == "text"
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    texto = system[0]["text"]
    assert texto.startswith(vision_agent.SYSTEM_PROMPT)
    assert vision_agent._FAMILIAS_DOC in texto
    assert f"<glosario_planos>\n{GLOSARIO}\n</glosario_planos>" in texto

    # El mensaje de usuario solo lleva lo variable y remite al glosario.
    prompt = _stream_kwargs(client)["messages"][0]["content"][-1]["text"]
    assert vision_agent._FAMILIAS_DOC not in prompt
    assert "Aplica el <glosario_planos> del sistema" in prompt


@patch("agents.vision_agent.anthropic.Anthropic")
def test_texto_del_pdf_en_el_contenido(mock_anthropic):
    client = _cliente(mock_anthropic)
    paginas = [b"jpeg-pagina-1", b"jpeg-pagina-2"]

    analyze_plan(DUMMY_B64, media_type="application/pdf", plano_id="p1", page_images=paginas,
                 pdf_text_pages=["MEDICIONES ROSALES\n15.01 Partida ud PE1 - PUERTA", ""])

    content = _stream_kwargs(client)["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "image", "text", "text"]
    texto_pdf = content[2]["text"]
    assert texto_pdf.startswith("<texto_del_pdf>") and texto_pdf.endswith("</texto_del_pdf>")
    assert "— página 1 —\nMEDICIONES ROSALES" in texto_pdf
    assert "— página 2 —" not in texto_pdf  # las páginas sin texto no se envían
    assert "<instructions>" in content[3]["text"]


@patch("agents.vision_agent.anthropic.Anthropic")
def test_texto_del_pdf_se_trunca_con_aviso(mock_anthropic):
    client = _cliente(mock_anthropic)

    analyze_plan(DUMMY_B64, plano_id="p1", pdf_text_pages=["x" * 40_000, "y" * 40_000])

    texto_pdf = _stream_kwargs(client)["messages"][0]["content"][1]["text"]
    assert "[texto truncado]" in texto_pdf
    assert len(texto_pdf) < vision_agent._MAX_TEXTO_PDF + 2_000


@patch("agents.vision_agent.anthropic.Anthropic")
def test_sin_texto_del_pdf_no_hay_bloque(mock_anthropic):
    client = _cliente(mock_anthropic)

    analyze_plan(DUMMY_B64, plano_id="p1", pdf_text_pages=["", "   "])

    content = _stream_kwargs(client)["messages"][0]["content"]
    assert not any("<texto_del_pdf>" in (b.get("text") or "") for b in content)


@patch("agents.vision_agent.anthropic.Anthropic")
def test_refusal_devuelve_error(mock_anthropic):
    _cliente(mock_anthropic, stop_reason="refusal")

    result = analyze_plan(DUMMY_B64, plano_id="p1")

    assert result.partidas == []
    assert result.confidence_score == 0.0
    assert result.error == "La visión rechazó el análisis (refusal)"


@patch("agents.vision_agent.anthropic.Anthropic")
def test_sdk_sin_kwargs_nuevos_usa_extra_body(mock_anthropic):
    client = _cliente(mock_anthropic)
    gestor = client.messages.stream.return_value
    client.messages.stream.side_effect = [TypeError("unexpected keyword 'thinking'"), gestor]

    result = analyze_plan(DUMMY_B64, plano_id="p1")

    assert result.error is None and len(result.partidas) == 1
    segunda = client.messages.stream.call_args_list[1].kwargs
    assert "thinking" not in segunda and "output_config" not in segunda
    assert segunda["extra_body"] == {"thinking": {"type": "adaptive", "display": "summarized"},
                                     "output_config": {"effort": "medium"}}


@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_json_error(mock_anthropic):
    _cliente(mock_anthropic, partidas_text="""<raw_reasoning>test</raw_reasoning>
<output_format>
{
  "proyecto": "x",
  invalid json
}
</output_format>""")

    result = analyze_plan(DUMMY_B64)

    assert result.confidence_score == 0.0
    assert result.error is not None and "JSON parse error" in result.error
    assert result.raw_reasoning == "test"


@patch("agents.vision_agent.anthropic.Anthropic")
def test_partida_invalida_se_descarta(mock_anthropic):
    _cliente(mock_anthropic, partidas_text="""<raw_reasoning>test validation</raw_reasoning>
<output_format>
{"partidas": [
  {"familia": "rodapie", "ancho_cm": 520, "alto_cm": 10, "cantidad": "muchas", "ref": "R1"},
  {"familia": "rodapie", "ancho_cm": 300, "alto_cm": 10, "cantidad": 1, "ref": "R2"}
], "confidence_score": 0.5}
</output_format>""")

    result = analyze_plan(DUMMY_B64)

    assert result.error is None
    assert [p.ref for p in result.partidas] == ["R2"]
    assert result.raw_reasoning == "test validation"


@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_markdown_json(mock_anthropic):
    _cliente(mock_anthropic, partidas_text="""<raw_reasoning>test markdown json</raw_reasoning>
<output_format>
```json
{"proyecto": "Goya 23", "partidas": [], "confidence_score": 0.8}
```
</output_format>""")

    result = analyze_plan(DUMMY_B64)

    assert result.error is None
    assert result.proyecto == "Goya 23"
    assert result.confidence_score == 0.8
    assert result.raw_reasoning == "test markdown json"


@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_missing_tags(mock_anthropic):
    _cliente(mock_anthropic, partidas_text="""Here is the result:
{"proyecto": "", "partidas": [], "confidence_score": 0.7}""")

    result = analyze_plan(DUMMY_B64)

    assert result.error is None
    assert result.confidence_score == 0.7
    assert result.raw_reasoning == ""


@patch("agents.vision_agent.anthropic.Anthropic")
def test_respuesta_truncada_avisa(mock_anthropic):
    texto_cortado = PARTIDAS_OK.replace('  ],\n  "confidence_score": 0.9\n}\n</output_format>', "")
    _cliente(mock_anthropic, partidas_text=texto_cortado, stop_reason="max_tokens")

    result = analyze_plan(DUMMY_B64)

    assert len(result.partidas) == 1
    assert result.raw_reasoning.startswith("⚠ RESPUESTA TRUNCADA/REPARADA")
    assert result.confidence_score < 0.9


def test_analyze_plan_corrupt_base64():
    result = analyze_plan("not-a-valid-base64-string!@#")

    assert result.confidence_score == 0.0
    assert result.error is not None and "Corrupt or invalid base64" in result.error


@pytest.mark.parametrize("error", [
    anthropic.APITimeoutError(request=MagicMock()),
    anthropic.APIStatusError("Internal Server Error", response=MagicMock(status_code=500), body=None),
    Exception("Unexpected Error"),
])
@patch("agents.vision_agent.anthropic.Anthropic")
def test_errores_de_api_no_rompen(mock_anthropic, error):
    client = _cliente(mock_anthropic)
    client.messages.create.side_effect = error   # pasada de códigos: degrada a []
    client.messages.stream.side_effect = error   # pasada de partidas: devuelve error

    result = analyze_plan(DUMMY_B64)

    assert result.confidence_score == 0.0
    assert result.partidas == []
    assert result.error == str(error)


# ── pasada de códigos de vista ──────────────────────────────────────────────

def test_detect_view_codes_con_page_images_manda_imagenes():
    client = MagicMock()
    client.messages.create.return_value = _response("A01, A02,PL")

    codes = _detect_view_codes(client, DUMMY_B64, "application/pdf", "p1",
                               page_images=[b"jpeg-1", b"jpeg-2"])

    assert codes == ["A01", "A02", "PL"]
    kw = client.messages.create.call_args.kwargs
    assert kw["model"] == VISION_FAST_MODEL
    tipos = [b["type"] for b in kw["messages"][0]["content"]]
    assert tipos == ["image", "image", "text"]
    assert "document" not in tipos
    assert all(b["source"]["media_type"] == "image/jpeg"
               for b in kw["messages"][0]["content"][:2])


def test_detect_view_codes_sin_page_images_manda_el_pdf():
    client = MagicMock()
    client.messages.create.return_value = _response("NINGUNO")

    codes = _detect_view_codes(client, DUMMY_B64, "application/pdf", "p1")

    assert codes == []
    content = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert content[0]["type"] == "document"


@patch("agents.vision_agent.anthropic.Anthropic")
def test_analyze_plan_pasa_page_images_a_los_codigos(mock_anthropic):
    client = _cliente(mock_anthropic)

    analyze_plan(DUMMY_B64, media_type="application/pdf", plano_id="p1", page_images=[b"jpeg-1"])

    content = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "text"]


# ── capa de texto del PDF ───────────────────────────────────────────────────

def test_extract_pdf_text_pages_pdf_real():
    paginas = extract_pdf_text_pages(PDF_ROSALES)

    assert len(paginas) == 3
    assert "MEDICIONES ROSALES" in paginas[0]
    assert all(len(t) <= 6000 for t in paginas)


def test_extract_pdf_text_pages_descarta_texto_girado_y_recorta():
    def _pagina(texto):
        pg = MagicMock()
        pg.extract_text.return_value = texto
        return pg

    pdf = MagicMock()
    medicion = "\n".join(f"15.{i:02d} Partida ud PL - PUERTA {i}" for i in range(10))
    pdf.pages = [_pagina("P C\nA O\nN N\nCASCO TEXTIL"), _pagina(None),
                 _pagina("H 212cm " * 50), _pagina(medicion)]
    pdf.__enter__.return_value = pdf
    with patch("pdfplumber.open", return_value=pdf):
        paginas = extract_pdf_text_pages("plano.pdf", max_chars=100)

    assert paginas[0] == ""          # 3 de 4 líneas con ≤ 2 caracteres → basura
    assert paginas[1] == ""          # sin texto
    # Una única fila más larga que max_chars no se envía a medias: solo el aviso
    assert paginas[2] == "[texto truncado]"
    # Con varias líneas se corta por un final de línea: ninguna fila a medias
    assert len(paginas[3]) <= 100
    filas = paginas[3].split("\n")
    assert filas[-1] == "[texto truncado]"
    assert len(filas) > 1 and all(f in medicion.split("\n") for f in filas[:-1])


def test_extract_pdf_text_pages_no_lanza():
    assert extract_pdf_text_pages("/no/existe.pdf") == []


def test_prompt_no_pide_el_razonamiento_del_modelo():
    """Pedir 'escribe tu razonamiento' dispara el filtro reasoning_extraction de los
    modelos 5.x (refusal). El prompt pide un resumen de lectura del plano."""
    import inspect
    from agents import vision_agent
    src = inspect.getsource(vision_agent._analyze_partidas_plan)
    assert "<resumen_lectura>" in src
    assert "en <raw_reasoning>" not in src
    assert vision_agent._extraer_resumen("<resumen_lectura> A01 armario </resumen_lectura>") == "A01 armario"
    assert vision_agent._extraer_resumen("<raw_reasoning>viejo</raw_reasoning>") == "viejo"
