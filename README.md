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

## Build Your Own

```python
from atrium import Agent, Atrium

class MyAgent(Agent):
    name = "my_agent"
    description = "Does something useful"
    capabilities = ["analyze"]

    async def run(self, input_data: dict) -> dict:
        await self.say("Working...")
        return {"result": "done"}

app = Atrium(agents=[MyAgent], llm="openai:gpt-4o-mini")
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

## Run Tests

```bash
pip install -e ".[dev,openai]"
pytest tests/ -v
```

## Docs

- [Getting Started](docs/getting-started.md)
- [Writing Agents](docs/guide/writing-agents.md)
- [Agent Patterns](docs/guide/agent-patterns.md)
- [Testing](docs/guide/testing-agents.md)
- [Concepts](docs/guide/concepts.md)

## What's Inside

- `src/atrium/core/` — Agent base class, registry, models, guardrails
- `src/atrium/engine/` — LLM Commander, LangGraph graph builder, orchestrator
- `src/atrium/streaming/` — Event recorder (SQLite-backed), SSE fan-out
- `src/atrium/api/` — FastAPI with 14 endpoints + OpenAPI docs
- `src/atrium/dashboard/` — Built-in real-time web console
- `src/atrium/examples/` — hello_world (Wikipedia) + observe (SRE)
- `docs/spec/` — Specification (matches implementation)
