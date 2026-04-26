import unittest

from backend.app.agents.observability.registry import AGENT_REGISTRY
from backend.app.services.observability_service import run_demo


class ObservabilityDemoTests(unittest.TestCase):
    def test_registry_contains_15_specialists(self):
        self.assertEqual(len(AGENT_REGISTRY), 15)

    def test_demo_runs_five_agent_scenario(self):
        report = run_demo("test observability simulation")
        self.assertEqual(report["scenario_agent_count"], 5)
        self.assertEqual(len(report["results"]), 5)
        self.assertTrue(all(v["success"] for v in report["results"].values()))


if __name__ == "__main__":
    unittest.main()
