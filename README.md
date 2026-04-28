# Atrium

Observable, cost-bounded, human-in-the-loop agent orchestration on top of LangGraph.

## Quick Start

```bash
pip install -e ".[all]"

# Set ANY one of these — Atrium auto-detects which provider to use:
export GEMINI_API_KEY="your-key"     # Google Gemini
# OR: export OPENAI_API_KEY="your-key"   # OpenAI
# OR: export ANTHROPIC_API_KEY="your-key" # Anthropic

python -m atrium.examples.hello_world.app
```

Open http://localhost:8080 — type a goal and watch agents work.

## Two Ways to Build Agents

### Option 1: From the Dashboard (no code)

Click **+ Create Agent** in the dashboard and fill in the form:

| Field | Example |
|---|---|
| Name | `weather_lookup` |
| Description | `Fetches current weather for a city` |
| Capabilities | `weather, location` |
| API URL | `https://api.weatherapi.com/v1/current.json` |
| Method | `GET` |
| Query Params | `q={query}` |
| Response Path | `current` |

The agent is registered immediately — the Commander can use it in the next thread. Agents persist to SQLite and survive server restarts.

You can also manage agents from the API:

```bash
# Create
curl -X POST http://localhost:8080/api/v1/agents/create \
  -H "Content-Type: application/json" \
  -d '{"name": "wiki", "description": "Search Wikipedia", "capabilities": ["search"], "api_url": "https://en.wikipedia.org/w/api.php", "method": "GET", "query_params": {"action": "query", "list": "search", "srsearch": "{query}", "format": "json"}, "response_path": "query.search"}'

# List
curl http://localhost:8080/api/v1/agents

# View config
curl http://localhost:8080/api/v1/agents/wiki/config

# Delete
curl -X DELETE http://localhost:8080/api/v1/agents/wiki
```

### Option 2: In Python (full control)

```python
from atrium import Agent, Atrium

class MyAgent(Agent):
    name = "my_agent"
    description = "Does something useful"
    capabilities = ["analyze"]

    async def run(self, input_data: dict) -> dict:
        await self.say("Working...")
        return {"result": "done"}

app = Atrium(agents=[MyAgent])
app.serve()
```

## Scaffold a New Agent

```bash
atrium new agent price_checker
```

## Docker

```bash
docker build -t atrium .
docker run -p 8080:8080 -e GEMINI_API_KEY=your-key atrium
```

Run with the hello_world example pre-loaded:

```bash
docker run -p 8080:8080 -e GEMINI_API_KEY=your-key atrium atrium example run hello_world
```

## Dashboard Features

- **Real-time execution** — watch agents plan, execute, and report live via SSE
- **Agent management** — create, view, edit, delete agents from the UI
- **Plan visualization** — DAG graph showing agent dependencies
- **HITL controls** — pause, resume, cancel, approve, reject mid-execution
- **Budget tracking** — live cost bar with guardrail enforcement
- **Thread history** — SQLite-persisted, survives restarts

## Run Tests

```bash
pip install -e ".[dev,all]"
pytest tests/ -v  # 103 tests
```

## Docs

- [Getting Started](docs/getting-started.md)
- [Writing Agents](docs/guide/writing-agents.md)
- [Agent Patterns](docs/guide/agent-patterns.md)
- [Testing](docs/guide/testing-agents.md)
- [Concepts](docs/guide/concepts.md)

## What's Inside

```
src/atrium/
  core/        Agent base class, registry, models, guardrails, HTTPAgent, agent store
  engine/      LLM Commander, LangGraph graph builder, orchestrator
  streaming/   Event recorder (SQLite-backed), SSE fan-out
  api/         FastAPI with 16 endpoints + OpenAPI docs
  dashboard/   Built-in real-time web console with agent builder
  examples/    hello_world (Wikipedia) + observe (SRE)
  testing/     run_thread() helper, MockCommander
docs/
  spec/        Specification (matches implementation)
  guide/       Developer guides
```
