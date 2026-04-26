# Atrium · the management plane for agents

Watch a team of agents think out loud. Atrium is a spec-aligned multi-agent
runtime with a streaming chat UI: a commander reads your goal, hires
specialists in parallel, narrates the plan, **pivots on evidence**, and ships
a human-friendly report — every step streamed over SSE.

## Quick start

```bash
PYTHONPATH=. python scripts/run_runtime_ui.py
```

Then open `http://127.0.0.1:8080` for the landing page and
`http://127.0.0.1:8080/console` for the live chat console.

## Run tests

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
```

## What's inside

- `backend/app/runtime/commander.py` — control plane: planning loop, agent
  hiring, pivot engine, presenter agent
- `backend/app/runtime/streaming.py` — async append-only event log with
  per-thread fan-out for SSE
- `backend/app/api/server.py` — HTTP API + real-time SSE endpoint
- `backend/app/runtime/{executor,worker,state_machine,guardrails}.py` — DAG
  executor, lifecycle, guardrails (max-agents, max-parallel, max-time,
  max-cost, max-pivots)
- `frontend/index.html` — landing page
- `frontend/console.html` + `console.js` — chat console (composer, plan card,
  agent timelines, pivot ribbon, evidence card with charts, live event feed)
- `frontend/styles.css` — design system (tokens, typography, motion)
- `docs/spec/` — normative spec (CONSTITUTION, SPEC, EVENTS, STATE_MACHINE,
  DATA_MODEL, EXECUTION_SEMANTICS, COST_MODEL, PLANNING, API, UI_SPEC)

## Demo prompts

- "Investigate a P1 incident: payments service latency is spiking…" → triggers
  the pivot path
- "Run an observability readiness review…"
- "Audit our cost model: retention windows…"
