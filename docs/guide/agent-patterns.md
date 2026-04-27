# Agent Patterns

Five patterns that cover most real-world agents. Pick the one closest to your use case and adapt it.

---

## Pattern 1: API Wrapper

The most common pattern. Wraps a single external API and returns structured data.

```python
import httpx
from atrium import Agent


class GitHubIssuesAgent(Agent):
    name = "github_issues"
    description = "Fetches and analyzes open issues from a GitHub repository"
    capabilities = ["github", "issue_tracking", "bug_analysis"]
    input_schema = {"repo": str}
    output_schema = {"issues": list, "count": int}

    async def run(self, input_data: dict) -> dict:
        repo = input_data["repo"]
        await self.say(f"Fetching issues from {repo}...")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.github.com/repos/{repo}/issues",
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            issues = resp.json()

        await self.say(f"Found {len(issues)} open issues")
        return {"issues": issues, "count": len(issues)}
```

Key points:
- Use `httpx.AsyncClient` for async HTTP — don't use `requests` in async agents
- Call `resp.raise_for_status()` before accessing the response body
- Return structured output that downstream agents can reference by key

---

## Pattern 2: LLM-Powered Analysis

An agent that uses an LLM internally to interpret or transform data. The agent manages its own LLM calls — Atrium does not intercept or cost-track these in v1.

```python
import json
import openai
from atrium import Agent


class SentimentAgent(Agent):
    name = "sentiment_analyzer"
    description = "Analyzes the sentiment and tone of a piece of text using an LLM"
    capabilities = ["sentiment", "text_analysis", "nlp"]
    input_schema = {"text": str}
    output_schema = {"sentiment": str, "confidence": float, "explanation": str}

    def __init__(self):
        self._client = openai.AsyncOpenAI()

    async def run(self, input_data: dict) -> dict:
        text = input_data["text"]
        await self.say("Analyzing sentiment...")

        response = await self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Analyze the sentiment of this text and return JSON with keys: "
                        f"sentiment (positive/negative/neutral), confidence (0.0-1.0), explanation.\n\n{text}"
                    ),
                }
            ],
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)

        await self.say(
            f"Sentiment: {result['sentiment']} "
            f"({result['confidence']:.0%} confidence)"
        )
        return result
```

Key points:
- Initialize the LLM client in `__init__`, not inside `run()` — avoids rebuilding on every call
- Use `response_format={"type": "json_object"}` to get structured output without manual parsing
- Agents using their own LLM clients are fully supported — you're not constrained to Atrium's LLM

---

## Pattern 3: Aggregator

Combines results from multiple upstream agents into a single output. The Commander automatically wires upstream outputs into this agent's `input_data` based on declared schemas.

```python
from atrium import Agent


class ReportCompilerAgent(Agent):
    name = "report_compiler"
    description = (
        "Compiles findings from multiple research agents into a structured final report. "
        "Run this last, after all analysis agents have completed."
    )
    capabilities = ["reporting", "summarization", "compilation"]
    input_schema = {"findings": list}
    output_schema = {"report": str, "finding_count": int, "sections": list}

    async def run(self, input_data: dict) -> dict:
        findings = input_data.get("findings", [])

        # Also check upstream dict if Commander passed outputs as nested data
        if not findings:
            upstream = input_data.get("upstream", {})
            for v in upstream.values():
                if isinstance(v, dict) and "findings" in v:
                    findings.extend(v["findings"])

        await self.say(f"Compiling {len(findings)} findings into report...")

        sections = []
        for i, finding in enumerate(findings, 1):
            sections.append(f"## Finding {i}\n{finding}")

        report = "\n\n".join(sections) if sections else "No findings to report."

        await self.say(f"Report compiled: {len(sections)} sections")
        return {
            "report": report,
            "finding_count": len(findings),
            "sections": sections,
        }
```

Key points:
- Aggregators should be the last step in the plan — mention this in the description
- Handle both the direct `input_data["findings"]` case and the nested `upstream` case for robustness
- Return the compiled artifact plus metadata (counts, section list) that the Commander can use to evaluate quality

---

## Pattern 4: External Config

Agents that need credentials or external configuration. Load everything in `__init__` so the dependency is explicit, the agent fails fast at startup (not mid-execution), and tests can mock the env var.

```python
import os
import httpx
from atrium import Agent


class SlackNotifierAgent(Agent):
    name = "slack_notifier"
    description = (
        "Sends a formatted summary message to a Slack channel. "
        "Use after analysis is complete to notify the on-call team."
    )
    capabilities = ["notification", "slack", "messaging"]
    input_schema = {"message": str, "channel": str}
    output_schema = {"sent": bool, "timestamp": str}

    def __init__(self):
        self._webhook_url = os.environ["SLACK_WEBHOOK_URL"]

    async def run(self, input_data: dict) -> dict:
        message = input_data["message"]
        channel = input_data.get("channel", "#alerts")

        await self.say(f"Sending notification to {channel}...")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._webhook_url,
                json={"text": message, "channel": channel},
            )
            resp.raise_for_status()

        await self.say("Notification sent successfully")
        return {"sent": True, "timestamp": resp.headers.get("x-slack-now", "")}
```

Key points:
- Load secrets from `os.environ` in `__init__`, not in `run()` — this surfaces missing secrets at startup
- The agent will raise `KeyError` if `SLACK_WEBHOOK_URL` is not set, which is the right behavior
- In tests, set the env var to a mock value: `monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://mock")`

---

## Pattern 5: Multi-Step Agent

An agent with an internal pipeline — it searches, fetches, and extracts in sequence. Use this when the steps are tightly coupled and don't make sense as independent agents.

```python
import asyncio
import httpx
from atrium import Agent


class WebResearcherAgent(Agent):
    name = "web_researcher"
    description = "Searches the web, reads the top results, and extracts key facts on a topic"
    capabilities = ["web_search", "research", "fact_extraction"]
    input_schema = {"query": str, "max_sources": int}
    output_schema = {"facts": list, "sources": list}

    async def run(self, input_data: dict) -> dict:
        query = input_data["query"]
        max_sources = input_data.get("max_sources", 3)

        await self.say(f"Searching for: {query}")
        urls = await self._search(query, max_sources)

        await self.say(f"Reading {len(urls)} sources...")
        contents = await asyncio.gather(*[self._fetch(url) for url in urls])

        await self.say("Extracting key facts...")
        facts = self._extract_facts(contents)

        await self.say(f"Done. Extracted {len(facts)} facts from {len(urls)} sources.")
        return {"facts": facts, "sources": urls}

    async def _search(self, query: str, limit: int) -> list[str]:
        # Your search implementation here
        # e.g., DuckDuckGo, SerpAPI, Bing
        return []

    async def _fetch(self, url: str) -> str:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            resp = await client.get(url)
            return resp.text if resp.status_code == 200 else ""

    def _extract_facts(self, contents: list[str]) -> list[str]:
        # Simple extraction — replace with LLM call for better results
        facts = []
        for content in contents:
            lines = [l.strip() for l in content.split("\n") if len(l.strip()) > 50]
            facts.extend(lines[:3])
        return facts[:10]
```

Key points:
- Private methods `_search`, `_fetch`, `_extract_facts` are independently testable
- `asyncio.gather` runs the fetches in parallel — don't fetch sequentially inside a loop
- When to split vs. keep together: if `_search` and `_fetch` make sense to the Commander as separate planning units, make them separate agents. If they're always used together, keep them in one agent.
