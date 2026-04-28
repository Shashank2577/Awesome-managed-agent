"""Guardrails — hard limits on agent count, parallelism, time, cost, and pivots."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

# GuardrailViolation is now in core.errors.  Re-export for backward compatibility
# so anything that does `from atrium.core.guardrails import GuardrailViolation` still works.
from atrium.core.errors import GuardrailViolation  # noqa: F401


@dataclass
class GuardrailsConfig:
    max_agents: int = 25
    max_parallel: int = 5
    max_time_seconds: int = 600
    max_cost_usd: Decimal = field(default_factory=lambda: Decimal("10.0"))
    max_pivots: int = 2


class GuardrailEnforcer:
    def __init__(self, config: GuardrailsConfig) -> None:
        self.config = config

    def check_spawn(self, agent_count: int) -> None:
        if agent_count > self.config.max_agents:
            raise GuardrailViolation(
                "MAX_AGENTS",
                f"agent_count {agent_count} exceeds limit {self.config.max_agents}",
            )

    def check_parallel(self, running: int) -> None:
        if running > self.config.max_parallel:
            raise GuardrailViolation(
                "MAX_PARALLEL",
                f"running {running} exceeds limit {self.config.max_parallel}",
            )

    def check_time(self, elapsed: int | float) -> None:
        if elapsed > self.config.max_time_seconds:
            raise GuardrailViolation(
                "MAX_TIME",
                f"elapsed {elapsed}s exceeds limit {self.config.max_time_seconds}s",
            )

    def check_cost(self, cost: Decimal) -> None:
        if cost > self.config.max_cost_usd:
            raise GuardrailViolation(
                "MAX_COST",
                f"cost {cost} exceeds limit {self.config.max_cost_usd}",
            )

    def check_pivots(self, pivot_count: int) -> None:
        if pivot_count > self.config.max_pivots:
            raise GuardrailViolation(
                "MAX_PIVOTS",
                f"pivot_count {pivot_count} exceeds limit {self.config.max_pivots}",
            )
