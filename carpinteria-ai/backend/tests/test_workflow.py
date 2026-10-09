"""
Tests for workflow
"""
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from agents.consolidation_agent import PresupuestoConsolidado
from api.schemas.estimate import Partida, PlanoAnalizado, Presupuesto
from graph.workflow import handle_error, workflow


def _fake_session_maker():
    """async_session_maker falso: la BD real no interviene en estos tests."""
    session = MagicMock()
    session.commit = AsyncMock()
    resultado = MagicMock()
    resultado.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=resultado)
    maker = MagicMock()
    maker.return_value.__aenter__ = AsyncMock(return_value=session)
    maker.return_value.__aexit__ = AsyncMock(return_value=False)
    return maker, session


@pytest.fixture
def sin_infra(monkeypatch):
    """Aísla el grafo de BD, lecciones, few-shot y recortes del plano."""
    maker, session = _fake_session_maker()
    monkeypatch.setattr("graph.workflow.async_session_maker", maker)
    monkeypatch.setattr("graph.workflow.get_recent_corrections", AsyncMock(return_value=[]))
    monkeypatch.setattr("graph.workflow._generar_recortes_partidas", AsyncMock())
    monkeypatch.setattr("agents.lecciones.cargar_lecciones", AsyncMock(return_value=[]))
    return session


@pytest.mark.anyio
@patch("graph.workflow.notify_n8n_error")
async def test_handle_error_node(mock_notify_n8n, sin_infra):
    state = {
        "plano_id": "test_plano_123",
        "thread_id": "test_job_123",
        "status": "error",
        "error": "Failed in pricing: error_detail"
    }

    result = await handle_error(state)

    assert result["status"] == "error"

    # Check that job log was added
    sin_infra.add.assert_called_once()
    added_log = sin_infra.add.call_args[0][0]
    assert added_log.job_id == "test_job_123"
    assert added_log.nodo == "rag_pricing"
    assert added_log.mensaje == "Failed in pricing: error_detail"
    assert added_log.error_type == "workflow_error"

    sin_infra.commit.assert_awaited_once()

    # Check that N8N was notified
    mock_notify_n8n.assert_awaited_once_with(
        plano_id="test_plano_123",
        nodo="rag_pricing",
        mensaje="Failed in pricing: error_detail"
    )


@pytest.mark.anyio
@patch("graph.workflow.crear_presupuesto")
@patch("graph.workflow.execute_consolidation", new_callable=AsyncMock)
@patch("graph.workflow.calculate_pricing")
@patch("graph.workflow.analyze_plan")
@patch("builtins.open", new_callable=mock_open, read_data=b"dummy")
async def test_workflow_human_approval_interrupt(mock_file, mock_analyze_plan, mock_calculate_pricing,
                                                 mock_execute_consolidation, mock_crear_presupuesto,
                                                 sin_infra):
    mock_crear_presupuesto.return_value = "holded_123"

    # Configuramos el checkpointer para habilitar la interrupción
    # (se usa interrupt() dentro de human_approval)
    app = workflow.compile(checkpointer=MemorySaver())

    mock_analyze_plan.return_value = PlanoAnalizado(
        plano_id="test", tipo_plano="partidas", confidence_score=1.0, raw_reasoning="test",
        partidas=[Partida(familia="armario", ref="A01", ancho_cm=120, alto_cm=240)],
    )
    mock_calculate_pricing.return_value = Presupuesto(plano_id="test", lineas=[], total=0.0)
    mock_execute_consolidation.return_value = PresupuestoConsolidado(
        cliente_id="test_client", plano_id="test", lineas=[], subtotal=0.0, iva=0.0,
        total=0.0, lineas_pendientes=[], status="pending_review",
    )

    initial_state = {"archivo_path": "dummy.jpg", "status": "init"}
    config = {"configurable": {"thread_id": "test_thread_1"}}

    # Ejecutamos el grafo
    async for event in app.astream(initial_state, config=config):
        pass

    # Verificamos que se detuvo dentro de human_approval
    state = await app.aget_state(config)
    assert state.next == ('human_approval',)
    assert state.values["plano_analizado"]["partidas"][0]["ref"] == "A01"

    # We also check that there are tasks with an interrupt
    assert len(state.tasks) == 1
    assert len(state.tasks[0].interrupts) == 1
    assert state.tasks[0].interrupts[0].value["message"] == "Waiting for human approval"

    # Resume the workflow with approval
    from langgraph.types import Command
    async for event in app.astream(Command(resume={"action": "approve"}), config=config):
        pass

    final_state = await app.aget_state(config)
    assert not final_state.next
    assert final_state.values["status"] == "completed"
    mock_crear_presupuesto.assert_called_once()


@pytest.mark.anyio
@patch("graph.workflow.analyze_plan")
@patch("builtins.open", new_callable=mock_open, read_data=b"%PDF-dummy")
async def test_vision_analysis_pasa_capa_de_texto_del_pdf(mock_file, mock_analyze_plan, sin_infra, monkeypatch):
    from graph.workflow import vision_analysis

    monkeypatch.setattr("graph.workflow._cargar_paginas_para_vision", AsyncMock(return_value=[b"jpeg-1"]))
    extraer = MagicMock(return_value=["MEDICIONES ROSALES", ""])
    monkeypatch.setattr("core.plan_images.extract_pdf_text_pages", extraer)
    mock_analyze_plan.return_value = PlanoAnalizado(
        plano_id="t", tipo_plano="partidas", confidence_score=0.9, raw_reasoning="",
        partidas=[Partida(familia="puerta_paso_abatible", ref="PL", cantidad=10)],
    )

    out = await vision_analysis({"archivo_path": "/tmp/plano.pdf", "content_type": "application/pdf",
                                 "thread_id": "t", "status": "received"})

    assert out["status"] == "vision_analyzed"
    extraer.assert_called_once_with("/tmp/plano.pdf")
    kw = mock_analyze_plan.call_args.kwargs
    assert kw["pdf_text_pages"] == ["MEDICIONES ROSALES", ""]
    assert kw["page_images"] == [b"jpeg-1"]
