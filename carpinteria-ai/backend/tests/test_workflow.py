"""
Tests for workflow
"""
import pytest
from langgraph.checkpoint.memory import MemorySaver
from graph.workflow import workflow

def test_workflow_human_approval_interrupt():
    # Configuramos el checkpointer para habilitar la interrupción
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer, interrupt_before=["human_approval"])
    
    initial_state = {"input_data": {}, "status": "init"}
    config = {"configurable": {"thread_id": "test_thread_1"}}
    
    # Ejecutamos el grafo
    for event in app.stream(initial_state, config=config):
        pass
        
    # Verificamos que se detuvo antes de human_approval
    state = app.get_state(config)
    assert state.next == ('human_approval',)
    assert state.values["status"] == "consolidated"
