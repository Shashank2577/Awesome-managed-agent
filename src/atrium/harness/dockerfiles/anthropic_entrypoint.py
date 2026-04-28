"""Inside-the-sandbox entrypoint for the Direct Anthropic runtime.

Reads stdin (first line = objective), drives the Claude agent SDK's async
iterator, and emits one claude_code_stream_json event per line to stdout.
No output goes to stdout except JSON event lines; errors go to stderr.

Usage:
  python anthropic_entrypoint.py [--model MODEL] [--system-prompt-file PATH]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Optional: claude-agent-sdk-python is only installed in the container image.
try:
    from claude_agent import ClaudeAgent  # type: ignore[import-not-found]
except ImportError:
    ClaudeAgent = None  # type: ignore[misc,assignment]

try:
    import anthropic as _anthropic_sdk  # type: ignore[import-not-found]
except ImportError:
    _anthropic_sdk = None  # type: ignore[assignment]


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--system-prompt-file", default=None)
    return p


async def _run_with_agent_sdk(model: str, system_prompt: str | None, objective: str) -> None:
    """Drive claude-agent-sdk-python and emit events."""
    if ClaudeAgent is None:
        emit({"type": "result", "subtype": "error", "message": "claude-agent-sdk-python not installed"})
        return

    agent = ClaudeAgent(
        model=model,
        system_prompt=system_prompt,
        workspace_dir=os.environ.get("ATRIUM_WORKSPACE_DIR", "/workspace"),
        stream=True,
    )

    emit({"type": "system", "subtype": "init", "model": model})

    async for event in agent.run(objective):
        emit(event)
        if event.get("type") == "result":
            break


async def _run_fallback(model: str, system_prompt: str | None, objective: str) -> None:
    """Fallback: use anthropic SDK directly when claude-agent-sdk not available."""
    if _anthropic_sdk is None:
        emit({"type": "result", "subtype": "error", "message": "anthropic SDK not installed"})
        return

    client = _anthropic_sdk.AsyncAnthropic()
    emit({"type": "system", "subtype": "init", "model": model})

    messages = [{"role": "user", "content": objective}]
    system = system_prompt or ""

    async with client.messages.stream(
        model=model,
        max_tokens=8192,
        system=system,
        messages=messages,
    ) as stream:
        async for event in stream:
            # Map raw anthropic stream events to our format
            ev_type = type(event).__name__
            if ev_type == "RawContentBlockDeltaEvent":
                if hasattr(event, "delta") and hasattr(event.delta, "text"):
                    emit({
                        "type": "assistant",
                        "message": {"content": [{"type": "text", "text": event.delta.text}]},
                    })
            elif ev_type == "RawMessageStopEvent":
                pass

        final = await stream.get_final_message()
        usage = final.usage
        emit({
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": final.content[0].text if final.content else ""}],
                "usage": {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                },
            },
        })

    emit({"type": "result", "subtype": "success", "result": "Done."})


async def main() -> int:
    args = _build_parser().parse_args()
    system_prompt: str | None = None
    if args.system_prompt_file:
        with open(args.system_prompt_file) as f:
            system_prompt = f.read()

    objective = sys.stdin.readline().strip()
    if not objective:
        emit({"type": "result", "subtype": "error", "message": "no objective provided"})
        return 1

    if ClaudeAgent is not None:
        await _run_with_agent_sdk(args.model, system_prompt, objective)
    else:
        await _run_fallback(args.model, system_prompt, objective)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
