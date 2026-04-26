from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agents.base import BaseAgent
from backend.app.models.domain import AgentStatus
from backend.app.runtime.state_machine import validate_agent_transition


class LifecycleAgent(BaseAgent):
    """Base class that enforces canonical agent lifecycle transitions."""

    def __init__(self, agent_type: str):
        super().__init__(agent_type=agent_type)
        self.status = AgentStatus.CREATED.value

    def transition(self, target: AgentStatus) -> None:
        current = AgentStatus(self.status)
        validation = validate_agent_transition(current=current, target=target)
        if not validation.allowed:
            raise ValueError(validation.reason)
        self.set_status(target.value)


class DummyAgent(LifecycleAgent):
    """Simple deterministic agent used for runtime wiring and integration checks."""

    def __init__(self):
        super().__init__(agent_type="dummy")

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self.transition(AgentStatus.REGISTERED)
        self.transition(AgentStatus.READY)
        self.transition(AgentStatus.QUEUED)
        self.transition(AgentStatus.RUNNING)

        wait_ms = int(input_data.get("wait_ms", 0))
        if wait_ms > 0:
            self.transition(AgentStatus.WAITING)
            await asyncio.sleep(wait_ms / 1000)
            self.transition(AgentStatus.RUNNING)

        text = str(input_data.get("text", ""))
        words = [w for w in text.split(" ") if w]
        result = {
            "agent_type": self.agent_type,
            "echo": text,
            "word_count": len(words),
            "char_count": len(text),
            "uppercase": text.upper(),
        }

        self.transition(AgentStatus.COMPLETED)
        return result


class SummaryAgent(LifecycleAgent):
    """Aggregates outputs from prior agents and returns a compact summary."""

    def __init__(self):
        super().__init__(agent_type="summary")

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        self.transition(AgentStatus.REGISTERED)
        self.transition(AgentStatus.READY)
        self.transition(AgentStatus.QUEUED)
        self.transition(AgentStatus.RUNNING)

        results = input_data.get("results", [])
        if not isinstance(results, list):
            raise TypeError("results must be a list")

        total_words = 0
        total_chars = 0
        valid_items_count = 0
        for item in results:
            if isinstance(item, dict):
                total_words += int(item.get("word_count", 0))
                total_chars += int(item.get("char_count", 0))
                valid_items_count += 1

        summary = {
            "agent_type": self.agent_type,
            "result_count": len(results),
            "total_words": total_words,
            "avg_words": (total_words / valid_items_count) if valid_items_count > 0 else 0.0,
            "total_chars": total_chars,
        }

        self.transition(AgentStatus.COMPLETED)
        return summary
