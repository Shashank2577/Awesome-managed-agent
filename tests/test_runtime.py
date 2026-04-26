import asyncio
import unittest
from uuid import uuid4

from backend.app.agents.dummy import DummyAgent, SummaryAgent
from backend.app.models.domain import AgentStatus, NodeStatus, PlanNode
from backend.app.runtime.events import InMemoryEventBus
from backend.app.runtime.executor import ParallelExecutor
from backend.app.runtime.guardrails import GuardrailEnforcer, GuardrailsConfig
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.state_machine import (
    AgentRuntimeState,
    AgentStateMachine,
    TransitionRejectedError,
)


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


class RuntimeContractsTests(unittest.TestCase):
    def _node(self, key: str, deps: list[str], node_type: str = "dummy") -> PlanNode:
        thread_id = uuid4()
        org_id = uuid4()
        return PlanNode(
            node_id=uuid4(),
            plan_id=uuid4(),
            thread_id=thread_id,
            org_id=org_id,
            node_key=key,
            node_type=node_type,
            depends_on=deps,
            status=NodeStatus.PENDING,
            timeout_ms=1000,
        )

    def _registry(self) -> AgentRegistry:
        registry = AgentRegistry()
        registry.register("dummy", DummyAgent)
        registry.register("summary", SummaryAgent)
        return registry

    def test_parallel_executor_resolves_dependencies_and_emits_events(self):
        n1 = self._node("n1", [])
        n2 = self._node("n2", [])
        n3 = self._node("n3", ["n1", "n2"], node_type="summary")
        n2.thread_id = n1.thread_id
        n3.thread_id = n1.thread_id
        n2.org_id = n1.org_id
        n3.org_id = n1.org_id
        nodes = [n1, n2, n3]

        inputs = {
            "n1": {"text": "one two"},
            "n2": {"text": "three four five"},
            "n3": {"results": [{"word_count": 2, "char_count": 7}]},
        }

        event_bus = InMemoryEventBus()
        executor = ParallelExecutor(
            guardrails=GuardrailEnforcer(GuardrailsConfig(max_agents=10, max_parallel=2)),
            event_bus=event_bus,
        )
        results = asyncio.run(executor.execute(nodes=nodes, registry=self._registry(), node_inputs=inputs))

        self.assertEqual(set(results.keys()), {"n1", "n2", "n3"})
        self.assertTrue(results["n3"].success)

        emitted = event_bus.list_events(n1.thread_id)
        self.assertTrue(any(evt.type == "NODE_SUCCEEDED" for evt in emitted))
        self.assertTrue(any(evt.type == "AGENT_STATE_TRANSITIONED" for evt in emitted))

    def test_state_machine_rejects_invalid_transition(self):
        captured: list[tuple[str, dict]] = []
        machine = AgentStateMachine(
            state=AgentRuntimeState(status=AgentStatus.CREATED),
            emit=lambda event_type, payload: captured.append((event_type, payload)),
        )

        with self.assertRaises(TransitionRejectedError):
            machine.transition(AgentStatus.RUNNING, reason="bad", actor="test")

        self.assertEqual(captured[-1][0], "STATE_TRANSITION_REJECTED")


if __name__ == "__main__":
    unittest.main()
