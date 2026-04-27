# Getting Started

Get Atrium running in under 5 minutes.

## 1. Install

```bash
pip install atrium
```

Atrium requires Python 3.11+ and an OpenAI API key for the Commander (the LLM planner that orchestrates your agents).

## 2. Run the Example

```bash
python -m atrium.examples.hello_world.app
```

Open [http://localhost:8080](http://localhost:8080).

You'll see the dashboard with three registered agents: `wiki_search`, `summarizer`, and `fact_checker`. Type an objective like "What is quantum computing?" and watch the Commander plan, the agents execute, and results stream in real-time.

No external dependencies beyond an OpenAI key — the hello world example uses Wikipedia's public API.

## 3. Build Your First Agent

Scaffold a new project:

```bash
mkdir my_project && cd my_project
atrium new agent my_agent
```

This creates `agents/my_agent.py` with a working stub and `tests/test_my_agent.py` with a test scaffold.

Open `agents/my_agent.py` and fill in the three things that matter:

```python
from atrium import Agent

class MyAgent(Agent):
    name = "my_agent"
    description = "Fetches the current weather for a city"  # Tell the Commander what you do
    capabilities = ["weather", "data_lookup"]               # Tags for capability matching

    async def run(self, input_data: dict) -> dict:
        city = input_data.get("city", "London")
        await self.say(f"Fetching weather for {city}...")
        # Your logic here
        return {"city": city, "temperature": 22, "condition": "sunny"}
```

Register it in `app.py`:

```python
from atrium import Atrium
from agents.my_agent import MyAgent

app = Atrium(
    agents=[MyAgent],
    llm="openai:gpt-4o-mini",
)

if __name__ == "__main__":
    app.serve()
```

## 4. Run

```bash
python app.py
```

Open [http://localhost:8080](http://localhost:8080). Your agent appears in the dashboard. Submit an objective that involves weather — the Commander will plan a thread using your agent.

---

## Next Steps

- **[Concepts](guide/concepts.md)** — understand what a Thread, Plan, Commander, and Pivot are
- **[Writing Agents](guide/writing-agents.md)** — the complete guide to building agents
- **[Agent Patterns](guide/agent-patterns.md)** — cookbook with 5 common patterns and full code
- **[Testing Agents](guide/testing-agents.md)** — test agents in isolation without a running server
