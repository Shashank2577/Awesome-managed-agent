from __future__ import annotations

from collections.abc import Callable

from backend.app.agents.base import BaseAgent


class AgentRegistry:
    def __init__(self):
        self._factories: dict[str, Callable[[], BaseAgent]] = {}

    def register(self, agent_type: str, factory: Callable[[], BaseAgent]) -> None:
        self._factories[agent_type] = factory

    def create(self, agent_type: str) -> BaseAgent:
        if agent_type not in self._factories:
            raise KeyError(f"Unknown agent type: {agent_type}")
        return self._factories[agent_type]()

    def known_types(self) -> set[str]:
        return set(self._factories)
