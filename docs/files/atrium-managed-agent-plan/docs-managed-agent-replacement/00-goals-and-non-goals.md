# 00 — Goals and Non-Goals

## What we are replacing

Anthropic's Claude Managed Agents service. Specifically the parts a customer
actually uses:

- A long-running sandboxed environment per session (bash, files, web fetch,
  code execution).
- A durable session — events accumulate over hours or days, survive process
  restarts, are queryable after the fact.
- A harness loop that handles tool dispatch, error retry, context compaction,
  and prompt caching.
- A streaming view of what the agent is doing right now (the equivalent of
  watching tool calls scroll past in Claude Code).
- HITL pause / resume / cancel.
- Cost and time guardrails.
- An API surface so other systems can drive it programmatically.

We are also replacing the *pricing model*: $0.08 per active session-hour plus
token costs. Self-hosted on our own infra, the marginal cost is just the
container time and the model API tokens.

## Goals — must-have for v1

1. **Single-agent harness in a sandbox.** Run a Claude-Code-style loop (read
   files, edit files, run bash, fetch URLs, call MCP tools) inside an isolated
   container, for one session, for hours if needed.
2. **Session persistence.** Each session has a unique ID, a per-session
   filesystem mounted into the container, an append-only event log, and the
   ability to resume after the process bounces.
3. **Model-agnostic.** Same harness must work with Claude, GPT, Gemini, and any
   OpenAI-compatible endpoint (DeepSeek, Qwen, local Ollama). The choice of
   model is configuration, not code.
4. **Integration with the existing Atrium DAG orchestrator.** A harness session
   shows up as a regular agent in the registry. The Commander can plan a DAG
   that includes harness agents alongside HTTP agents.
5. **Event bridging.** Every tool call, file edit, and bash command inside the
   harness becomes an event in Atrium's existing event stream. The dashboard
   renders it. SSE subscribers receive it.
6. **External API.** Other systems can: create a session, send a message to a
   running session, subscribe to its event stream, read its file artifacts,
   pause / cancel it, and read historical sessions.
7. **Widget endpoints.** Read-only embed-friendly endpoints for live event
   feeds, plan DAGs, budget bars, and final reports — so other UIs can drop
   in pieces of Atrium.
8. **Cost and time guardrails actually enforced.** Real token counting (not
   the hard-coded `0.10` placeholder in the current code), real wall-clock
   tracking, real container kill on violation.
9. **Multi-tenant isolation.** A session for client A cannot read the
   filesystem, environment, or events of client B.

## Non-goals — explicitly out of scope for v1

- **Replacing Claude Code as a CLI.** We're replacing the *managed service*,
  not the developer tool. Engineers can still use Claude Code locally.
- **Multi-agent coordination as a research feature.** Atrium already does
  multi-agent better than Managed Agents' research preview by virtue of the
  existing Commander/DAG model. We don't need to copy Anthropic's specific
  approach.
- **Beating Anthropic on quality.** Their harness is tuned to Claude.
  We will be 5–10 points behind on Claude-specific benchmarks. The trade is
  model agnosticism, no vendor lock-in, on-prem deployability, and zero
  per-session-hour fees. Quality parity on Claude specifically is not the
  goal; quality parity on the *task the customer cares about* is.
- **A model gateway.** We use OpenRouter / LangDB / direct provider SDKs.
  Building our own routing layer is a separate problem.
- **Fine-tuning, training, or model hosting.** We orchestrate; we don't host
  models.

## Success criteria — concrete and measurable

- A single PLC Direct SKU classification task runs end-to-end inside the
  harness with Claude Sonnet, then again with Gemini, with no code changes.
- The same task can also be expressed as a DAG (extract → classify → review)
  with three sub-agents, demonstrating the orchestrator and the harness work
  together.
- A session that is paused mid-execution can be resumed in a different
  process and reach completion.
- The dashboard shows the live tool-by-tool execution of an in-flight harness
  session, identical in spirit to what Claude Code shows in its terminal.
- An external service can POST to `/api/v1/sessions`, get a session_id back,
  subscribe to its SSE stream, and watch the work happen — all without
  touching the dashboard.
- A guardrail violation (max cost, max time) actually kills the container and
  marks the session FAILED, with the partial artifacts preserved.
- The harness can be deployed to an EKS cluster (the team already runs one)
  with one container per session, behind a single Atrium API service.
