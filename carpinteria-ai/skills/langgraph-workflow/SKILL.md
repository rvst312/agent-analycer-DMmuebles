# LangGraph Workflow Skill

Orchestrates the multi-step estimate generation pipeline with human-in-the-loop approval.

## Purpose
Coordinates vision_agent → pricing_agent → human approval → Holded export using LangGraph's StateGraph, checkpointing, and interrupt mechanism.

## Workflow Definition (backend/graph/workflow.py)

### Graph Structure
```
StateGraph(GraphState)
├─ receive_input
├─ vision_analysis
├─ extract_entities
├─ rag_pricing
├─ consolidate
├─ human_approval (HITL with interrupt())
├─ send_to_holded
├─ notify_team
└─ END
```

### GraphState TypedDict
```python
class GraphState(TypedDict):
    input_data: Dict[str, Any]     # Original estimate request
    status: str                     # Current node status
    vision_result: Dict             # vision_agent output
    pricing_result: Dict            # pricing_agent output
    estimate_id: str                # Assigned by consolidate node
    approval_notes: str             # From human_approval interrupt
    holded_document_id: str         # From Holded API response
    error: Optional[str]            # Error message if failed
```

## Node Implementations

Each node updates `status` and returns partial state updates:

```python
def receive_input(state: GraphState):
    logger.info(f"Processing estimate: {state['input_data']['client_id']}")
    return {"status": "received"}

def vision_analysis(state: GraphState):
    result = vision_agent.analyze(state["input_data"]["plan"])
    return {"status": "vision_analyzed", "vision_result": result}

def human_approval(state: GraphState):
    # interrupt() is called by LangGraph checkpointer
    # Workflow pauses and waits for /resume endpoint
    return {"status": "pending_approval"}
```

## Checkpointing & Interrupt Mechanism

**Setup with Persistence** (for production):
```python
from db.persistence import PostgresCheckpointer

checkpointer = PostgresCheckpointer()
app_workflow = workflow.compile(checkpointer=checkpointer)
```

**Pausing at human_approval:**
- `interrupt()` halts execution after human_approval node
- State is saved to PostgreSQL
- POST `/resume` endpoint resumes from checkpoint

**Resume Flow** (api/routes/workflow.py):
```python
@app.post("/resume")
async def resume_workflow(estimate_id: str, approved: bool, notes: str = ""):
    # Fetch saved state from checkpoint
    # Update approval fields
    # Call workflow.invoke(state) to resume
    return {"status": "resumed", ...}
```

## Running the Workflow

**Manual Invocation**
```python
from graph.workflow import app_workflow

initial_state = {
    "input_data": {
        "client_id": "acme_inc",
        "plan": image_bytes,
    },
    "status": "initialized"
}

result = app_workflow.invoke(initial_state)
print(result["status"])  # "completed"
```

**Via API** (POST /estimates):
```bash
curl -X POST http://localhost:8000/estimates \
  -F "client_id=acme_inc" \
  -F "plan_image=@plan.pdf"
# Returns estimate_id, workflow pauses at human_approval
```

## Error Handling Pattern

Each node wraps logic in try/except:
```python
def rag_pricing(state: GraphState):
    try:
        result = pricing_agent.calculate(state["vision_result"])
        return {"status": "priced", "pricing_result": result}
    except Exception as e:
        logger.error(f"Pricing failed: {e}")
        return {"status": "pricing_failed", "error": str(e)}
```

Downstream nodes check `status` before proceeding:
```python
def consolidate(state: GraphState):
    if state.get("error"):
        return {"status": "aborted"}
    # Continue...
```

## Integration Points

**Input Source:** API endpoint `/estimates` (api/routes/estimates.py)

**Output Sink:** Holded API via `send_to_holded` node

**Checkpointing:** PostgreSQL (db/persistence.py, POSTGRES_URL env var)

**Notifications:** Slack/n8n webhooks via `notify_team` node

## Common Tasks

**Test workflow execution**
```bash
pytest tests/test_workflow.py -v
```

**Trace workflow state transitions**
- Enable LangGraph debug logging: `LANGRAPH_DEBUG=true`
- Check PostgreSQL checkpoint table (estimate_checkpoints)

**Add a new node**
1. Define node function with (state: GraphState) → dict
2. Add to workflow: `workflow.add_node("new_node", new_node)`
3. Add edges: `workflow.add_edge("prev_node", "new_node")`
4. Add test case in tests/test_workflow.py

**Modify human approval logic**
- Edit `human_approval()` function
- Test resume path with `@app.post("/resume")` endpoint
- Update frontend to call /resume with approval decision

## Dependencies
- langgraph
- langchain-core (StateGraph)
- sqlalchemy (PostgresCheckpointer)
- logging
