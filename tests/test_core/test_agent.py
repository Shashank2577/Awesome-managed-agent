import pytest
from atrium.core.agent import Agent


class DummyAgent(Agent):
    name = "dummy"
    description = "A test agent"
    capabilities = ["test"]
    input_schema = {"text": str}
    output_schema = {"result": str}

    async def run(self, input_data: dict) -> dict:
        return {"result": input_data["text"].upper()}


class MinimalAgent(Agent):
    name = "minimal"
    description = "Minimal agent"
    capabilities = []

    async def run(self, input_data: dict) -> dict:
        return {}


class BadAgent(Agent):
    description = "no name"
    capabilities = []

    async def run(self, input_data: dict) -> dict:
        return {}


async def test_agent_run():
    agent = DummyAgent()
    result = await agent.run({"text": "hello"})
    assert result == {"result": "HELLO"}


async def test_agent_has_metadata():
    agent = DummyAgent()
    assert agent.name == "dummy"
    assert agent.description == "A test agent"
    assert agent.capabilities == ["test"]
    assert agent.input_schema == {"text": str}
    assert agent.output_schema == {"result": str}


async def test_minimal_agent_defaults():
    agent = MinimalAgent()
    assert agent.input_schema is None
    assert agent.output_schema is None
    assert agent.capabilities == []


async def test_agent_manifest():
    agent = DummyAgent()
    manifest = agent.manifest()
    assert manifest["name"] == "dummy"
    assert manifest["description"] == "A test agent"
    assert manifest["capabilities"] == ["test"]
    assert manifest["input_schema"] == {"text": str}
    assert manifest["output_schema"] == {"result": str}


async def test_agent_say_collects_messages():
    agent = DummyAgent()
    await agent.say("thinking...")
    await agent.say("done")
    assert agent._messages == ["thinking...", "done"]


async def test_agent_say_calls_emitter_when_set():
    emitted = []

    async def mock_emit(event_type, payload, causation=None):
        emitted.append((event_type, payload))

    agent = DummyAgent()
    agent.set_emitter(mock_emit)
    await agent.say("hello")
    assert len(emitted) == 1
    assert emitted[0][0] == "AGENT_MESSAGE"
    assert emitted[0][1]["text"] == "hello"
    assert emitted[0][1]["agent_key"] == "dummy"


def test_agent_without_name_raises():
    with pytest.raises(TypeError):
        BadAgent()


def test_abstract_run_raises():
    with pytest.raises(TypeError):
        Agent()
