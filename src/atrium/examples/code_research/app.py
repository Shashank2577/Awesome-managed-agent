"""Runnable example app for code_research."""
from atrium import Atrium
from atrium.examples.code_research.agent import CodeResearchAgent


app = Atrium(agents=[CodeResearchAgent])

if __name__ == "__main__":
    app.serve()
