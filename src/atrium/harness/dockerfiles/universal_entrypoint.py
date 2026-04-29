"""Universal LLM entrypoint — works with any OpenAI-compatible API.

Reads from env vars:
  LLM_BASE_URL  — provider API base (e.g. https://openrouter.ai/api/v1)
  LLM_API_KEY   — provider API key
  LLM_MODEL     — model identifier as the provider expects it
  ATRIUM_OBJECTIVE — the task to complete

Emits claude_code_stream_json events to stdout.
Works with: OpenRouter, OpenAI, xAI, NVIDIA NIM, Groq, Gemini (compat),
            Together, Perplexity, Ollama, any OpenAI-compatible endpoint.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from openai import AsyncOpenAI


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


async def main() -> int:
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    objective = os.environ.get("ATRIUM_OBJECTIVE", "").strip()

    if not objective:
        objective = sys.stdin.readline().strip()
    if not objective:
        emit({"type": "result", "subtype": "error", "message": "no objective provided"})
        return 1

    if not api_key:
        emit({"type": "result", "subtype": "error",
              "message": "LLM_API_KEY not set — configure a provider in Settings"})
        return 1

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    emit({"type": "system", "subtype": "init", "model": model, "base_url": base_url})

    system_prompt = os.environ.get(
        "LLM_SYSTEM_PROMPT",
        "You are a capable AI assistant. Reason carefully and complete the objective."
    )

    full_text = ""
    input_tokens = 0
    output_tokens = 0

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": objective},
            ],
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                full_text += delta.content
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens or 0
                output_tokens = chunk.usage.completion_tokens or 0

    except Exception as exc:
        emit({"type": "result", "subtype": "error", "message": str(exc)})
        return 1

    emit({
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": full_text}],
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        },
    })
    emit({"type": "result", "subtype": "success", "result": full_text})
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
