"""AgentRegistry — holds registered agent classes and exposes manifests for the Commander."""

from __future__ import annotations

from typing import Any

from atrium.core.agent import Agent


class AgentRegistry:
    """Registry of Agent subclasses, keyed by their ``name`` class attribute.

    Usage::

        registry = AgentRegistry()
        registry.register(MyAgent)
        agent = registry.create("my_agent")
    """

    def __init__(self) -> None:
        self._agents: dict[str, type[Agent]] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, agent_class: type[Agent]) -> None:
        """Register *agent_class* by its ``name`` class attribute.

        Raises:
            ValueError: If an agent with the same name is already registered.
        """
        key = agent_class.name
        if key in self._agents:
            raise ValueError(
                f"Agent '{key}' is already registered. "
                "Each agent name must be unique within a registry."
            )
        self._agents[key] = agent_class

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> type[Agent]:
        """Return the agent class registered under *name*.

        Raises:
            KeyError: If no agent with that name has been registered.
        """
        try:
            return self._agents[name]
        except KeyError:
            raise KeyError(name) from None

    def create(self, name: str) -> Agent:
        """Instantiate and return the agent registered under *name*.

        Raises:
            KeyError: If no agent with that name has been registered.
        """
        return self.get(name)()

    # ------------------------------------------------------------------
    # Enumeration
    # ------------------------------------------------------------------

    def list_all(self) -> list[type[Agent]]:
        """Return a list of all registered agent classes."""
        return list(self._agents.values())

    def find_by_capability(self, tag: str) -> list[type[Agent]]:
        """Return all agent classes whose ``capabilities`` list contains *tag*."""
        return [cls for cls in self._agents.values() if tag in cls.capabilities]

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def manifest(self) -> list[dict[str, Any]]:
        """Return a list of manifest dicts for every registered agent.

        Each dict contains ``name``, ``description``, ``capabilities``,
        ``input_schema``, and ``output_schema`` — read directly from class
        attributes (no instantiation).
        """
        return [
            {
                "name": cls.name,
                "description": cls.description,
                "capabilities": list(cls.capabilities),
                "input_schema": cls.input_schema,
                "output_schema": cls.output_schema,
            }
            for cls in self._agents.values()
        ]
