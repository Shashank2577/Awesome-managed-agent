"""Universal agentic entrypoint — provider-agnostic agent loop with tools.

Works with any OpenAI-compatible API:
  OpenRouter, OpenAI, Google Gemini, xAI/Grok, NVIDIA NIM, Groq, Ollama, Anthropic (via OpenRouter)

Env vars:
  LLM_BASE_URL      — provider API base URL
  LLM_API_KEY       — provider API key
  LLM_MODEL         — model identifier
  LLM_SYSTEM_PROMPT — optional system prompt override
  ATRIUM_OBJECTIVE  — task objective
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from openai import AsyncOpenAI


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Execute a shell command in the sandbox. Working directory is /workspace. "
                "Returns stdout+stderr. Use to run scripts, compile code, list files, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents. Path relative to /workspace or absolute.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates parent directories automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (relative to /workspace or absolute)"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a URL and return its content as clean markdown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"}
                },
                "required": ["url"],
            },
        },
    },
]


async def run_bash(command: str) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd="/workspace",
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        output = stdout.decode(errors="replace").strip()
        return output[:8000] if output else "(no output)"
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return "Error: command timed out after 30 seconds"
    except Exception as exc:
        return f"Error: {exc}"


def run_read_file(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join("/workspace", path)
    try:
        with open(path) as f:
            return f.read(8000)
    except Exception as exc:
        return f"Error reading {path}: {exc}"


def run_write_file(path: str, content: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join("/workspace", path)
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:
        return f"Error writing {path}: {exc}"


async def run_web_fetch(url: str) -> str:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(
                f"https://r.jina.ai/{url}",
                headers={"User-Agent": "Atrium/0.1"},
            )
            return resp.text[:8000]
    except Exception as exc:
        return f"Error fetching {url}: {exc}"


async def execute_tool(name: str, args: dict[str, Any]) -> str:
    if name == "bash":
        return await run_bash(args.get("command", ""))
    if name == "read_file":
        return run_read_file(args.get("path", ""))
    if name == "write_file":
        return run_write_file(args.get("path", ""), args.get("content", ""))
    if name == "web_fetch":
        return await run_web_fetch(args.get("url", ""))
    return f"Unknown tool: {name}"


async def main() -> int:
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    objective = os.environ.get("ATRIUM_OBJECTIVE", "").strip()
    system_prompt = os.environ.get(
        "LLM_SYSTEM_PROMPT",
        (
            "You are a capable AI agent running inside an isolated sandbox. "
            "You have tools to write and run code, read/write files, and fetch web pages. "
            "Think step by step. Use tools to complete the objective. "
            "When finished, provide a clear summary of what you did and the results."
        ),
    )

    if not objective:
        objective = sys.stdin.readline().strip()
    if not objective:
        emit({"type": "result", "subtype": "error", "message": "no objective provided"})
        return 1
    if not api_key:
        emit({"type": "result", "subtype": "error",
              "message": "LLM_API_KEY not set — enter your API key in the provider panel"})
        return 1

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    emit({"type": "system", "subtype": "init", "model": model, "base_url": base_url})

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": objective},
    ]

    total_input_tokens = 0
    total_output_tokens = 0
    final_text = ""

    for _ in range(20):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
        except Exception as exc:
            emit({"type": "result", "subtype": "error", "message": str(exc)})
            return 1

        msg = response.choices[0].message
        if response.usage:
            total_input_tokens += response.usage.prompt_tokens or 0
            total_output_tokens += response.usage.completion_tokens or 0

        tool_calls = msg.tool_calls or []

        # Build content blocks for Atrium event
        content_blocks: list[dict] = []
        if msg.content:
            content_blocks.append({"type": "text", "text": msg.content})
            final_text = msg.content
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}
            content_blocks.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.function.name,
                "input": args,
            })

        emit({
            "type": "assistant",
            "message": {
                "content": content_blocks,
                "usage": {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                },
            },
        })

        if not tool_calls:
            break

        # Append assistant turn (OpenAI wire format)
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        })

        # Execute tools and emit results
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}
            result = await execute_tool(tc.function.name, args)
            emit({
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "tool_use_id": tc.id, "content": result}]
                },
            })
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    emit({"type": "result", "subtype": "success", "result": final_text or "Task completed."})
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
