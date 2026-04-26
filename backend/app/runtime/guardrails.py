from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class GuardrailsConfig:
    max_agents: int = 25
    max_parallel: int = 5
    max_time_seconds: int = 600
    max_cost_usd: Decimal = Decimal("10.0")
    max_pivots: int = 2


@dataclass(slots=True)
class ExecutionCounters:
    total_agents_spawned: int = 0
    running_parallel: int = 0
    elapsed_seconds: int = 0
    cost_usd: Decimal = Decimal("0")
    pivots: int = 0


@dataclass(slots=True)
class GuardrailViolation(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class GuardrailEnforcer:
    def __init__(self, config: GuardrailsConfig):
        self.config = config

    def check_spawn(self, counters: ExecutionCounters) -> None:
        if counters.total_agents_spawned > self.config.max_agents:
            raise GuardrailViolation("MAX_AGENTS", "agent count exceeded")

    def check_parallel(self, counters: ExecutionCounters) -> None:
        if counters.running_parallel > self.config.max_parallel:
            raise GuardrailViolation("MAX_PARALLEL", "parallelism exceeded")

    def check_time(self, counters: ExecutionCounters) -> None:
        if counters.elapsed_seconds > self.config.max_time_seconds:
            raise GuardrailViolation("MAX_TIME", "execution time exceeded")

    def check_cost(self, counters: ExecutionCounters) -> None:
        if counters.cost_usd > self.config.max_cost_usd:
            raise GuardrailViolation("MAX_COST", "cost exceeded")

    def check_pivots(self, counters: ExecutionCounters) -> None:
        if counters.pivots > self.config.max_pivots:
            raise GuardrailViolation("MAX_PIVOTS", "pivot count exceeded")

    def check_all(self, counters: ExecutionCounters) -> None:
        self.check_spawn(counters)
        self.check_parallel(counters)
        self.check_time(counters)
        self.check_cost(counters)
        self.check_pivots(counters)
