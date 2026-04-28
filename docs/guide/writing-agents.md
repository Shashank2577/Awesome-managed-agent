# Writing Agents

This is the most important document in the framework. Read it before writing your first agent.

## What is an Agent?

An agent is a Python class that does one thing well. It has a name, a description, a list of capabilities, and a `run()` method. The Commander LLM reads your name, description, and capabilities to decide whether and when to hire your agent. Your `run()` method receives input and returns output. The framework handles everything else: lifecycle management, event emission, cost tracking, retries on failure.

## The Minimal Agent

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

That's it. Register it in your `Atrium()` app and it's available to the Commander.

## The Five Fields That Matter

| Field | Purpose | Who reads it |
|---|---|---|
| `name` | Unique identifier for this agent | Framework (routing, logging, dashboard display) |
| `description` | Plain English explanation of what this agent does | Commander LLM (decides whether to hire this agent for a task) |
| `capabilities` | Tags describing what this agent can do | Commander LLM (matches agents to sub-tasks in the plan) |
| `input_schema` | What data this agent expects to receive | Commander LLM (wires outputs from upstream agents into this agent's input) |
| `output_schema` | What data this agent returns | Commander LLM (knows what downstream agents can consume from this agent) |

`name` and `description` are required. The framework will raise a `TypeError` at instantiation if either is missing or empty. `capabilities`, `input_schema`, and `output_schema` are optional but strongly recommended.

## Writing Good Descriptions

The description is the single most important field. The Commander reads it to decide whether to hire your agent for a given objective. Write it like you're explaining to a smart colleague what you do:

```python
# BAD — too vague, Commander can't tell when to use this
description = "Processes data"

# BAD — too technical, explains how but not what value it provides
description = "Executes PromQL range queries against VictoriaMetrics HTTP API v1"

# GOOD — clear purpose, clear when to use it
description = "Analyzes memory and CPU metrics for a Kubernetes namespace to identify resource exhaustion patterns like sawtooth leaks or sudden spikes"

# GOOD — explains what AND when to use it
description = "Sends a formatted summary to a Slack channel. Use after analysis is complete to notify the team."
```

Rules of thumb:
- Start with a verb: Analyzes, Fetches, Compiles, Sends, Searches, Verifies
- Say what it does AND what domain it operates in
- Mention when it's appropriate to use if that isn't obvious
- Keep it under 2 sentences

## Writing Good Capabilities

Capabilities are matchmaking tags. The Commander uses them to find agents that can handle specific sub-tasks. Be specific enough to match real intent, broad enough to be useful:

```python
# BAD — too generic, matches everything
capabilities = ["data"]

# BAD — too narrow, only matches one exact phrasing
capabilities = ["kubernetes_pod_memory_working_set_bytes_analysis"]

# GOOD — specific domain tags that match real use cases
capabilities = ["memory_metrics", "cpu_metrics", "resource_analysis", "kubernetes"]
```

Use 2–5 tags. More than 5 is usually a sign your agent is doing too many things.

## Input and Output Schemas

Schemas are optional but powerful. They tell the Commander exactly how to wire agents together:

```python
class Researcher(Agent):
    name = "researcher"
    output_schema = {"findings": list, "sources": list}

class Writer(Agent):
    name = "writer"
    input_schema = {"findings": list, "tone": str}
```

The Commander sees: `Researcher` outputs `findings`, `Writer` needs `findings` — it wires them together automatically. Without schemas, the Commander guesses based on descriptions. With schemas, the wiring is precise.

Schema values are Python types or type hints. Keep them simple — the Commander needs to understand them, not validate them:

```python
input_schema = {"query": str, "max_results": int}
output_schema = {"articles": list, "total_count": int, "next_page": str}
```

## The run() Contract

- Receives `input_data: dict` — may contain data from upstream agents, wired by the Commander
- Must return a `dict` — this becomes the agent's output, visible in the dashboard and passed to downstream agents
- Should be `async` — you can call APIs, run LLMs, do I/O
- Should raise exceptions on failure — the framework catches them, marks the agent `FAILED`, and surfaces the error in the dashboard
- Can emit progress messages via `self.say()`

```python
async def run(self, input_data: dict) -> dict:
    await self.say("Looking up prices...")

    try:
        result = await api.fetch(input_data["query"])
    except httpx.HTTPError as e:
        raise RuntimeError(f"API unavailable: {e}")   # agent marked FAILED, error shown in UI

    await self.say(f"Found {len(result)} results")
    return {"results": result}                         # output stored and passed downstream
```

**Don't catch exceptions silently.** If you return `{"error": "something went wrong"}` instead of raising, the framework thinks your agent succeeded. The downstream agents get garbage input and the Commander can't make informed pivot decisions.

## self.say() — Your Voice in the Dashboard

`self.say(text)` streams a message to the dashboard in real-time. It appears as a thought bubble under your agent's card. Use it for:

- Progress updates: `"Searching 3 databases..."`
- Intermediate findings: `"Found 47 error entries, analyzing patterns..."`
- Explaining decisions: `"No errors in the last hour, expanding window to 24h..."`
- Completions: `"Analysis complete. 3 critical findings identified."`

```python
async def run(self, input_data: dict) -> dict:
    await self.say(f"Starting analysis for namespace: {input_data['namespace']}")

    metrics = await self._fetch_metrics(input_data)
    await self.say(f"Fetched {len(metrics)} data points over 1h window")

    findings = self._analyze(metrics)
    await self.say(f"Analysis complete. {len(findings)} anomalies detected.")

    return {"findings": findings}
```

2–4 `self.say()` calls per agent run is the sweet spot. Every message appears in the live event stream — spamming creates noise for humans watching the dashboard.

## Best Practices Checklist

Before shipping an agent, verify:

1. **Single responsibility** — Your agent does one thing. If you wrote "and" in the description, consider splitting into two agents.

2. **Descriptive over clever** — A clear description is worth more than a clever algorithm. The Commander makes hiring decisions based on your description, not your code.

3. **Fail loudly** — Raise exceptions with clear, actionable messages. Never silently return error dicts. The framework needs exceptions to mark agents failed, surface errors in the dashboard, and give the Commander accurate information for pivot decisions.

4. **Schema your interfaces** — Declare `input_schema` and `output_schema`. This dramatically improves how accurately the Commander wires agents together. It costs you 2 lines of code.

5. **Say what you're doing** — Call `self.say()` at the start, at meaningful progress points, and at completion. Users watching the dashboard want to know what's happening inside your agent.

6. **Test in isolation** — Your agent should be fully testable with just `await agent.run({...})`. No running server, no Commander, no LangGraph. If it can't be tested this way, it's too tightly coupled.

7. **Keep secrets in env vars** — Load credentials in `__init__` via `os.environ["SECRET_KEY"]`, not inside `run()`. This makes the dependency explicit and the agent testable (mock the env var, not the runtime).

8. **Return structured data** — Dicts with named keys, not raw strings. Downstream agents and the Commander need structure they can reference by key. A summary string with no keys is a dead end in the pipeline.

## Config-driven LLM Agent

You don't need Python to create an expert LLM agent. Send a `POST /api/v1/agents/create` request with `agent_type: "llm"` and a system prompt:

```bash
curl -X POST http://localhost:8080/api/v1/agents/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "code_reviewer",
    "description": "Reviews Python code for style, correctness, and security issues",
    "agent_type": "llm",
    "category": "coding",
    "capabilities": ["code_review", "python", "security"],
    "system_prompt": "You are an expert Python code reviewer. Analyze the provided code for:\n- PEP 8 style violations\n- Logical errors and edge cases\n- Security vulnerabilities (injection, auth bypass, secrets in code)\n- Performance issues\n\nRespond with a structured review: summary, issues list (severity + line + fix), and an overall rating.",
    "model": "anthropic:claude-sonnet-4-6"
  }'
```

The agent is registered immediately and available to the Commander for the next thread.

### The `model` field

Use a provider-qualified string: `<provider>:<model-id>`.

| Provider | Example |
|---|---|
| Anthropic | `anthropic:claude-sonnet-4-6` |
| OpenAI | `openai:gpt-4o` |
| Google | `google:gemini-2.0-flash` |

Atrium auto-detects the provider and routes the call to the appropriate LangChain integration. The matching API key must be set in the environment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`).
