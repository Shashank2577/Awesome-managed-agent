"""Test helpers for Atrium — run threads without a server."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from atrium.core.agent import Agent
from atrium.core.guardrails import GuardrailsConfig
from atrium.core.models import AtriumEvent, Plan, PlanStep
from atrium.core.registry import AgentRegistry
from atrium.engine.commander import Commander, EvalDecision
from atrium.engine.orchestrator import ThreadOrchestrator
from atrium.streaming.events import EventRecorder


@dataclass
class ThreadResult:
    thread_id: str
    status: str
    events: list[AtriumEvent] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)


class MockCommander(Commander):
    """Commander that runs all agents sequentially without LLM calls."""

    def __init__(self, registry: AgentRegistry):
        self._registry = registry

    async def plan(self, objective: str) -> tuple[Plan, dict]:
        agents = self._registry.list_all()
        steps = [PlanStep(agent=a.name, inputs={}, depends_on=[]) for a in agents]
        return Plan(thread_id="", rationale="Mock plan: run all agents", steps=steps), {}


    async def evaluate(self, objective: str, outputs: dict[str, Any]) -> EvalDecision:
        return EvalDecision(
            action="finalize",
            headline="Mock Report",
            summary="Mock evaluation complete",
            sections=[{"title": "Results", "content": "All agents completed.", "key_facts": []}],
            usage={},
        )



async def run_thread(
    agents: list[type[Agent]],
    objective: str,
    llm: str = "mock",
    guardrails: GuardrailsConfig | None = None,
) -> ThreadResult:
    """Run a complete thread for testing. Use llm='mock' to skip real LLM calls."""
    registry = AgentRegistry()
    for agent_cls in agents:
        registry.register(agent_cls)

    recorder = EventRecorder()
    orchestrator = ThreadOrchestrator(
        registry=registry,
        recorder=recorder,
        guardrails=guardrails or GuardrailsConfig(),
        llm_config=llm,
    )

    if llm == "mock":
        orchestrator._commander = MockCommander(registry)

    result = await orchestrator.run(objective)
    events = recorder.replay(result["thread_id"])

    return ThreadResult(
        thread_id=result["thread_id"],
        status=result["status"],
        events=events,
        outputs=result.get("outputs", {}),
    )
