"""Tests for atrium.engine.graph_builder."""
import pytest

from atrium.core.agent import Agent
from atrium.core.models import Plan, PlanStep
from atrium.core.registry import AgentRegistry
from atrium.engine.graph_builder import build_agent_node, build_graph_from_plan
from atrium.streaming.events import EventRecorder


class EchoAgent(Agent):
    name = "echo"
    description = "Echoes input"
    capabilities = ["echo"]

    async def run(self, input_data: dict) -> dict:
        return {"echoed": input_data.get("text", "nothing")}


class UpperAgent(Agent):
    name = "upper"
    description = "Uppercases text"
    capabilities = ["transform"]

    async def run(self, input_data: dict) -> dict:
        text = input_data.get("text", "")
        return {"result": text.upper()}


@pytest.fixture
def registry():
    reg = AgentRegistry()
    reg.register(EchoAgent)
    reg.register(UpperAgent)
    return reg


@pytest.fixture
def recorder():
    return EventRecorder()


def test_build_agent_node_returns_callable(registry, recorder):
    node_fn = build_agent_node("echo", registry, recorder, "t1")
    assert callable(node_fn)


@pytest.mark.asyncio
async def test_agent_node_runs_agent(registry, recorder):
    node_fn = build_agent_node("echo", registry, recorder, "t1")
    state = {"agent_outputs": {}, "inputs": {"echo": {"text": "hello"}}}
    result = await node_fn(state)
    assert result["agent_outputs"]["echo"]["echoed"] == "hello"


@pytest.mark.asyncio
async def test_agent_node_emits_events(registry, recorder):
    node_fn = build_agent_node("echo", registry, recorder, "t1")
    state = {"agent_outputs": {}, "inputs": {"echo": {"text": "hi"}}}
    await node_fn(state)
    events = recorder.replay("t1")
    types = [e.type for e in events]
    assert "AGENT_RUNNING" in types
    assert "AGENT_COMPLETED" in types


@pytest.mark.asyncio
async def test_build_graph_from_plan(registry, recorder):
    plan = Plan(
        thread_id="t1",
        rationale="test",
        steps=[
            PlanStep(agent="echo", inputs={"text": "hello"}, depends_on=[]),
            PlanStep(agent="upper", inputs={"text": "world"}, depends_on=["echo"]),
        ],
    )
    graph = build_graph_from_plan(plan, registry, recorder)
    assert graph is not None
