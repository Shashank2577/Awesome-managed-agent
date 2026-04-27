"""Atrium — observable agent orchestration on top of LangGraph."""

from atrium.core.agent import Agent
from atrium.core.guardrails import GuardrailsConfig
from atrium.core.registry import AgentRegistry

__version__ = "0.1.0"


class Atrium:
    """Main entry point for building an Atrium application."""

    def __init__(self, agents=None, llm=None, guardrails=None):
        from atrium.engine.llm import detect_llm

        self.registry = AgentRegistry()
        self.llm_config = llm or detect_llm()
        self.guardrails = guardrails or GuardrailsConfig()
        for agent_cls in (agents or []):
            self.registry.register(agent_cls)

    def register(self, agent_cls):
        self.registry.register(agent_cls)

    def serve(self, host=None, port=8080):
        import os
        import uvicorn
        from atrium.api.app import create_app

        if host is None:
            host = os.getenv("ATRIUM_HOST", "0.0.0.0")
        app = create_app(registry=self.registry, llm_config=self.llm_config, guardrails=self.guardrails)
        print(f"Atrium serving at http://{host}:{port}")
        print(f"LLM: {self.llm_config}")
        uvicorn.run(app, host=host, port=port)


__all__ = ["Agent", "Atrium", "GuardrailsConfig", "__version__"]
