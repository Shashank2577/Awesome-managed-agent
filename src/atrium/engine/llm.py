"""LLM client supporting multiple providers via langchain-core."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage


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
    """Unified LLM client for Commander planning calls."""

    def __init__(self, config: str = "openai:gpt-4o-mini"):
        self._provider, self._model = parse_llm_config(config)

    def _get_chat_model(self):
        """Lazy-load the appropriate chat model."""
        if self._provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=self._model or "gpt-4o-mini")
        elif self._provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=self._model or "claude-sonnet-4-6")
        elif self._provider in ("google", "gemini"):
            import os
            from langchain_google_genai import ChatGoogleGenerativeAI
            # Support both GEMINI_API_KEY and GOOGLE_API_KEY
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            kwargs = {"model": self._model or "gemini-2.5-flash"}
            if api_key:
                kwargs["google_api_key"] = api_key
            return ChatGoogleGenerativeAI(**kwargs)
        else:
            raise ValueError(f"Unknown LLM provider: {self._provider}")

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        """Send a system+user prompt and return the raw text response.

        Args:
            system_prompt: The system-level instruction for the model.
            user_prompt: The user-level message / query.

        Returns:
            Stripped text content from the model response.
        """
        model = self._get_chat_model()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = await model.ainvoke(messages)
        return response.content.strip()

    async def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Send a system+user prompt and parse the response as JSON."""
        text = await self.generate_text(system_prompt, user_prompt)
        text = _strip_markdown_fence(text)
        return json.loads(text)
