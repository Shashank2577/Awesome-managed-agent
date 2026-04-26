import asyncio
import unittest
from uuid import uuid4

from backend.app.runtime.commander import Commander, CommanderConfig, classify_objective
from backend.app.runtime.streaming import ThreadStream


def fast_config() -> CommanderConfig:
    return CommanderConfig(
        plan_delay_ms=0,
        hire_delay_ms=0,
        agent_think_min_ms=0,
        agent_think_max_ms=0,
        pivot_delay_ms=0,
        presenter_delay_ms=0,
    )


class ClassifyTests(unittest.TestCase):
    def test_incident_keywords_route_to_incident(self):
        self.assertEqual(classify_objective("we have a P1 outage on payments"), "incident")
        self.assertEqual(classify_objective("latency on checkout is bad"), "incident")

    def test_cost_keywords_route_to_cost(self):
        self.assertEqual(classify_objective("review the bill and retention"), "cost")

    def test_default_is_observability(self):
        self.assertEqual(classify_objective("hello"), "observability")


class CommanderTests(unittest.TestCase):
    def _stream(self, objective: str) -> ThreadStream:
        return ThreadStream(
            thread_id=uuid4(),
            org_id=uuid4(),
            objective=objective,
            title="test",
        )

    async def _drive(self, objective: str) -> ThreadStream:
        stream = self._stream(objective)

        async def emit(event_type, payload, causation):
            await stream.emit(event_type, payload, causation_id=causation)

        commander = Commander(
            thread_id=stream.thread_id,
            org_id=stream.org_id,
            objective=objective,
            emit=emit,
            config=fast_config(),
        )
        await commander.run()
        await stream.mark_complete()
        return stream

    def test_incident_flow_emits_full_taxonomy(self):
        stream = asyncio.run(self._drive("P1 incident on payments service"))
        types = [e["type"] for e in stream.events_after(0)]

        for required in [
            "THREAD_CREATED",
            "THREAD_PLANNING_STARTED",
            "PLAN_GENERATION_STARTED",
            "PLAN_CREATED",
            "PLAN_APPROVED",
            "THREAD_RUNNING",
            "PLAN_EXECUTION_STARTED",
            "AGENT_HIRED",
            "AGENT_RUNNING",
            "AGENT_COMPLETED",
            "PIVOT_REQUESTED",
            "PIVOT_APPLIED",
            "EVIDENCE_PUBLISHED",
            "PLAN_COMPLETED",
            "THREAD_COMPLETED",
        ]:
            self.assertIn(required, types, f"missing event {required}")

    def test_pivot_only_fires_for_incident_scenario(self):
        stream = asyncio.run(self._drive("review observability readiness"))
        types = [e["type"] for e in stream.events_after(0)]
        self.assertNotIn("PIVOT_REQUESTED", types)
        self.assertIn("THREAD_COMPLETED", types)

    def test_evidence_payload_carries_chart_and_recommendations(self):
        stream = asyncio.run(self._drive("payments outage"))
        evidence_events = [e for e in stream.events_after(0) if e["type"] == "EVIDENCE_PUBLISHED"]
        self.assertEqual(len(evidence_events), 1)
        payload = evidence_events[0]["payload"]
        self.assertIn("chart", payload)
        self.assertIn("findings", payload)
        self.assertIn("recommendations", payload)
        self.assertGreater(len(payload["recommendations"]), 0)

    def test_event_sequence_is_monotonic(self):
        stream = asyncio.run(self._drive("review cost and retention"))
        sequences = [e["sequence"] for e in stream.events_after(0)]
        self.assertEqual(sequences, sorted(sequences))
        self.assertEqual(sequences[0], 1)


if __name__ == "__main__":
    unittest.main()
