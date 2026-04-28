# `atrium.harness` — long-running sandboxed agent loops

This is the package that turns Atrium into a complete Managed Agents
replacement. It wraps an open-source Claude-Code-equivalent loop (Open
Agent SDK or OpenClaude) inside a Docker sandbox and exposes the result
as a first-class Atrium `Agent`.

If you are about to add code here, read
[`/docs/managed-agent-replacement/04-harness-integration.md`](../../../docs/managed-agent-replacement/04-harness-integration.md)
first. It describes the full design.

## Files in this package

| File | What it does |
|------|--------------|
| `agent.py` | `HarnessAgent`. The Atrium-side wrapper. Subclass of `core.agent.Agent`. From the Commander's view, it's an agent like any other. |
| `session.py` | `Session` model + workspace filesystem. Long-lived state for a harness run. |
| `sandbox.py` | `SandboxRunner`. Boots a container, mounts workspace, streams stdio, kills on timeout. |
| `bridge.py` | `BridgeStream`. Translates inner-runtime JSON-line events into Atrium events. Where the real integration logic lives. |
| `mcp_gateway.py` | Workspace-scoped MCP proxy. Audit trail + allow-listing. |
| `runtimes/base.py` | `Runtime` protocol — what an inner-loop adapter must provide. |
| `runtimes/open_agent_sdk.py` | Adapter for `@shipany/open-agent-sdk` (TypeScript, in-process). |
| `runtimes/openclaude.py` | Adapter for OpenClaude (multi-provider, OpenAI-compatible). |
| `runtimes/direct_anthropic.py` | Adapter for `claude-agent-sdk-python` (native Claude). |
| `runtimes/echo.py` | Trivial fake runtime. Used in tests; doesn't call any LLM. |
| `dockerfiles/` | Per-runtime Docker images. Built and pushed by CI. |

## How a harness session runs (sequence)

1. The orchestrator hits `HarnessAgent.run(input_data)`.
2. The agent calls `Session.create_or_resume(...)`. A row goes into the
   `sessions` table and a directory is created at `/var/atrium/sessions/{id}/`.
3. The agent calls `SandboxRunner.start(session, runtime, model)`. A container
   boots, the session directory is mounted to `/workspace`, model API keys are
   passed as env vars, and the inner runtime starts in stream-json mode.
4. `BridgeStream.run(...)` reads JSON lines from the container's stdout,
   translates each one into an Atrium event, and emits via the recorder.
5. The bridge accumulates token usage. When the running cost crosses
   `max_cost_usd`, the bridge calls `sandbox.kill()` and raises
   `GuardrailViolation`.
6. When the inner loop emits its final result, the bridge persists any new
   files in `/workspace` as artifacts and returns the result dict to the
   orchestrator.
7. The orchestrator continues the DAG (if this was a step in one) or marks
   the session COMPLETED (if standalone).

## Adding a new runtime

A `Runtime` only has to do three things:

1. Build a Docker image that includes the inner-loop CLI.
2. Define the command line that starts a session in stream-json mode.
3. Translate its event stream into Atrium events (typically by mapping in
   `bridge.py`).

See `runtimes/base.py` for the protocol and `runtimes/echo.py` for the
simplest possible implementation.

## What does NOT belong in this package

- Anything that knows about the Commander, the DAG, or planning. The harness
  is one agent type; planning is in `engine/`.
- Any LLM API calls from the host process. The host doesn't call models;
  the inner runtime inside the sandbox does.
- HTTP routes. Routes live in `api/routes/`. They call into harness only
  through the `HarnessAgent` and `Session` surfaces.
