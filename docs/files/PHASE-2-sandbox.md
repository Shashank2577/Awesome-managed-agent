# PHASE 2 — Sandbox Foundation

**Goal:** the SandboxRunner, Session, and BridgeStream all work end-to-end
with a trivial Echo runtime that doesn't call any LLM. Lays the entire
plumbing for the harness without any model integration risk.

**Estimated effort:** 7 days (1 engineer).

**Depends on:** Phase 1.

**Unblocks:** Phases 3–6.

## 2.1 Files to create or modify

| Action | Path | What |
|--------|------|------|
| MODIFY | `src/atrium/harness/__init__.py` | Real exports. |
| MODIFY | `src/atrium/harness/agent.py` | Real implementation. |
| MODIFY | `src/atrium/harness/session.py` | Real implementation + SessionStore. |
| MODIFY | `src/atrium/harness/sandbox.py` | DockerSandboxRunner + InMemorySandboxRunner. |
| MODIFY | `src/atrium/harness/bridge.py` | Real BridgeStream. |
| MODIFY | `src/atrium/harness/runtimes/base.py` | Final Runtime protocol. |
| MODIFY | `src/atrium/harness/runtimes/echo.py` | Working echo runtime. |
| CREATE | `src/atrium/harness/dockerfiles/echo.Dockerfile` | Echo image. |
| CREATE | `src/atrium/harness/runtimes/echo_runtime.py` | The Python script that runs INSIDE the echo container. |
| CREATE | `src/atrium/api/routes/sessions.py` | `/api/v1/sessions/*` routes. |
| CREATE | `src/atrium/api/routes/artifacts.py` | `/api/v1/artifacts/*` routes. |
| CREATE | `src/atrium/core/sessions_store.py` | Session persistence. |
| CREATE | `src/atrium/core/artifact_store.py` | Artifact persistence. |
| MODIFY | `src/atrium/api/app.py` | Mount new routes; init new stores. |
| MODIFY | `migrations/versions/0002_artifacts.py` | Artifacts table. |
| MODIFY | `pyproject.toml` | Add `aiodocker`, `aiofiles`. |
| CREATE | `tests/test_harness/test_session_lifecycle.py` |  |
| CREATE | `tests/test_harness/test_in_memory_sandbox.py` |  |
| CREATE | `tests/test_harness/test_bridge_stream.py` |  |
| CREATE | `tests/test_harness/test_artifacts.py` |  |
| CREATE | `tests/integration/test_echo_session_end_to_end.py` |  |

## 2.2 Final `Runtime` protocol

```python
# verbatim — src/atrium/harness/runtimes/base.py
"""Runtime protocol implemented by every inner-loop adapter."""
from __future__ import annotations

from typing import Protocol


class Runtime(Protocol):
    """A runtime tells the SandboxRunner WHICH image and HOW to start it."""

    name: str
    event_format: str

    def image_tag(self, registry: str) -> str:
        """Full image reference, e.g. 'atrium/echo:0.1.0'."""
        ...

    def command(self, model: str, system_prompt_path: str | None) -> list[str]:
        """argv for the container entrypoint."""
        ...

    def model_endpoint(self, model: str) -> str:
        """Egress URL to allow-list for the network policy. Empty if no egress needed."""
        ...

    def required_env(self, model: str) -> dict[str, str]:
        """Names of env vars the runtime needs. Values come from the secret store."""
        ...
```

`event_format` is one of: `"claude_code_stream_json"` (real runtimes),
`"echo"` (test runtime). The bridge picks a translator based on this.

## 2.3 Final `EchoRuntime`

```python
# verbatim — src/atrium/harness/runtimes/echo.py
"""Echo runtime — emits scripted events; no model call. Phase 2 uses this."""
from __future__ import annotations


class EchoRuntime:
    name = "echo"
    event_format = "echo"

    def image_tag(self, registry: str) -> str:
        return f"{registry}/echo:0.1.0"

    def command(self, model: str, system_prompt_path: str | None) -> list[str]:
        return ["python", "/app/echo_runtime.py"]

    def model_endpoint(self, model: str) -> str:
        return ""  # echo needs no egress

    def required_env(self, model: str) -> dict[str, str]:
        return {}  # no secrets needed
```

## 2.4 The container script: `runtimes/echo_runtime.py`

This is the CODE that runs INSIDE the echo container, not on the host.
Bundled into the echo Docker image at `/app/echo_runtime.py`.

```python
# verbatim
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

    emit({"type": "result", "text": f"Done. Wrote echo.txt with the result.", "files": ["echo.txt"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 2.5 The Echo Dockerfile

```dockerfile
# verbatim — src/atrium/harness/dockerfiles/echo.Dockerfile
FROM python:3.12-slim

RUN useradd -u 10001 -m atrium
RUN mkdir -p /workspace /app && chown -R atrium:atrium /workspace /app

COPY --chown=atrium:atrium echo_runtime.py /app/echo_runtime.py

USER atrium
WORKDIR /workspace

ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/echo_runtime.py"]
```

Build: `docker build -f src/atrium/harness/dockerfiles/echo.Dockerfile
-t atrium/echo:0.1.0 src/atrium/harness/runtimes/`.

## 2.6 `SandboxRunner` — abstract interface and two implementations

```python
# verbatim — src/atrium/harness/sandbox.py (interface portion)
"""Container lifecycle abstraction. Two implementations in v1."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import AsyncIterator

from atrium.harness.runtimes.base import Runtime
from atrium.harness.session import Session


@dataclass
class ResourceLimits:
    cpus: float = 2.0
    memory_mb: int = 4096
    disk_mb: int = 8192
    wall_clock_seconds: int = 3600


@dataclass
class NetworkPolicy:
    allow_egress: list[str] = field(default_factory=list)
    allow_mcp: bool = False  # Phase 4 wires this to the gateway


class SandboxRunner(abc.ABC):
    """Abstract sandbox runner. Subclasses: Docker, Kubernetes, InMemory."""

    @classmethod
    @abc.abstractmethod
    async def start(
        cls,
        session: Session,
        runtime: Runtime,
        model: str,
        env: dict[str, str],
        limits: ResourceLimits,
        network_policy: NetworkPolicy,
    ) -> "SandboxRunner": ...

    @abc.abstractmethod
    async def stream_events(self) -> AsyncIterator[bytes]: ...

    @abc.abstractmethod
    async def send_input(self, text: str) -> None: ...

    @abc.abstractmethod
    async def stop(self, timeout_seconds: float = 10.0) -> None: ...

    @abc.abstractmethod
    async def kill(self) -> None: ...

    @property
    @abc.abstractmethod
    def container_id(self) -> str: ...
```

### `DockerSandboxRunner`

Backed by `aiodocker`. Concrete behaviour:

- `start()`:
  - Pull the image if not present.
  - Create a container with:
    - `Image=runtime.image_tag(registry)`
    - `Cmd=runtime.command(model, system_prompt_path)`
    - `Env=[f"{k}={v}" for k,v in env.items()]`
    - `WorkingDir="/workspace"`
    - `User="10001:10001"`
    - `HostConfig.Binds=[f"{session.workspace_dir}:/workspace:rw"]`
    - `HostConfig.NetworkMode="atrium-egress-{session_id}"`
      (a network we create with iptables egress rules, OR — for v1
      simplicity — `bridge` with no egress restriction; the formal
      egress allow-list comes via the MCP gateway in Phase 4)
    - `HostConfig.Memory=limits.memory_mb * 1024 * 1024`
    - `HostConfig.NanoCpus=int(limits.cpus * 1_000_000_000)`
    - `HostConfig.AutoRemove=True` (cleanup on stop)
    - `HostConfig.SecurityOpt=["no-new-privileges:true"]`
    - `HostConfig.ReadonlyRootfs=True` (workspace is the only writable mount)
    - `HostConfig.Tmpfs={"/tmp": "rw,size=100m"}`
  - Start the container.
  - Attach to stdin/stdout/stderr.
  - Spawn an asyncio task that watches container state; if it exits,
    enqueues a sentinel on the event queue.

- `stream_events()`:
  - Yields raw bytes one JSON line at a time from container stdout.
  - On container exit, raises `StopAsyncIteration` after flushing
    buffered stdout.

- `send_input(text)`:
  - Writes `text + "\n"` to container stdin.
  - Used for sending the initial objective and for follow-up messages.

- `stop(timeout_seconds=10.0)`:
  - Send SIGTERM; wait up to `timeout_seconds`; if still running, SIGKILL.
  - Container is auto-removed.

- `kill()`:
  - Immediate SIGKILL. Used on guardrail violations.

### `InMemorySandboxRunner`

Used in unit tests. Doesn't actually start a container; runs the
runtime's command as a subprocess on the host with the workspace dir
mounted as the cwd. Implements the same protocol. Suitable only for
the Echo runtime.

```python
# template
class InMemorySandboxRunner(SandboxRunner):
    """In-process subprocess runner. Tests only."""

    @classmethod
    async def start(cls, session, runtime, model, env, limits, network_policy):
        # Spawn echo_runtime.py via asyncio.create_subprocess_exec, with
        # cwd=session.workspace_dir. Hold proc handle.
        ...

    async def stream_events(self):
        async for line in self._proc.stdout:
            yield line
```

## 2.7 `Session` and `SessionStore`

```python
# verbatim — src/atrium/harness/session.py (model)
class SessionStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    title: str = ""
    objective: str = ""
    status: SessionStatus = SessionStatus.CREATED
    runtime: str = ""
    model: str = ""
    container_id: str | None = None
    workspace_path: str = ""
    parent_thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    last_active_at: datetime = Field(default_factory=_utcnow)

    @property
    def workspace_dir(self) -> Path:
        return Path(self.workspace_path)
```

`SessionStore` (in `core/sessions_store.py`) follows the same pattern
as `ThreadStore`. Methods:

- `async def create(session: Session) -> None`
- `async def get(workspace_id: str, session_id: str) -> Session | None`
- `async def list_by_workspace(workspace_id: str, status: SessionStatus | None = None) -> list[Session]`
- `async def set_status(workspace_id: str, session_id: str, status: SessionStatus) -> None`
- `async def set_container_id(workspace_id: str, session_id: str, container_id: str | None) -> None`
- `async def touch(workspace_id: str, session_id: str) -> None` — update `last_active_at` to now.
- `async def delete(workspace_id: str, session_id: str) -> None`

Status transitions are validated:

```
CREATED → RUNNING
CREATED → CANCELLED
RUNNING → PAUSED
RUNNING → COMPLETED
RUNNING → FAILED
RUNNING → CANCELLED
PAUSED  → RUNNING
PAUSED  → CANCELLED
```

Anything else raises `ConflictError`.

The session's `workspace_path` is set on creation by SessionStore as
`{config.sessions_root}/{workspace_id}/{session_id}`. The directory is
created with mode 0700.

## 2.8 `BridgeStream` — the integration core

```python
# template — src/atrium/harness/bridge.py
class BridgeStream:
    def __init__(
        self,
        sandbox: SandboxRunner,
        session: Session,
        recorder: EventRecorder,
        artifact_store: ArtifactStore,
        guardrails: GuardrailEnforcer,
    ): ...

    async def run(
        self,
        objective: str,
        max_tool_calls: int = 200,
    ) -> BridgeResult:
        """Drive the sandbox to completion. Stream events. Apply guardrails."""
        # 1. Send objective on stdin.
        await self._sandbox.send_input(objective)

        # 2. Iterate the sandbox's stdout.
        result_event: dict | None = None
        async for raw_line in self._sandbox.stream_events():
            try:
                event = json.loads(raw_line.decode().strip())
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.debug("dropped non-json line", extra={"line": raw_line[:200]})
                continue

            atrium_drafts = self._translate(event)
            for draft in atrium_drafts:
                await self._recorder.emit(
                    self._session.session_id,
                    draft.type,
                    draft.payload,
                    workspace_id=self._session.workspace_id,
                )

            self._apply_guardrails(event)

            if event.get("type") == "result":
                result_event = event
                break

        # 3. Index artifacts produced.
        artifacts = await self._index_artifacts(result_event.get("files", []))

        return BridgeResult(
            final_message=result_event.get("text", ""),
            artifacts=artifacts,
            tokens_used=self._tokens_used,
        )

    def _translate(self, event: dict) -> list[AtriumEventDraft]: ...
    def _apply_guardrails(self, event: dict) -> None: ...
    async def _index_artifacts(self, file_paths: list[str]) -> list[Artifact]: ...
```

### Translation table — Echo format (Phase 2)

| Inner event | Atrium event(s) |
|-------------|-----------------|
| `{"type": "ready"}` | (none — internal handshake) |
| `{"type": "tool_call", "tool": T, "input": I}` | `HARNESS_TOOL_CALLED` payload `{tool: T, input: I}` |
| `{"type": "tool_result", "tool": T, "output": O}` | `HARNESS_TOOL_RESULT` payload `{tool: T, output: O}` |
| `{"type": "message", "text": X}` | `HARNESS_MESSAGE` payload `{text: X}` |
| `{"type": "result", "text": X, "files": F}` | `HARNESS_MESSAGE` payload `{text: X}` then loop emits `ARTIFACT_CREATED` per file in `_index_artifacts` |

Phase 3 will extend this table with `claude_code_stream_json` mappings.

### Artifact indexing

After the runtime's `result` event:

1. Walk the session's workspace directory.
2. For each file (skipping `.atrium/` and dotfiles), compute sha256
   and size.
3. For each file present in `result.files`, INSERT an `Artifact` row.
   For files NOT in `result.files` but present in the workspace, also
   INSERT (so external file writes are captured).
4. Emit `ARTIFACT_CREATED` per new file.

## 2.9 New table: `artifacts` (migration 0002)

```sql
CREATE TABLE artifacts (
    artifact_id   TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    path          TEXT NOT NULL,            -- relative to /workspace
    size_bytes    INTEGER NOT NULL,
    sha256        TEXT NOT NULL,
    content_type  TEXT NOT NULL DEFAULT 'application/octet-stream',
    created_at    TEXT NOT NULL,
    UNIQUE(session_id, path)
);

CREATE INDEX idx_artifacts_session ON artifacts(session_id);
CREATE INDEX idx_artifacts_workspace ON artifacts(workspace_id);
```

Updated existing files (same path) replace the row; the `created_at`
column stays as the original creation timestamp; an
`updated_at` is added if useful — left out for v1.

## 2.10 New routes

### POST `/api/v1/sessions`

Request:
```json
{
  "agent": "code_research",          // name in workspace registry
  "objective": "Investigate why X failing",
  "model_override": null,             // optional
  "timeout_seconds": 1800,            // optional, max 86400
  "metadata": {}                      // optional
}
```

Response 201:
```json
{
  "session_id": "...",
  "title": "Investigate why X failing",
  "status": "RUNNING",
  "stream_url": "/api/v1/sessions/{id}/stream",
  "workspace_id": "ws_..."
}
```

Errors: 400 if agent not found, 422 if agent isn't a HarnessAgent,
429 if workspace's `max_concurrent_sessions` quota exceeded.

Behaviour: Creates Session row, kicks off background task that
instantiates the HarnessAgent and runs it.

### GET `/api/v1/sessions`

Query params: `status` (optional, filter), `limit` (default 50, max 200).
Response: `{sessions: [SessionResponse]}`.

### GET `/api/v1/sessions/{id}`

Response: full session detail with all events (similar shape to
`GET /threads/{id}`).

### GET `/api/v1/sessions/{id}/stream`

SSE stream of events for this session. Same format as
`/threads/{id}/stream`.

### POST `/api/v1/sessions/{id}/cancel`

Marks the session CANCELLED. Calls `sandbox.kill()` if container exists.

### POST `/api/v1/sessions/{id}/messages`

Body: `{"text": "..."}`. Sends a follow-up to the running session
via `sandbox.send_input()`. 409 if session is not RUNNING.

(Pause/resume is Phase 5, when checkpointing lands.)

### GET `/api/v1/sessions/{id}/artifacts`

Response: `{artifacts: [{artifact_id, path, size_bytes, sha256, content_type, created_at}]}`.

### GET `/api/v1/artifacts/{artifact_id}`

Streams the file. Sets `Content-Type` from artifact's `content_type`.

### GET `/api/v1/artifacts/{artifact_id}/preview`

Returns text preview, capped at 1MB. 415 if `content_type` is binary.

### DELETE `/api/v1/artifacts/{artifact_id}`

409 if session is not in a terminal state. Otherwise deletes row and
underlying file.

## 2.11 Event schemas added in Phase 2

```
SESSION_CREATED       payload: {session_id, agent, objective, runtime, model}
SESSION_RUNNING       payload: {container_id}
SESSION_PAUSED        payload: {by: "operator" | "checkpoint"}
SESSION_RESUMED       payload: {by: "operator"}
SESSION_COMPLETED     payload: {final_message, artifacts: [artifact_id]}
SESSION_FAILED        payload: {error, error_code}
SESSION_CANCELLED     payload: {by: "operator" | "guardrail"}
SANDBOX_STARTED       payload: {container_id, image, limits}
SANDBOX_STOPPED       payload: {exit_code}
SANDBOX_KILLED        payload: {reason: "timeout" | "cost" | "operator"}
HARNESS_TOOL_CALLED   payload: {tool, input}
HARNESS_TOOL_RESULT   payload: {tool, output}
HARNESS_MESSAGE       payload: {text}
ARTIFACT_CREATED      payload: {artifact_id, path, size_bytes, sha256}
ARTIFACT_UPDATED      payload: {artifact_id, path, size_bytes, sha256}
ARTIFACT_DELETED      payload: {artifact_id, path}
```

## 2.12 `HarnessAgent.run()` — the real implementation

```python
# template
async def run(self, input_data: dict) -> dict:
    workspace_id = input_data["workspace_id"]
    objective = input_data["objective"]

    session = await self._session_store.create(
        Session(
            workspace_id=workspace_id,
            objective=objective,
            runtime=self.runtime.name,
            model=input_data.get("model_override") or self.model,
            parent_thread_id=input_data.get("thread_id"),
            workspace_path=self._workspace_path_for(workspace_id, ...),
        )
    )

    await self._recorder.emit(
        session.session_id, "SESSION_CREATED",
        {"session_id": session.session_id, "agent": self.name,
         "objective": objective, "runtime": self.runtime.name,
         "model": session.model},
        workspace_id=workspace_id,
    )

    sandbox = await self._sandbox_runner_cls.start(
        session=session,
        runtime=self.runtime,
        model=session.model,
        env=self._build_env(session),
        limits=ResourceLimits(wall_clock_seconds=self.timeout_seconds),
        network_policy=NetworkPolicy(
            allow_egress=[self.runtime.model_endpoint(session.model)],
            allow_mcp=bool(self.allowed_mcp_servers),
        ),
    )

    await self._session_store.set_container_id(
        workspace_id, session.session_id, sandbox.container_id,
    )
    await self._session_store.set_status(
        workspace_id, session.session_id, SessionStatus.RUNNING,
    )
    await self._recorder.emit(
        session.session_id, "SESSION_RUNNING",
        {"container_id": sandbox.container_id},
        workspace_id=workspace_id,
    )

    bridge = BridgeStream(sandbox, session, self._recorder,
                         self._artifact_store, self._guardrails)

    try:
        result = await bridge.run(objective, max_tool_calls=self.max_tool_calls)
        await self._session_store.set_status(
            workspace_id, session.session_id, SessionStatus.COMPLETED,
        )
        await self._recorder.emit(
            session.session_id, "SESSION_COMPLETED",
            {"final_message": result.final_message,
             "artifacts": [a.artifact_id for a in result.artifacts]},
            workspace_id=workspace_id,
        )
        return {
            "result": result.final_message,
            "artifacts": [a.artifact_id for a in result.artifacts],
            "session_id": session.session_id,
        }
    except GuardrailViolation as exc:
        await self._session_store.set_status(
            workspace_id, session.session_id, SessionStatus.FAILED,
        )
        await self._recorder.emit(
            session.session_id, "SESSION_FAILED",
            {"error": str(exc), "error_code": exc.error_code},
            workspace_id=workspace_id,
        )
        raise
    finally:
        await sandbox.stop()
```

## 2.13 Acceptance tests

### `tests/test_harness/test_session_lifecycle.py`

```
test_create_session_creates_workspace_dir_with_mode_0700
test_set_status_validates_transition
test_set_status_rejects_invalid_transition
test_get_returns_none_for_unknown_session
test_list_by_workspace_filters_by_status
test_session_isolated_across_workspaces
test_workspace_dir_is_deleted_on_session_delete
```

### `tests/test_harness/test_in_memory_sandbox.py`

```
test_in_memory_runner_starts_echo_subprocess
test_stream_events_yields_one_event_per_line
test_send_input_writes_to_subprocess_stdin
test_stop_terminates_subprocess
test_kill_sigkills_subprocess
```

### `tests/test_harness/test_bridge_stream.py`

```
test_translate_echo_tool_call_emits_harness_tool_called
test_translate_echo_result_emits_harness_message
test_artifacts_indexed_after_result_event
test_running_cost_accumulates_from_usage_events
test_guardrail_violation_kills_sandbox
test_malformed_json_lines_are_dropped_not_fatal
test_bridge_returns_after_result_event
```

### `tests/test_harness/test_artifacts.py`

```
test_artifact_row_inserted_with_correct_sha256
test_artifact_size_matches_file_size
test_duplicate_path_in_session_replaces_row
test_get_artifact_returns_404_in_other_workspace
test_delete_artifact_409_when_session_running
```

### `tests/integration/test_echo_session_end_to_end.py` (gated `-m integration`)

```
test_post_session_creates_running_session
test_session_completes_within_30s_for_echo_runtime
test_completed_session_has_one_artifact_named_echo_txt
test_artifact_is_downloadable
test_sse_stream_emits_session_completed_event
test_session_visible_in_list_with_status_completed
```

The integration test uses `InMemorySandboxRunner` not Docker — keeps
CI fast. There's a separate `tests/integration/docker/` suite that
exercises the real DockerSandboxRunner; gated behind a second marker
`-m docker` and only run nightly.

## 2.14 Non-goals for Phase 2

- Real LLM-driven runtimes (Open Agent SDK, etc.) — Phase 3.
- MCP gateway — Phase 4.
- Resume after process restart — Phase 5.
- Webhook delivery on session events — Phase 5.
- Widgets — Phase 5.
- Kubernetes sandbox runner — Phase 6.

## 2.15 Definition of done

- [ ] All files in §2.1 created or modified per spec.
- [ ] All acceptance tests in §2.13 present and passing.
- [ ] Integration test suite (`pytest -m integration`) passes locally
      and in CI.
- [ ] Docker integration suite (`pytest -m docker`) passes nightly.
- [ ] Manual smoke: `POST /api/v1/sessions` with the echo agent;
      observe SSE; confirm `/api/v1/sessions/{id}/artifacts/echo.txt`
      downloads.
- [ ] `ruff check src/atrium/harness/ tests/test_harness/` clean.
- [ ] No `TODO(phase-2)` markers remain in the harness package.
