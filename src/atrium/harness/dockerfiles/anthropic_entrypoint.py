"""Inside-the-sandbox entrypoint for the Direct Anthropic runtime.

Reads objective from ATRIUM_OBJECTIVE env var (or first stdin line as fallback),
drives the Anthropic SDK, and emits claude_code_stream_json events to stdout.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import anthropic


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--system-prompt-file", default=None)
    return p


async def main() -> int:
    args = _build_parser().parse_args()

    system_prompt = "You are a capable AI assistant. Reason carefully and complete the objective."
    if args.system_prompt_file:
        try:
            with open(args.system_prompt_file) as f:
                system_prompt = f.read()
        except OSError:
            pass

    objective = os.environ.get("ATRIUM_OBJECTIVE", "").strip()
    if not objective:
        objective = sys.stdin.readline().strip()
    if not objective:
        emit({"type": "result", "subtype": "error", "message": "no objective provided"})
        return 1

    client = anthropic.AsyncAnthropic()
    model = args.model

    emit({"type": "system", "subtype": "init", "model": model})

    full_text = ""
    input_tokens = 0
    output_tokens = 0

    try:
        async with client.messages.stream(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": objective}],
        ) as stream:
            async for text_chunk in stream.text_stream:
                full_text += text_chunk

            final = await stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens
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
