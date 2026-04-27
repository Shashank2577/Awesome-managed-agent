"""Hello World — run with: python -m atrium.examples.hello_world.app"""
from atrium import Atrium
from atrium.examples.hello_world.agents import FactCheckerAgent, SummarizerAgent, WikiSearchAgent

app = Atrium(
    agents=[WikiSearchAgent, SummarizerAgent, FactCheckerAgent],
    llm="openai:gpt-4o-mini",
)

if __name__ == "__main__":
    app.serve()
