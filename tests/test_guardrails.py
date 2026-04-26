import unittest
from decimal import Decimal
from backend.app.runtime.guardrails import (
    GuardrailEnforcer,
    GuardrailsConfig,
    ExecutionCounters,
    GuardrailViolation,
)

class TestGuardrailEnforcer(unittest.TestCase):
    def setUp(self):
        self.config = GuardrailsConfig(
            max_agents=10,
            max_parallel=5,
            max_time_seconds=100,
            max_cost_usd=Decimal("1.0"),
            max_pivots=3
        )
        self.enforcer = GuardrailEnforcer(self.config)

    def test_check_spawn(self):
        # Within limit
        counters = ExecutionCounters(total_agents_spawned=10)
        self.enforcer.check_spawn(counters)

        # Exceed limit
        counters.total_agents_spawned = 11
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_spawn(counters)
        self.assertEqual(cm.exception.code, "MAX_AGENTS")

    def test_check_parallel(self):
        # Within limit
        counters = ExecutionCounters(running_parallel=5)
        self.enforcer.check_parallel(counters)

        # Exceed limit
        counters.running_parallel = 6
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_parallel(counters)
        self.assertEqual(cm.exception.code, "MAX_PARALLEL")

    def test_check_time(self):
        # Within limit
        counters = ExecutionCounters(elapsed_seconds=100)
        self.enforcer.check_time(counters)

        # Exceed limit
        counters.elapsed_seconds = 101
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_time(counters)
        self.assertEqual(cm.exception.code, "MAX_TIME")

    def test_check_cost(self):
        # Within limit
        counters = ExecutionCounters(cost_usd=Decimal("1.0"))
        self.enforcer.check_cost(counters)

        # Exceed limit
        counters.cost_usd = Decimal("1.01")
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_cost(counters)
        self.assertEqual(cm.exception.code, "MAX_COST")

    def test_check_pivots(self):
        # Within limit
        counters = ExecutionCounters(pivots=3)
        self.enforcer.check_pivots(counters)

        # Exceed limit
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
            pivots=3
        )
        # Should not raise any exception
        self.enforcer.check_all(counters)

    def test_check_all_violation_order(self):
        # Test that check_all catches violations in the expected order
        # 1. Total agents
        counters = ExecutionCounters(total_agents_spawned=11, running_parallel=6)
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_all(counters)
        self.assertEqual(cm.exception.code, "MAX_AGENTS")

        # 2. Parallel agents
        counters = ExecutionCounters(total_agents_spawned=10, running_parallel=6, elapsed_seconds=101)
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_all(counters)
        self.assertEqual(cm.exception.code, "MAX_PARALLEL")

        # 3. Time
        counters = ExecutionCounters(total_agents_spawned=10, running_parallel=5, elapsed_seconds=101, cost_usd=Decimal("1.01"))
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_all(counters)
        self.assertEqual(cm.exception.code, "MAX_TIME")

        # 4. Cost
        counters = ExecutionCounters(total_agents_spawned=10, running_parallel=5, elapsed_seconds=100, cost_usd=Decimal("1.01"), pivots=4)
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_all(counters)
        self.assertEqual(cm.exception.code, "MAX_COST")

        # 5. Pivots
        counters = ExecutionCounters(total_agents_spawned=10, running_parallel=5, elapsed_seconds=100, cost_usd=Decimal("1.0"), pivots=4)
        with self.assertRaises(GuardrailViolation) as cm:
            self.enforcer.check_all(counters)
        self.assertEqual(cm.exception.code, "MAX_PIVOTS")

if __name__ == "__main__":
    unittest.main()
