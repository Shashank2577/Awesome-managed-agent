"""Atrium harness — sandboxed agent runtime infrastructure.

Public API::

    from atrium.harness import HarnessAgent
    from atrium.harness.runtimes.echo import EchoRuntime
    from atrium.harness.runtimes.open_agent_sdk import OpenAgentSDKRuntime
    from atrium.harness.runtimes.direct_anthropic import DirectAnthropicRuntime
"""
from atrium.harness.agent import HarnessAgent
from atrium.harness.bridge import BridgeResult, BridgeStream, GuardrailEnforcer
from atrium.harness.sandbox import (
    DockerSandboxRunner,
    InMemorySandboxRunner,
    NetworkPolicy,
    ResourceLimits,
    SandboxRunner,
)
from atrium.harness.session import Session, SessionStatus, SessionStore

__all__ = [
    "HarnessAgent",
    "BridgeResult",
    "BridgeStream",
    "GuardrailEnforcer",
    "DockerSandboxRunner",
    "InMemorySandboxRunner",
    "NetworkPolicy",
    "ResourceLimits",
    "SandboxRunner",
    "Session",
    "SessionStatus",
    "SessionStore",
]
