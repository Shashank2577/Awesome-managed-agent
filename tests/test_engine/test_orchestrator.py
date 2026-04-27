"""Tests for ThreadOrchestrator."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass, field
from atrium.core.agent import Agent
from atrium.core.guardrails import GuardrailsConfig
from atrium.core.models import Plan, PlanStep
from atrium.engine.orchestrator import ThreadOrchestrator
from atrium.core.registry import AgentRegistry
from atrium.streaming.events import EventRecorder


class AddAgent(Agent):
    name = "adder"
    description = "Adds numbers"
    capabilities = ["math"]

    async def run(self, input_data: dict) -> dict:
        a = input_data.get("a", 0)
        b = input_data.get("b", 0)
        return {"sum": a + b}


@pytest.fixture
def registry():
    reg = AgentRegistry()
    reg.register(AddAgent)
    return reg


@pytest.fixture
def recorder():
    return EventRecorder()


async def test_orchestrator_runs_thread(registry, recorder):
    mock_plan = Plan(
        thread_id="",
        rationale="test",
        steps=[PlanStep(agent="adder", inputs={"a": 1, "b": 2}, depends_on=[])],
    )

    orchestrator = ThreadOrchestrator(
        registry=registry,
        recorder=recorder,
        guardrails=GuardrailsConfig(),
        llm_config="openai:gpt-4o-mini",
    )

    # Mock both plan and evaluate
    mock_eval_decision = MagicMock()
    mock_eval_decision.action = "finalize"
    mock_eval_decision.summary = "Done"

    with patch.object(orchestrator._commander, "plan", new_callable=AsyncMock, return_value=mock_plan):
        with patch.object(orchestrator._commander, "evaluate", new_callable=AsyncMock, return_value=mock_eval_decision):
            result = await orchestrator.run("compute 1 + 2")

    assert result["status"] == "COMPLETED"
    events = recorder.replay(result["thread_id"])
    types = [e.type for e in events]
    assert "THREAD_CREATED" in types
    assert "PLAN_CREATED" in types
    assert "THREAD_COMPLETED" in types


async def test_orchestrator_emits_plan_events(registry, recorder):
    mock_plan = Plan(
        thread_id="",
        rationale="test plan",
        steps=[PlanStep(agent="adder", inputs={"a": 5, "b": 3}, depends_on=[])],
    )

    orchestrator = ThreadOrchestrator(
        registry=registry,
        recorder=recorder,
        guardrails=GuardrailsConfig(),
        llm_config="openai:gpt-4o-mini",
    )

    mock_eval_decision = MagicMock()
    mock_eval_decision.action = "finalize"
    mock_eval_decision.summary = "OK"

    with patch.object(orchestrator._commander, "plan", new_callable=AsyncMock, return_value=mock_plan):
        with patch.object(orchestrator._commander, "evaluate", new_callable=AsyncMock, return_value=mock_eval_decision):
            result = await orchestrator.run("test")

    events = recorder.replay(result["thread_id"])
    types = [e.type for e in events]
    assert "PLAN_CREATED" in types
    assert "PLAN_EXECUTION_STARTED" in types
    assert "PLAN_COMPLETED" in types


async def test_orchestrator_handles_plan_failure(registry, recorder):
    orchestrator = ThreadOrchestrator(
        registry=registry,
        recorder=recorder,
        guardrails=GuardrailsConfig(),
        llm_config="openai:gpt-4o-mini",
    )

    with patch.object(orchestrator._commander, "plan", new_callable=AsyncMock, side_effect=RuntimeError("LLM failed")):
        result = await orchestrator.run("test")

    assert result["status"] == "FAILED"
    assert "LLM failed" in result["error"]
    events = recorder.replay(result["thread_id"])
    types = [e.type for e in events]
    assert "THREAD_CREATED" in types
    assert "THREAD_FAILED" in types
