# 07 — Decision Log

Design decisions made during this planning round. Each entry has the decision,
the alternatives considered, and the rationale. The goal is so a future
engineer (including a future you) can see *why* a thing was done that way and
challenge it if conditions change.

## D-001: Use an existing open-source harness rather than write our own

**Decision:** integrate Open Agent SDK and OpenClaude as runtime adapters.
Do not write a Claude-Code-equivalent harness from scratch.

**Alternatives:**
- Build our own harness from primitives (LangChain, Anthropic SDK directly).
- License the Anthropic Claude Agent SDK and bundle it.

**Rationale:** the harness loop is the most-tested part of the agent stack
right now. Open Agent SDK is a near-direct port of Claude Code. OpenClaude
adds multi-provider support. Building our own would mean re-inventing
context compaction, prompt caching, error retry, and tool dispatch — all
of which the open-source projects already do well. We get to focus on
integration and value-add (DAGs, multi-tenancy, widgets), not on
re-implementing the loop.

**Reversal cost:** medium. If both upstream projects became unmaintained,
we could fork. The runtime adapter interface keeps our code de-coupled.

## D-002: Atrium remains the outer orchestrator; the harness is an inner agent

**Decision:** the existing Commander/DAG model is preserved. A
`HarnessAgent` is just another agent the Commander can pick.

**Alternatives:**
- Make the harness the top-level entry point and treat HTTP agents as
  tools inside the harness.
- Two parallel systems with no shared infrastructure.

**Rationale:** the orchestrator is the thing that lets us mix sandboxed
long-running work with quick HTTP calls in the same plan. Inverting this
would lose the multi-agent advantage we already have over Managed Agents.
Two parallel systems would double the surface area and split the
dashboard / event stream / API.

**Reversal cost:** high. Most of the rest of the architecture assumes
this.

## D-003: Postgres replaces SQLite for production; SQLite stays for dev

**Decision:** introduce a Postgres backend for `EventRecorder`, `ThreadStore`,
`AgentStore`, and the new `SessionStore`. SQLite remains the default for
local dev and tests.

**Alternatives:**
- SQLite-only forever.
- Postgres-only.
- Some other store (DynamoDB, Mongo, Redis Streams).

**Rationale:** the team already runs PostgreSQL 14 with pgBackRest, so
ops is familiar. SQLite's `check_same_thread=False` plus concurrent
writes is the wrong call for production. Postgres also unblocks
horizontal scaling of the API. SQLite stays so local dev doesn't need
docker-compose for a unit test.

**Reversal cost:** low. The store interfaces are abstract.

## D-004: Workspaces are the multi-tenancy boundary

**Decision:** every session, thread, agent config, artifact, and webhook
belongs to a workspace. API keys resolve to a workspace. There is no
cross-workspace read.

**Alternatives:**
- User-scoped (per-user, no workspace concept).
- Project-scoped (more granular).
- No isolation (single-tenant Atrium per client).

**Rationale:** workspaces are the right granularity for an internal
platform. CIVI is a workspace, PLC Direct is a workspace, Daylight Core
internal is a workspace. Per-user is too granular for tools that are
shared across a team. Per-project is appealing but adds a layer we don't
need yet — we can introduce projects-inside-workspaces in a later phase
without a breaking change. Single-tenant deployments are what we'd
recommend for CIVI's data residency anyway, but multi-tenant Atrium is
also useful for internal Taazaa workloads.

**Reversal cost:** low for adding projects later; high for removing
workspaces.

## D-005: Docker first, gVisor / Firecracker later

**Decision:** the v1 SandboxRunner uses Docker. The interface allows
swapping in stronger isolation later.

**Alternatives:**
- gVisor from day one.
- Firecracker / micro-VMs.
- Process-level isolation only (cgroups + namespaces, no Docker).

**Rationale:** Docker is what every developer on the team already uses
for local work. Adding gVisor or Firecracker now would slow the v1
delivery for a security improvement that matters mostly for
client-deployed workloads (CIVI). The interface is clean enough that we
can introduce a `GVisorSandboxRunner` later without touching callers.

**Reversal cost:** low. Bounded by the runner interface.

## D-006: MCP traffic goes through a gateway, not direct from sandbox

**Decision:** sandboxed agents talk to MCP servers via a Unix-socket
gateway. The gateway enforces workspace allow-lists and logs every call.

**Alternatives:**
- Let the sandbox open arbitrary network connections (no gateway).
- Run MCP servers inside the sandbox.

**Rationale:** without a gateway, a compromised or misbehaving agent
can call any MCP server it knows about, including production-write
servers like GitHub or Linear. The gateway gives us audit trail (CIVI
will need it), allow-listing (multi-tenant safety), and a chokepoint
for rate limiting. Running MCP servers inside the sandbox would isolate
them but precludes shared persistent state (a Linear MCP would need a
fresh auth on every session).

**Reversal cost:** low.

## D-007: Sessions and threads coexist; sessions are not "threads with one agent"

**Decision:** `Session` is a separate first-class entity from `Thread`. A
thread can spawn a session as one of its DAG steps; a session can also
exist independently with no parent thread.

**Alternatives:**
- Sessions are a special kind of thread.
- Threads are a special kind of session.
- Only sessions exist; multi-agent is sessions-of-sessions.

**Rationale:** Threads are short-lived, plan-driven, and DAG-shaped.
Sessions are long-lived, conversational, and stream-shaped. Forcing one
model on both produces ugly compromises (a thread with a 4-hour single
step is awkward; a session with a planned DAG is awkward). Keeping them
distinct lets each one have an idiomatic API.

**Reversal cost:** medium. The data model differences are real.

## D-008: Real token accounting via LangChain `usage_metadata`

**Decision:** read `response.usage_metadata` after every LLM call and
plumb it into BUDGET_CONSUMED events. Replace the hardcoded `0.10` and
`0.20` placeholders.

**Alternatives:**
- Estimate from token counts (tiktoken locally).
- Reconcile from monthly provider invoices (post-hoc only).
- Don't track at all.

**Rationale:** providers return real usage data. Using estimates from
tiktoken disagrees with provider billing for tools / system prompts /
caching. Post-hoc reconciliation can't drive guardrails in real time.
Not tracking means we can't enforce budget caps, which is the whole
point of having them.

**Reversal cost:** trivial.

## D-009: Embeddable widgets are HTML iframes, not JS components

**Decision:** widgets are server-rendered HTML pages served from
Atrium and embedded via `<iframe>` in consuming products.

**Alternatives:**
- Web Components (`<atrium-feed session-id="...">`).
- Distributed npm package with React components.
- Read-only API only, consumers build their own UIs.

**Rationale:** iframes work in any host (CIVI's Vue, Master CRM's
Angular, a Slack canvas, a Confluence page). No JS bundle dependencies.
Atrium controls the styling and behaviour entirely. The trade-off is
that iframes are heavier and don't share the host's design language; for
our internal use that's an acceptable trade.

**Reversal cost:** low. We can ship Web Components later as a layer on
top of the same SSE backend.

## D-010: Agent names are namespaced as `{workspace_id}/{name}` internally

**Decision:** the registry key is `{workspace_id}/{name}`. The API
exposes the un-namespaced name within a workspace.

**Alternatives:**
- Globally unique names.
- Per-workspace registries with no namespacing.

**Rationale:** globally unique blocks two workspaces from both having a
"github_search" agent. Per-workspace registries force a separate
registry instance per workspace, complicating the orchestrator wiring.
Namespacing in storage but un-namespacing in the API is the natural
compromise — and crucially it makes the upcoming "agent marketplace"
work easy: a marketplace template is `marketplace/github_search` and
gets imported into a workspace as `{your_workspace}/github_search`.

**Reversal cost:** higher the longer we wait. Adopt now.

## D-011: Use Anthropic's SDK as one of three runtimes; do not bet only on it

**Decision:** include `direct_anthropic.py` as a runtime alongside
`open_agent_sdk.py` and `openclaude.py`. The team can pick per-agent.

**Alternatives:**
- Anthropic-only (best Claude experience, locks us in).
- Anthropic-never (avoids licensing complexity, gives up some quality
  on Claude-specific tasks).

**Rationale:** the Anthropic SDK source is governed by Anthropic
Commercial Terms of Service. We can use it, but it limits our options
for client redistribution. Having all three lets us pick: use Anthropic
direct for internal high-quality Claude work, use Open Agent SDK for
client-deployable Anthropic work, use OpenClaude for cross-provider
work.

**Reversal cost:** low. Runtime adapters are isolated.

## D-012: Defer "computer use" tool to v2

**Decision:** v1 supports bash, file edit, web fetch, code execution,
and MCP. Computer use (the screen-plus-mouse model) is not in v1.

**Alternatives:**
- Include computer use from day one.

**Rationale:** computer use needs a virtual display and a separate
container image, and the use cases for our portfolio (PLC Direct,
CIVI, Daylight Core, Master CRM) don't currently call for it. Skipping
v1 saves a meaningful chunk of work and keeps the sandbox image lean.

**Reversal cost:** medium — probably one phase of work to add.
