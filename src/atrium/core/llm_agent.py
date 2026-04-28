"""Config-driven LLM agent — created from a dict, no Python code needed."""

from __future__ import annotations

import logging
from typing import Any

from atrium.core.agent import Agent
from atrium.core._input_utils import extract_query

logger = logging.getLogger(__name__)


def create_agent_class(config: dict[str, Any]) -> type[Agent]:
    """Create an Agent subclass that runs LLM queries, from a config dict.

    The returned class satisfies the AgentMeta checks (``name`` and
    ``description`` are set as class attributes) and captures *config* in a
    closure so each instance has access to the full LLM configuration.

    Args:
        config: Must contain at least ``name``, ``description``, and a
            non-empty ``system_prompt``.  Optional keys: ``capabilities``,
            ``category``, ``model``, ``input_schema``, ``output_schema``.

    Returns:
        A unique ``Agent`` subclass ready for registration.

    Raises:
        KeyError: If ``name`` or ``description`` is missing from *config*.
        ValueError: If ``system_prompt`` is empty or absent.
    """
    agent_name: str = config["name"]
    agent_desc: str = config["description"]
    agent_caps: list[str] = config.get("capabilities", [])
    agent_category: str | None = config.get("category", None)

    system_prompt: str = config.get("system_prompt", "") or ""
    if not system_prompt:
        raise ValueError(
            f"LLM agent '{agent_name}' requires a non-empty 'system_prompt' in config."
        )

    # Resolve model string — if it already has ':' treat as provider:model,
    # otherwise fall back to auto-detection via detect_llm().
    raw_model: str = config.get("model", "") or ""
    if raw_model and ":" in raw_model:
        resolved_model: str = raw_model
    else:
        from atrium.engine.llm import detect_llm
        resolved_model = detect_llm()

    _input_schema: dict = config.get("input_schema", {"query": "str"}) or {"query": "str"}
    _output_schema: dict = config.get("output_schema", {"response": "str"}) or {"response": "str"}

    class ConfiguredLLMAgent(Agent):
        name = agent_name
        description = agent_desc
        capabilities = list(agent_caps)
        input_schema = _input_schema
        output_schema = _output_schema

        async def run(self, input_data: dict) -> dict:
            query = extract_query(input_data)

            try:
                from atrium.engine.llm import LLMClient
                llm_client = LLMClient(config=resolved_model)
                text = await llm_client.generate_text(system_prompt, query)
                return {
                    "response": text,
                    "model": resolved_model,
                    "source": agent_name,
                }
            except Exception as exc:
                logger.warning(
                    "LLM agent '%s' failed: %s", agent_name, exc, exc_info=True
                )
                return {
                    "response": "",
                    "error": str(exc),
                    "source": agent_name,
                }

    # Give the class a unique name for debugging / repr
    ConfiguredLLMAgent.__name__ = f"{agent_name}_LLMAgent"
    ConfiguredLLMAgent.__qualname__ = f"{agent_name}_LLMAgent"

    # Propagate category and agent_type so _agent_info() can read them
    ConfiguredLLMAgent.category = agent_category
    ConfiguredLLMAgent.agent_type = "llm"

    return ConfiguredLLMAgent
