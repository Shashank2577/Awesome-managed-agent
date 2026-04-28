# Getting Started

Get Atrium running in under 5 minutes.

## 1. Install

```bash
pip install -e ".[all]"
```

Set any one LLM API key — Atrium auto-detects:

```bash
export GEMINI_API_KEY="your-key"     # Google Gemini
# OR: export OPENAI_API_KEY="your-key"   # OpenAI
# OR: export ANTHROPIC_API_KEY="your-key" # Anthropic
```

## 2. Run the Example

```bash
python -m atrium.examples.hello_world.app
```

Open [http://localhost:8080](http://localhost:8080).

You'll see the dashboard with three registered agents. Type "What is quantum computing?" and watch the Commander plan, agents execute, and results stream in real-time.

## 3. Create an Agent from the Dashboard (no code)

Click **+ Create Agent** in the top nav. Fill in:

| Field | Value |
|---|---|
| Name | `weather` |
| Description | `Fetches current weather for a city` |
| Capabilities | `weather, forecast` |
| API URL | `https://wttr.in/{query}?format=j1` |
| Method | `GET` |

Click **Create Agent**. It's immediately registered — the Commander will use it next time someone asks about weather.

### Managing Agents

The left sidebar shows all registered agents. Click any agent to:
- **View** its full configuration (API URL, headers, params)
- **Edit** — opens the create form pre-filled with current values
- **Delete** — removes from both the registry and storage

Agents persist to SQLite. Restart the server — they're still there.

## 4. Or Build in Python (full control)

```bash
atrium new agent price_checker
```

Edit `agents/price_checker.py`:

```python
from atrium import Agent

class PriceCheckerAgent(Agent):
    name = "price_checker"
    description = "Looks up product prices from an online catalog"
    capabilities = ["pricing", "products"]

    async def run(self, input_data: dict) -> dict:
        query = input_data.get("query", "laptop")
        await self.say(f"Looking up prices for {query}...")
        # Your logic here — call APIs, use LLMs, anything
        return {"product": query, "price": 999.99}
```

Register in `app.py`:

```python
from atrium import Atrium
from agents.price_checker import PriceCheckerAgent

app = Atrium(agents=[PriceCheckerAgent])

if __name__ == "__main__":
    app.serve()
```

Run: `python app.py` — open http://localhost:8080.

## 5. Docker

```bash
docker build -t atrium .
docker run -p 8080:8080 -e GEMINI_API_KEY=your-key atrium atrium example run hello_world
```

---

## Next Steps

- **[Concepts](guide/concepts.md)** — understand Threads, Plans, Commander, Pivots
- **[Writing Agents](guide/writing-agents.md)** — the complete guide to building agents
- **[Agent Patterns](guide/agent-patterns.md)** — cookbook with 5 common patterns
- **[Testing Agents](guide/testing-agents.md)** — test agents without a running server
