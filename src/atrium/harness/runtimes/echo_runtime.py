"""Inside-the-sandbox script for the Echo runtime.

Reads stdin lines as user inputs. Emits scripted JSON events on stdout.
Writes a file to /workspace/echo.txt. No LLM call.

Event format (one JSON object per line):
  {"type": "ready"}
  {"type": "tool_call", "tool": "echo", "input": {"text": "..."}}
  {"type": "tool_result", "tool": "echo", "output": "..."}
  {"type": "message", "text": "..."}
  {"type": "result", "text": "...", "files": ["echo.txt"]}
"""
from __future__ import annotations

import json
import os
import sys
import time


def emit(event: dict) -> None:
    """Write one JSON line to stdout and flush."""
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def main() -> int:
    emit({"type": "ready"})

    # Read first line of input — that's the objective.
    objective = sys.stdin.readline().strip()
    if not objective:
        emit({"type": "result", "text": "no objective provided", "files": []})
        return 0

    # Simulate two scripted tool calls.
    emit({"type": "tool_call", "tool": "echo", "input": {"text": objective}})
    time.sleep(0.05)
    emit({"type": "tool_result", "tool": "echo", "output": objective.upper()})

    emit({"type": "message", "text": f"Echoing: {objective}"})

    # Write an artifact.
    workspace = os.environ.get("ATRIUM_WORKSPACE_DIR", "/workspace")
    out_path = os.path.join(workspace, "echo.txt")
    with open(out_path, "w") as f:
        f.write(f"Echo result: {objective}\nUppercase: {objective.upper()}\n")

    emit({"type": "tool_call", "tool": "write_file", "input": {"path": "echo.txt"}})
    emit({"type": "tool_result", "tool": "write_file", "output": f"wrote {len(objective)*2 + 30} bytes"})

    emit({"type": "result", "text": "Done. Wrote echo.txt with the result.", "files": ["echo.txt"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
