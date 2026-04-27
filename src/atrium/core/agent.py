"""Agent base class for the Atrium framework."""

from __future__ import annotations

import abc
from typing import Any, Callable, Coroutine

# Event type constant
AGENT_MESSAGE = "AGENT_MESSAGE"


class AgentMeta(abc.ABCMeta):
    """Metaclass that enforces required class-level attributes on instantiation."""

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        # Agent itself is abstract — let ABCMeta handle the abstractmethod check
        if cls is Agent:
            return super().__call__(*args, **kwargs)

        # Subclasses must define `name` and `description`
        if not getattr(cls, "name", None):
            raise TypeError(
                f"Agent subclass '{cls.__name__}' must define a non-empty class attribute 'name'."
            )
        if not getattr(cls, "description", None):
            raise TypeError(
                f"Agent subclass '{cls.__name__}' must define a non-empty class attribute"
                " 'description'."
            )
        return super().__call__(*args, **kwargs)


class Agent(abc.ABC, metaclass=AgentMeta):
    """Base class for all Atrium agents.

    Subclasses must define:
        name (str): Unique identifier for this agent type.
        description (str): Human-readable description of what the agent does.

    Subclasses may define:
        capabilities (list[str]): List of capability tags (default []).
        input_schema (dict | None): JSON-serialisable schema for input (default None).
        output_schema (dict | None): JSON-serialisable schema for output (default None).

    Subclasses must implement:
        async run(input_data: dict) -> dict
    """

    # --- Class-level metadata (subclasses override these) ---
    name: str = ""
    description: str = ""
    capabilities: list[str] = []
    input_schema: dict | None = None
    output_schema: dict | None = None

    def __init__(self) -> None:
        self._messages: list[str] = []
        self._emitter: Callable[..., Coroutine[Any, Any, None]] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_emitter(
        self, emitter: Callable[..., Coroutine[Any, Any, None]]
    ) -> None:
        """Wire an async event emitter to this agent.

        The emitter will be called with ``(event_type, payload, causation=None)``
        whenever :meth:`say` is invoked.
        """
        self._emitter = emitter

    async def say(self, text: str) -> None:
        """Append *text* to the internal message log and optionally emit an event."""
        self._messages.append(text)
        if self._emitter is not None:
            await self._emitter(
                AGENT_MESSAGE,
                {"text": text, "agent_key": self.name},
            )

    def manifest(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict of all agent metadata."""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def run(self, input_data: dict) -> dict:
        """Execute the agent's core logic.

        Args:
            input_data: Validated input dictionary.

        Returns:
            Output dictionary.
        """
