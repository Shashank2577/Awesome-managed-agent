"""LLM client supporting multiple providers via langchain-core."""

from __future__ import annotations

import asyncio
import json
import re
from decimal import Decimal
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from atrium.core.retry import async_retry


def parse_llm_config(config_str: str) -> tuple[str, str | None]:
    """Parse 'provider:model' string. Model is optional."""
    if ":" in config_str:
        provider, model = config_str.split(":", 1)
        return provider, model
    return config_str, None


def detect_llm() -> str:
    """Auto-detect the best LLM config from environment variables.

    Checks for API keys in order: GEMINI_API_KEY, GOOGLE_API_KEY,
    OPENAI_API_KEY, ANTHROPIC_API_KEY. Returns a 'provider:model' string
    for the first key found. Falls back to 'openai:gpt-4o-mini'.
    """
    import os

    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini:gemini-2.5-flash"
    if os.getenv("OPENAI_API_KEY"):
        return "openai:gpt-4o-mini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic:claude-sonnet-4-6"
    return "openai:gpt-4o-mini"  # fallback


def _strip_markdown_fence(text: str) -> str:
    """Remove ```json ... ``` wrappers if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


class LLMClient:
    """Unified LLM client for Commander and config-driven agent calls."""

    def __init__(self, config: str = "openai:gpt-4o-mini"):
        self._provider, self._model = parse_llm_config(config)

    def _get_chat_model(self):
        """Lazy-load the appropriate chat model with structured output where supported."""
        if self._provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self._model or "gpt-4o-mini",
                model_kwargs={"response_format": {"type": "json_object"}},
            )
        elif self._provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            # Anthropic structured output via tool-use is Phase 3; plain for now
            return ChatAnthropic(model=self._model or "claude-sonnet-4-6")
        elif self._provider in ("google", "gemini"):
            import os
            from langchain_google_genai import ChatGoogleGenerativeAI
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            kwargs: dict[str, Any] = {
                "model": self._model or "gemini-2.5-flash",
            }
            if api_key:
                kwargs["google_api_key"] = api_key
            return ChatGoogleGenerativeAI(**kwargs)
        else:
            raise ValueError(f"Unknown LLM provider: {self._provider}")

    def _extract_usage(self, response: Any) -> dict[str, int]:
        """LangChain v0.3 standardizes usage_metadata on the AIMessage."""
        meta = getattr(response, "usage_metadata", None)
        if not meta:
            return {}
        return {
            "input_tokens": int(meta.get("input_tokens", 0)),
            "output_tokens": int(meta.get("output_tokens", 0)),
            "total_tokens": int(meta.get("total_tokens", 0)),
        }

    async def generate_text(self, system_prompt: str, user_prompt: str, timeout: float = 60.0) -> str:
        """Send a system+user prompt and return the raw text response."""
        model = self._get_chat_model()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        async def _call():
            return await asyncio.wait_for(model.ainvoke(messages), timeout=timeout)

        response = await async_retry(_call, max_attempts=3)
        return response.content.strip()

    async def generate_json(
        self, system_prompt: str, user_prompt: str
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Send a system+user prompt and parse the response as JSON.

        Returns:
            (parsed_payload, usage_dict) where usage_dict has keys:
            'input_tokens', 'output_tokens', 'total_tokens'.
            Empty dict if the provider didn't return usage.
        """
        model = self._get_chat_model()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        async def _call():
            return await model.ainvoke(messages)

        response = await async_retry(_call, max_attempts=3)
        text = _strip_markdown_fence(response.content)
        payload = json.loads(text)
        usage = self._extract_usage(response)
        return payload, usage

    def model_key(self) -> str:
        """Return the canonical 'provider:model' key for pricing lookups."""
        model = self._model or ""
        return f"{self._provider}:{model}"
