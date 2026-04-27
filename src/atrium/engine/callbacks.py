"""Bridges agent execution events to the Atrium EventRecorder."""
from __future__ import annotations

from atrium.streaming.events import EventRecorder


async def emit_agent_running(recorder: EventRecorder, thread_id: str, agent_key: str) -> None:
    await recorder.emit(thread_id, "AGENT_RUNNING", {"agent_key": agent_key})


async def emit_agent_completed(
    recorder: EventRecorder, thread_id: str, agent_key: str, output: dict
) -> None:
    await recorder.emit(thread_id, "AGENT_COMPLETED", {"agent_key": agent_key})
    await recorder.emit(thread_id, "AGENT_OUTPUT", {"agent_key": agent_key, "output": output})


async def emit_agent_failed(
    recorder: EventRecorder, thread_id: str, agent_key: str, error: str
) -> None:
    await recorder.emit(thread_id, "AGENT_FAILED", {"agent_key": agent_key, "error": error})
