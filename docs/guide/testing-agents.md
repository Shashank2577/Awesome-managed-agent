# Testing Agents

Agents are plain Python classes. Test them directly — no running server, no Commander, no LangGraph required.

## Unit Testing with pytest

The core principle: an agent is a function. Input in, output out.

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
    # Verify every declared output key is present
    for key in PriceChecker.output_schema:
        assert key in result, f"Missing output key: {key}"
```

Install `pytest-asyncio` to run async tests:

```bash
pip install pytest pytest-asyncio
```

Add to your `pyproject.toml` or `pytest.ini`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## Mocking External Dependencies

If your agent calls external APIs, mock them so tests run offline and fast:

```python
import pytest
from unittest.mock import AsyncMock, patch
from agents.github_issues import GitHubIssuesAgent


@pytest.mark.asyncio
async def test_github_agent_returns_issues():
    mock_issues = [
        {"number": 1, "title": "Bug: login fails", "state": "open"},
        {"number": 2, "title": "Feature: dark mode", "state": "open"},
    ]

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_issues,
            raise_for_status=lambda: None,
        )
        mock_client_cls.return_value = mock_client

        agent = GitHubIssuesAgent()
        result = await agent.run({"repo": "octocat/hello-world"})

    assert result["count"] == 2
    assert result["issues"][0]["title"] == "Bug: login fails"


@pytest.mark.asyncio
async def test_github_agent_raises_on_api_error():
    import httpx

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get.return_value = AsyncMock(
            raise_for_status=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "404", request=None, response=None
                )
            )
        )
        mock_client_cls.return_value = mock_client

        agent = GitHubIssuesAgent()
        with pytest.raises(httpx.HTTPStatusError):
            await agent.run({"repo": "nonexistent/repo"})
```

## Testing self.say() Messages

`self.say()` messages are stored in `agent._messages`. You can assert on them without needing the dashboard:

```python
@pytest.mark.asyncio
async def test_agent_emits_progress_messages():
    agent = PriceChecker()
    await agent.run({"product": "laptop"})

    assert len(agent._messages) >= 1
    assert any("laptop" in msg for msg in agent._messages)
```

## Testing Agents with Environment Variables

For agents that load credentials in `__init__`, use `monkeypatch`:

```python
@pytest.mark.asyncio
async def test_slack_notifier(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/mock")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_resp = AsyncMock(raise_for_status=lambda: None)
        mock_resp.headers = {}
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        from agents.slack_notifier import SlackNotifierAgent
        agent = SlackNotifierAgent()
        result = await agent.run({"message": "Deployment complete", "channel": "#releases"})

    assert result["sent"] is True
```

## Integration Testing with run_thread()

For integration tests — running a full Atrium thread without a real LLM — use `run_thread()` from `atrium.testing`:

```python
import pytest
from atrium.testing import run_thread
from agents.researcher import ResearchAgent
from agents.writer import WriterAgent


@pytest.mark.asyncio
async def test_full_research_thread():
    result = await run_thread(
        agents=[ResearchAgent, WriterAgent],
        objective="Research AI trends in healthcare",
        llm="mock",  # Mock Commander runs all agents sequentially — no LLM key needed
    )

    assert result.status == "COMPLETED"
    assert len(result.events) > 0


@pytest.mark.asyncio
async def test_thread_emits_agent_completed_events():
    result = await run_thread(
        agents=[ResearchAgent, WriterAgent],
        objective="Summarize recent ML papers",
        llm="mock",
    )

    completed_events = [e for e in result.events if e.type == "AGENT_COMPLETED"]
    # Both agents should complete
    assert len(completed_events) >= 2


@pytest.mark.asyncio
async def test_thread_has_outputs_for_each_agent():
    result = await run_thread(
        agents=[ResearchAgent, WriterAgent],
        objective="Write a report on quantum computing",
        llm="mock",
    )

    # Each agent's output is stored in result.outputs by agent name
    assert "researcher" in result.outputs or "writer" in result.outputs
```

`llm="mock"` uses a `MockCommander` that runs all registered agents sequentially with empty inputs. This is fast, requires no API keys, and verifies the full execution path. Use it for CI.

## Test Checklist

For each agent, write tests that cover:

- **Happy path** — valid input, expected output shape and types
- **Missing optional inputs** — graceful handling when optional keys are absent
- **API failure** — the agent raises (not silently returns an error dict)
- **Output schema compliance** — all declared `output_schema` keys are present
- **Edge cases** — empty lists, zero counts, very large inputs, unexpected types
- **Integration** — one `run_thread()` test verifying the agent works in the full pipeline
