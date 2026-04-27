"""End-to-end integration test — runs a full thread without real LLM calls."""
import pytest
from atrium.core.agent import Agent
from atrium.testing.helpers import run_thread


class EchoAgent(Agent):
    name = "echo"
    description = "Echoes input back"
    capabilities = ["echo"]
    async def run(self, input_data: dict) -> dict:
        await self.say("Echoing...")
        return {"echoed": True}


class ReverseAgent(Agent):
    name = "reverse"
    description = "Reverses text"
    capabilities = ["transform"]
    async def run(self, input_data: dict) -> dict:
        await self.say("Reversing...")
        return {"reversed": True}


async def test_full_thread_lifecycle():
    result = await run_thread(
        agents=[EchoAgent, ReverseAgent],
        objective="Test the system",
        llm="mock",
    )
    assert result.status == "COMPLETED"
    assert len(result.events) > 0
    types = [e.type for e in result.events]
    assert "THREAD_CREATED" in types
    assert "PLAN_CREATED" in types
    assert "AGENT_RUNNING" in types
    assert "AGENT_COMPLETED" in types
    assert "THREAD_COMPLETED" in types


async def test_thread_produces_outputs():
    result = await run_thread(
        agents=[EchoAgent],
        objective="Echo test",
        llm="mock",
    )
    assert "echo" in result.outputs
    assert result.outputs["echo"]["echoed"] is True


async def test_agent_say_messages_appear_in_events():
    result = await run_thread(
        agents=[EchoAgent],
        objective="Test say",
        llm="mock",
    )
    message_events = [e for e in result.events if e.type == "AGENT_MESSAGE"]
    assert len(message_events) > 0
    assert any("Echoing" in e.payload.get("text", "") for e in message_events)
