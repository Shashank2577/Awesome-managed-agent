"""Long-running sandboxed agent loops — Atrium's harness layer.

See ``docs/managed-agent-replacement/04-harness-integration.md`` for the
design. This package is the integration point with open-source agentic
runtimes (Open Agent SDK, OpenClaude, direct Anthropic SDK).

Public surface
--------------
``HarnessAgent``      Atrium-side agent wrapper. Subclass of ``core.agent.Agent``.
``Session``           Long-running state and workspace for a harness run.
``Runtime``           Protocol that runtime adapters implement.
``SandboxRunner``     Container lifecycle abstraction.

Nothing here is wired up yet — these are scaffolds. Implementation lands
in phases 2–5 of the roadmap.
"""

from atrium.harness.agent import HarnessAgent
from atrium.harness.session import Session
from atrium.harness.sandbox import SandboxRunner
from atrium.harness.runtimes.base import Runtime

__all__ = ["HarnessAgent", "Session", "SandboxRunner", "Runtime"]
