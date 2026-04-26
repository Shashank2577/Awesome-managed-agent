import asyncio
import unittest
from uuid import uuid4

from backend.app.agents.dummy import DummyAgent, SummaryAgent
from backend.app.models.domain import NodeStatus, PlanNode
from backend.app.runtime.executor import ParallelExecutor
from backend.app.runtime.guardrails import GuardrailEnforcer, GuardrailsConfig


class DummyAgentTests(unittest.TestCase):
    def test_dummy_agent_run(self):
        result = asyncio.run(DummyAgent().run({"text": "hello world"}))
        self.assertEqual(result["word_count"], 2)
        self.assertEqual(result["uppercase"], "HELLO WORLD")

    def test_summary_agent_run(self):
        payload = {
            "results": [
                {"word_count": 2, "char_count": 10},
                {"word_count": 4, "char_count": 20},
            ]
        }
        result = asyncio.run(SummaryAgent().run(payload))
        self.assertEqual(result["result_count"], 2)
        self.assertEqual(result["total_words"], 6)


class ParallelExecutorTests(unittest.TestCase):
    def _node(self, key: str, deps: list[str], node_type: str = "dummy") -> PlanNode:
        return PlanNode(
            node_id=uuid4(),
            plan_id=uuid4(),
            thread_id=uuid4(),
            org_id=uuid4(),
            node_key=key,
            node_type=node_type,
            depends_on=deps,
            status=NodeStatus.PENDING,
            timeout_ms=1000,
        )

    def test_parallel_executor_resolves_dependencies(self):
        nodes = [
            self._node("n1", []),
            self._node("n2", []),
            self._node("n3", ["n1", "n2"], node_type="summary"),
        ]

        def factory(node_type: str):
            if node_type == "summary":
                return SummaryAgent()
            return DummyAgent()

        inputs = {
            "n1": {"text": "one two"},
            "n2": {"text": "three four five"},
            "n3": {"results": [{"word_count": 2, "char_count": 7}]},
        }

        executor = ParallelExecutor(
            guardrails=GuardrailEnforcer(GuardrailsConfig(max_agents=10, max_parallel=2))
        )
        results = asyncio.run(executor.execute(nodes=nodes, agent_factory=factory, node_inputs=inputs))

        self.assertEqual(set(results.keys()), {"n1", "n2", "n3"})
        self.assertTrue(results["n3"].success)


if __name__ == "__main__":
    unittest.main()
