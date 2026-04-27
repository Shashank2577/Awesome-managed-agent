from atrium.core.models import AtriumEvent, BudgetSnapshot, Plan, PlanStep, Thread, ThreadStatus


def test_thread_creation():
    t = Thread(thread_id="abc", objective="test goal")
    assert t.status == ThreadStatus.CREATED
    assert t.thread_id == "abc"
    assert t.title == ""


def test_thread_serialization():
    t = Thread(thread_id="abc", objective="test goal", title="Test")
    d = t.model_dump()
    assert d["thread_id"] == "abc"
    assert d["status"] == "CREATED"


def test_plan_step():
    step = PlanStep(agent="researcher", inputs={"q": "test"}, depends_on=[])
    assert step.status == "pending"


def test_plan_creation():
    steps = [
        PlanStep(agent="a", inputs={}, depends_on=[]),
        PlanStep(agent="b", inputs={}, depends_on=["a"]),
    ]
    plan = Plan(plan_id="p1", thread_id="t1", plan_number=1, rationale="test", steps=steps)
    assert len(plan.steps) == 2


def test_event_creation():
    evt = AtriumEvent(
        event_id="e1", thread_id="t1", type="AGENT_RUNNING",
        payload={"agent_key": "alpha"}, sequence=1,
    )
    assert evt.type == "AGENT_RUNNING"
    assert evt.causation_id is None


def test_budget_snapshot():
    b = BudgetSnapshot(consumed="0.42", limit="10.00", currency="USD")
    assert b.consumed == "0.42"
