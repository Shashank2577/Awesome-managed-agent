"""Phase 0 acceptance tests — Commander plan validation and guardrails."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atrium.core.errors import ValidationError
from atrium.core.guardrails import GuardrailEnforcer, GuardrailsConfig
from atrium.core.models import PlanStep
from atrium.core.registry import AgentRegistry
from atrium.engine.commander import Commander, _validate_plan


# ---------------------------------------------------------------------------
# Helper — build a minimal registry with named agents
# ---------------------------------------------------------------------------

def _make_registry(*names: str) -> AgentRegistry:
    from atrium.core.agent import Agent

    registry = AgentRegistry()
    for n in names:
        cls = type(
            n,
            (Agent,),
            {
                "name": n,
                "description": f"test agent {n}",
                "run": AsyncMock(return_value={}),
            },
        )
        registry.register(cls)
    return registry


# ---------------------------------------------------------------------------
# _validate_plan
# ---------------------------------------------------------------------------

async def test_unknown_agent_raises_validation_error():
    registry = _make_registry("agent_a")
    steps = [PlanStep(agent="agent_b", inputs={}, depends_on=[])]
    with pytest.raises(ValidationError, match="unknown agent"):
        _validate_plan(steps, registry)


async def test_duplicate_agent_raises_validation_error():
    registry = _make_registry("agent_a")
    steps = [
        PlanStep(agent="agent_a", inputs={}, depends_on=[]),
        PlanStep(agent="agent_a", inputs={}, depends_on=[]),
    ]
    with pytest.raises(ValidationError, match="more than once"):
        _validate_plan(steps, registry)


async def test_cycle_in_dependencies_raises_validation_error():
    registry = _make_registry("agent_a", "agent_b")
    steps = [
        PlanStep(agent="agent_a", inputs={}, depends_on=["agent_b"]),
        PlanStep(agent="agent_b", inputs={}, depends_on=["agent_a"]),
    ]
    with pytest.raises(ValidationError, match="cycle"):
        _validate_plan(steps, registry)


async def test_missing_dependency_raises_validation_error():
    registry = _make_registry("agent_a")
    steps = [
        PlanStep(agent="agent_a", inputs={}, depends_on=["missing_step"]),
    ]
    with pytest.raises(ValidationError, match="missing step"):
        _validate_plan(steps, registry)


async def test_valid_plan_passes_validation():
    registry = _make_registry("agent_a", "agent_b")
    steps = [
        PlanStep(agent="agent_a", inputs={}, depends_on=[]),
        PlanStep(agent="agent_b", inputs={}, depends_on=["agent_a"]),
    ]
    # Should not raise
    _validate_plan(steps, registry)


# ---------------------------------------------------------------------------
# Guardrail enforcement
# ---------------------------------------------------------------------------

def test_max_time_raises_guardrail_violation():
    cfg = GuardrailsConfig(max_time_seconds=10)
    enforcer = GuardrailEnforcer(cfg)
    from atrium.core.errors import GuardrailViolation
    with pytest.raises(GuardrailViolation):
        enforcer.check_time(11)


def test_max_cost_raises_guardrail_violation():
    cfg = GuardrailsConfig(max_cost_usd=Decimal("5"))
    enforcer = GuardrailEnforcer(cfg)
    from atrium.core.errors import GuardrailViolation
    with pytest.raises(GuardrailViolation):
        enforcer.check_cost(Decimal("5.01"))


def test_max_cost_at_limit_is_fine():
    cfg = GuardrailsConfig(max_cost_usd=Decimal("5"))
    enforcer = GuardrailEnforcer(cfg)
    # Exactly at limit — should NOT raise
    enforcer.check_cost(Decimal("5"))
