from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

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


@dataclass(slots=True)
class AgentRuntimeState:
    status: AgentStatus = AgentStatus.CREATED


class TransitionRejectedError(ValueError):
    """Raised when a requested lifecycle transition violates the contract."""


def validate_agent_transition(current: AgentStatus, target: AgentStatus) -> TransitionResult:
    if current == target:
        return TransitionResult(allowed=True, reason="no-op transition")

    if target in ALLOWED_AGENT_TRANSITIONS.get(current, set()):
        return TransitionResult(allowed=True, reason="allowed")

    return TransitionResult(
        allowed=False,
        reason=f"invalid transition from {current.value} to {target.value}",
    )


class AgentStateMachine:
    """Transition helper that enforces canonical lifecycle + emits transition events."""

    def __init__(self, state: AgentRuntimeState, emit: Any):
        self._state = state
        self._emit = emit

    @property
    def status(self) -> AgentStatus:
        return self._state.status

    def transition(
        self,
        target: AgentStatus,
        *,
        reason: str,
        actor: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentStatus:
        current = self._state.status
        validation = validate_agent_transition(current=current, target=target)
        timestamp = datetime.now(timezone.utc).isoformat()

        if not validation.allowed:
            self._emit(
                "STATE_TRANSITION_REJECTED",
                {
                    "entity": "agent_instance",
                    "from": current.value,
                    "to": target.value,
                    "reason": validation.reason,
                    "actor": actor,
                    "timestamp": timestamp,
                    "metadata": metadata or {},
                },
            )
            raise TransitionRejectedError(validation.reason)

        self._state.status = target
        self._emit(
            "AGENT_STATE_TRANSITIONED",
            {
                "from": current.value,
                "to": target.value,
                "reason": reason,
                "actor": actor,
                "timestamp": timestamp,
                "metadata": metadata or {},
            },
        )
        return self._state.status
