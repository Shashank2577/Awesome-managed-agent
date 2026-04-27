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
    enforcer.check_spawn(agent_count=3)


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
