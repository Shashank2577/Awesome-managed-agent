import unittest
from decimal import Decimal

from backend.app.runtime.guardrails import (
    ExecutionCounters,
    GuardrailEnforcer,
    GuardrailViolation,
    GuardrailsConfig,
)


class TestGuardrailEnforcer(unittest.TestCase):
    def setUp(self):
        self.config = GuardrailsConfig(
            max_agents=10,
            max_parallel=5,
            max_time_seconds=100,
            max_cost_usd=Decimal("1.0"),
            max_pivots=3,
        )
        self.enforcer = GuardrailEnforcer(self.config)

    def test_check_spawn(self):
        counters = ExecutionCounters(total_agents_spawned=10)
        self.enforcer.check_spawn(counters)

        counters.total_agents_spawned = 11
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_spawn(counters)
        self.assertEqual(cm.exception.code, "MAX_AGENTS")

    def test_check_parallel(self):
        counters = ExecutionCounters(running_parallel=5)
        self.enforcer.check_parallel(counters)

        counters.running_parallel = 6
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_parallel(counters)
        self.assertEqual(cm.exception.code, "MAX_PARALLEL")

    def test_check_time(self):
        counters = ExecutionCounters(elapsed_seconds=100)
        self.enforcer.check_time(counters)

        counters.elapsed_seconds = 101
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_time(counters)
        self.assertEqual(cm.exception.code, "MAX_TIME")

    def test_check_cost(self):
        counters = ExecutionCounters(cost_usd=Decimal("1.0"))
        self.enforcer.check_cost(counters)

        counters.cost_usd = Decimal("1.01")
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_cost(counters)
        self.assertEqual(cm.exception.code, "MAX_COST")

    def test_check_pivots(self):
        counters = ExecutionCounters(pivots=3)
        self.enforcer.check_pivots(counters)

        counters.pivots = 4
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_pivots(counters)
        self.assertEqual(cm.exception.code, "MAX_PIVOTS")

    def test_check_all_success(self):
        counters = ExecutionCounters(
            total_agents_spawned=10,
            running_parallel=5,
            elapsed_seconds=100,
            cost_usd=Decimal("1.0"),
            pivots=3,
        )
        self.enforcer.check_all(counters)


if __name__ == "__main__":
    unittest.main()
