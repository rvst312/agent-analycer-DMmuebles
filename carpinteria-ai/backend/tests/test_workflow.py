"""
Tests for workflow
"""
import pytest
from unittest.mock import patch, mock_open, AsyncMock, MagicMock
from langgraph.checkpoint.memory import MemorySaver
from graph.workflow import workflow, handle_error

@pytest.mark.anyio
@patch("graph.workflow.get_session")
@patch("graph.workflow.notify_n8n_error")
async def test_handle_error_node(mock_notify_n8n, mock_get_session):
    # Mocking db session
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    
    async def mock_session_generator():
        yield mock_session
        
    mock_get_session.return_value = mock_session_generator()
    
    state = {
        "plano_id": "test_plano_123",
        "thread_id": "test_job_123",
        "status": "error",
        "error": "Failed in pricing: error_detail"
    }
    
    result = await handle_error(state)
    
    assert result["status"] == "error"
    
    # Check that job log was added
    mock_session.add.assert_called_once()
    added_log = mock_session.add.call_args[0][0]
    assert added_log.job_id == "test_job_123"
    assert added_log.nodo == "rag_pricing"
    assert added_log.mensaje == "Failed in pricing: error_detail"
    assert added_log.error_type == "workflow_error"
    
    mock_session.commit.assert_awaited_once()
    
    # Check that N8N was notified
    mock_notify_n8n.assert_awaited_once_with(
        plano_id="test_plano_123",
        nodo="rag_pricing",
        mensaje="Failed in pricing: error_detail"
    )

@pytest.mark.anyio
@patch("graph.workflow.crear_presupuesto")
@patch("graph.workflow.execute_consolidation", new_callable=AsyncMock)
@patch("graph.workflow.analyze_plan")
@patch("builtins.open", new_callable=mock_open, read_data=b"dummy")
async def test_workflow_human_approval_interrupt(mock_file, mock_analyze_plan, mock_execute_consolidation, mock_crear_presupuesto):
    # Mocking crear_presupuesto
    mock_crear_presupuesto.return_value = "holded_123"
    
    # Configuramos el checkpointer para habilitar la interrupción
    checkpointer = MemorySaver()
    # Ya no necesitamos interrupt_before porque se usa interrupt() internamente
    app = workflow.compile(checkpointer=checkpointer)
    # Mocking analyze_plan para que no falle
    class MockResult:
        error = None
        def model_dump(self):
            return {
                "plano_id": "test",
                "componentes": [],
                "confidence_score": 1.0,
                "raw_reasoning": "test"
            }
    mock_analyze_plan.return_value = MockResult()
    
    class MockConsolidado:
        def model_dump(self):
            return {
                "cliente_id": "test_client",
                "plano_id": "test",
                "lineas": [],
                "subtotal": 0.0,
                "iva": 0.0,
                "total": 0.0,
                "lineas_pendientes": [],
                "status": "pending_review"
            }
    mock_execute_consolidation.return_value = MockConsolidado()

    initial_state = {"archivo_path": "dummy.jpg", "status": "init"}
    config = {"configurable": {"thread_id": "test_thread_1"}}

    # Ejecutamos el grafo
    async for event in app.astream(initial_state, config=config):
        pass
        
    # Verificamos que se detuvo dentro de human_approval
    state = await app.aget_state(config)
    assert state.next == ('human_approval',)
    
    # We also check that there are tasks with an interrupt
    assert len(state.tasks) == 1
    assert len(state.tasks[0].interrupts) == 1
    assert state.tasks[0].interrupts[0].value["message"] == "Waiting for human approval"
    
    # Resume the workflow with approval
    from langgraph.types import Command
    async for event in app.astream(Command(resume={"approved": True, "notes": "Looks good"}), config=config):
        pass
        
    final_state = await app.aget_state(config)
    assert not final_state.next
    assert final_state.values["status"] == "completed"
