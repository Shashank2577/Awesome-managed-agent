# Per-Phase Technical Specifications

These documents are designed to be fed to an LLM (or read by a human implementer)
with **zero ambiguity**. Each one specifies, for a single roadmap phase:

- The exact files to create or modify, with full content where small enough.
- Every function signature, parameter type, return type, and exception.
- Every database table with column types, constraints, and indexes.
- Every API route with request/response schemas.
- Every event type with its payload schema.
- Acceptance tests that must pass for the phase to be considered done.
- Explicit non-goals — what the phase will NOT do.

## How to use these documents

If you are an LLM implementing a phase:

1. Read the corresponding spec file end-to-end first.
2. Read the cross-cutting [`CONTRACTS.md`](./CONTRACTS.md) document for shared
   types and conventions.
3. Implement files in the order they are listed. Do not invent new files.
4. Do not invent new fields, parameters, or events. If something is missing,
   stop and ask.
5. Write the acceptance tests at the end of each spec. The phase is done
   when those tests pass.

If you are a human reviewer:

1. Spot-check that the spec matches the existing codebase patterns
   (`src/atrium/core/agent.py`, `engine/orchestrator.py` are the canonical
   references).
2. Diff the produced code against the spec; anything in the code that's not
   in the spec is suspect.

## Reading order

| File | Phase | What it covers |
|------|-------|----------------|
| [`CONTRACTS.md`](./CONTRACTS.md) | All phases | Cross-cutting types, error model, naming, testing conventions |
| [`PHASE-0-stabilization.md`](./PHASE-0-stabilization.md) | 0 | Fix existing bugs before any new features |
| [`PHASE-1-multitenancy.md`](./PHASE-1-multitenancy.md) | 1 | Workspaces, auth, Postgres backend |
| [`PHASE-2-sandbox.md`](./PHASE-2-sandbox.md) | 2 | SandboxRunner, Session, BridgeStream, EchoRuntime |
| [`PHASE-3-real-runtimes.md`](./PHASE-3-real-runtimes.md) | 3 | OpenAgentSDK + DirectAnthropic runtimes; HarnessAgent live |
| [`PHASE-4-multimodel-mcp.md`](./PHASE-4-multimodel-mcp.md) | 4 | OpenClaude runtime, MCP gateway, model agnosticism proof |
| [`PHASE-5-resume-webhooks-widgets.md`](./PHASE-5-resume-webhooks-widgets.md) | 5 | Checkpoint/resume, webhook delivery, embed widgets |
| [`PHASE-6-hardening.md`](./PHASE-6-hardening.md) | 6 | Helm, K8s sandbox runner, OTEL, Prometheus, runbooks |

## Conventions used in every spec

- **MUST / SHOULD / MAY** are RFC 2119. MUST is non-negotiable.
- Code blocks marked `# verbatim` are copied into source files exactly as
  shown. Code blocks marked `# template` show the shape; the implementer
  fills in the body.
- `path/to/file.py` references are relative to the repo root.
- Database column types use Postgres types; SQLite equivalents are noted
  where they differ.
- `TODO(phase-N)` markers in code stubs reference the phase that fills them
  in. They MUST NOT be deleted before that phase.

## Estimating effort

Effort estimates inside each spec assume:

- One competent Python engineer, FastAPI/asyncio fluent, who has read the
  existing Atrium codebase and understands LangGraph at the level of the
  current `engine/graph_builder.py`.
- Test infrastructure is already set up (pytest, asyncio_mode=auto).
- Reviews are turned around in <24h.

For an LLM-assisted implementation, multiply estimates by 0.6 for the
straightforward phases (0, 1, 5) and by 0.9 for the harness-heavy phases
(2, 3, 4, 6) — the LLM helps less where novel system design is involved.
