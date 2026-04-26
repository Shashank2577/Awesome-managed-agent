from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from backend.app.models.domain import AgentStatus, PlanNode
from backend.app.runtime.events import InMemoryEventBus
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.state_machine import AgentRuntimeState, AgentStateMachine


@dataclass(slots=True)
class WorkerResult:
    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None


class Worker:
    """Executes one node and enforces agent lifecycle/event emission."""

    def __init__(self, registry: AgentRegistry, event_bus: InMemoryEventBus):
        self.registry = registry
        self.event_bus = event_bus

    async def run_node(
        self,
        *,
        org_id: UUID,
        thread_id: UUID,
        node: PlanNode,
        payload: dict[str, Any],
    ) -> WorkerResult:
        state_machine = AgentStateMachine(
            state=AgentRuntimeState(),
            emit=lambda event_type, body: self.event_bus.emit(
                org_id=org_id,
                thread_id=thread_id,
                event_type=event_type,
                payload={"node_key": node.node_key, **body},
            ),
        )
        agent = self.registry.create(node.node_type)

        try:
            state_machine.transition(AgentStatus.REGISTERED, reason="worker_register", actor="worker")
            state_machine.transition(AgentStatus.READY, reason="worker_ready", actor="worker")
            state_machine.transition(AgentStatus.QUEUED, reason="worker_enqueue", actor="worker")
            state_machine.transition(AgentStatus.RUNNING, reason="worker_start", actor="worker")

            output = await agent.run(payload)
            state_machine.transition(AgentStatus.COMPLETED, reason="worker_complete", actor="worker")
            return WorkerResult(success=True, output=output)
        except Exception as exc:
            state_machine.transition(AgentStatus.FAILED, reason="worker_failed", actor="worker")
            return WorkerResult(success=False, error=str(exc))
