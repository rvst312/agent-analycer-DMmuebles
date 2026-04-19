"""
Tests for workflow
"""
import pytest
from unittest.mock import patch, mock_open, AsyncMock
from langgraph.checkpoint.memory import MemorySaver
from graph.workflow import workflow

@pytest.mark.anyio
@patch("graph.workflow.execute_consolidation", new_callable=AsyncMock)
@patch("graph.workflow.analyze_plan")
@patch("builtins.open", new_callable=mock_open, read_data=b"dummy")
async def test_workflow_human_approval_interrupt(mock_file, mock_analyze_plan, mock_execute_consolidation):
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
