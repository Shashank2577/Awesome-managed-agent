"""Dispatcher that creates an Agent subclass from a config dict."""

from __future__ import annotations

from atrium.core.agent import Agent


def build_agent_class(config: dict) -> type[Agent]:
    """Return an Agent subclass for the given config.

    Dispatches on ``config.get("agent_type", "http")``:

    - ``"http"``  → delegates to :func:`atrium.core.http_agent.create_agent_class`
    - ``"llm"``   → raises :exc:`NotImplementedError` (wired in P1)
    - anything else → raises :exc:`ValueError`

    Args:
        config: Agent configuration dict.  Must contain at least ``name`` and
            ``description``.

    Returns:
        A concrete :class:`~atrium.core.agent.Agent` subclass.

    Raises:
        NotImplementedError: When ``agent_type`` is ``"llm"`` (not yet implemented).
        ValueError: When ``agent_type`` is an unknown value.
    """
    agent_type: str = config.get("agent_type", "http")

    if agent_type == "http":
        from atrium.core import http_agent
        return http_agent.create_agent_class(config)

    if agent_type == "llm":
        raise NotImplementedError("LLMAgent not yet implemented — will be added in P1")

    raise ValueError(f"Unknown agent_type: {agent_type}")
