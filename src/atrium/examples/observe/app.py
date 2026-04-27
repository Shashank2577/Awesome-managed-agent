"""Observe SRE Example — run with: python -m atrium.examples.observe.app

Requires: VICTORIAMETRICS_URL, LOKI_URL, and an LLM API key."""
from atrium import Atrium
from atrium.examples.observe.agents.pathfinder import PathfinderAgent
from atrium.examples.observe.agents.mapper import MapperAgent
from atrium.examples.observe.agents.analyst import AnalystAgent
from atrium.examples.observe.agents.deep_diver import DeepDiverAgent

app = Atrium(
    agents=[PathfinderAgent, MapperAgent, AnalystAgent, DeepDiverAgent],
    llm="openai:gpt-4o-mini",
)

if __name__ == "__main__":
    app.serve()
