# Atrium Framework Design Spec

**Date**: 2026-04-27
**Status**: Approved
**Scope**: Rebuild Atrium as an open-source agent orchestration framework on top of LangGraph

---

## 1. What Atrium Is

Atrium is an **observable, cost-bounded, human-in-the-loop orchestration layer** for LLM-powered multi-agent systems. It wraps LangGraph as the execution engine and adds:

- **A Commander** — an LLM planner that reads a registry of available agents and dynamically decides which to run, in what order, with what inputs
- **Real-time event streaming** — every agent start, completion, failure, LLM call, and pivot is captured in an append-only event log and streamed via SSE
- **A built-in dashboard** — a web UI where you watch agents plan, execute, pivot, and report in real-time
- **Cost/time/parallelism guardrails** — hard limits that can halt execution mid-flight
- **Human-in-the-loop controls** — pause, resume, approve, reject, and inject input during execution

Atrium does NOT rebuild agent execution, checkpointing, or state management. LangGraph handles those.

## 2. Architecture

```
+---------------------------------------------------+
|                  Dashboard (UI)                    |  Real-time visual console
+---------------------------------------------------+
|               FastAPI + SSE Layer                  |  Threads, HITL controls, streaming
+---------------------------------------------------+
|              Atrium Orchestrator                   |
|  +-------------+---------------+-----------------+ |
|  | Commander   | Guardrails    | Event Recorder  | |
|  | (LLM        | (cost, time,  | (append-only    | |
|  |  planner)   |  parallelism) |  event log)     | |
|  +-------------+---------------+-----------------+ |
+---------------------------------------------------+
|           LangGraph (execution engine)             |  StateGraph, interrupts, checkpoints
+---------------------------------------------------+
|         User-defined Agents (your code)            |
+---------------------------------------------------+
```

### Responsibility Split

| Concern | Owner |
|---|---|
| Agent execution, state management | LangGraph |
| Checkpointing / persistence | LangGraph (SQLite checkpointer) |
| Interrupt / resume | LangGraph |
| Graph compilation and execution | LangGraph |
| Deciding which agents to run | Atrium Commander |
| Cost/time/parallelism guardrails | Atrium |
| Real-time event streaming to UI | Atrium |
| Visual dashboard | Atrium |
| HITL UX (approve/reject/input) | Atrium (using LangGraph interrupts) |
| Agent registration + capability matching | Atrium |

## 3. Package Structure

```
atrium/
  pyproject.toml
  src/
    atrium/
      __init__.py           # Public: Agent, Atrium, GuardrailsConfig
      cli.py                # `atrium serve`, `atrium example run`

      core/
        agent.py            # Agent base class + AgentCapability
        registry.py         # AgentRegistry (register, find_by_capability, manifest)
        models.py           # Thread, Plan, Event (Pydantic models)
        guardrails.py       # GuardrailEnforcer (adapted from existing)

      engine/
        graph_builder.py    # Builds LangGraph StateGraph from Commander's plan
        commander.py        # LLM planner: registry -> plan -> execute -> evaluate -> pivot
        callbacks.py        # LangGraph callbacks -> Atrium event stream
        llm.py              # LLMClient (OpenAI, Gemini, Anthropic)

      streaming/
        events.py           # Event types, EventRecorder (append-only, persisted)
        bus.py              # SSE fan-out to subscribers

      api/
        app.py              # FastAPI app factory
        routes/
          threads.py        # CRUD + SSE streaming
          control.py        # Pause/resume/cancel/approve/reject/input
          registry.py       # List agents + capabilities
        schemas.py          # Pydantic request/response models
        middleware.py        # CORS, error handling

      dashboard/
        static/             # CSS, JS (adapted from current frontend)

      testing/
        helpers.py          # run_thread() test helper, mock Commander

      examples/
        hello_world/        # Zero-dep getting started (Wikipedia agents)
        observe/            # SRE agents (advanced, real VictoriaMetrics/Loki)

      templates/
        agent.py.j2         # Jinja2 template for `atrium new agent`
        test_agent.py.j2    # Jinja2 template for agent test scaffold

  docs/
    getting-started.md
    guide/
      concepts.md
      writing-agents.md
      agent-patterns.md
      testing-agents.md
      guardrails.md
      hitl.md
      deployment.md

  tests/
    test_core/
    test_engine/
    test_streaming/
    test_api/
```

## 4. Core Layer

### Agent Interface

The developer's primary touchpoint. Minimal surface — one class, one method.

```python
from atrium import Agent

class MyAgent(Agent):
    name = "my_agent"                    # Unique identifier
    description = "Does something"       # Natural language, fed to Commander LLM
    capabilities = ["analyze"]           # Tags for capability matching
    input_schema = {"query": str}        # Optional: helps Commander wire data
    output_schema = {"result": str}      # Optional: helps Commander wire data

    async def run(self, input_data: dict) -> dict:
        # Your logic here. Call APIs, use libraries, run LLMs.
        return {"result": "..."}
```

Developer controls: name, description, capabilities, schemas, run() logic.
Developer does NOT manage: lifecycle transitions, event emission, cost tracking, retry/failure.

### Agent Registry

Holds all registered agents. Exposes a structured manifest the Commander uses for planning.

```python
app = Atrium(agents=[MyAgent, OtherAgent])
# Internally: registry.register(MyAgent), registry.register(OtherAgent)
# Commander receives manifest:
# [{"name": "my_agent", "description": "...", "capabilities": [...], "input_schema": {...}}, ...]
```

Methods:
- `register(agent_class)` — register an agent by class
- `get(name)` — get agent class by name
- `find_by_capability(tag)` — find agents matching a capability tag
- `manifest()` — JSON-serializable list of all agents for the Commander prompt

### Guardrails

Adapted from existing `guardrails.py`. Same logic, exposed via config:

```python
app = Atrium(
    agents=[...],
    guardrails=GuardrailsConfig(
        max_agents=25,
        max_parallel=5,
        max_time_seconds=600,
        max_cost_usd=10.0,
        max_pivots=2,
    )
)
```

Five independent checks: spawn count, parallelism, time, cost, pivots.
Each raises `GuardrailViolation` which halts execution and emits a `BUDGET_EXCEEDED` event.

### Domain Models

Pydantic models for serialization:
- `Thread` — id, objective, status, created_at
- `Plan` — id, thread_id, plan_number, rationale, steps
- `PlanStep` — agent name, inputs, depends_on, status
- `AtriumEvent` — id, thread_id, type, payload, sequence, timestamp, causation_id
- `BudgetSnapshot` — consumed, limit, currency

Removed from current domain.py (not implemented, won't promise):
- WorkerJob, ToolInvocation, ToolDefinition, Checkpoint, BudgetLedger

## 5. Engine Layer

### Execution Flow

```
User objective
    |
    v
Commander (LLM)
    | reads agent manifest, generates plan JSON
    v
Graph Builder
    | converts plan to LangGraph StateGraph
    | - each agent = a node
    | - dependencies = edges
    | - parallel agents = fan-out branches
    v
LangGraph Runtime
    | executes graph with:
    | - SqliteSaver checkpointer
    | - AtriumCallbacks for event capture
    | - Semaphore for parallelism guardrail
    v
Evaluator (LLM)
    | reviews outputs, decides:
    | - Finalize -> synthesize report -> END
    | - Pivot -> re-plan with new/changed agents -> re-execute
```

### Commander

Two LLM calls per thread lifecycle:

**Plan Generation**: Receives user objective + agent manifest. Returns:
```json
{
  "rationale": "string",
  "steps": [
    {"agent": "name", "inputs": {}, "depends_on": ["other_name"]}
  ]
}
```

**Evaluation / Pivot**: After execution, reviews all outputs. Decides finalize or pivot.
Pivot loop is hard-capped by `guardrails.max_pivots`.

The Commander does NOT use hardcoded scenario templates. It generates plans dynamically from the registered agents and the user's objective.

### Graph Builder

Compiles Commander's plan JSON into a LangGraph StateGraph:

- Each plan step becomes a graph node wrapping `agent.run()`
- Dependencies become edges
- Steps with no dependencies fan out in parallel (LangGraph handles this)
- All leaf nodes feed into an evaluator node
- Evaluator has conditional edges: pivot (back to commander) or finalize (END)
- Graph is compiled with `SqliteSaver` for checkpointing

### Callbacks

Bridge between LangGraph events and Atrium's event stream:

- `on_chain_start` -> `AGENT_RUNNING`
- `on_chain_end` -> `AGENT_COMPLETED` + `AGENT_OUTPUT`
- `on_chain_error` -> `AGENT_FAILED`
- `on_llm_start` -> `LLM_CALL_STARTED` (for cost tracking)
- `on_llm_end` -> `LLM_CALL_COMPLETED` (accumulate token usage)

Every LLM call is intercepted for cost tracking. The guardrail enforcer checks accumulated cost after each callback and can interrupt execution if the budget is exceeded.

### HITL via LangGraph Interrupts

When the Commander's plan includes steps that need human approval, or when a user presses "Pause":

1. LangGraph interrupt fires, execution pauses, state is checkpointed
2. Atrium emits `HUMAN_APPROVAL_REQUESTED` event
3. Dashboard shows approve/reject UI
4. User action -> FastAPI endpoint -> LangGraph resumes from checkpoint (or re-plans on reject)

## 6. Streaming & Events

### Event Taxonomy

Trimmed to what's actually implemented:

```
Thread:     THREAD_CREATED, THREAD_PLANNING, THREAD_RUNNING,
            THREAD_COMPLETED, THREAD_FAILED, THREAD_CANCELLED, THREAD_PAUSED
Plan:       PLAN_CREATED, PLAN_APPROVED, PLAN_REJECTED,
            PLAN_EXECUTION_STARTED, PLAN_COMPLETED
Agent:      AGENT_RUNNING, AGENT_COMPLETED, AGENT_FAILED,
            AGENT_MESSAGE, AGENT_OUTPUT
Commander:  COMMANDER_MESSAGE, PIVOT_REQUESTED, PIVOT_APPLIED
HITL:       HUMAN_APPROVAL_REQUESTED, HUMAN_INPUT_RECEIVED
Budget:     BUDGET_RESERVED, BUDGET_CONSUMED, BUDGET_EXCEEDED
Evidence:   EVIDENCE_PUBLISHED
```

Removed from current spec: AGENT_REGISTERED, AGENT_READY, AGENT_QUEUED (internal states the dashboard doesn't meaningfully distinguish).

### EventRecorder

Unified component replacing current split between ThreadStream and InMemoryEventBus:

- `emit(thread_id, event_type, payload)` — creates event, persists to SQLite, fans out to SSE subscribers
- `subscribe(thread_id, since_sequence)` — async iterator for SSE streaming
- `replay(thread_id, since_sequence)` — read from SQLite for historical threads

Events are persisted as they're emitted. Server restarts don't lose history.

### SSE Transport

Same proven design as current `streaming.py`: asyncio.Queue per subscriber, sentinel-based termination. Served via FastAPI StreamingResponse instead of stdlib HTTP.

## 7. API Layer

### Endpoints (14 total)

```
GET  /api/v1/health                      -> status, version, agents_registered

POST /api/v1/threads                     -> Create thread, start execution
GET  /api/v1/threads                     -> List threads
GET  /api/v1/threads/{id}                -> Thread detail + event history
GET  /api/v1/threads/{id}/stream         -> SSE event stream
DELETE /api/v1/threads/{id}              -> Cancel and archive

POST /api/v1/threads/{id}/pause          -> Pause execution
POST /api/v1/threads/{id}/resume         -> Resume execution
POST /api/v1/threads/{id}/cancel         -> Cancel execution
POST /api/v1/threads/{id}/approve        -> Approve pending plan/action
POST /api/v1/threads/{id}/reject         -> Reject pending plan/action
POST /api/v1/threads/{id}/input          -> Inject human input

GET  /api/v1/agents                      -> List agents + capabilities
GET  /api/v1/agents/{name}               -> Agent detail

GET  /dashboard                          -> Built-in web UI
```

### Schemas

Request/response models via Pydantic:
- `CreateThreadRequest` — objective, optional config overrides
- `ThreadResponse` — id, title, objective, status, created_at, stream_url
- `ThreadDetailResponse` — extends ThreadResponse with plan, events, budget
- `PlanResponse` — id, plan_number, rationale, steps
- `EventResponse` — id, type, payload, sequence, timestamp
- `AgentInfoResponse` — name, description, capabilities, schemas
- `HumanInputRequest` — input string
- `BudgetSnapshot` — consumed, limit, currency

### Explicitly NOT in v1

- Auth (Bearer tokens, X-Org-Id) — single-tenant, local dev
- Pagination — not needed at v1 scale
- Agent registration via HTTP — agents registered in Python code
- Multi-tenancy — single user, single instance
- Idempotency keys

## 8. Dashboard

### Kept from current frontend

- CSS design system (844 lines) — OKLCH palette, glassmorphism, responsive
- Three-column layout — thread list, transcript, event feed + budget
- Agent cards — collapsible with status pills, thought stream, output viewer
- SVG charts — bar, donut, scorecard
- Message animations — fade-in, thinking dots, pivot ribbon

### Changed

- SSE wiring adapted to new event taxonomy
- HITL controls wired to real endpoints (approve/reject/input)
- Plan DAG nodes update in real-time with color transitions
- Historical thread loading from SQLite on page load
- Landing page removed — dashboard is the root

### Not in v1

- No frontend framework — vanilla JS stays
- No 10k event virtualization
- No WebSocket — SSE sufficient

## 9. Examples

### hello_world (zero dependencies)

Three agents using Wikipedia's public API:
- `WikiSearchAgent` — searches Wikipedia
- `SummarizerAgent` — extractive summary (no LLM needed)
- `FactCheckerAgent` — cross-references claims

Only external requirement: OpenAI key for the Commander's planning.
Run: `pip install atrium && cd examples/hello_world && python app.py`

### observe (advanced SRE)

Adapted from current real agents:
- `PathfinderAgent` — resolves ambiguous resource names via VictoriaMetrics
- `MapperAgent` — maps service topology via PromQL
- `AnalystAgent` — analyzes time-series metrics
- `DeepDiverAgent` — forensic log correlation via Loki

Requires: VictoriaMetrics, Loki, LLM API key.

## 10. What Gets Deleted

| File/Directory | Reason |
|---|---|
| `backend/app/agents/observability/specialists.py` | 15 stub agent classes |
| `backend/app/agents/observability/registry.py` | Stub registry |
| `backend/app/agents/dummy.py` | DummyAgent, SummaryAgent (replaced by examples) |
| `backend/app/runtime/commander.py` | Hardcoded SCENARIO_LIBRARY, fake data |
| `backend/app/services/observability_service.py` | Unused |
| `frontend/index.html` | Marketing landing page |
| `scripts/run_observability_demo.py` | Old entry point |
| `scripts/run_runtime_ui.py` | Old entry point |
| `backend/app/api/server.py` | Stdlib HTTP server (replaced by FastAPI) |

## 11. What Gets Kept (adapted)

| File | Adaptation |
|---|---|
| `guardrails.py` | Minor: expose via Pydantic config |
| `streaming.py` | Core SSE fan-out logic reused in EventRecorder |
| `state_machine.py` | Reference for event types; LangGraph manages actual state |
| `frontend/styles.css` | As-is |
| `frontend/console.js` | Adapt SSE wiring and HITL controls |
| `frontend/console.html` | Remove landing page refs, becomes dashboard |
| `backend/app/agents/observe/*` | Move to examples/observe/, adapt to Agent base class |

## 12. Dependencies

```toml
[project]
dependencies = [
    "langgraph>=0.2",
    "langchain-core>=0.3",
    "fastapi>=0.115",
    "uvicorn>=0.32",
    "httpx>=0.27",
    "pydantic>=2.9",
]

[project.optional-dependencies]
openai = ["langchain-openai>=0.2"]
anthropic = ["langchain-anthropic>=0.3"]
google = ["langchain-google-genai>=2.0"]
```

## 13. CLI

```bash
atrium serve                    # Start API + dashboard on :8080
atrium serve --port 9000        # Custom port
atrium new agent <name>         # Scaffold a new agent + test file
atrium agents list              # List registered agents (requires app module)
atrium example run hello_world  # Run the hello_world example
atrium version                  # Print version
```

## 14. Spec Documents

The existing 10 spec files in `docs/spec/` will be rewritten to match implementation:

- `SPEC.md` — rewritten to describe the LangGraph-based system
- `CONSTITUTION.md` — kept, annotated with enforcement status
- `DATA_MODEL.md` — trimmed to implemented models only
- `API.md` — generated from FastAPI OpenAPI + usage examples
- `STATE_MACHINE.md` — kept (accurate)
- `EVENTS.md` — rewritten to match trimmed event taxonomy
- `EXECUTION_SEMANTICS.md`, `PLANNING.md`, `COST_MODEL.md`, `UI_SPEC.md` — merged into SPEC.md

## 15. Developer Documentation & Onboarding

The framework is useless if developers can't figure out how to build on it. Documentation ships as part of the package and is the primary onboarding path.

### Documentation Structure

```
docs/
  getting-started.md              # 5-minute quickstart (install -> run example -> build first agent)
  guide/
    concepts.md                   # What is a Thread, Agent, Plan, Commander, Pivot
    writing-agents.md             # THE key document — how to build agents
    agent-patterns.md             # Cookbook: common agent patterns with full code
    testing-agents.md             # Test agents in isolation, no server needed
    guardrails.md                 # Configuring cost/time/parallelism limits
    hitl.md                       # Human-in-the-loop patterns and UX
    deployment.md                 # Running in production
  api-reference/                  # Auto-generated from FastAPI OpenAPI
```

### Getting Started (docs/getting-started.md)

The 5-minute path:

```bash
pip install atrium
atrium example run hello_world
# Opens http://localhost:8080
# Type "What is quantum computing?" and watch agents work
```

Then build your first agent:

```bash
mkdir my_project && cd my_project
atrium new agent my_first_agent
# Creates agents/my_first_agent.py + tests/test_my_first_agent.py
```

Edit `agents/my_first_agent.py`, register it in `app.py`, run `atrium serve`. Under 5 minutes from install to custom agent running in the dashboard.

### Writing Agents Guide (docs/guide/writing-agents.md)

This is the most important document in the framework. It covers:

#### What is an Agent?

An agent is a Python class that does one thing well. It has a name, a description, a list of capabilities, and a `run()` method. The Commander LLM reads your name, description, and capabilities to decide whether and when to hire your agent. Your `run()` method receives input and returns output. The framework handles everything else.

#### The Minimal Agent

```python
from atrium import Agent

class PriceChecker(Agent):
    name = "price_checker"
    description = "Looks up the current price of a product from an online catalog"
    capabilities = ["pricing", "product_lookup"]

    async def run(self, input_data: dict) -> dict:
        product = input_data["product"]
        price = await some_api.get_price(product)
        return {"product": product, "price": price}
```

#### The Five Fields That Matter

| Field | Purpose | Who reads it |
|---|---|---|
| `name` | Unique identifier for this agent | Framework (routing, logging, dashboard display) |
| `description` | Plain English explanation of what this agent does | Commander LLM (decides whether to hire this agent for a task) |
| `capabilities` | Tags describing what this agent can do | Commander LLM (matches agents to sub-tasks in the plan) |
| `input_schema` | What data this agent expects to receive | Commander LLM (wires outputs from upstream agents into this agent's input) |
| `output_schema` | What data this agent returns | Commander LLM (knows what downstream agents can consume from this agent) |

#### Writing Good Descriptions

The description is the single most important field. The Commander reads it to decide whether to hire your agent. Write it like you're explaining to a smart colleague what you do:

```python
# BAD — too vague, Commander can't tell when to use this
description = "Processes data"

# BAD — too technical, doesn't explain the value
description = "Executes PromQL range queries against VictoriaMetrics HTTP API v1"

# GOOD — clear purpose, clear when to use it
description = "Analyzes memory and CPU metrics for a Kubernetes namespace to identify resource exhaustion patterns like sawtooth leaks or sudden spikes"

# GOOD — explains what AND when
description = "Sends a formatted summary to a Slack channel. Use after analysis is complete to notify the team."
```

Rules of thumb:
- Start with a verb (Analyzes, Fetches, Compiles, Sends)
- Say what it does AND what domain it operates in
- Mention when it's useful if that's not obvious
- Keep it under 2 sentences

#### Writing Good Capabilities

Capabilities are matchmaking tags. When the Commander plans, it maps sub-tasks to agent capabilities. Be specific enough to match real intent:

```python
# BAD — too generic, matches everything
capabilities = ["data"]

# BAD — too narrow, only matches exact wording
capabilities = ["kubernetes_pod_memory_working_set_bytes_analysis"]

# GOOD — specific enough to match, broad enough to be useful
capabilities = ["memory_metrics", "cpu_metrics", "resource_analysis", "kubernetes"]
```

#### Input and Output Schemas

Schemas are optional but powerful. They tell the Commander how to wire agents together:

```python
class Researcher(Agent):
    name = "researcher"
    output_schema = {"findings": list[str], "sources": list[str]}

class Writer(Agent):
    name = "writer"
    input_schema = {"findings": list[str], "tone": str}
```

The Commander sees: Researcher outputs "findings", Writer needs "findings" — it wires them. Without schemas, the Commander guesses based on descriptions. With schemas, it's precise.

#### The run() Contract

- Receives `input_data: dict` — may contain data from upstream agents, wired by the Commander
- Must return a `dict` — becomes the agent's output, visible in the dashboard and passed to downstream agents
- Can be async — call APIs, run LLMs, do I/O, take as long as needed (within guardrail time limits)
- Should raise exceptions on failure — the framework catches them, marks the agent FAILED, and surfaces the error in the dashboard
- Can emit progress messages via `self.say()`

```python
async def run(self, input_data: dict) -> dict:
    await self.say("Looking up prices...")        # appears in dashboard live
    
    try:
        result = await api.fetch(input_data["query"])
    except httpx.HTTPError as e:
        raise RuntimeError(f"API failed: {e}")    # agent marked FAILED, error shown in UI
    
    await self.say(f"Found {len(result)} results") # progress update
    return {"results": result}                     # output stored + passed downstream
```

#### self.say() — Your Voice in the Dashboard

`self.say(text)` streams a message to the dashboard in real-time. It appears as a thought bubble under your agent's card. Use it for:

- Progress updates: `"Searching 3 databases..."`
- Intermediate findings: `"Found 47 error entries, analyzing patterns..."`
- Explaining decisions: `"No errors in last hour, expanding window to 24h..."`
- Completions: `"Analysis complete. 3 critical findings."`

Don't over-use it. 2-4 messages per agent run is the sweet spot. Every message appears in the live event stream, so spamming creates noise.

### Agent Patterns Cookbook (docs/guide/agent-patterns.md)

#### Pattern 1: API Wrapper

Wraps an external API. Most common pattern.

```python
class GitHubIssueAgent(Agent):
    name = "github_issues"
    description = "Fetches and analyzes open issues from a GitHub repository"
    capabilities = ["github", "issue_tracking", "bug_analysis"]
    input_schema = {"repo": str}
    output_schema = {"issues": list[dict], "count": int}

    async def run(self, input_data: dict) -> dict:
        repo = input_data["repo"]
        await self.say(f"Fetching issues from {repo}...")
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://api.github.com/repos/{repo}/issues")
            resp.raise_for_status()
            issues = resp.json()
        await self.say(f"Found {len(issues)} open issues")
        return {"issues": issues, "count": len(issues)}
```

#### Pattern 2: LLM-Powered Analysis

Uses an LLM internally to interpret data. The agent manages its own LLM calls.

```python
class SentimentAgent(Agent):
    name = "sentiment_analyzer"
    description = "Analyzes the sentiment and tone of text using an LLM"
    capabilities = ["sentiment", "text_analysis", "nlp"]
    input_schema = {"text": str}
    output_schema = {"sentiment": str, "confidence": float, "explanation": str}

    async def run(self, input_data: dict) -> dict:
        text = input_data["text"]
        await self.say("Analyzing sentiment...")
        # Agent uses its own LLM — Atrium doesn't intercept this
        import openai
        client = openai.AsyncOpenAI()
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"Analyze sentiment: {text}. Return JSON with sentiment, confidence, explanation."}],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        await self.say(f"Sentiment: {result['sentiment']} ({result['confidence']:.0%} confidence)")
        return result
```

#### Pattern 3: Aggregator (consumes upstream outputs)

Combines results from multiple upstream agents. The Commander wires upstream outputs into this agent's input.

```python
class ReportCompiler(Agent):
    name = "report_compiler"
    description = "Compiles findings from multiple research agents into a structured report"
    capabilities = ["reporting", "summarization", "compilation"]
    input_schema = {"findings": list}
    output_schema = {"report": str, "finding_count": int}

    async def run(self, input_data: dict) -> dict:
        findings = input_data.get("findings", [])
        await self.say(f"Compiling {len(findings)} findings into report...")
        report = "\n".join(f"- {f}" for f in findings)
        return {"report": report, "finding_count": len(findings)}
```

#### Pattern 4: External Config (env vars, secrets)

Agents that need credentials or configuration.

```python
class SlackNotifier(Agent):
    name = "slack_notifier"
    description = "Sends a summary message to a Slack channel when analysis is complete"
    capabilities = ["notification", "slack", "messaging"]
    input_schema = {"message": str}
    output_schema = {"sent": bool}

    def __init__(self):
        self.webhook_url = os.environ["SLACK_WEBHOOK_URL"]

    async def run(self, input_data: dict) -> dict:
        message = input_data["message"]
        await self.say("Sending to Slack...")
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.webhook_url, json={"text": message})
            resp.raise_for_status()
        await self.say("Sent successfully")
        return {"sent": True}
```

#### Pattern 5: Multi-Step Agent (internal pipeline)

An agent that does multiple things internally. Keep it as one agent when the steps are tightly coupled and don't make sense independently.

```python
class WebResearcher(Agent):
    name = "web_researcher"
    description = "Searches the web, reads top results, and extracts key facts"
    capabilities = ["web_search", "research", "fact_extraction"]
    input_schema = {"query": str, "max_sources": int}
    output_schema = {"facts": list[str], "sources": list[str]}

    async def run(self, input_data: dict) -> dict:
        query = input_data["query"]
        max_sources = input_data.get("max_sources", 3)
        
        await self.say(f"Searching for: {query}")
        urls = await self._search(query, max_sources)
        
        await self.say(f"Reading {len(urls)} sources...")
        contents = await asyncio.gather(*[self._fetch(url) for url in urls])
        
        await self.say("Extracting key facts...")
        facts = self._extract_facts(contents)
        
        return {"facts": facts, "sources": urls}
```

### Testing Agents (docs/guide/testing-agents.md)

Agents are plain Python classes. Test them by calling `run()` directly. No framework setup needed.

```python
# tests/test_price_checker.py
import pytest
from agents.price_checker import PriceChecker

@pytest.mark.asyncio
async def test_returns_price():
    agent = PriceChecker()
    result = await agent.run({"product": "laptop"})
    assert "price" in result
    assert isinstance(result["price"], (int, float))

@pytest.mark.asyncio
async def test_handles_unknown_product():
    agent = PriceChecker()
    with pytest.raises(RuntimeError, match="not found"):
        await agent.run({"product": "nonexistent_xyz_123"})

@pytest.mark.asyncio
async def test_output_matches_schema():
    agent = PriceChecker()
    result = await agent.run({"product": "laptop"})
    # Verify output matches declared schema
    for key in PriceChecker.output_schema:
        assert key in result
```

Key principle: agents are testable in isolation. You don't need a running server, a Commander, or LangGraph. Your agent is a function: input in, output out.

For integration tests (agent within a full Atrium execution), the framework provides a test helper:

```python
from atrium.testing import run_thread

@pytest.mark.asyncio
async def test_full_thread():
    result = await run_thread(
        agents=[ResearchAgent, WriterAgent],
        objective="Research AI in healthcare",
        llm="mock",  # uses a mock Commander that runs all agents sequentially
    )
    assert result.status == "COMPLETED"
    assert len(result.events) > 0
    assert any(e.type == "EVIDENCE_PUBLISHED" for e in result.events)
```

### CLI Scaffolding

```bash
atrium new agent price_checker
```

Generates:

```python
# agents/price_checker.py
from atrium import Agent

class PriceCheckerAgent(Agent):
    name = "price_checker"
    description = ""  # TODO: Describe what this agent does
    capabilities = []  # TODO: Add capability tags

    # Optional: declare schemas for better Commander planning
    # input_schema = {"key": type}
    # output_schema = {"key": type}

    async def run(self, input_data: dict) -> dict:
        # TODO: Implement your agent logic
        await self.say("Starting work...")
        
        result = {}
        
        await self.say("Done")
        return result
```

```python
# tests/test_price_checker.py
import pytest
from agents.price_checker import PriceCheckerAgent

@pytest.mark.asyncio
async def test_price_checker_runs():
    agent = PriceCheckerAgent()
    result = await agent.run({})
    assert isinstance(result, dict)
```

The scaffolding includes TODOs at exactly the points the developer needs to fill in. The generated agent runs immediately (returns empty dict), so they can register it and see it in the dashboard before writing real logic.

### Agent Design Best Practices

Documented in writing-agents.md as a checklist:

1. **Single responsibility** — One agent, one job. If you're writing "and" in the description, consider splitting into two agents.
2. **Descriptive over clever** — A clear description is worth more than a clever algorithm. The Commander hires based on description.
3. **Fail loudly** — Raise exceptions with clear error messages. Don't return `{"error": "..."}` — raise so the framework can handle it.
4. **Schema your interfaces** — `input_schema` and `output_schema` make the Commander dramatically better at wiring agents together.
5. **Say what you're doing** — 2-4 `self.say()` calls per run. Users watching the dashboard want to know what's happening.
6. **Test in isolation** — If your agent can't be tested with just `await agent.run({...})`, it's too coupled to the framework.
7. **Keep secrets in env vars** — Use `os.environ` in `__init__`, not hardcoded in `run()`.
8. **Return structured data** — Dicts with named keys, not raw strings. Downstream agents and the Commander need structure.

## 16. LLM Usage Clarification

There are two distinct LLM consumers in Atrium:

1. **The Commander** — uses `engine/llm.py` to make planning/evaluation calls. This is Atrium's internal LLM usage, configured via `Atrium(llm="openai:gpt-4o-mini")`. The cost of these calls is tracked by guardrails.

2. **User-defined agents** — may or may not use LLMs. An agent can call any API, run any code, or use any LLM provider directly. Atrium does NOT wrap or intercept agent-internal LLM calls for v1. If an agent uses OpenAI directly, that cost is not tracked by Atrium's guardrails. Cost tracking in v1 covers only Commander LLM calls. Agent-level cost tracking is a v2 feature.

This is an honest limitation. The alternative (wrapping all LLM calls) would require agents to use Atrium's LLM client, which constrains agent authors unnecessarily.

## 16. Success Criteria

1. `pip install atrium` works
2. `atrium serve` starts FastAPI + dashboard on :8080
3. Dashboard shows registered agents, accepts objectives, streams execution in real-time
4. Commander dynamically plans from registered agents (no hardcoded scenarios)
5. Guardrails halt execution when limits are exceeded
6. HITL: pause/resume/approve/reject work from the dashboard
7. Server restart preserves thread history (SQLite)
8. hello_world example runs with only an OpenAI key
9. observe example runs with VictoriaMetrics + Loki + LLM key
10. All tests pass without external API keys (mocked LLM calls)
