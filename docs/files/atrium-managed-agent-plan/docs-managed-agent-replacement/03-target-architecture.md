# 03 — Target Architecture

The end-state design after the harness layer is added. This is what Atrium
looks like once it's a complete Managed Agents replacement.

## Layer cake

```
┌─────────────────────────────────────────────────────────────────────┐
│                       External consumers                            │
│   (CIVI UI · Master CRM · PLC Direct pipelines · partner APIs)      │
└──────────────────────┬──────────────────────────────────────────────┘
                       │  HTTPS + API key
┌──────────────────────▼──────────────────────────────────────────────┐
│                       Atrium API service                            │
│   FastAPI · auth middleware · workspace scoping · rate limiting     │
│   /api/v1/sessions  /threads  /agents  /artifacts  /widgets  …      │
└──────────┬───────────────────────────────────────┬──────────────────┘
           │                                       │
           │ orchestrates                          │ subscribes
           │                                       │
┌──────────▼─────────────────────┐    ┌────────────▼──────────────────┐
│      ThreadOrchestrator        │    │      EventRecorder            │
│  Commander → plan → DAG        │    │  append-only · per-session    │
│  graph_builder + LangGraph     │    │  Postgres + SSE fan-out       │
│  ThreadController (HITL)       │◀───│                               │
└────┬────────────────┬──────────┘    └────────────┬──────────────────┘
     │                │                            │
     │                │                            │
┌────▼─────┐    ┌─────▼──────────┐           ┌─────▼──────────┐
│  HTTP    │    │   Harness      │           │  Dashboard     │
│  agents  │    │   agents       │           │  + widgets     │
│  (leaf)  │    │   (long-run)   │           │  (SSE client)  │
└──────────┘    └─────┬──────────┘           └────────────────┘
                      │
                      │ runs
                      │
                ┌─────▼──────────────────────────────────────┐
                │           Sandbox Runner                   │
                │  Docker · per-session container · session  │
                │  filesystem mount · resource limits        │
                └─────┬──────────────────────────────────────┘
                      │
                      │ inside
                      │
                ┌─────▼──────────────────────────────────────┐
                │     Inner harness loop                     │
                │  Open Agent SDK / OpenClaude               │
                │  bash · file edit · web fetch · MCP        │
                │  driven by Claude / GPT / Gemini / etc.    │
                └────────────────────────────────────────────┘
```

## What changes from today

- **`/sessions` is the new top-level concept.** A session is a long-running
  unit of work owned by a single harness agent. It can also embed inside a
  thread (a DAG that includes a `HarnessAgent` step). Threads remain for
  multi-step DAG orchestrations.
- **Postgres replaces SQLite for events and threads.** SQLite stays as an
  option for single-node dev. Production uses Postgres so multiple Atrium
  API replicas behind a load balancer can share state.
- **The harness package is new.** It contains the `HarnessAgent` base class,
  the sandbox runner, the bridge that translates inner-harness events into
  Atrium events, and the MCP gateway.
- **Auth middleware is new.** API keys at minimum, JWT later.
- **Workspace scoping is new.** Every session, thread, agent config, and
  artifact belongs to a workspace. The registry and recorder are
  workspace-scoped.

## What stays from today

- The Agent base class. `HarnessAgent` extends it.
- The Commander, registry, plan model. A harness session is just an agent
  the planner can pick.
- The HITL ThreadController. Pause / approve / cancel apply uniformly to
  threads and sessions.
- The dashboard. New widgets are added; the existing console keeps working.
- The event recorder. Postgres swap is below the API.

## Module layout (target)

```
src/atrium/
├── __init__.py
├── api/
│   ├── app.py                     ← workspace-aware, no module-level state
│   ├── auth.py                    ← NEW: API key + JWT middleware
│   ├── middleware.py
│   ├── routes/
│   │   ├── threads.py
│   │   ├── sessions.py            ← NEW: long-running harness sessions
│   │   ├── messages.py            ← NEW: send messages into a session
│   │   ├── artifacts.py           ← NEW: read files produced by a session
│   │   ├── webhooks.py            ← NEW: external delivery on events
│   │   ├── widgets.py             ← NEW: embeddable read-only views
│   │   ├── workspaces.py          ← NEW: tenant scoping
│   │   ├── control.py
│   │   ├── registry.py
│   │   └── agent_builder.py
│   └── schemas.py
├── core/
│   ├── agent.py
│   ├── http_agent.py
│   ├── agent_store.py
│   ├── registry.py                ← workspace-scoped
│   ├── guardrails.py              ← actually enforced now
│   ├── models.py                  ← Session model added
│   ├── retry.py                   ← NEW: backoff + idempotency
│   └── auth.py                    ← NEW: workspace + token model
├── engine/
│   ├── commander.py               ← validates plans against registry
│   ├── graph_builder.py           ← fail-policy-aware
│   ├── orchestrator.py            ← workspace-aware
│   ├── llm.py                     ← real token accounting
│   └── callbacks.py
├── streaming/
│   ├── bus.py
│   ├── events.py                  ← Postgres adapter alongside SQLite
│   └── webhooks.py                ← NEW: outbound delivery
├── harness/                       ← NEW PACKAGE
│   ├── __init__.py
│   ├── README.md                  ← how the harness fits into Atrium
│   ├── agent.py                   ← HarnessAgent base class
│   ├── sandbox.py                 ← Docker / Firecracker runner
│   ├── session.py                 ← session lifecycle + filesystem
│   ├── bridge.py                  ← inner SDK events → Atrium events
│   ├── mcp_gateway.py             ← MCP server proxy
│   ├── runtimes/
│   │   ├── __init__.py
│   │   ├── base.py                ← Runtime protocol
│   │   ├── open_agent_sdk.py      ← TS Open Agent SDK runtime
│   │   ├── openclaude.py          ← OpenClaude runtime
│   │   └── direct_anthropic.py    ← native Claude Agent SDK runtime
│   └── tests/
├── dashboard/
│   └── static/
│       ├── console.html
│       └── widgets/               ← NEW: embeddable widget shells
│           ├── feed.html
│           ├── plan.html
│           └── budget.html
├── examples/
│   ├── hello_world/
│   ├── observe/
│   ├── code_research/             ← NEW: harness-based example
│   └── multi_agent_with_harness/  ← NEW: DAG that uses a harness agent
└── testing/
```

## Key data model additions

### Session (new)
```python
class Session(BaseModel):
    session_id: str
    workspace_id: str
    title: str
    status: SessionStatus     # CREATED, RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED
    runtime: str              # "open_agent_sdk" | "openclaude" | "direct_anthropic"
    model: str                # "anthropic:claude-sonnet-4-6" | "google:gemini-2.5-pro" | ...
    container_id: str | None
    workspace_path: str       # /var/atrium/sessions/{session_id}
    created_at: datetime
    last_active_at: datetime
    parent_thread_id: str | None  # if spawned from a DAG step
```

### Workspace (new)
```python
class Workspace(BaseModel):
    workspace_id: str
    name: str
    api_keys: list[str]     # hashed
    quota: Quota            # max_concurrent_sessions, max_monthly_spend, ...
```

### Artifact (new)
```python
class Artifact(BaseModel):
    artifact_id: str
    session_id: str
    workspace_id: str
    path: str               # path inside the session workspace
    size_bytes: int
    sha256: str
    created_at: datetime
```

## Key invariants

1. **Sessions are workspace-scoped.** Every read/write checks workspace_id.
2. **Events are append-only.** Existing invariant; preserved.
3. **The recorder is the source of truth for status.** Thread/session
   records project from the latest status event.
4. **Container kill is permanent.** Once a sandbox is killed for a guardrail
   violation, the session is FAILED and cannot be resumed in the same
   container — a new session must be started, optionally with the
   previous workspace mounted.
5. **The harness never holds API keys for the model provider in plaintext on
   disk.** Keys are passed via env vars at container start, never written.
6. **MCP servers are accessed through the gateway**, not directly by the
   inner harness. The gateway enforces workspace-scoped allow-lists.

## Deployment topology (EKS)

- 1 Atrium API deployment (3 replicas behind an ALB) — stateless except
  for the in-process registry, which is rebuilt on startup from the
  agent_configs table.
- 1 Postgres (RDS, Multi-AZ) — events, threads, sessions, workspaces,
  artifacts (metadata).
- 1 S3 bucket (or EBS volume per node) — session workspaces.
- N Sandbox-runner pods — one container per active session; horizontal
  pod autoscaler on session count.
- 1 Webhook delivery worker (1 replica is fine; idempotent retries).
- Optional: Redis for ephemeral cross-replica state (active controllers,
  rate limits). For v1 a single API replica is acceptable.

This slots into the team's existing EKS deployment patterns directly.
