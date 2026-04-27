import pytest
from atrium.core.agent import Agent
from atrium.core.registry import AgentRegistry


class AlphaAgent(Agent):
    name = "alpha"
    description = "Does alpha things"
    capabilities = ["search", "analyze"]
    async def run(self, input_data: dict) -> dict:
        return {"ok": True}


class BetaAgent(Agent):
    name = "beta"
    description = "Does beta things"
    capabilities = ["analyze", "report"]
    async def run(self, input_data: dict) -> dict:
        return {"ok": True}


def test_register_and_get():
    reg = AgentRegistry()
    reg.register(AlphaAgent)
    assert reg.get("alpha") is AlphaAgent


def test_get_unknown_raises():
    reg = AgentRegistry()
    with pytest.raises(KeyError, match="unknown_agent"):
        reg.get("unknown_agent")


def test_register_duplicate_raises():
    reg = AgentRegistry()
    reg.register(AlphaAgent)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(AlphaAgent)


def test_list_all():
    reg = AgentRegistry()
    reg.register(AlphaAgent)
    reg.register(BetaAgent)
    names = {a.name for a in reg.list_all()}
    assert names == {"alpha", "beta"}


def test_find_by_capability():
    reg = AgentRegistry()
    reg.register(AlphaAgent)
    reg.register(BetaAgent)
    analyzers = reg.find_by_capability("analyze")
    assert len(analyzers) == 2
    searchers = reg.find_by_capability("search")
    assert len(searchers) == 1
    assert searchers[0] is AlphaAgent


def test_manifest():
    reg = AgentRegistry()
    reg.register(AlphaAgent)
    reg.register(BetaAgent)
    m = reg.manifest()
    assert len(m) == 2
    assert m[0]["name"] == "alpha"
    assert m[1]["name"] == "beta"


def test_create_instance():
    reg = AgentRegistry()
    reg.register(AlphaAgent)
    instance = reg.create("alpha")
    assert isinstance(instance, AlphaAgent)
