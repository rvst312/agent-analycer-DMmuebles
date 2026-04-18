"""
Tests for workflow
"""
import pytest
from unittest.mock import patch, mock_open
from langgraph.checkpoint.memory import MemorySaver
from graph.workflow import workflow

@patch("graph.workflow.analyze_plan")
@patch("builtins.open", new_callable=mock_open, read_data=b"dummy")
def test_workflow_human_approval_interrupt(mock_file, mock_analyze_plan):
    # Configuramos el checkpointer para habilitar la interrupción
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer, interrupt_before=["human_approval"])
    
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
    
    initial_state = {"input_data": {"file_path": "dummy.jpg"}, "status": "init"}
    config = {"configurable": {"thread_id": "test_thread_1"}}
    
    # Ejecutamos el grafo
    for event in app.stream(initial_state, config=config):
        pass
        
    # Verificamos que se detuvo antes de human_approval
    state = app.get_state(config)
    assert state.next == ('human_approval',)
    assert state.values["status"] == "consolidated"
