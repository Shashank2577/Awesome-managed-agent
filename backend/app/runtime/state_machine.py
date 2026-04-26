from __future__ import annotations

from dataclasses import dataclass

from backend.app.models.domain import AgentStatus


ALLOWED_AGENT_TRANSITIONS: dict[AgentStatus, set[AgentStatus]] = {
    AgentStatus.CREATED: {AgentStatus.REGISTERED},
    AgentStatus.REGISTERED: {AgentStatus.READY},
    AgentStatus.READY: {AgentStatus.QUEUED},
    AgentStatus.QUEUED: {AgentStatus.RUNNING, AgentStatus.TERMINATED},
    AgentStatus.RUNNING: {
        AgentStatus.WAITING,
        AgentStatus.COMPLETED,
        AgentStatus.FAILED,
        AgentStatus.TERMINATED,
    },
    AgentStatus.WAITING: {AgentStatus.RUNNING, AgentStatus.TERMINATED},
    AgentStatus.COMPLETED: set(),
    AgentStatus.FAILED: set(),
    AgentStatus.TERMINATED: set(),
}


@dataclass(slots=True)
class TransitionResult:
    allowed: bool
    reason: str


def validate_agent_transition(current: AgentStatus, target: AgentStatus) -> TransitionResult:
    if current == target:
        return TransitionResult(allowed=True, reason="no-op transition")

    if target in ALLOWED_AGENT_TRANSITIONS.get(current, set()):
        return TransitionResult(allowed=True, reason="allowed")

    return TransitionResult(
        allowed=False,
        reason=f"invalid transition from {current.value} to {target.value}",
    )
