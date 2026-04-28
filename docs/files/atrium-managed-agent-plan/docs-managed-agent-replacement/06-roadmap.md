# 06 — Roadmap

A phased plan to take Atrium from where it is today to a complete Managed
Agents replacement. Each phase produces something demonstrable. Each phase
has explicit entry / exit criteria so we know when to move on.

The phases are ordered by dependency, not by glamour. The harness layer is
phase 3, not phase 1, because there are real prerequisites.

## Phase 0 — Stabilize what exists (1 week)

**Goal:** fix the issues from `01-code-review.md` that block everything else.
No new features.

| Item | Where |
|------|-------|
| Move thread storage out of `_threads` dict into a `ThreadStore` backed by SQLite (and Postgres-ready). | `api/routes/threads.py`, new `core/thread_store.py` |
| Wire real guardrail enforcement at runtime. `check_time` ticked from a background task; `check_cost` ticked on every BUDGET_CONSUMED; `check_parallel` and `check_spawn` checked in `graph_builder`. | `engine/orchestrator.py`, `engine/graph_builder.py` |
| Add a fail policy to `graph_builder`. Default `stop-thread` on agent error. Configurable per-step in the future. | `engine/graph_builder.py` |
| Wrap LLM calls in retry/backoff with jitter. | `engine/llm.py` |
| Add real token accounting from LLM responses (LangChain returns usage data on the response object). Plumb through to BUDGET_CONSUMED. | `engine/llm.py`, `engine/orchestrator.py` |
| Use provider-native structured output where available (OpenAI tool calling, Anthropic tool use, Gemini response_mime_type). Falls back to the current strip-fence + json.loads. | `engine/llm.py`, `engine/commander.py` |
| Validate Commander plans against the registry before execution. Reject duplicate agents, missing depends_on targets, cycles. | `engine/commander.py` |
| Serialize SQLite writes via aiosqlite or a single writer task. | `streaming/events.py`, `core/agent_store.py` |
| Add CORS configuration to `api/middleware.py`. | `api/middleware.py` |

**Exit criteria:** all existing tests pass; new tests cover the fixed
issues; a thread that exceeds `max_cost_usd` actually gets killed; restart
mid-thread doesn't lose the thread record.

## Phase 1 — Production prerequisites (1.5 weeks)

**Goal:** auth, multi-tenancy, Postgres. Nothing about harness yet, but
everything that follows depends on these.

| Item | Where |
|------|-------|
| Add `Workspace` model and table. | `core/models.py`, `core/auth.py` |
| Add API-key middleware. Resolve workspace from key. Inject workspace_id into request state. | `api/auth.py`, `api/middleware.py` |
| Workspace-scope the registry, agent_store, and recorder. Each gets a workspace_id parameter and filters reads/writes accordingly. | `core/registry.py`, `core/agent_store.py`, `streaming/events.py` |
| Add a Postgres backend for `EventRecorder`. SQLite stays as the default for dev; production sets `ATRIUM_DB_URL`. | `streaming/events.py` |
| Add `Session` model and `sessions` table (still unused; harness will use it in phase 3). | `core/models.py` |
| Replace module-level state in `api/app.py` with a per-app dependency injection container. | `api/app.py`, all routes |
| Replace module-level `_controllers` dict with a per-orchestrator registry that's passed in. | `engine/orchestrator.py` |
| Admin routes for workspace + key management. | `api/routes/workspaces.py` |
| Migration scripts (Alembic). | `migrations/` |

**Exit criteria:** two API keys belonging to two different workspaces
cannot see each other's threads, agents, or events. A single deployed
Atrium API can serve both. Postgres mode passes the same test suite as
SQLite mode.

## Phase 2 — Sandbox foundation (1 week)

**Goal:** the SandboxRunner and Session lifecycle work, with a trivial
"echo" runtime, before we introduce real agentic loops. Smaller pieces,
testable independently.

| Item | Where |
|------|-------|
| `SandboxRunner` Docker implementation: start, stop, kill, exec_streaming. | `harness/sandbox.py` |
| `Session` model + table, lifecycle methods (create, resume, fail, complete). Per-session workspace directory. | `harness/session.py` |
| `BridgeStream` skeleton — reads JSON lines from sandbox stdout, emits typed Atrium events. Initially supports only an "echo" event format. | `harness/bridge.py` |
| Trivial `EchoRuntime` that just echoes its input as tool calls and produces a final message. Used for end-to-end testing without API costs. | `harness/runtimes/echo.py` |
| Routes: `POST /api/v1/sessions`, `GET /api/v1/sessions`, `GET /api/v1/sessions/{id}`, `GET /api/v1/sessions/{id}/stream`. | `api/routes/sessions.py` |
| Artifact indexing: filesystem watcher inside the sandbox image emits events when files are created/modified in /workspace. | `harness/bridge.py`, sandbox image |
| Routes: `GET /api/v1/sessions/{id}/artifacts`, `GET /api/v1/artifacts/{id}`. | `api/routes/artifacts.py` |
| Container resource limits enforced at boot (cpus, memory, disk, network policy). | `harness/sandbox.py` |
| Guardrail integration: bridge accumulates time and tool-call count; SandboxRunner kills container on violation. | `harness/bridge.py`, `harness/sandbox.py` |

**Exit criteria:** a session created with the echo runtime starts a
container, runs to completion, produces an artifact, the artifact is
downloadable, the live event stream renders in the dashboard. A session
that exceeds `timeout_seconds` actually gets killed.

## Phase 3 — Real harness runtimes (1.5 weeks)

**Goal:** plug in actual Open Agent SDK and verify the harness works
end-to-end with Claude.

| Item | Where |
|------|-------|
| `OpenAgentSDKRuntime` adapter. Builds the Docker image with @shipany/open-agent-sdk preinstalled. Translates the SDK's `--output-format stream-json` events into the bridge schema. | `harness/runtimes/open_agent_sdk.py`, `harness/dockerfiles/open_agent_sdk.Dockerfile` |
| `HarnessAgent` class. Subclassable from Python (Option A) or instantiable from config (Option B). | `harness/agent.py` |
| Config-driven harness creation: `kind: "harness"` in `POST /api/v1/agents/create`. | `api/routes/agent_builder.py` |
| Update `LLMClient`-style provider config to also pass model API keys to the sandbox env. | `harness/sandbox.py` |
| Example agent: `code_research_harness` for the existing PLC Direct taxonomy work. Uses real Claude. | `examples/code_research/` |
| Integration test: standalone harness session that lists files, edits one, writes a report. | `tests/test_harness/` |

**Exit criteria:** a `code_research` harness session investigates a
mounted repository and produces `/workspace/report.md`. The dashboard
streams every tool call. Token counts in BUDGET_CONSUMED match the
provider's reported usage within 1%. A wall-clock timeout actually
fires.

## Phase 4 — Multi-model and MCP (1 week)

**Goal:** prove model agnosticism end-to-end and add MCP gateway.

| Item | Where |
|------|-------|
| `OpenClaudeRuntime` adapter as a second runtime. | `harness/runtimes/openclaude.py` |
| Add Gemini and OpenAI passthrough via OpenRouter (and direct provider where supported). | `harness/runtimes/*.py`, `harness/sandbox.py` (env wiring) |
| `MCPGateway`: Unix-socket-mounted-into-sandbox proxy with workspace-scoped allow-lists. | `harness/mcp_gateway.py` |
| Atrium-side MCP server registry per workspace: `POST /api/v1/workspaces/me/mcp-servers`. | `api/routes/workspaces.py` |
| Integration test: same `code_research` agent with Claude *then* Gemini, no code change. | `tests/test_harness/` |

**Exit criteria:** the same agent definition completes the same task on
two different models with no code change. The MCP gateway successfully
proxies a call to a real MCP server (e.g. GitHub) and rejects an
unlisted server.

## Phase 5 — Resume, webhooks, widgets (1 week)

**Goal:** the long-tail of "complete the surface area".

| Item | Where |
|------|-------|
| Session checkpoint / resume. The inner runtime already supports compaction; we persist the compaction snapshot to S3 and replay it on a new container start. | `harness/session.py`, `harness/runtimes/*.py` |
| Webhook delivery worker. Reads new events, matches subscriptions, posts with HMAC, retries. | `streaming/webhooks.py`, `api/routes/webhooks.py` |
| Widget endpoints (`/widgets/feed`, `/plan`, `/budget`, `/report`). Read-only short-lived tokens. | `dashboard/static/widgets/`, `api/routes/widgets.py` |
| OpenAPI polish + Swagger UI publication. | `api/app.py`, `api/schemas.py` |
| Generated SDK clients (`atrium-client-py`, `atrium-client-ts`). | separate repos |

**Exit criteria:** the three integration tests at the end of
`04-harness-integration.md` all pass. A session paused in one process
resumes in another. CIVI's dashboard can embed a live `feed` widget
pointing at an Atrium session and see live events.

## Phase 6 — Hardening and operational readiness (1 week)

**Goal:** be deployable to production EKS without hand-holding.

| Item | Where |
|------|-------|
| Helm chart. | `deploy/helm/atrium/` |
| `KubernetesSandboxRunner` — creates Pods instead of local Docker containers. | `harness/sandbox.py` |
| OpenTelemetry tracing across the API → orchestrator → bridge → sandbox boundary. | cross-cutting |
| Prometheus metrics: active sessions, queue depth, p99 latency, token cost. | cross-cutting |
| Runbooks: deploy, rollback, backfill events, kill stuck sessions. | `docs/operations/` |
| Load test: 50 concurrent sessions on a 3-node cluster. Document the throughput / cost numbers. | `tests/load/` |

**Exit criteria:** the full system runs on the team's existing EKS
cluster, scales horizontally on session load, and is observable enough
that an on-call engineer can debug a stuck session without ssh'ing into
a container.

## Total: roughly 7 weeks of focused work

This is end-to-end. With one strong engineer working on it, plus part-time
help on the dashboard and ops, it's tight but achievable. With two engineers
in parallel (one on harness/runtime, one on API/auth/multi-tenancy), 5 weeks
is realistic.

The phases are designed so the system is incrementally useful at every step:

- After phase 0, Atrium is more stable and ready for production.
- After phase 1, it's safely multi-tenant.
- After phase 2, it can run sandboxed agents (trivially, but really).
- After phase 3, it's a genuine Managed Agents replacement for one model.
- After phase 4, it's a genuine model-agnostic Managed Agents replacement.
- After phase 5, it's drop-in for external integrations.
- After phase 6, it's production-deployable across the Taazaa portfolio.

The team can stop at any phase boundary and have a useful system. There are
no "all or nothing" dependencies inside the plan.

## Risks and what to do about them

| Risk | Mitigation |
|------|------------|
| Open Agent SDK or OpenClaude evolves rapidly and breaks our adapter. | Pin specific versions; gate upgrades through the runtime adapter test suite; keep both runtimes as alternatives. |
| Anthropic changes the Claude Code CLI protocol that Open Agent SDK depends on. | Same — pinned versions, plus we have a direct Anthropic SDK runtime as a fallback. |
| Container escape / sandbox bypass. | Start with Docker; escalate to gVisor or Firecracker before any client-deployed use. Network egress allow-listed by default. |
| Token cost accounting is off and we under-bill or over-bill. | Cross-check with provider invoices monthly during phase 3–6. Build a reconciliation script. |
| Postgres migration drift between SQLite and Postgres modes. | Single Alembic migration tree; CI runs both backends. |
| Multi-tenancy bug leaks data between workspaces. | Workspace_id checked at every query; SQL constraints; integration tests with two workspaces explicitly looking for leaks. |
| The "agent marketplace" effort lands in parallel and produces lots of HTTP agents that conflict with harness agents in naming or schema. | Adopt namespacing now: agent names are `{workspace_id}/{name}`. Cheap to add in phase 1, expensive to retrofit later. |
