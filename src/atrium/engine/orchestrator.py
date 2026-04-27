"""Thread orchestrator — ties Commander, GraphBuilder, and EventRecorder together."""
from __future__ import annotations

from typing import Any

from atrium.core.guardrails import GuardrailEnforcer, GuardrailsConfig
from atrium.core.models import Plan, Thread
from atrium.core.registry import AgentRegistry
from atrium.engine.commander import Commander
from atrium.engine.graph_builder import build_graph_from_plan
from atrium.streaming.events import EventRecorder


def _build_severity_chart(findings: list[dict]) -> list[dict]:
    """Build a simple bar chart from finding severities."""
    counts = {"high": 0, "med": 0, "low": 0}
    for f in findings:
        sev = f.get("severity", "low")
        if sev in counts:
            counts[sev] += 1
    return [{"label": k, "value": v} for k, v in counts.items() if v > 0]


class ThreadOrchestrator:
    """Runs a complete thread: plan -> execute -> evaluate -> pivot/finalize."""

    def __init__(
        self,
        registry: AgentRegistry,
        recorder: EventRecorder,
        guardrails: GuardrailsConfig,
        llm_config: str,
    ) -> None:
        self._registry = registry
        self._recorder = recorder
        self._guardrails = GuardrailEnforcer(guardrails)
        self._commander = Commander(llm_config=llm_config, registry=registry)

    async def run(self, objective: str, thread_id: str | None = None) -> dict[str, Any]:
        """Execute a full thread lifecycle and return a summary dict."""
        thread = Thread(objective=objective)
        if thread_id is not None:
            thread.thread_id = thread_id
        tid = thread.thread_id

        # Phase 1: Thread creation (emitted before try so thread_id is always recorded)
        await self._recorder.emit(tid, "THREAD_CREATED", {"objective": objective, "thread_id": tid})
        await self._recorder.emit(tid, "BUDGET_RESERVED", {
            "currency": "USD",
            "allocated": str(self._guardrails.config.max_cost_usd),
            "consumed": "0.00",
            "hard_limit": str(self._guardrails.config.max_cost_usd),
        })

        try:
            await self._recorder.emit(tid, "THREAD_PLANNING", {"objective": objective})
            await self._recorder.emit(
                tid,
                "COMMANDER_MESSAGE",
                {"text": "Analyzing objective and selecting agents...", "phase": "planning"},
            )

            # Phase 2: Plan
            plan = await self._commander.plan(objective)
            plan.thread_id = tid
            await self._recorder.emit(tid, "BUDGET_CONSUMED", {
                "currency": "USD",
                "consumed": "0.10",  # estimated planning cost
                "hard_limit": str(self._guardrails.config.max_cost_usd),
            })

            await self._recorder.emit(
                tid,
                "PLAN_CREATED",
                {
                    "plan_id": plan.plan_id,
                    "plan_number": plan.plan_number,
                    "rationale": plan.rationale,
                    "graph": {
                        "nodes": [
                            {
                                "key": s.agent,
                                "role": s.agent,
                                "objective": "",
                                "depends_on": s.depends_on,
                            }
                            for s in plan.steps
                        ]
                    },
                },
            )

            for step in plan.steps:
                agent_cls = self._registry.get(step.agent)
                await self._recorder.emit(
                    tid,
                    "AGENT_HIRED",
                    {
                        "agent_key": step.agent,
                        "role": step.agent,
                        "objective": agent_cls.description,
                        "depends_on": step.depends_on,
                    },
                )

            # Phase 3: Execute
            await self._recorder.emit(tid, "PLAN_EXECUTION_STARTED", {"plan_id": plan.plan_id})
            await self._recorder.emit(tid, "THREAD_RUNNING", {"plan_id": plan.plan_id})

            graph = build_graph_from_plan(plan, self._registry, self._recorder)
            initial_state = {
                "inputs": {s.agent: s.inputs for s in plan.steps},
                "agent_outputs": {},
            }
            final_state = await graph.ainvoke(initial_state)
            outputs: dict[str, Any] = final_state.get("agent_outputs", {})

            # Phase 4: Evaluate (and pivot loop)
            decision = await self._commander.evaluate(objective, outputs)
            await self._recorder.emit(tid, "BUDGET_CONSUMED", {
                "currency": "USD",
                "consumed": "0.20",  # estimated total
                "hard_limit": str(self._guardrails.config.max_cost_usd),
            })

            pivot_count = 0
            while decision.action == "pivot" and getattr(decision, "new_steps", None):
                self._guardrails.check_pivots(pivot_count + 1)
                pivot_count += 1

                await self._recorder.emit(
                    tid,
                    "PIVOT_REQUESTED",
                    {"rationale": getattr(decision, "rationale", "")},
                )
                await self._recorder.emit(
                    tid,
                    "COMMANDER_MESSAGE",
                    {"text": getattr(decision, "rationale", ""), "phase": "pivot"},
                )

                pivot_plan = Plan(
                    thread_id=tid,
                    plan_number=plan.plan_number + pivot_count,
                    rationale=getattr(decision, "rationale", ""),
                    steps=decision.new_steps,
                )

                for step in pivot_plan.steps:
                    agent_cls = self._registry.get(step.agent)
                    await self._recorder.emit(
                        tid,
                        "AGENT_HIRED",
                        {
                            "agent_key": step.agent,
                            "role": step.agent,
                            "objective": agent_cls.description,
                            "depends_on": step.depends_on,
                        },
                    )

                pivot_graph = build_graph_from_plan(pivot_plan, self._registry, self._recorder)
                pivot_state = {
                    "inputs": {s.agent: s.inputs for s in pivot_plan.steps},
                    "agent_outputs": dict(outputs),
                }
                pivot_result = await pivot_graph.ainvoke(pivot_state)
                outputs.update(pivot_result.get("agent_outputs", {}))

                await self._recorder.emit(
                    tid,
                    "PIVOT_APPLIED",
                    {"added_agents": [s.agent for s in decision.new_steps]},
                )
                decision = await self._commander.evaluate(objective, outputs)

            # Phase 5: Finalize
            await self._recorder.emit(tid, "PLAN_COMPLETED", {"plan_id": plan.plan_id})
            await self._recorder.emit(
                tid,
                "EVIDENCE_PUBLISHED",
                {
                    "headline": decision.summary or "Analysis Complete",
                    "summary": decision.summary,
                    "findings": decision.findings,
                    "recommendations": decision.recommendations,
                    "chart": {
                        "type": "bar",
                        "title": "Findings by Severity",
                        "series": _build_severity_chart(decision.findings),
                    },
                },
            )
            await self._recorder.emit(tid, "THREAD_COMPLETED", {"thread_id": tid})
            await self._recorder.complete(tid)

            return {"thread_id": tid, "status": "COMPLETED", "outputs": outputs}

        except Exception as exc:
            await self._recorder.emit(tid, "THREAD_FAILED", {"error": str(exc), "thread_id": tid})
            await self._recorder.complete(tid)
            return {"thread_id": tid, "status": "FAILED", "error": str(exc)}
