"""Phase 2 BridgeStream unit tests (mocked sandbox)."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from atrium.harness.bridge import BridgeStream, GuardrailEnforcer
from atrium.harness.session import Session
from atrium.core.errors import GuardrailViolation
from atrium.streaming.events import EventRecorder
from atrium.core.artifact_store import ArtifactStore


def make_session(tmp_path) -> Session:
    ws = tmp_path / "ws"
    ws.mkdir(mode=0o700, exist_ok=True)
    return Session(
        workspace_id="ws1",
        objective="test",
        runtime="echo",
        model="",
        workspace_path=str(ws),
    )


class FakeSandbox:
    """Sandbox that yields scripted event lines."""

    def __init__(self, lines: list[dict]) -> None:
        self._lines = lines
        self._stdin: list[str] = []
        self.stopped = False
        self.killed = False
        self.container_id = "fake:1"

    async def send_input(self, text: str) -> None:
        self._stdin.append(text)

    async def stream_events(self):
        for line in self._lines:
            yield json.dumps(line).encode()

    async def stop(self, timeout_seconds: float = 10.0) -> None:
        self.stopped = True

    async def kill(self) -> None:
        self.killed = True


async def make_bridge(tmp_path, lines: list[dict]) -> tuple[BridgeStream, EventRecorder, FakeSandbox]:
    session = make_session(tmp_path)
    recorder = EventRecorder()
    artifact_store = ArtifactStore(":memory:")
    await artifact_store.open()
    sandbox = FakeSandbox(lines)
    guardrails = GuardrailEnforcer(max_tool_calls=200)
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, guardrails)
    return bridge, recorder, sandbox


async def test_translate_echo_tool_call_emits_harness_tool_called(tmp_path):
    lines = [
        {"type": "ready"},
        {"type": "tool_call", "tool": "grep", "input": {"pattern": "foo"}},
        {"type": "result", "text": "done", "files": []},
    ]
    bridge, recorder, _ = await make_bridge(tmp_path, lines)
    await bridge.run("find foo")
    events = recorder.replay(bridge._session.session_id)
    types = [e.type for e in events]
    assert "HARNESS_TOOL_CALLED" in types


async def test_translate_echo_result_emits_harness_message(tmp_path):
    lines = [
        {"type": "ready"},
        {"type": "result", "text": "All done!", "files": []},
    ]
    bridge, recorder, _ = await make_bridge(tmp_path, lines)
    result = await bridge.run("do it")
    assert result.final_message == "All done!"
    events = recorder.replay(bridge._session.session_id)
    types = [e.type for e in events]
    assert "HARNESS_MESSAGE" in types


async def test_artifacts_indexed_after_result_event(tmp_path):
    # Write a file into the workspace before the bridge runs
    session = make_session(tmp_path)
    ws = session.workspace_dir
    (ws / "output.txt").write_text("some output")

    recorder = EventRecorder()
    artifact_store = ArtifactStore(":memory:")
    await artifact_store.open()
    sandbox = FakeSandbox([
        {"type": "ready"},
        {"type": "result", "text": "done", "files": ["output.txt"]},
    ])
    guardrails = GuardrailEnforcer()
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, guardrails)
    result = await bridge.run("test")
    assert len(result.artifacts) == 1
    assert result.artifacts[0].path == "output.txt"



async def test_malformed_json_lines_are_dropped_not_fatal(tmp_path):
    lines_raw = [
        b"not json at all\n",
        json.dumps({"type": "result", "text": "ok", "files": []}).encode(),
    ]

    class RawSandbox(FakeSandbox):
        def __init__(self, raw_lines):
            self._raw_lines = raw_lines
            self._stdin = []
            self.stopped = False
            self.killed = False
            self.container_id = "raw:1"

        async def stream_events(self):
            for line in self._raw_lines:
                yield line

    session = make_session(tmp_path)
    recorder = EventRecorder()
    artifact_store = ArtifactStore(":memory:")
    await artifact_store.open()
    sandbox = RawSandbox(lines_raw)
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, GuardrailEnforcer())
    result = await bridge.run("test")
    assert result.final_message == "ok"


async def test_bridge_returns_after_result_event(tmp_path):
    lines = [
        {"type": "ready"},
        {"type": "message", "text": "working..."},
        {"type": "result", "text": "finished", "files": []},
        # These should NOT be consumed
        {"type": "message", "text": "after result"},
    ]
    bridge, recorder, _ = await make_bridge(tmp_path, lines)
    result = await bridge.run("test")
    assert result.final_message == "finished"


async def test_guardrail_violation_kills_sandbox(tmp_path):
    # Exceed tool call limit
    lines = [{"type": "tool_call", "tool": "bash", "input": {}} for _ in range(5)]
    lines.append({"type": "result", "text": "done", "files": []})

    session = make_session(tmp_path)
    recorder = EventRecorder()
    artifact_store = ArtifactStore(":memory:")
    await artifact_store.open()
    sandbox = FakeSandbox(lines)
    guardrails = GuardrailEnforcer(max_tool_calls=3)  # limit set to 3
    bridge = BridgeStream(sandbox, session, recorder, artifact_store, guardrails)

    with pytest.raises(GuardrailViolation, match="MAX_TOOL_CALLS"):
        await bridge.run("test")
