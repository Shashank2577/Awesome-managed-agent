import pytest
from unittest.mock import AsyncMock, patch
from atrium.core.registry import AgentRegistry
from atrium.core.agent import Agent
from atrium.engine.commander import Commander


class SearchAgent(Agent):
    name = "searcher"
    description = "Searches for information"
    capabilities = ["search"]
    input_schema = {"query": str}
    output_schema = {"results": list}
    async def run(self, input_data: dict) -> dict:
        return {"results": []}


class WriterAgent(Agent):
    name = "writer"
    description = "Writes reports"
    capabilities = ["writing"]
    input_schema = {"findings": list}
    output_schema = {"report": str}
    async def run(self, input_data: dict) -> dict:
        return {"report": ""}


@pytest.fixture
def registry():
    reg = AgentRegistry()
    reg.register(SearchAgent)
    reg.register(WriterAgent)
    return reg


async def test_plan_returns_valid_structure(registry):
    plan_json = {
        "rationale": "Search first, then write",
        "steps": [
            {"agent": "searcher", "inputs": {"query": "test"}, "depends_on": []},
            {"agent": "writer", "inputs": {"findings": []}, "depends_on": ["searcher"]},
        ],
    }
    commander = Commander(llm_config="openai:gpt-4o-mini", registry=registry)
    with patch.object(commander._llm, "generate_json", new_callable=AsyncMock, return_value=plan_json):
        plan = await commander.plan("Research AI in healthcare")
    assert plan.rationale == "Search first, then write"
    assert len(plan.steps) == 2
    assert plan.steps[0].agent == "searcher"
    assert plan.steps[1].depends_on == ["searcher"]


async def test_plan_validates_agent_names(registry):
    bad_plan = {
        "rationale": "test",
        "steps": [{"agent": "nonexistent", "inputs": {}, "depends_on": []}],
    }
    commander = Commander(llm_config="openai:gpt-4o-mini", registry=registry)
    with patch.object(commander._llm, "generate_json", new_callable=AsyncMock, return_value=bad_plan):
        plan = await commander.plan("test")
    assert len(plan.steps) == 0


async def test_evaluate_returns_finalize(registry):
    commander = Commander(llm_config="openai:gpt-4o-mini", registry=registry)
    eval_result = {"decision": "finalize", "summary": "All good"}
    with patch.object(commander._llm, "generate_json", new_callable=AsyncMock, return_value=eval_result):
        decision = await commander.evaluate(
            objective="test",
            outputs={"searcher": {"results": ["found"]}},
        )
    assert decision.action == "finalize"
    assert decision.summary == "All good"


async def test_evaluate_returns_finalize_with_findings(registry):
    commander = Commander(llm_config="openai:gpt-4o-mini", registry=registry)
    eval_result = {
        "decision": "finalize",
        "summary": "All good",
        "findings": [{"severity": "low", "text": "Minor issue"}],
        "recommendations": ["Monitor closely"],
    }
    with patch.object(commander._llm, "generate_json", new_callable=AsyncMock, return_value=eval_result):
        decision = await commander.evaluate(objective="test", outputs={"searcher": {"results": ["found"]}})
    assert decision.action == "finalize"
    assert len(decision.findings) == 1
    assert len(decision.recommendations) == 1


async def test_evaluate_returns_pivot(registry):
    commander = Commander(llm_config="openai:gpt-4o-mini", registry=registry)
    eval_result = {
        "decision": "pivot",
        "rationale": "Need deeper analysis",
        "new_steps": [{"agent": "writer", "inputs": {}, "depends_on": []}],
    }
    with patch.object(commander._llm, "generate_json", new_callable=AsyncMock, return_value=eval_result):
        decision = await commander.evaluate(
            objective="test",
            outputs={"searcher": {"results": ["found"]}},
        )
    assert decision.action == "pivot"
    assert len(decision.new_steps) == 1
