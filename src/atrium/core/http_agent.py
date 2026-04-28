"""Config-driven HTTP agent — created from a dict, no Python code needed."""

from __future__ import annotations

from typing import Any

import httpx

from atrium.core.agent import Agent
from atrium.core._input_utils import extract_query


def create_agent_class(config: dict[str, Any]) -> type[Agent]:
    """Create an Agent subclass from a config dict.

    The returned class satisfies the AgentMeta checks (``name`` and ``description``
    are set as class attributes) and captures *config* in a closure so each instance
    has access to the full HTTP configuration.

    Args:
        config: Must contain at least ``name`` and ``description``.  Optional keys:
            ``capabilities``, ``api_url``, ``method``, ``headers``,
            ``query_params``, ``response_path``.

    Returns:
        A unique ``Agent`` subclass ready for registration.
    """

    agent_name: str = config["name"]
    agent_desc: str = config["description"]
    agent_caps: list[str] = config.get("capabilities", [])

    class ConfiguredHTTPAgent(Agent):
        name = agent_name
        description = agent_desc
        capabilities = list(agent_caps)
        input_schema: dict | None = {"query": "str"}
        output_schema: dict | None = {"result": "dict"}

        def __init__(self) -> None:
            super().__init__()
            self._config: dict[str, Any] = config

        async def run(self, input_data: dict) -> dict:
            query = extract_query(input_data)

            api_url = self._config.get("api_url", "")
            await self.say(f"Calling {api_url or 'API'}...")

            method = self._config.get("method", "GET").upper()
            headers = dict(self._config.get("headers", {}))

            # Substitute {query} / {input.query} in URL
            url = api_url.replace("{query}", query).replace("{input.query}", query)

            # Substitute in query params
            params: dict[str, str] = {}
            for k, v in self._config.get("query_params", {}).items():
                params[k] = (
                    str(v).replace("{query}", query).replace("{input.query}", query)
                )

            async with httpx.AsyncClient(
                headers={"User-Agent": "Atrium/0.1", **headers},
                timeout=30.0,
            ) as client:
                if method == "GET":
                    resp = await client.get(url, params=params)
                else:
                    resp = await client.post(url, json=params)
                resp.raise_for_status()
                data = resp.json()

            # Extract nested data via response_path
            result: Any = data
            response_path: str = self._config.get("response_path", "")
            if response_path:
                for key in response_path.split("."):
                    if isinstance(result, dict):
                        result = result.get(key, result)
                    elif isinstance(result, list) and key.isdigit():
                        result = result[int(key)]

            await self.say(f"Got response from {self._config['name']}")

            return {"result": result, "query": query, "source": self._config["name"]}

    # Give the class a unique name for debugging / repr
    ConfiguredHTTPAgent.__name__ = f"{agent_name}_Agent"
    ConfiguredHTTPAgent.__qualname__ = f"{agent_name}_Agent"

    # Propagate category and agent_type so _agent_info() can read them
    ConfiguredHTTPAgent.category = config.get("category")
    ConfiguredHTTPAgent.agent_type = config.get("agent_type", "http")

    return ConfiguredHTTPAgent
