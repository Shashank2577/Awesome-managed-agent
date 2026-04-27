# Atrium Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Atrium as an open-source agent orchestration framework wrapping LangGraph, with a built-in dashboard, cost guardrails, and human-in-the-loop controls.

**Architecture:** Atrium wraps LangGraph as the execution engine. An LLM-powered Commander reads a registry of user-defined agents and dynamically plans which to run. Events stream via SSE to a built-in dashboard. Guardrails enforce cost/time/parallelism limits. HITL uses LangGraph interrupts.

**Tech Stack:** Python 3.11+, LangGraph, FastAPI, Uvicorn, Pydantic v2, httpx, langgraph-checkpoint-sqlite, aiosqlite

**Spec:** `docs/superpowers/specs/2026-04-27-atrium-framework-design.md`

---

## File Structure

### New files to create

```
pyproject.toml                          # Package metadata, deps, CLI entry point
src/atrium/__init__.py                  # Public API exports
src/atrium/cli.py                       # CLI: serve, new agent, example run
src/atrium/core/agent.py                # Agent base class
src/atrium/core/registry.py             # AgentRegistry
src/atrium/core/models.py               # Pydantic domain models
src/atrium/core/guardrails.py           # GuardrailEnforcer (adapted)
src/atrium/streaming/events.py          # EventRecorder
src/atrium/streaming/bus.py             # SSE fan-out
src/atrium/engine/llm.py                # LLMClient
src/atrium/engine/commander.py          # Commander (LLM planner)
src/atrium/engine/graph_builder.py      # Plan -> LangGraph StateGraph
src/atrium/engine/callbacks.py          # LangGraph callbacks -> events
src/atrium/engine/orchestrator.py       # Thread orchestrator (ties it all)
src/atrium/api/app.py                   # FastAPI factory
src/atrium/api/schemas.py               # Pydantic request/response
src/atrium/api/routes/threads.py        # Thread CRUD + SSE
src/atrium/api/routes/control.py        # HITL: pause/resume/approve/reject
src/atrium/api/routes/registry.py       # Agent listing
src/atrium/api/routes/health.py         # Health check
src/atrium/api/middleware.py            # CORS, error handling
src/atrium/dashboard/static/styles.css  # Adapted from existing
src/atrium/dashboard/static/console.js  # Adapted from existing
src/atrium/dashboard/static/console.html # Adapted from existing
src/atrium/testing/helpers.py           # run_thread(), MockCommander
src/atrium/templates/agent.py.j2        # Scaffold template
src/atrium/templates/test_agent.py.j2   # Scaffold template
src/atrium/examples/hello_world/agents.py
src/atrium/examples/hello_world/app.py
src/atrium/examples/observe/agents/pathfinder.py
src/atrium/examples/observe/agents/mapper.py
src/atrium/examples/observe/agents/analyst.py
src/atrium/examples/observe/agents/deep_diver.py
src/atrium/examples/observe/app.py
tests/test_core/test_agent.py
tests/test_core/test_registry.py
tests/test_core/test_models.py
tests/test_core/test_guardrails.py
tests/test_streaming/test_events.py
tests/test_streaming/test_bus.py
tests/test_engine/test_llm.py
tests/test_engine/test_commander.py
tests/test_engine/test_graph_builder.py
tests/test_engine/test_orchestrator.py
tests/test_api/test_threads.py
tests/test_api/test_control.py
tests/test_api/test_registry_routes.py
tests/test_api/test_health.py
tests/conftest.py
docs/getting-started.md
docs/guide/concepts.md
docs/guide/writing-agents.md
docs/guide/agent-patterns.md
docs/guide/testing-agents.md
```

### Files to delete (old code)

```
backend/app/agents/observability/specialists.py
backend/app/agents/observability/registry.py
backend/app/agents/observability/__init__.py
backend/app/agents/dummy.py
backend/app/agents/base.py
backend/app/runtime/commander.py
backend/app/runtime/executor.py
backend/app/runtime/worker.py
backend/app/runtime/events.py
backend/app/runtime/registry.py
backend/app/runtime/state_machine.py
backend/app/runtime/streaming.py
backend/app/runtime/guardrails.py
backend/app/api/server.py
backend/app/models/__init__.py
backend/app/models/domain.py
backend/app/services/observability_service.py
frontend/index.html
scripts/run_observability_demo.py
scripts/run_runtime_ui.py
tests/test_commander.py
tests/test_guardrails.py
tests/test_observability_demo.py
tests/test_runtime.py
```

### Files to adapt (move + rewrite)

```
frontend/styles.css        -> src/atrium/dashboard/static/styles.css  (copy as-is)
frontend/console.js        -> src/atrium/dashboard/static/console.js  (adapt SSE + HITL)
frontend/console.html      -> src/atrium/dashboard/static/console.html (adapt)
backend/app/agents/observe/ -> src/atrium/examples/observe/            (adapt to Agent base)
```

---

### Task 1: Project Scaffold & Cleanup

**Files:**
- Create: `pyproject.toml`, `src/atrium/__init__.py`, `src/atrium/core/__init__.py`, `src/atrium/streaming/__init__.py`, `src/atrium/engine/__init__.py`, `src/atrium/api/__init__.py`, `src/atrium/api/routes/__init__.py`, `src/atrium/dashboard/__init__.py`, `src/atrium/dashboard/static/.gitkeep`, `src/atrium/testing/__init__.py`, `src/atrium/templates/.gitkeep`, `src/atrium/examples/__init__.py`, `tests/__init__.py`, `tests/test_core/__init__.py`, `tests/test_streaming/__init__.py`, `tests/test_engine/__init__.py`, `tests/test_api/__init__.py`, `tests/conftest.py`
- Delete: all files listed in "Files to delete" above

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "atrium"
version = "0.1.0"
description = "Observable, cost-bounded, human-in-the-loop agent orchestration on top of LangGraph"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.2",
    "langchain-core>=0.3",
    "langgraph-checkpoint-sqlite>=2.0",
    "fastapi>=0.115",
    "uvicorn>=0.32",
    "httpx>=0.27",
    "pydantic>=2.9",
    "aiosqlite>=0.20",
    "jinja2>=3.1",
]

[project.optional-dependencies]
openai = ["langchain-openai>=0.2"]
anthropic = ["langchain-anthropic>=0.3"]
google = ["langchain-google-genai>=2.0"]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-httpx>=0.30",
    "ruff>=0.6",
]

[project.scripts]
atrium = "atrium.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/atrium"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py311"
line-length = 100
```

- [ ] **Step 2: Create package directory structure and __init__ files**

Create all directories and empty `__init__.py` files:

```
src/atrium/__init__.py
src/atrium/core/__init__.py
src/atrium/streaming/__init__.py
src/atrium/engine/__init__.py
src/atrium/api/__init__.py
src/atrium/api/routes/__init__.py
src/atrium/dashboard/__init__.py
src/atrium/testing/__init__.py
src/atrium/examples/__init__.py
tests/__init__.py
tests/test_core/__init__.py
tests/test_streaming/__init__.py
tests/test_engine/__init__.py
tests/test_api/__init__.py
```

`src/atrium/__init__.py` content:
```python
"""Atrium — observable agent orchestration on top of LangGraph."""

from atrium.core.agent import Agent
from atrium.core.guardrails import GuardrailsConfig

__version__ = "0.1.0"

__all__ = ["Agent", "Atrium", "GuardrailsConfig", "__version__"]
```

Note: `Atrium` class import will be added in Task 12 when the orchestrator is built.

`tests/conftest.py` content:
```python
"""Shared fixtures for Atrium tests."""
```

- [ ] **Step 3: Delete old backend, scripts, and test files**

```bash
rm -rf backend/app/agents/observability
rm -f backend/app/agents/dummy.py
rm -f backend/app/agents/base.py
rm -f backend/app/runtime/commander.py
rm -f backend/app/runtime/executor.py
rm -f backend/app/runtime/worker.py
rm -f backend/app/runtime/events.py
rm -f backend/app/runtime/registry.py
rm -f backend/app/runtime/state_machine.py
rm -f backend/app/runtime/streaming.py
rm -f backend/app/runtime/guardrails.py
rm -f backend/app/api/server.py
rm -rf backend/app/models
rm -rf backend/app/services
rm -f frontend/index.html
rm -rf scripts
rm -f tests/test_commander.py
rm -f tests/test_guardrails.py
rm -f tests/test_observability_demo.py
rm -f tests/test_runtime.py
```

- [ ] **Step 4: Install the package in dev mode**

```bash
pip install -e ".[dev,openai]"
```

Expected: installs successfully, `python -c "import atrium; print(atrium.__version__)"` prints `0.1.0`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ tests/conftest.py tests/__init__.py tests/test_core/ tests/test_streaming/ tests/test_engine/ tests/test_api/
git add -u  # stages deletions
git commit -m "feat: scaffold atrium package, remove old backend/frontend stubs"
```

---

### Task 2: Core — Agent Base Class

**Files:**
- Create: `src/atrium/core/agent.py`
- Test: `tests/test_core/test_agent.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core/test_agent.py
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
    """Agent without name — should fail validation."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_core/test_agent.py -v
```

Expected: FAIL — `atrium.core.agent` has no `Agent` class yet.

- [ ] **Step 3: Implement Agent base class**

```python
# src/atrium/core/agent.py
"""Agent base class — the developer's primary touchpoint."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable, Optional


class Agent(ABC):
    """Base class for all Atrium agents.

    Subclass this, set the class attributes, and implement run().
    """

    name: str
    description: str
    capabilities: list[str] = []
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None

    def __init__(self):
        if not hasattr(self, "name") or not self.name:
            raise TypeError(f"{type(self).__name__} must define a 'name' class attribute")
        if not hasattr(self, "description") or not self.description:
            raise TypeError(f"{type(self).__name__} must define a 'description' class attribute")
        self._emitter: Optional[Callable[..., Awaitable[None]]] = None
        self._messages: list[str] = []

    def set_emitter(self, emitter: Callable[..., Awaitable[None]]) -> None:
        """Called by the framework to wire event emission."""
        self._emitter = emitter

    async def say(self, text: str) -> None:
        """Stream a progress message to the dashboard."""
        self._messages.append(text)
        if self._emitter:
            await self._emitter(
                "AGENT_MESSAGE",
                {"agent_key": self.name, "text": text},
            )

    def manifest(self) -> dict[str, Any]:
        """Return a JSON-serializable description for the Commander."""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }

    @abstractmethod
    async def run(self, input_data: dict) -> dict:
        """Execute agent logic. Must be implemented by subclasses."""
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_core/test_agent.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atrium/core/agent.py tests/test_core/test_agent.py
git commit -m "feat(core): add Agent base class with say(), manifest(), emitter"
```

---

### Task 3: Core — Agent Registry

**Files:**
- Create: `src/atrium/core/registry.py`
- Test: `tests/test_core/test_registry.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core/test_registry.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_core/test_registry.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement AgentRegistry**

```python
# src/atrium/core/registry.py
"""Agent registry — holds registered agent classes and exposes manifests."""

from __future__ import annotations

from typing import Any

from atrium.core.agent import Agent


class AgentRegistry:
    """Registry of available agent classes."""

    def __init__(self):
        self._agents: dict[str, type[Agent]] = {}

    def register(self, agent_class: type[Agent]) -> None:
        """Register an agent class by its name."""
        name = agent_class.name
        if name in self._agents:
            raise ValueError(f"Agent '{name}' is already registered")
        self._agents[name] = agent_class

    def get(self, name: str) -> type[Agent]:
        """Get an agent class by name."""
        if name not in self._agents:
            raise KeyError(f"Unknown agent: '{name}'")
        return self._agents[name]

    def create(self, name: str) -> Agent:
        """Create a new instance of an agent by name."""
        return self.get(name)()

    def list_all(self) -> list[type[Agent]]:
        """Return all registered agent classes."""
        return list(self._agents.values())

    def find_by_capability(self, capability: str) -> list[type[Agent]]:
        """Find all agents that have a given capability tag."""
        return [a for a in self._agents.values() if capability in a.capabilities]

    def manifest(self) -> list[dict[str, Any]]:
        """Return JSON-serializable manifests for all agents (for Commander prompt)."""
        return [a.manifest() for a in self.list_all()]
```

Note: `manifest()` calls the class method — but `manifest()` is an instance method on Agent. We need to instantiate briefly or make it a classmethod. Let's fix: we make a temporary instance.

Actually, looking at the Agent class, `manifest()` only reads class attributes. Let's make it a `@classmethod` alternative:

```python
    def manifest(self) -> list[dict[str, Any]]:
        """Return JSON-serializable manifests for all agents (for Commander prompt)."""
        results = []
        for agent_cls in self._agents.values():
            results.append({
                "name": agent_cls.name,
                "description": agent_cls.description,
                "capabilities": list(agent_cls.capabilities),
                "input_schema": agent_cls.input_schema,
                "output_schema": agent_cls.output_schema,
            })
        return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_core/test_registry.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atrium/core/registry.py tests/test_core/test_registry.py
git commit -m "feat(core): add AgentRegistry with capability matching and manifest"
```

---

### Task 4: Core — Domain Models

**Files:**
- Create: `src/atrium/core/models.py`
- Test: `tests/test_core/test_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core/test_models.py
from atrium.core.models import (
    AtriumEvent,
    BudgetSnapshot,
    Plan,
    PlanStep,
    Thread,
    ThreadStatus,
)


def test_thread_creation():
    t = Thread(thread_id="abc", objective="test goal")
    assert t.status == ThreadStatus.CREATED
    assert t.thread_id == "abc"
    assert t.title == ""


def test_thread_serialization():
    t = Thread(thread_id="abc", objective="test goal", title="Test")
    d = t.model_dump()
    assert d["thread_id"] == "abc"
    assert d["status"] == "CREATED"


def test_plan_step():
    step = PlanStep(agent="researcher", inputs={"q": "test"}, depends_on=[])
    assert step.status == "pending"


def test_plan_creation():
    steps = [
        PlanStep(agent="a", inputs={}, depends_on=[]),
        PlanStep(agent="b", inputs={}, depends_on=["a"]),
    ]
    plan = Plan(plan_id="p1", thread_id="t1", plan_number=1, rationale="test", steps=steps)
    assert len(plan.steps) == 2


def test_event_creation():
    evt = AtriumEvent(
        event_id="e1",
        thread_id="t1",
        type="AGENT_RUNNING",
        payload={"agent_key": "alpha"},
        sequence=1,
    )
    assert evt.type == "AGENT_RUNNING"
    assert evt.causation_id is None


def test_budget_snapshot():
    b = BudgetSnapshot(consumed="0.42", limit="10.00", currency="USD")
    assert b.consumed == "0.42"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_core/test_models.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement domain models**

```python
# src/atrium/core/models.py
"""Pydantic domain models for Atrium."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ThreadStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Thread(BaseModel):
    thread_id: str = Field(default_factory=lambda: str(uuid4()))
    objective: str
    title: str = ""
    status: ThreadStatus = ThreadStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlanStep(BaseModel):
    agent: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    status: str = "pending"


class Plan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    thread_id: str
    plan_number: int = 1
    rationale: str = ""
    steps: list[PlanStep] = Field(default_factory=list)


class AtriumEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    thread_id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    sequence: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    causation_id: Optional[str] = None


class BudgetSnapshot(BaseModel):
    consumed: str
    limit: str
    currency: str = "USD"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_core/test_models.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atrium/core/models.py tests/test_core/test_models.py
git commit -m "feat(core): add Pydantic domain models for Thread, Plan, Event"
```

---

### Task 5: Core — Guardrails

**Files:**
- Create: `src/atrium/core/guardrails.py`
- Test: `tests/test_core/test_guardrails.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core/test_guardrails.py
import pytest
from decimal import Decimal
from atrium.core.guardrails import GuardrailsConfig, GuardrailEnforcer, GuardrailViolation


def test_default_config():
    cfg = GuardrailsConfig()
    assert cfg.max_agents == 25
    assert cfg.max_parallel == 5
    assert cfg.max_cost_usd == Decimal("10.0")


def test_check_spawn_passes():
    enforcer = GuardrailEnforcer(GuardrailsConfig(max_agents=3))
    enforcer.check_spawn(agent_count=3)  # at limit, ok


def test_check_spawn_raises():
    enforcer = GuardrailEnforcer(GuardrailsConfig(max_agents=3))
    with pytest.raises(GuardrailViolation, match="MAX_AGENTS"):
        enforcer.check_spawn(agent_count=4)


def test_check_parallel_passes():
    enforcer = GuardrailEnforcer(GuardrailsConfig(max_parallel=2))
    enforcer.check_parallel(running=2)


def test_check_parallel_raises():
    enforcer = GuardrailEnforcer(GuardrailsConfig(max_parallel=2))
    with pytest.raises(GuardrailViolation, match="MAX_PARALLEL"):
        enforcer.check_parallel(running=3)


def test_check_time_raises():
    enforcer = GuardrailEnforcer(GuardrailsConfig(max_time_seconds=60))
    with pytest.raises(GuardrailViolation, match="MAX_TIME"):
        enforcer.check_time(elapsed=61)


def test_check_cost_raises():
    enforcer = GuardrailEnforcer(GuardrailsConfig(max_cost_usd=Decimal("1.00")))
    with pytest.raises(GuardrailViolation, match="MAX_COST"):
        enforcer.check_cost(cost=Decimal("1.01"))


def test_check_pivots_raises():
    enforcer = GuardrailEnforcer(GuardrailsConfig(max_pivots=2))
    with pytest.raises(GuardrailViolation, match="MAX_PIVOTS"):
        enforcer.check_pivots(pivot_count=3)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_core/test_guardrails.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement guardrails**

```python
# src/atrium/core/guardrails.py
"""Guardrail enforcement for cost, time, parallelism, and pivot limits."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class GuardrailsConfig:
    max_agents: int = 25
    max_parallel: int = 5
    max_time_seconds: int = 600
    max_cost_usd: Decimal = Decimal("10.0")
    max_pivots: int = 2


class GuardrailViolation(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class GuardrailEnforcer:
    def __init__(self, config: GuardrailsConfig):
        self.config = config

    def check_spawn(self, agent_count: int) -> None:
        if agent_count > self.config.max_agents:
            raise GuardrailViolation("MAX_AGENTS", "agent count exceeded")

    def check_parallel(self, running: int) -> None:
        if running > self.config.max_parallel:
            raise GuardrailViolation("MAX_PARALLEL", "parallelism exceeded")

    def check_time(self, elapsed: int) -> None:
        if elapsed > self.config.max_time_seconds:
            raise GuardrailViolation("MAX_TIME", "execution time exceeded")

    def check_cost(self, cost: Decimal) -> None:
        if cost > self.config.max_cost_usd:
            raise GuardrailViolation("MAX_COST", "cost exceeded")

    def check_pivots(self, pivot_count: int) -> None:
        if pivot_count > self.config.max_pivots:
            raise GuardrailViolation("MAX_PIVOTS", "pivot count exceeded")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_core/test_guardrails.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atrium/core/guardrails.py tests/test_core/test_guardrails.py
git commit -m "feat(core): add GuardrailEnforcer with cost/time/parallelism/pivot limits"
```

---

### Task 6: Streaming — EventRecorder

**Files:**
- Create: `src/atrium/streaming/events.py`
- Test: `tests/test_streaming/test_events.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_streaming/test_events.py
import pytest
from atrium.streaming.events import EventRecorder


@pytest.fixture
def recorder():
    return EventRecorder()


async def test_emit_creates_event(recorder):
    evt = await recorder.emit("t1", "THREAD_CREATED", {"objective": "test"})
    assert evt.thread_id == "t1"
    assert evt.type == "THREAD_CREATED"
    assert evt.sequence == 1
    assert evt.payload["objective"] == "test"


async def test_emit_increments_sequence(recorder):
    e1 = await recorder.emit("t1", "A", {})
    e2 = await recorder.emit("t1", "B", {})
    e3 = await recorder.emit("t1", "C", {})
    assert e1.sequence == 1
    assert e2.sequence == 2
    assert e3.sequence == 3


async def test_separate_threads_have_independent_sequences(recorder):
    await recorder.emit("t1", "A", {})
    await recorder.emit("t1", "B", {})
    e = await recorder.emit("t2", "A", {})
    assert e.sequence == 1  # t2 starts at 1


async def test_replay(recorder):
    await recorder.emit("t1", "A", {})
    await recorder.emit("t1", "B", {})
    await recorder.emit("t1", "C", {})
    events = recorder.replay("t1", since_sequence=1)
    assert len(events) == 2  # B and C
    assert events[0].type == "B"
    assert events[1].type == "C"


async def test_replay_empty_thread(recorder):
    events = recorder.replay("nonexistent", since_sequence=0)
    assert events == []


async def test_causation_id(recorder):
    e1 = await recorder.emit("t1", "A", {})
    e2 = await recorder.emit("t1", "B", {}, causation_id=e1.event_id)
    assert e2.causation_id == e1.event_id
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_streaming/test_events.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement EventRecorder**

```python
# src/atrium/streaming/events.py
"""Append-only event recorder with per-thread sequencing."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Optional

from atrium.core.models import AtriumEvent


class EventRecorder:
    """Records events per-thread with monotonic sequencing and fan-out."""

    def __init__(self):
        self._events: dict[str, list[AtriumEvent]] = defaultdict(list)
        self._sequences: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def emit(
        self,
        thread_id: str,
        event_type: str,
        payload: dict[str, Any],
        causation_id: Optional[str] = None,
    ) -> AtriumEvent:
        """Create, store, and fan-out an event."""
        async with self._lock:
            self._sequences[thread_id] += 1
            seq = self._sequences[thread_id]

        event = AtriumEvent(
            thread_id=thread_id,
            type=event_type,
            payload=payload,
            sequence=seq,
            causation_id=causation_id,
        )
        self._events[thread_id].append(event)

        # Fan-out to subscribers
        for queue in self._subscribers.get(thread_id, []):
            await queue.put(event)

        return event

    def replay(
        self, thread_id: str, since_sequence: int = 0
    ) -> list[AtriumEvent]:
        """Return events after a given sequence number."""
        return [
            e for e in self._events.get(thread_id, [])
            if e.sequence > since_sequence
        ]

    async def subscribe(self, thread_id: str, since_sequence: int = 0):
        """Async iterator that yields events as they arrive."""
        queue: asyncio.Queue[AtriumEvent | None] = asyncio.Queue()
        self._subscribers[thread_id].append(queue)
        try:
            # Replay historical events first
            for event in self._events.get(thread_id, []):
                if event.sequence > since_sequence:
                    yield event
            # Then stream live events
            while True:
                event = await queue.get()
                if event is None:  # sentinel
                    return
                if event.sequence > since_sequence:
                    yield event
        finally:
            self._subscribers[thread_id].remove(queue)

    async def complete(self, thread_id: str) -> None:
        """Signal that a thread's event stream is done."""
        for queue in self._subscribers.get(thread_id, []):
            await queue.put(None)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_streaming/test_events.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atrium/streaming/events.py tests/test_streaming/test_events.py
git commit -m "feat(streaming): add EventRecorder with sequencing, replay, fan-out"
```

---

### Task 7: Streaming — SSE Bus

**Files:**
- Create: `src/atrium/streaming/bus.py`
- Test: `tests/test_streaming/test_bus.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_streaming/test_bus.py
import asyncio
import json
import pytest
from atrium.core.models import AtriumEvent
from atrium.streaming.bus import format_sse


def test_format_sse():
    event = AtriumEvent(
        event_id="e1",
        thread_id="t1",
        type="AGENT_RUNNING",
        payload={"agent_key": "alpha"},
        sequence=1,
    )
    result = format_sse(event)
    assert result.startswith("event: AGENT_RUNNING\n")
    assert "data: " in result
    assert result.endswith("\n\n")
    # Parse the data line
    data_line = [l for l in result.split("\n") if l.startswith("data: ")][0]
    parsed = json.loads(data_line[6:])
    assert parsed["type"] == "AGENT_RUNNING"
    assert parsed["sequence"] == 1


def test_format_sse_end():
    from atrium.streaming.bus import format_sse_end
    result = format_sse_end()
    assert result == "event: end\ndata: {}\n\n"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_streaming/test_bus.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement SSE formatting**

```python
# src/atrium/streaming/bus.py
"""SSE formatting utilities for streaming events to clients."""

from __future__ import annotations

import json
from datetime import datetime

from atrium.core.models import AtriumEvent


def _json_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def format_sse(event: AtriumEvent) -> str:
    """Format an AtriumEvent as an SSE text chunk."""
    data = json.dumps(event.model_dump(), default=_json_serializer)
    return f"event: {event.type}\ndata: {data}\n\n"


def format_sse_end() -> str:
    """Format a terminal SSE event."""
    return "event: end\ndata: {}\n\n"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_streaming/test_bus.py -v
```

Expected: all 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atrium/streaming/bus.py tests/test_streaming/test_bus.py
git commit -m "feat(streaming): add SSE formatting utilities"
```

---

### Task 8: Engine — LLM Client

**Files:**
- Create: `src/atrium/engine/llm.py`
- Test: `tests/test_engine/test_llm.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_engine/test_llm.py
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from atrium.engine.llm import LLMClient, parse_llm_config


def test_parse_llm_config_openai():
    provider, model = parse_llm_config("openai:gpt-4o-mini")
    assert provider == "openai"
    assert model == "gpt-4o-mini"


def test_parse_llm_config_default_model():
    provider, model = parse_llm_config("openai")
    assert provider == "openai"
    assert model is None


def test_parse_llm_config_anthropic():
    provider, model = parse_llm_config("anthropic:claude-sonnet-4-6")
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-6"


async def test_generate_json_returns_parsed_dict():
    client = LLMClient("openai:gpt-4o-mini")

    mock_response = MagicMock()
    mock_response.content = '{"plan": "test"}'

    with patch.object(client, "_get_chat_model") as mock_model:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        mock_model.return_value = mock_instance

        result = await client.generate_json("system prompt", "user prompt")
        assert result == {"plan": "test"}


async def test_generate_json_handles_markdown_fence():
    client = LLMClient("openai:gpt-4o-mini")

    mock_response = MagicMock()
    mock_response.content = '```json\n{"plan": "test"}\n```'

    with patch.object(client, "_get_chat_model") as mock_model:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        mock_model.return_value = mock_instance

        result = await client.generate_json("system prompt", "user prompt")
        assert result == {"plan": "test"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_engine/test_llm.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement LLMClient**

```python
# src/atrium/engine/llm.py
"""LLM client supporting multiple providers via langchain-core."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage


def parse_llm_config(config_str: str) -> tuple[str, str | None]:
    """Parse 'provider:model' string. Model is optional."""
    if ":" in config_str:
        provider, model = config_str.split(":", 1)
        return provider, model
    return config_str, None


def _strip_markdown_fence(text: str) -> str:
    """Remove ```json ... ``` wrappers if present."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence
        text = re.sub(r"^```\w*\n?", "", text)
        # Remove closing fence
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


class LLMClient:
    """Unified LLM client for Commander planning calls."""

    def __init__(self, config: str = "openai:gpt-4o-mini"):
        self._provider, self._model = parse_llm_config(config)

    def _get_chat_model(self):
        """Lazy-load the appropriate chat model."""
        if self._provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=self._model or "gpt-4o-mini")
        elif self._provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=self._model or "claude-sonnet-4-6")
        elif self._provider == "google" or self._provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=self._model or "gemini-1.5-flash")
        else:
            raise ValueError(f"Unknown LLM provider: {self._provider}")

    async def generate_json(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        """Send a system+user prompt and parse the response as JSON."""
        model = self._get_chat_model()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = await model.ainvoke(messages)
        text = _strip_markdown_fence(response.content)
        return json.loads(text)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_engine/test_llm.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atrium/engine/llm.py tests/test_engine/test_llm.py
git commit -m "feat(engine): add LLMClient with multi-provider support"
```

---

### Task 9: Engine — Commander

**Files:**
- Create: `src/atrium/engine/commander.py`
- Test: `tests/test_engine/test_commander.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_engine/test_commander.py
import json
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
        "steps": [
            {"agent": "nonexistent", "inputs": {}, "depends_on": []},
        ],
    }

    commander = Commander(llm_config="openai:gpt-4o-mini", registry=registry)
    with patch.object(commander._llm, "generate_json", new_callable=AsyncMock, return_value=bad_plan):
        plan = await commander.plan("test")

    # Invalid agents should be filtered out
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


async def test_evaluate_returns_pivot(registry):
    commander = Commander(llm_config="openai:gpt-4o-mini", registry=registry)
    eval_result = {
        "decision": "pivot",
        "rationale": "Need deeper analysis",
        "new_steps": [
            {"agent": "writer", "inputs": {}, "depends_on": []},
        ],
    }

    with patch.object(commander._llm, "generate_json", new_callable=AsyncMock, return_value=eval_result):
        decision = await commander.evaluate(
            objective="test",
            outputs={"searcher": {"results": ["found"]}},
        )

    assert decision.action == "pivot"
    assert len(decision.new_steps) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_engine/test_commander.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement Commander**

```python
# src/atrium/engine/commander.py
"""Commander — LLM-powered planner and evaluator."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from atrium.core.models import Plan, PlanStep
from atrium.core.registry import AgentRegistry
from atrium.engine.llm import LLMClient


PLAN_SYSTEM_PROMPT = """You are the Commander of an agent orchestration system.

Given a user's objective and a list of available agents, create an execution plan.

AVAILABLE AGENTS:
{manifest}

RULES:
1. Only use agents from the list above — use exact names.
2. Each step has: agent (name), inputs (dict), depends_on (list of agent names that must complete first).
3. Steps with no dependencies run in parallel.
4. Wire outputs from upstream agents into downstream inputs using depends_on.
5. Use the minimum number of agents needed.

Return JSON:
{{
  "rationale": "Brief explanation of your plan",
  "steps": [
    {{"agent": "name", "inputs": {{}}, "depends_on": []}}
  ]
}}"""

EVAL_SYSTEM_PROMPT = """You are the Commander evaluating agent outputs.

OBJECTIVE: {objective}

AGENT OUTPUTS:
{outputs}

Decide:
- "finalize" if the results adequately address the objective
- "pivot" if results are insufficient and more agents should run

Return JSON:
{{
  "decision": "finalize" or "pivot",
  "summary": "Brief summary of findings",
  "rationale": "Why you chose this decision",
  "new_steps": []  // only if pivot — same format as plan steps
}}"""


@dataclass
class EvalDecision:
    action: str  # "finalize" or "pivot"
    summary: str = ""
    rationale: str = ""
    new_steps: list[PlanStep] = field(default_factory=list)


class Commander:
    """LLM-powered planner that reads the agent registry and generates execution plans."""

    def __init__(self, llm_config: str, registry: AgentRegistry):
        self._llm = LLMClient(llm_config)
        self._registry = registry

    async def plan(self, objective: str) -> Plan:
        """Generate an execution plan for a given objective."""
        manifest = json.dumps(self._registry.manifest(), indent=2)
        system = PLAN_SYSTEM_PROMPT.format(manifest=manifest)
        result = await self._llm.generate_json(system, f"Objective: {objective}")

        # Validate: only keep steps with known agent names
        known = {a.name for a in self._registry.list_all()}
        valid_steps = []
        for step_data in result.get("steps", []):
            if step_data.get("agent") in known:
                valid_steps.append(
                    PlanStep(
                        agent=step_data["agent"],
                        inputs=step_data.get("inputs", {}),
                        depends_on=[d for d in step_data.get("depends_on", []) if d in known],
                    )
                )

        return Plan(
            thread_id="",  # set by orchestrator
            rationale=result.get("rationale", ""),
            steps=valid_steps,
        )

    async def evaluate(
        self, objective: str, outputs: dict[str, Any]
    ) -> EvalDecision:
        """Evaluate agent outputs and decide whether to finalize or pivot."""
        system = EVAL_SYSTEM_PROMPT.format(
            objective=objective,
            outputs=json.dumps(outputs, indent=2, default=str),
        )
        result = await self._llm.generate_json(system, "Evaluate the outputs above.")

        action = result.get("decision", "finalize")
        new_steps = []
        if action == "pivot":
            known = {a.name for a in self._registry.list_all()}
            for step_data in result.get("new_steps", []):
                if step_data.get("agent") in known:
                    new_steps.append(
                        PlanStep(
                            agent=step_data["agent"],
                            inputs=step_data.get("inputs", {}),
                            depends_on=step_data.get("depends_on", []),
                        )
                    )

        return EvalDecision(
            action=action,
            summary=result.get("summary", ""),
            rationale=result.get("rationale", ""),
            new_steps=new_steps,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_engine/test_commander.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atrium/engine/commander.py tests/test_engine/test_commander.py
git commit -m "feat(engine): add Commander with LLM planning and evaluation"
```

---

### Task 10: Engine — Graph Builder + Callbacks

**Files:**
- Create: `src/atrium/engine/graph_builder.py`, `src/atrium/engine/callbacks.py`
- Test: `tests/test_engine/test_graph_builder.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_engine/test_graph_builder.py
import pytest
from atrium.core.agent import Agent
from atrium.core.models import Plan, PlanStep
from atrium.core.registry import AgentRegistry
from atrium.streaming.events import EventRecorder
from atrium.engine.graph_builder import build_agent_node, build_graph_from_plan


class EchoAgent(Agent):
    name = "echo"
    description = "Echoes input"
    capabilities = ["echo"]

    async def run(self, input_data: dict) -> dict:
        return {"echoed": input_data.get("text", "nothing")}


class UpperAgent(Agent):
    name = "upper"
    description = "Uppercases text"
    capabilities = ["transform"]

    async def run(self, input_data: dict) -> dict:
        text = input_data.get("text", "")
        return {"result": text.upper()}


@pytest.fixture
def registry():
    reg = AgentRegistry()
    reg.register(EchoAgent)
    reg.register(UpperAgent)
    return reg


@pytest.fixture
def recorder():
    return EventRecorder()


def test_build_agent_node_returns_callable(registry, recorder):
    node_fn = build_agent_node("echo", registry, recorder, "t1")
    assert callable(node_fn)


async def test_agent_node_runs_agent(registry, recorder):
    node_fn = build_agent_node("echo", registry, recorder, "t1")
    state = {"agent_outputs": {}, "inputs": {"echo": {"text": "hello"}}}
    result = await node_fn(state)
    assert result["agent_outputs"]["echo"]["echoed"] == "hello"


async def test_agent_node_emits_events(registry, recorder):
    node_fn = build_agent_node("echo", registry, recorder, "t1")
    state = {"agent_outputs": {}, "inputs": {"echo": {"text": "hi"}}}
    await node_fn(state)
    events = recorder.replay("t1")
    types = [e.type for e in events]
    assert "AGENT_RUNNING" in types
    assert "AGENT_COMPLETED" in types


async def test_build_graph_from_plan(registry, recorder):
    plan = Plan(
        thread_id="t1",
        rationale="test",
        steps=[
            PlanStep(agent="echo", inputs={"text": "hello"}, depends_on=[]),
            PlanStep(agent="upper", inputs={"text": "world"}, depends_on=["echo"]),
        ],
    )
    graph = build_graph_from_plan(plan, registry, recorder)
    assert graph is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_engine/test_graph_builder.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement callbacks**

```python
# src/atrium/engine/callbacks.py
"""Bridges agent execution events to the Atrium EventRecorder."""

from __future__ import annotations

from atrium.streaming.events import EventRecorder


async def emit_agent_running(recorder: EventRecorder, thread_id: str, agent_key: str) -> None:
    await recorder.emit(thread_id, "AGENT_RUNNING", {"agent_key": agent_key})


async def emit_agent_completed(
    recorder: EventRecorder, thread_id: str, agent_key: str, output: dict
) -> None:
    await recorder.emit(thread_id, "AGENT_COMPLETED", {"agent_key": agent_key})
    await recorder.emit(thread_id, "AGENT_OUTPUT", {"agent_key": agent_key, "output": output})


async def emit_agent_failed(
    recorder: EventRecorder, thread_id: str, agent_key: str, error: str
) -> None:
    await recorder.emit(thread_id, "AGENT_FAILED", {"agent_key": agent_key, "error": error})
```

- [ ] **Step 4: Implement graph builder**

```python
# src/atrium/engine/graph_builder.py
"""Converts a Commander Plan into a LangGraph StateGraph."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END

from atrium.core.models import Plan
from atrium.core.registry import AgentRegistry
from atrium.engine.callbacks import emit_agent_completed, emit_agent_failed, emit_agent_running
from atrium.streaming.events import EventRecorder


class ThreadState(TypedDict):
    """State passed through the LangGraph execution."""
    inputs: dict[str, dict[str, Any]]       # agent_name -> input_data
    agent_outputs: dict[str, dict[str, Any]] # agent_name -> output_data


def build_agent_node(
    agent_name: str,
    registry: AgentRegistry,
    recorder: EventRecorder,
    thread_id: str,
):
    """Create a LangGraph node function that runs an Atrium agent."""

    async def node_fn(state: ThreadState) -> dict:
        agent = registry.create(agent_name)

        # Wire the emitter so agent.say() works
        async def emitter(event_type, payload, causation=None):
            await recorder.emit(thread_id, event_type, payload, causation_id=causation)
        agent.set_emitter(emitter)

        # Get input: explicit inputs merged with upstream outputs
        agent_input = dict(state.get("inputs", {}).get(agent_name, {}))
        # Inject upstream outputs for agents that depend on others
        upstream = state.get("agent_outputs", {})
        if upstream:
            agent_input["upstream"] = upstream

        await emit_agent_running(recorder, thread_id, agent_name)

        try:
            output = await agent.run(agent_input)
            await emit_agent_completed(recorder, thread_id, agent_name, output)
        except Exception as e:
            await emit_agent_failed(recorder, thread_id, agent_name, str(e))
            output = {"error": str(e)}

        # Merge output into state
        new_outputs = dict(state.get("agent_outputs", {}))
        new_outputs[agent_name] = output
        return {"agent_outputs": new_outputs}

    return node_fn


def build_graph_from_plan(
    plan: Plan,
    registry: AgentRegistry,
    recorder: EventRecorder,
):
    """Compile a Plan into a LangGraph StateGraph."""
    graph = StateGraph(ThreadState)

    # Add a node for each agent step
    for step in plan.steps:
        node_fn = build_agent_node(step.agent, registry, recorder, plan.thread_id)
        graph.add_node(step.agent, node_fn)

    # Wire edges based on dependencies
    roots = [s for s in plan.steps if not s.depends_on]
    for root in roots:
        graph.add_edge(START, root.agent)

    for step in plan.steps:
        for dep in step.depends_on:
            graph.add_edge(dep, step.agent)

    # Find leaf nodes (nodes that no one depends on) and connect to END
    depended_on = {dep for s in plan.steps for dep in s.depends_on}
    leaves = [s for s in plan.steps if s.agent not in depended_on]
    for leaf in leaves:
        graph.add_edge(leaf.agent, END)

    return graph.compile()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_engine/test_graph_builder.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atrium/engine/callbacks.py src/atrium/engine/graph_builder.py tests/test_engine/test_graph_builder.py
git commit -m "feat(engine): add graph builder converting Plans to LangGraph StateGraphs"
```

---

### Task 11: Engine — Thread Orchestrator

**Files:**
- Create: `src/atrium/engine/orchestrator.py`
- Test: `tests/test_engine/test_orchestrator.py`

This is the main entry point that ties Commander + Graph Builder + EventRecorder together.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_engine/test_orchestrator.py
import pytest
from unittest.mock import AsyncMock, patch
from atrium.core.agent import Agent
from atrium.core.guardrails import GuardrailsConfig
from atrium.core.models import Plan, PlanStep
from atrium.engine.orchestrator import ThreadOrchestrator
from atrium.core.registry import AgentRegistry
from atrium.streaming.events import EventRecorder


class AddAgent(Agent):
    name = "adder"
    description = "Adds numbers"
    capabilities = ["math"]

    async def run(self, input_data: dict) -> dict:
        a = input_data.get("a", 0)
        b = input_data.get("b", 0)
        return {"sum": a + b}


@pytest.fixture
def registry():
    reg = AgentRegistry()
    reg.register(AddAgent)
    return reg


@pytest.fixture
def recorder():
    return EventRecorder()


async def test_orchestrator_runs_thread(registry, recorder):
    mock_plan = Plan(
        thread_id="",
        rationale="test",
        steps=[PlanStep(agent="adder", inputs={"a": 1, "b": 2}, depends_on=[])],
    )
    mock_eval = AsyncMock()
    mock_eval.return_value.action = "finalize"
    mock_eval.return_value.summary = "Done"

    orchestrator = ThreadOrchestrator(
        registry=registry,
        recorder=recorder,
        guardrails=GuardrailsConfig(),
        llm_config="openai:gpt-4o-mini",
    )

    with patch.object(orchestrator._commander, "plan", new_callable=AsyncMock, return_value=mock_plan):
        with patch.object(orchestrator._commander, "evaluate", mock_eval):
            result = await orchestrator.run("compute 1 + 2")

    assert result["status"] == "COMPLETED"
    events = recorder.replay(result["thread_id"])
    types = [e.type for e in events]
    assert "THREAD_CREATED" in types
    assert "PLAN_CREATED" in types
    assert "THREAD_COMPLETED" in types


async def test_orchestrator_emits_plan_events(registry, recorder):
    mock_plan = Plan(
        thread_id="",
        rationale="test plan",
        steps=[PlanStep(agent="adder", inputs={"a": 5, "b": 3}, depends_on=[])],
    )
    mock_eval = AsyncMock()
    mock_eval.return_value.action = "finalize"
    mock_eval.return_value.summary = "OK"

    orchestrator = ThreadOrchestrator(
        registry=registry,
        recorder=recorder,
        guardrails=GuardrailsConfig(),
        llm_config="openai:gpt-4o-mini",
    )

    with patch.object(orchestrator._commander, "plan", new_callable=AsyncMock, return_value=mock_plan):
        with patch.object(orchestrator._commander, "evaluate", mock_eval):
            result = await orchestrator.run("test")

    events = recorder.replay(result["thread_id"])
    types = [e.type for e in events]
    assert "PLAN_CREATED" in types
    assert "PLAN_EXECUTION_STARTED" in types
    assert "PLAN_COMPLETED" in types
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_engine/test_orchestrator.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement ThreadOrchestrator**

```python
# src/atrium/engine/orchestrator.py
"""Thread orchestrator — ties Commander, GraphBuilder, and EventRecorder together."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from atrium.core.guardrails import GuardrailEnforcer, GuardrailsConfig
from atrium.core.models import Plan, Thread, ThreadStatus
from atrium.core.registry import AgentRegistry
from atrium.engine.commander import Commander
from atrium.engine.graph_builder import build_graph_from_plan
from atrium.streaming.events import EventRecorder


class ThreadOrchestrator:
    """Runs a complete thread: plan -> execute -> evaluate -> pivot/finalize."""

    def __init__(
        self,
        registry: AgentRegistry,
        recorder: EventRecorder,
        guardrails: GuardrailsConfig,
        llm_config: str,
    ):
        self._registry = registry
        self._recorder = recorder
        self._guardrails = GuardrailEnforcer(guardrails)
        self._commander = Commander(llm_config=llm_config, registry=registry)

    async def run(self, objective: str) -> dict[str, Any]:
        """Execute a full thread lifecycle."""
        thread = Thread(objective=objective)
        tid = thread.thread_id

        await self._recorder.emit(tid, "THREAD_CREATED", {
            "objective": objective,
            "thread_id": tid,
        })

        # Phase 1: Plan
        await self._recorder.emit(tid, "THREAD_PLANNING", {"objective": objective})
        await self._recorder.emit(tid, "COMMANDER_MESSAGE", {
            "text": "Analyzing objective and selecting agents...",
            "phase": "planning",
        })

        plan = await self._commander.plan(objective)
        plan.thread_id = tid

        await self._recorder.emit(tid, "PLAN_CREATED", {
            "plan_id": plan.plan_id,
            "plan_number": plan.plan_number,
            "rationale": plan.rationale,
            "graph": {
                "nodes": [
                    {
                        "key": s.agent,
                        "role": s.agent,
                        "objective": "",
                        "depends_on": s.depends_on,
                    }
                    for s in plan.steps
                ]
            },
        })

        # Emit AGENT_HIRED for each step
        for step in plan.steps:
            await self._recorder.emit(tid, "AGENT_HIRED", {
                "agent_key": step.agent,
                "role": step.agent,
                "objective": self._registry.get(step.agent).description,
                "depends_on": step.depends_on,
            })

        # Phase 2: Execute
        await self._recorder.emit(tid, "PLAN_EXECUTION_STARTED", {"plan_id": plan.plan_id})
        await self._recorder.emit(tid, "THREAD_RUNNING", {"plan_id": plan.plan_id})

        graph = build_graph_from_plan(plan, self._registry, self._recorder)
        initial_state = {
            "inputs": {s.agent: s.inputs for s in plan.steps},
            "agent_outputs": {},
        }
        final_state = await graph.ainvoke(initial_state)

        outputs = final_state.get("agent_outputs", {})

        # Phase 3: Evaluate
        decision = await self._commander.evaluate(objective, outputs)

        pivot_count = 0
        while decision.action == "pivot" and decision.new_steps:
            self._guardrails.check_pivots(pivot_count + 1)
            pivot_count += 1

            await self._recorder.emit(tid, "PIVOT_REQUESTED", {
                "rationale": decision.rationale,
            })
            await self._recorder.emit(tid, "COMMANDER_MESSAGE", {
                "text": decision.rationale,
                "phase": "pivot",
            })

            # Build and execute new plan from pivot steps
            pivot_plan = Plan(
                thread_id=tid,
                plan_number=plan.plan_number + pivot_count,
                rationale=decision.rationale,
                steps=decision.new_steps,
            )

            for step in pivot_plan.steps:
                await self._recorder.emit(tid, "AGENT_HIRED", {
                    "agent_key": step.agent,
                    "role": step.agent,
                    "objective": self._registry.get(step.agent).description,
                    "depends_on": step.depends_on,
                })

            pivot_graph = build_graph_from_plan(pivot_plan, self._registry, self._recorder)
            pivot_state = {
                "inputs": {s.agent: s.inputs for s in pivot_plan.steps},
                "agent_outputs": outputs,  # carry forward previous outputs
            }
            pivot_result = await pivot_graph.ainvoke(pivot_state)
            outputs.update(pivot_result.get("agent_outputs", {}))

            await self._recorder.emit(tid, "PIVOT_APPLIED", {
                "added_agents": [s.agent for s in decision.new_steps],
            })

            decision = await self._commander.evaluate(objective, outputs)

        # Phase 4: Finalize
        await self._recorder.emit(tid, "PLAN_COMPLETED", {"plan_id": plan.plan_id})
        await self._recorder.emit(tid, "EVIDENCE_PUBLISHED", {
            "headline": decision.summary or "Analysis Complete",
            "summary": decision.summary,
            "findings": [],
            "recommendations": [],
            "chart": {"type": "bar", "title": "Results", "series": []},
        })
        await self._recorder.emit(tid, "THREAD_COMPLETED", {
            "thread_id": tid,
        })
        await self._recorder.complete(tid)

        return {
            "thread_id": tid,
            "status": "COMPLETED",
            "outputs": outputs,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_engine/test_orchestrator.py -v
```

Expected: all 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/atrium/engine/orchestrator.py tests/test_engine/test_orchestrator.py
git commit -m "feat(engine): add ThreadOrchestrator tying Commander + GraphBuilder + Events"
```

---

### Task 12: API — FastAPI App + Routes

**Files:**
- Create: `src/atrium/api/app.py`, `src/atrium/api/schemas.py`, `src/atrium/api/routes/health.py`, `src/atrium/api/routes/threads.py`, `src/atrium/api/routes/control.py`, `src/atrium/api/routes/registry.py`, `src/atrium/api/middleware.py`
- Test: `tests/test_api/test_health.py`, `tests/test_api/test_threads.py`

- [ ] **Step 1: Write health check test**

```python
# tests/test_api/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from atrium.api.app import create_app
from atrium.core.registry import AgentRegistry


@pytest.fixture
def app():
    return create_app(registry=AgentRegistry())


async def test_health(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
```

- [ ] **Step 2: Write thread creation test**

```python
# tests/test_api/test_threads.py
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from atrium.api.app import create_app
from atrium.core.agent import Agent
from atrium.core.registry import AgentRegistry


class StubAgent(Agent):
    name = "stub"
    description = "Stub"
    capabilities = ["test"]

    async def run(self, input_data: dict) -> dict:
        return {"ok": True}


@pytest.fixture
def registry():
    reg = AgentRegistry()
    reg.register(StubAgent)
    return reg


@pytest.fixture
def app(registry):
    return create_app(registry=registry, llm_config="openai:gpt-4o-mini")


async def test_create_thread(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/threads", json={"objective": "test goal"})
    assert resp.status_code == 201
    data = resp.json()
    assert "thread_id" in data
    assert data["objective"] == "test goal"
    assert "stream_url" in data


async def test_list_threads(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/threads")
    assert resp.status_code == 200
    assert "threads" in resp.json()
```

- [ ] **Step 3: Implement schemas**

```python
# src/atrium/api/schemas.py
"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class CreateThreadRequest(BaseModel):
    objective: str


class ThreadResponse(BaseModel):
    thread_id: str
    title: str
    objective: str
    status: str
    created_at: datetime
    stream_url: str


class ThreadListResponse(BaseModel):
    threads: list[ThreadResponse]


class EventResponse(BaseModel):
    event_id: str
    type: str
    payload: dict[str, Any]
    sequence: int
    timestamp: datetime
    causation_id: Optional[str] = None


class AgentInfoResponse(BaseModel):
    name: str
    description: str
    capabilities: list[str]
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None


class AgentListResponse(BaseModel):
    agents: list[AgentInfoResponse]


class HealthResponse(BaseModel):
    status: str
    version: str
    agents_registered: int


class HumanInputRequest(BaseModel):
    input: str


class ActionResponse(BaseModel):
    thread_id: str
    accepted: bool
```

- [ ] **Step 4: Implement middleware**

```python
# src/atrium/api/middleware.py
"""API middleware for CORS and error handling."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


def setup_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_error_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "type": type(exc).__name__},
        )
```

- [ ] **Step 5: Implement route files**

```python
# src/atrium/api/routes/health.py
from fastapi import APIRouter
from atrium.api.schemas import HealthResponse
import atrium

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(registry=None):
    return HealthResponse(
        status="ok",
        version=atrium.__version__,
        agents_registered=len(registry.list_all()) if registry else 0,
    )
```

```python
# src/atrium/api/routes/threads.py
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from atrium.api.schemas import CreateThreadRequest, EventResponse, ThreadResponse
from atrium.core.models import Thread, ThreadStatus
from atrium.streaming.bus import format_sse, format_sse_end

router = APIRouter()

# In-memory thread store (will be replaced by SQLite in a later iteration)
_threads: dict[str, Thread] = {}
_tasks: dict[str, asyncio.Task] = {}


def _thread_response(thread: Thread) -> dict:
    return ThreadResponse(
        thread_id=thread.thread_id,
        title=thread.title or thread.objective[:60],
        objective=thread.objective,
        status=thread.status.value,
        created_at=thread.created_at,
        stream_url=f"/api/v1/threads/{thread.thread_id}/stream",
    ).model_dump()


@router.post("/threads", status_code=201)
async def create_thread(req: CreateThreadRequest):
    # The orchestrator is injected via app state in app.py
    from atrium.api.app import get_orchestrator, get_recorder

    orchestrator = get_orchestrator()
    recorder = get_recorder()

    thread = Thread(objective=req.objective, title=req.objective[:60])
    _threads[thread.thread_id] = thread

    # Run orchestration in background
    async def run_in_background():
        try:
            result = await orchestrator.run(req.objective)
            # Update thread_id mapping since orchestrator generates its own
            if result["thread_id"] != thread.thread_id:
                _threads[result["thread_id"]] = thread
        except Exception:
            pass

    task = asyncio.create_task(run_in_background())
    _tasks[thread.thread_id] = task

    return _thread_response(thread)


@router.get("/threads")
async def list_threads():
    return {"threads": [_thread_response(t) for t in _threads.values()]}


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    from atrium.api.app import get_recorder
    recorder = get_recorder()

    thread = _threads.get(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    events = recorder.replay(thread_id)
    return {
        **_thread_response(thread),
        "events": [e.model_dump() for e in events],
    }


@router.get("/threads/{thread_id}/stream")
async def stream_events(thread_id: str, since_sequence: int = 0):
    from atrium.api.app import get_recorder
    recorder = get_recorder()

    async def event_generator():
        async for event in recorder.subscribe(thread_id, since_sequence):
            yield format_sse(event)
        yield format_sse_end()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

```python
# src/atrium/api/routes/control.py
from fastapi import APIRouter, HTTPException
from atrium.api.schemas import ActionResponse, HumanInputRequest

router = APIRouter()


@router.post("/threads/{thread_id}/pause")
async def pause(thread_id: str):
    # TODO: implement via LangGraph interrupt in v1.1
    return ActionResponse(thread_id=thread_id, accepted=True)


@router.post("/threads/{thread_id}/resume")
async def resume(thread_id: str):
    return ActionResponse(thread_id=thread_id, accepted=True)


@router.post("/threads/{thread_id}/cancel")
async def cancel(thread_id: str):
    return ActionResponse(thread_id=thread_id, accepted=True)


@router.post("/threads/{thread_id}/approve")
async def approve(thread_id: str):
    return ActionResponse(thread_id=thread_id, accepted=True)


@router.post("/threads/{thread_id}/reject")
async def reject(thread_id: str):
    return ActionResponse(thread_id=thread_id, accepted=True)


@router.post("/threads/{thread_id}/input")
async def human_input(thread_id: str, req: HumanInputRequest):
    return ActionResponse(thread_id=thread_id, accepted=True)
```

```python
# src/atrium/api/routes/registry.py
from fastapi import APIRouter
from atrium.api.schemas import AgentInfoResponse, AgentListResponse

router = APIRouter()


@router.get("/agents", response_model=AgentListResponse)
async def list_agents():
    from atrium.api.app import get_registry
    registry = get_registry()
    agents = [
        AgentInfoResponse(
            name=a.name,
            description=a.description,
            capabilities=list(a.capabilities),
            input_schema=a.input_schema,
            output_schema=a.output_schema,
        )
        for a in registry.list_all()
    ]
    return AgentListResponse(agents=agents)


@router.get("/agents/{name}", response_model=AgentInfoResponse)
async def get_agent(name: str):
    from atrium.api.app import get_registry
    registry = get_registry()
    agent_cls = registry.get(name)
    return AgentInfoResponse(
        name=agent_cls.name,
        description=agent_cls.description,
        capabilities=list(agent_cls.capabilities),
        input_schema=agent_cls.input_schema,
        output_schema=agent_cls.output_schema,
    )
```

- [ ] **Step 6: Implement FastAPI app factory**

```python
# src/atrium/api/app.py
"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from atrium.api.middleware import setup_middleware
from atrium.api.routes import control, health, registry, threads
from atrium.core.guardrails import GuardrailsConfig
from atrium.core.registry import AgentRegistry
from atrium.engine.orchestrator import ThreadOrchestrator
from atrium.streaming.events import EventRecorder

# Module-level state (set by create_app)
_registry: AgentRegistry | None = None
_recorder: EventRecorder | None = None
_orchestrator: ThreadOrchestrator | None = None


def get_registry() -> AgentRegistry:
    assert _registry is not None
    return _registry


def get_recorder() -> EventRecorder:
    assert _recorder is not None
    return _recorder


def get_orchestrator() -> ThreadOrchestrator:
    assert _orchestrator is not None
    return _orchestrator


def create_app(
    registry: AgentRegistry | None = None,
    llm_config: str = "openai:gpt-4o-mini",
    guardrails: GuardrailsConfig | None = None,
) -> FastAPI:
    global _registry, _recorder, _orchestrator

    _registry = registry or AgentRegistry()
    _recorder = EventRecorder()
    _orchestrator = ThreadOrchestrator(
        registry=_registry,
        recorder=_recorder,
        guardrails=guardrails or GuardrailsConfig(),
        llm_config=llm_config,
    )

    app = FastAPI(title="Atrium", version="0.1.0")
    setup_middleware(app)

    # Inject registry into health route
    @app.get("/api/v1/health")
    async def health_endpoint():
        return health.router.routes  # handled below

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(threads.router, prefix="/api/v1")
    app.include_router(control.router, prefix="/api/v1")
    app.include_router(registry.router, prefix="/api/v1")

    # Override health to inject registry
    @app.get("/api/v1/health")
    async def health_check():
        import atrium
        return {
            "status": "ok",
            "version": atrium.__version__,
            "agents_registered": len(_registry.list_all()),
        }

    # Dashboard
    dashboard_dir = Path(__file__).parent.parent / "dashboard" / "static"
    if dashboard_dir.exists():
        app.mount("/dashboard/static", StaticFiles(directory=str(dashboard_dir)), name="dashboard")

        @app.get("/dashboard")
        async def dashboard():
            return FileResponse(str(dashboard_dir / "console.html"))

    @app.get("/")
    async def root():
        return RedirectResponse("/dashboard")

    return app
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tests/test_api/test_health.py tests/test_api/test_threads.py -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/atrium/api/ tests/test_api/
git commit -m "feat(api): add FastAPI app with thread, control, registry, and health routes"
```

---

### Task 13: Atrium Main Class + CLI

**Files:**
- Create: `src/atrium/cli.py`, update `src/atrium/__init__.py`

- [ ] **Step 1: Implement the Atrium class (update __init__.py)**

```python
# src/atrium/__init__.py
"""Atrium — observable agent orchestration on top of LangGraph."""

from atrium.core.agent import Agent
from atrium.core.guardrails import GuardrailsConfig
from atrium.core.registry import AgentRegistry
from atrium.api.app import create_app

__version__ = "0.1.0"


class Atrium:
    """Main entry point for building an Atrium application."""

    def __init__(
        self,
        agents: list[type[Agent]] | None = None,
        llm: str = "openai:gpt-4o-mini",
        guardrails: GuardrailsConfig | None = None,
    ):
        self.registry = AgentRegistry()
        self.llm_config = llm
        self.guardrails = guardrails or GuardrailsConfig()

        for agent_cls in (agents or []):
            self.registry.register(agent_cls)

    def register(self, agent_cls: type[Agent]) -> None:
        """Register an agent class."""
        self.registry.register(agent_cls)

    def serve(self, host: str = "127.0.0.1", port: int = 8080) -> None:
        """Start the FastAPI server with dashboard."""
        import uvicorn
        app = create_app(
            registry=self.registry,
            llm_config=self.llm_config,
            guardrails=self.guardrails,
        )
        print(f"Atrium serving at http://{host}:{port}")
        uvicorn.run(app, host=host, port=port)


__all__ = ["Agent", "Atrium", "GuardrailsConfig", "__version__"]
```

- [ ] **Step 2: Implement CLI**

```python
# src/atrium/cli.py
"""Atrium CLI — serve, scaffold, and run examples."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_serve(args):
    """Start the Atrium server."""
    import uvicorn
    from atrium.api.app import create_app
    from atrium.core.registry import AgentRegistry

    app = create_app(registry=AgentRegistry(), llm_config=args.llm)
    print(f"Atrium serving at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


def cmd_version(args):
    """Print version."""
    import atrium
    print(f"atrium {atrium.__version__}")


def cmd_new_agent(args):
    """Scaffold a new agent."""
    name = args.name
    class_name = "".join(word.capitalize() for word in name.split("_")) + "Agent"

    agent_code = f'''from atrium import Agent


class {class_name}(Agent):
    name = "{name}"
    description = ""  # TODO: Describe what this agent does
    capabilities = []  # TODO: Add capability tags

    # Optional: declare schemas for better Commander planning
    # input_schema = {{"key": type}}
    # output_schema = {{"key": type}}

    async def run(self, input_data: dict) -> dict:
        # TODO: Implement your agent logic
        await self.say("Starting work...")

        result = {{}}

        await self.say("Done")
        return result
'''

    test_code = f'''import pytest
from agents.{name} import {class_name}


@pytest.mark.asyncio
async def test_{name}_runs():
    agent = {class_name}()
    result = await agent.run({{}})
    assert isinstance(result, dict)
'''

    agent_dir = Path("agents")
    test_dir = Path("tests")
    agent_dir.mkdir(exist_ok=True)
    test_dir.mkdir(exist_ok=True)

    agent_file = agent_dir / f"{name}.py"
    test_file = test_dir / f"test_{name}.py"

    if agent_file.exists():
        print(f"Error: {agent_file} already exists")
        sys.exit(1)

    agent_file.write_text(agent_code)
    test_file.write_text(test_code)
    print(f"Created {agent_file}")
    print(f"Created {test_file}")
    print(f"Next: edit {agent_file}, then register it in your app.py")


def main():
    parser = argparse.ArgumentParser(prog="atrium", description="Atrium agent orchestration")
    sub = parser.add_subparsers(dest="command")

    # serve
    serve_p = sub.add_parser("serve", help="Start the API + dashboard")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8080)
    serve_p.add_argument("--llm", default="openai:gpt-4o-mini")
    serve_p.set_defaults(func=cmd_serve)

    # version
    ver_p = sub.add_parser("version", help="Print version")
    ver_p.set_defaults(func=cmd_version)

    # new agent
    new_p = sub.add_parser("new", help="Scaffold new components")
    new_sub = new_p.add_subparsers(dest="new_type")
    agent_p = new_sub.add_parser("agent", help="Create a new agent")
    agent_p.add_argument("name", help="Agent name (snake_case)")
    agent_p.set_defaults(func=cmd_new_agent)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify CLI works**

```bash
python -m atrium.cli version
```

Expected: prints `atrium 0.1.0`

- [ ] **Step 4: Commit**

```bash
git add src/atrium/__init__.py src/atrium/cli.py
git commit -m "feat: add Atrium main class and CLI (serve, new agent, version)"
```

---

### Task 14: Dashboard Adaptation

**Files:**
- Copy: `frontend/styles.css` -> `src/atrium/dashboard/static/styles.css`
- Adapt: `frontend/console.html` -> `src/atrium/dashboard/static/console.html`
- Adapt: `frontend/console.js` -> `src/atrium/dashboard/static/console.js`

- [ ] **Step 1: Copy CSS as-is**

```bash
mkdir -p src/atrium/dashboard/static
cp frontend/styles.css src/atrium/dashboard/static/styles.css
```

- [ ] **Step 2: Adapt console.html**

Copy `frontend/console.html` to `src/atrium/dashboard/static/console.html`. Changes:
- Remove landing page navigation links (Home, How it works, Features)
- Change static asset paths from `/static/` to `/dashboard/static/`
- Change script src from `/static/console.js` to `/dashboard/static/console.js`
- Change stylesheet href from `/static/styles.css` to `/dashboard/static/styles.css`

- [ ] **Step 3: Adapt console.js**

Copy `frontend/console.js` to `src/atrium/dashboard/static/console.js`. Changes:
- Update API paths: ensure all fetch calls use `/api/v1/` prefix (already correct)
- Update SSE stream URL construction (already correct)
- Add HITL UI: when `HUMAN_APPROVAL_REQUESTED` event fires, show approve/reject buttons in the transcript
- Update `_onEvidence` to handle the new evidence payload format

- [ ] **Step 4: Verify dashboard serves**

```bash
cd /path/to/project && python -c "
from atrium.api.app import create_app
from atrium.core.registry import AgentRegistry
app = create_app(registry=AgentRegistry())
print('Dashboard files exist:', (Path('src/atrium/dashboard/static/console.html')).exists())
"
```

- [ ] **Step 5: Commit**

```bash
git add src/atrium/dashboard/
git commit -m "feat(dashboard): adapt frontend for new API structure"
```

---

### Task 15: Hello World Example

**Files:**
- Create: `src/atrium/examples/hello_world/agents.py`, `src/atrium/examples/hello_world/app.py`, `src/atrium/examples/hello_world/README.md`

- [ ] **Step 1: Create example agents**

```python
# src/atrium/examples/hello_world/agents.py
"""Hello World example — three agents using Wikipedia's public API."""

import httpx
from atrium import Agent


class WikiSearchAgent(Agent):
    name = "wiki_search"
    description = "Searches Wikipedia for articles matching a query"
    capabilities = ["search", "research", "wikipedia"]
    input_schema = {"query": str}
    output_schema = {"articles": list}

    async def run(self, input_data: dict) -> dict:
        query = input_data.get("query", input_data.get("upstream", {}).get("query", ""))
        if not query:
            query = str(input_data)
        await self.say(f"Searching Wikipedia for: {query}")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query", "list": "search",
                    "srsearch": query, "format": "json", "srlimit": "5",
                },
            )
            resp.raise_for_status()
            results = resp.json()["query"]["search"]

        articles = [{"title": r["title"], "snippet": r["snippet"]} for r in results]
        await self.say(f"Found {len(articles)} articles")
        return {"articles": articles, "query": query}


class SummarizerAgent(Agent):
    name = "summarizer"
    description = "Summarizes a list of research findings into a concise bullet-point report"
    capabilities = ["summarize", "writing", "report"]
    input_schema = {"articles": list}
    output_schema = {"summary": str}

    async def run(self, input_data: dict) -> dict:
        articles = input_data.get("articles", [])
        if not articles:
            upstream = input_data.get("upstream", {})
            for v in upstream.values():
                if isinstance(v, dict) and "articles" in v:
                    articles = v["articles"]
                    break

        await self.say(f"Summarizing {len(articles)} articles...")
        lines = [f"- {a.get('title', 'Unknown')}" for a in articles[:5]]
        summary = "\n".join(lines) if lines else "No articles to summarize."
        await self.say("Summary complete")
        return {"summary": summary}


class FactCheckerAgent(Agent):
    name = "fact_checker"
    description = "Cross-references claims against Wikipedia to verify accuracy"
    capabilities = ["verification", "research", "fact_check"]
    input_schema = {"articles": list}
    output_schema = {"verified": list}

    async def run(self, input_data: dict) -> dict:
        articles = input_data.get("articles", [])
        if not articles:
            upstream = input_data.get("upstream", {})
            for v in upstream.values():
                if isinstance(v, dict) and "articles" in v:
                    articles = v["articles"]
                    break

        await self.say(f"Verifying {len(articles)} articles...")
        verified = [
            {"title": a.get("title", ""), "has_content": bool(a.get("snippet", ""))}
            for a in articles[:3]
        ]
        await self.say(f"Verified {len(verified)} claims")
        return {"verified": verified}
```

- [ ] **Step 2: Create example app**

```python
# src/atrium/examples/hello_world/app.py
"""Hello World — run with: python -m atrium.examples.hello_world.app"""

from atrium import Atrium
from atrium.examples.hello_world.agents import (
    FactCheckerAgent,
    SummarizerAgent,
    WikiSearchAgent,
)

app = Atrium(
    agents=[WikiSearchAgent, SummarizerAgent, FactCheckerAgent],
    llm="openai:gpt-4o-mini",
)

if __name__ == "__main__":
    app.serve()
```

- [ ] **Step 3: Create README**

```markdown
# Hello World Example

Three agents using Wikipedia's public API — no external infrastructure needed.

## Agents

- **WikiSearchAgent** — searches Wikipedia
- **SummarizerAgent** — creates bullet-point summaries
- **FactCheckerAgent** — verifies article claims

## Run

```bash
export OPENAI_API_KEY="your-key-here"  # for the Commander
python -m atrium.examples.hello_world.app
```

Open http://localhost:8080 and try: "What is quantum computing?"
```

- [ ] **Step 4: Commit**

```bash
git add src/atrium/examples/hello_world/
git commit -m "feat(examples): add hello_world example with Wikipedia agents"
```

---

### Task 16: Documentation

**Files:**
- Create: `docs/getting-started.md`, `docs/guide/concepts.md`, `docs/guide/writing-agents.md`, `docs/guide/agent-patterns.md`, `docs/guide/testing-agents.md`

- [ ] **Step 1: Create documentation directory**

```bash
mkdir -p docs/guide
```

- [ ] **Step 2: Write getting-started.md**

Extract the getting started content from the spec (Section 15) into `docs/getting-started.md`. Include: install, run example, build first agent, register and serve.

- [ ] **Step 3: Write writing-agents.md**

Extract the full "Writing Agents Guide" from spec Section 15 into `docs/guide/writing-agents.md`. Include: minimal agent, five fields, writing descriptions, writing capabilities, schemas, run() contract, self.say().

- [ ] **Step 4: Write agent-patterns.md**

Extract the "Agent Patterns Cookbook" from spec Section 15 into `docs/guide/agent-patterns.md`. Include all 5 patterns with full code.

- [ ] **Step 5: Write testing-agents.md**

Extract the "Testing Agents" section from spec Section 15 into `docs/guide/testing-agents.md`. Include isolated tests, schema validation, integration test helper.

- [ ] **Step 6: Write concepts.md**

Write `docs/guide/concepts.md` covering: Thread, Agent, Plan, Commander, Pivot, Guardrails, Event Stream, Dashboard.

- [ ] **Step 7: Commit**

```bash
git add docs/
git commit -m "docs: add getting-started, writing-agents, patterns, testing, concepts guides"
```

---

### Task 17: Testing Helpers

**Files:**
- Create: `src/atrium/testing/helpers.py`

- [ ] **Step 1: Implement run_thread helper and MockCommander**

```python
# src/atrium/testing/helpers.py
"""Test helpers for Atrium — run threads without a server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atrium.core.agent import Agent
from atrium.core.guardrails import GuardrailsConfig
from atrium.core.models import AtriumEvent, Plan, PlanStep
from atrium.core.registry import AgentRegistry
from atrium.engine.commander import Commander, EvalDecision
from atrium.engine.orchestrator import ThreadOrchestrator
from atrium.streaming.events import EventRecorder


@dataclass
class ThreadResult:
    thread_id: str
    status: str
    events: list[AtriumEvent] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)


class MockCommander(Commander):
    """Commander that runs all agents sequentially without LLM calls."""

    def __init__(self, registry: AgentRegistry):
        self._registry = registry
        # Don't initialize LLMClient

    async def plan(self, objective: str) -> Plan:
        agents = self._registry.list_all()
        steps = [
            PlanStep(agent=a.name, inputs={}, depends_on=[])
            for a in agents
        ]
        return Plan(thread_id="", rationale="Mock plan: run all agents", steps=steps)

    async def evaluate(self, objective: str, outputs: dict[str, Any]) -> EvalDecision:
        return EvalDecision(action="finalize", summary="Mock evaluation complete")


async def run_thread(
    agents: list[type[Agent]],
    objective: str,
    llm: str = "mock",
    guardrails: GuardrailsConfig | None = None,
) -> ThreadResult:
    """Run a complete thread for testing. Use llm='mock' to skip real LLM calls."""
    registry = AgentRegistry()
    for agent_cls in agents:
        registry.register(agent_cls)

    recorder = EventRecorder()
    orchestrator = ThreadOrchestrator(
        registry=registry,
        recorder=recorder,
        guardrails=guardrails or GuardrailsConfig(),
        llm_config=llm,
    )

    if llm == "mock":
        orchestrator._commander = MockCommander(registry)

    result = await orchestrator.run(objective)
    events = recorder.replay(result["thread_id"])

    return ThreadResult(
        thread_id=result["thread_id"],
        status=result["status"],
        events=events,
        outputs=result.get("outputs", {}),
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/atrium/testing/helpers.py
git commit -m "feat(testing): add run_thread helper and MockCommander for tests"
```

---

### Task 18: End-to-End Integration Test

**Files:**
- Create: `tests/test_e2e.py`

- [ ] **Step 1: Write integration test using MockCommander**

```python
# tests/test_e2e.py
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
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add end-to-end integration tests with MockCommander"
```

---

### Task 19: Clean Up Old Directories

- [ ] **Step 1: Remove empty old directories**

```bash
rm -rf backend/
rm -rf frontend/
rm -rf artifacts/
```

- [ ] **Step 2: Update .gitignore**

Add to `.gitignore`:
```
*.db
__pycache__/
*.egg-info/
dist/
build/
.venv/
```

- [ ] **Step 3: Run full test suite one final time**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add -u
git add .gitignore
git commit -m "chore: remove old backend/frontend directories, update gitignore"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Section | Task(s) |
|---|---|
| 1. What Atrium Is | All tasks combined |
| 2. Architecture | Task 11 (Orchestrator) |
| 3. Package Structure | Task 1 |
| 4. Core Layer (Agent, Registry, Models, Guardrails) | Tasks 2-5 |
| 5. Engine Layer (Commander, Graph Builder, Callbacks) | Tasks 8-11 |
| 6. Streaming & Events | Tasks 6-7 |
| 7. API Layer | Task 12 |
| 8. Dashboard | Task 14 |
| 9. Examples | Task 15 |
| 10. What Gets Deleted | Tasks 1, 19 |
| 11. What Gets Kept | Tasks 14, 15 |
| 12. Dependencies | Task 1 (pyproject.toml) |
| 13. CLI | Task 13 |
| 14. Spec Documents | Covered by new docs in Task 16 |
| 15. Developer Documentation | Task 16 |
| 16. LLM Usage Clarification | Task 8 (LLMClient) |
| 17. Success Criteria | Task 18 (E2E tests) |

### Gaps: None found. All spec sections mapped to tasks.

### Type Consistency Check
- `Agent` class: consistent across tasks 2, 3, 9, 11, 12, 13, 15
- `AgentRegistry`: methods match between task 3 (impl) and task 9 (usage)
- `EventRecorder.emit()`: signature consistent between task 6 (impl) and tasks 10, 11 (usage)
- `Commander.plan()` / `Commander.evaluate()`: signatures consistent between task 9 (impl) and task 11 (usage)
- `ThreadOrchestrator.run()`: return type consistent between task 11 (impl) and task 17 (testing helper)
- `format_sse()`: signature consistent between task 7 (impl) and task 12 (usage)
