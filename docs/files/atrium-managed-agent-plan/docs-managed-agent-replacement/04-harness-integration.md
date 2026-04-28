# 04 — Harness Integration

This is the concrete spec for the new `src/atrium/harness/` package and how it
plugs into the existing system. Read this if you're going to write the code.

## Where it lives

```
src/atrium/harness/
├── __init__.py            # public exports: HarnessAgent, RuntimeConfig
├── README.md              # how to add a new runtime
├── agent.py               # HarnessAgent — the Atrium-side wrapper
├── session.py             # Session record + workspace filesystem
├── sandbox.py             # SandboxRunner — Docker lifecycle
├── bridge.py              # BridgeStream — inner events → Atrium events
├── mcp_gateway.py         # MCP proxy with workspace-scoped allow-lists
└── runtimes/
    ├── __init__.py
    ├── base.py            # Runtime protocol (abstract)
    ├── open_agent_sdk.py  # @shipany/open-agent-sdk (TypeScript)
    ├── openclaude.py      # OpenClaude (TypeScript)
    └── direct_anthropic.py # claude-agent-sdk-python (Python)
```

The package is intentionally small. The heavy lifting — bash, file ops, web
fetch, model calls, compaction — happens *inside the inner runtime*, which is
itself an open-source project we don't have to maintain.

## The five components

### 1. `HarnessAgent` (`agent.py`)

A subclass of `core.agent.Agent`. From the orchestrator's point of view it
looks like any other agent: it has a `name`, `description`, `capabilities`,
and an async `run()` method. The Commander can pick it; the graph builder
runs it; the recorder receives its events.

What makes it special: its `run()` method delegates to a `Runtime` and a
`SandboxRunner`. It does not execute the inner loop itself. It manages a
session.

```python
class HarnessAgent(Agent):
    name = "harness"  # subclasses override
    description = "Long-running tool-using agent in a sandbox"
    capabilities = ["bash", "files", "web_fetch", "code"]

    runtime: Runtime          # injected: open_agent_sdk / openclaude / ...
    model: str                # "anthropic:claude-sonnet-4-6" etc.
    system_prompt: str | None # workspace-scoped instructions
    allowed_mcp_servers: list[str]
    timeout_seconds: int = 3600
    max_tool_calls: int = 200

    async def run(self, input_data: dict) -> dict:
        session = await Session.create_or_resume(
            workspace_id=input_data["workspace_id"],
            session_id=input_data.get("session_id"),
            parent_thread_id=input_data.get("thread_id"),
        )
        sandbox = await SandboxRunner.start(session, self.runtime, self.model)
        bridge = BridgeStream(sandbox, recorder=self._recorder, session=session)

        try:
            return await bridge.run(
                objective=input_data["objective"],
                system_prompt=self.system_prompt,
                allowed_mcp_servers=self.allowed_mcp_servers,
                max_tool_calls=self.max_tool_calls,
            )
        finally:
            await sandbox.stop()  # but workspace persists for resume
```

### 2. `Session` (`session.py`)

Per-session state and per-session filesystem.

- A `Session` is a Pydantic model persisted to the `sessions` table in
  Postgres.
- A session owns a directory at `/var/atrium/sessions/{session_id}/` (or
  the equivalent S3 prefix). This is mounted into the sandbox container
  as `/workspace`.
- Sessions can be **resumed**: starting a new sandbox with the same
  workspace path and replaying the inner runtime's checkpoint state.
- Session lifecycle methods: `create`, `resume`, `pause`, `cancel`,
  `complete`, `fail`.
- All state transitions emit Atrium events via the recorder.

### 3. `SandboxRunner` (`sandbox.py`)

The Docker (or gVisor / Firecracker / Kubernetes) abstraction.

- `start(session, runtime, model)` → boots a container with the
  workspace mounted, env vars set (model API key, runtime config),
  network policy applied (egress to the model provider only, plus
  allow-listed MCP servers).
- `stop()` / `kill()` — graceful shutdown then SIGKILL.
- `exec_streaming(command)` → async generator of stdout / stderr lines.
- Resource limits: CPU, memory, disk, wall clock — enforced by the
  container runtime, not by Python.

For v1 we use Docker. For v2 we can swap in gVisor or Firecracker without
changing callers — the runner is behind an interface.

There's a parallel `KubernetesSandboxRunner` for production EKS deploys.
Same interface, different backend (creates a Pod instead of a Docker
container, uses a PVC instead of a bind mount).

### 4. `BridgeStream` (`bridge.py`)

This is the most important new code in Atrium. It is the translator between
the inner runtime's event stream and Atrium's event stream.

The inner runtimes (Open Agent SDK, OpenClaude) all emit JSON-line events
over stdout when run with `--output-format stream-json`. The events look like:

```json
{"type": "tool_use", "name": "bash", "input": {"command": "ls"}}
{"type": "tool_result", "name": "bash", "output": "file1\nfile2\n"}
{"type": "text", "text": "I see two files."}
{"type": "usage", "input_tokens": 1234, "output_tokens": 56}
```

The bridge does three things:
1. **Translate**: each inner event becomes a typed Atrium event with a
   stable schema. `tool_use` → `HARNESS_TOOL_CALLED`, `tool_result` →
   `HARNESS_TOOL_RESULT`, `text` → `HARNESS_MESSAGE`, `usage` →
   `BUDGET_CONSUMED` (with real numbers).
2. **Apply guardrails**: every `usage` event accumulates into running
   token cost. If it exceeds the budget the bridge calls
   `sandbox.kill()` and raises `GuardrailViolation`.
3. **Persist artifacts**: when the inner runtime writes files to
   `/workspace`, those files become Atrium artifacts indexed in the
   `artifacts` table.

The bridge is the sole place where Atrium has knowledge of inner-runtime
specifics. Adding a new runtime means writing a new runtime adapter and
making sure its output maps onto the bridge's expected event types.

### 5. `MCPGateway` (`mcp_gateway.py`)

The inner runtime supports MCP. We could let it talk to MCP servers
directly, but then any session could call any MCP. That's not acceptable
for multi-tenant.

Instead the gateway:
- Sits between the sandbox and the outside world.
- Receives MCP requests from the sandbox over a Unix socket mounted into
  the container.
- Checks the session's `allowed_mcp_servers` allow-list.
- Forwards approved requests to the upstream MCP server.
- Logs every request as a `HARNESS_MCP_CALLED` event.
- Rejects unknown servers with a structured error.

This also gives us an audit trail for MCP usage, which CIVI's compliance
requirements will need.

## How a HarnessAgent gets registered

Two ways, mirroring the existing two-way pattern for HTTP agents.

### Option A: Python subclass (full control)

```python
from atrium.harness import HarnessAgent
from atrium.harness.runtimes.open_agent_sdk import OpenAgentSDKRuntime

class CodeResearchAgent(HarnessAgent):
    name = "code_research"
    description = "Investigates a codebase and produces a report"
    capabilities = ["bash", "files", "search", "summarize"]
    runtime = OpenAgentSDKRuntime()
    model = "anthropic:claude-sonnet-4-6"
    allowed_mcp_servers = ["github", "linear"]
    timeout_seconds = 1800
    system_prompt = """You are a senior engineer investigating a codebase.
Read files, run searches, and produce a structured report at /workspace/report.md."""
```

### Option B: Config-driven (dashboard / API)

POST `/api/v1/agents/create` with:

```json
{
  "kind": "harness",
  "name": "code_research",
  "description": "Investigates a codebase and produces a report",
  "capabilities": ["bash", "files", "search", "summarize"],
  "runtime": "open_agent_sdk",
  "model": "anthropic:claude-sonnet-4-6",
  "allowed_mcp_servers": ["github", "linear"],
  "timeout_seconds": 1800,
  "system_prompt": "You are a senior engineer investigating a codebase..."
}
```

Stored in `agent_configs`, loaded into the registry on startup.

## How the Commander uses HarnessAgents

The Commander sees harness agents in the manifest just like any other agent.
Example plan:

```json
{
  "rationale": "First fetch latest PRs to understand context, then run a code research harness to investigate, then summarize.",
  "steps": [
    {"agent": "github_prs", "inputs": {"repo": "acme/api"}, "depends_on": []},
    {"agent": "code_research", "inputs": {"objective": "Find why the auth tests are flaky"}, "depends_on": ["github_prs"]},
    {"agent": "summarizer", "inputs": {}, "depends_on": ["code_research"]}
  ]
}
```

The graph builder runs `code_research` like any other node — it just
takes much longer and emits many more events.

## Three integration tests we want green before declaring victory

1. **Standalone harness session.** `POST /api/v1/sessions` with objective
   "list all .py files in /workspace and write a summary". Sandbox starts,
   runs, completes. Events stream live. Final artifact is queryable via
   `GET /api/v1/artifacts/{id}`.

2. **DAG including a harness step.** Plan with `[github_prs →
   code_research → summarizer]`. Code_research is the harness; it gets
   github_prs's output as input; summarizer reads code_research's output.
   Whole thing completes; dashboard shows the DAG with the harness node
   highlighted while it's running.

3. **Resume after restart.** Start a session that takes 5 minutes. After
   1 minute, kill the API process. Restart it. Issue
   `POST /api/v1/sessions/{id}/resume`. The new sandbox boots with the same
   workspace, the inner runtime picks up its last checkpoint, and the
   session reaches completion.

If those three tests pass, the harness layer is done.
