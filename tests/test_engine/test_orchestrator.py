"""Tests for ThreadOrchestrator and ThreadController."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass, field
from atrium.core.agent import Agent
from atrium.core.guardrails import GuardrailsConfig
from atrium.core.models import Plan, PlanStep
from atrium.engine.orchestrator import ThreadOrchestrator, ThreadController, get_controller
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
    mock_eval_decision.findings = []
    mock_eval_decision.recommendations = []

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
    mock_eval_decision.findings = []
    mock_eval_decision.recommendations = []

    with patch.object(orchestrator._commander, "plan", new_callable=AsyncMock, return_value=mock_plan):
        with patch.object(orchestrator._commander, "evaluate", new_callable=AsyncMock, return_value=mock_eval_decision):
            result = await orchestrator.run("test")

    events = recorder.replay(result["thread_id"])
    types = [e.type for e in events]
    assert "PLAN_CREATED" in types
    assert "PLAN_EXECUTION_STARTED" in types
    assert "PLAN_COMPLETED" in types
    assert "BUDGET_RESERVED" in types
    assert "BUDGET_CONSUMED" in types


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


# ---------------------------------------------------------------------------
# ThreadController unit tests
# ---------------------------------------------------------------------------


async def test_thread_controller_not_paused_initially():
    ctrl = ThreadController()
    # Should not block — completes within timeout
    await asyncio.wait_for(ctrl.wait_if_paused(), timeout=0.1)


async def test_thread_controller_pause_resume():
    ctrl = ThreadController()
    ctrl.pause()
    ctrl.resume()
    # After resume, should not block
    await asyncio.wait_for(ctrl.wait_if_paused(), timeout=0.1)


async def test_thread_controller_cancel():
    ctrl = ThreadController()
    assert not ctrl.is_cancelled
    ctrl.cancel()
    assert ctrl.is_cancelled


async def test_thread_controller_cancel_unblocks_pause():
    ctrl = ThreadController()
    ctrl.pause()
    ctrl.cancel()
    # cancel() sets the pause event, so this should not block
    await asyncio.wait_for(ctrl.wait_if_paused(), timeout=0.1)
    assert ctrl.is_cancelled


async def test_thread_controller_approve():
    ctrl = ThreadController()

    async def approve_soon():
        await asyncio.sleep(0.05)
        ctrl.approve()

    task = asyncio.create_task(approve_soon())
    result = await asyncio.wait_for(ctrl.wait_for_approval(), timeout=1.0)
    assert result == "approve"
    await task


async def test_thread_controller_reject():
    ctrl = ThreadController()

    async def reject_soon():
        await asyncio.sleep(0.05)
        ctrl.reject()

    task = asyncio.create_task(reject_soon())
    result = await asyncio.wait_for(ctrl.wait_for_approval(), timeout=1.0)
    assert result == "reject"
    await task


async def test_thread_controller_submit_input():
    ctrl = ThreadController()

    async def submit_soon():
        await asyncio.sleep(0.05)
        ctrl.submit_input("hello world")

    task = asyncio.create_task(submit_soon())
    result = await asyncio.wait_for(ctrl.wait_for_input(), timeout=1.0)
    assert result == "hello world"
    await task


# ---------------------------------------------------------------------------
# Orchestrator HITL integration tests
# ---------------------------------------------------------------------------


async def test_orchestrator_approval_flow(registry, recorder):
    """When require_approval=True, orchestrator waits and proceeds on approve."""
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
        require_approval=True,
    )

    mock_eval_decision = MagicMock()
    mock_eval_decision.action = "finalize"
    mock_eval_decision.summary = "Done"
    mock_eval_decision.findings = []
    mock_eval_decision.recommendations = []

    async def approve_after_delay():
        # Wait briefly for the orchestrator to reach the approval gate
        await asyncio.sleep(0.1)
        # Find the controller that was registered
        for _, ctrl in list(get_controller.__wrapped__() if hasattr(get_controller, '__wrapped__') else []):
            pass  # noqa
        # Use the module-level registry directly
        from atrium.engine.orchestrator import _controllers
        for ctrl in _controllers.values():
            ctrl.approve()
            break

    with patch.object(orchestrator._commander, "plan", new_callable=AsyncMock, return_value=mock_plan):
        with patch.object(orchestrator._commander, "evaluate", new_callable=AsyncMock, return_value=mock_eval_decision):
            task = asyncio.create_task(approve_after_delay())
            result = await asyncio.wait_for(orchestrator.run("compute 1 + 2"), timeout=5.0)
            await task

    assert result["status"] == "COMPLETED"
    events = recorder.replay(result["thread_id"])
    types = [e.type for e in events]
    assert "HUMAN_APPROVAL_REQUESTED" in types
    assert "PLAN_APPROVED" in types


async def test_orchestrator_rejection_flow(registry, recorder):
    """When require_approval=True and plan is rejected, thread is cancelled."""
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
        require_approval=True,
    )

    async def reject_after_delay():
        await asyncio.sleep(0.1)
        from atrium.engine.orchestrator import _controllers
        for ctrl in _controllers.values():
            ctrl.reject()
            break

    with patch.object(orchestrator._commander, "plan", new_callable=AsyncMock, return_value=mock_plan):
        task = asyncio.create_task(reject_after_delay())
        result = await asyncio.wait_for(orchestrator.run("compute 1 + 2"), timeout=5.0)
        await task

    assert result["status"] == "CANCELLED"
    events = recorder.replay(result["thread_id"])
    types = [e.type for e in events]
    assert "HUMAN_APPROVAL_REQUESTED" in types
    assert "PLAN_REJECTED" in types
    assert "THREAD_CANCELLED" in types


async def test_orchestrator_cancel_during_run(registry, recorder):
    """Cancelling via controller mid-run results in CANCELLED status."""
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
        require_approval=True,
    )

    async def cancel_after_delay():
        await asyncio.sleep(0.1)
        from atrium.engine.orchestrator import _controllers
        for ctrl in _controllers.values():
            ctrl.cancel()
            break

    with patch.object(orchestrator._commander, "plan", new_callable=AsyncMock, return_value=mock_plan):
        task = asyncio.create_task(cancel_after_delay())
        result = await asyncio.wait_for(orchestrator.run("compute 1 + 2"), timeout=5.0)
        await task

    assert result["status"] == "CANCELLED"


async def test_orchestrator_controller_cleaned_up(registry, recorder):
    """After run() completes, the controller is removed from the registry."""
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

    mock_eval_decision = MagicMock()
    mock_eval_decision.action = "finalize"
    mock_eval_decision.summary = "Done"
    mock_eval_decision.findings = []
    mock_eval_decision.recommendations = []

    with patch.object(orchestrator._commander, "plan", new_callable=AsyncMock, return_value=mock_plan):
        with patch.object(orchestrator._commander, "evaluate", new_callable=AsyncMock, return_value=mock_eval_decision):
            result = await orchestrator.run("test")

    tid = result["thread_id"]
    assert get_controller(tid) is None
