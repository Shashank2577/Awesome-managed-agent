"""Thread orchestrator — ties Commander, GraphBuilder, and EventRecorder together."""
from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any

from atrium.core.errors import GuardrailViolation
from atrium.core.guardrails import GuardrailEnforcer, GuardrailsConfig
from atrium.core.models import Plan, Thread, ThreadStatus
from atrium.core.registry import AgentRegistry
from atrium.engine.commander import Commander
from atrium.engine.graph_builder import FailPolicy, build_graph_from_plan
from atrium.engine.pricing import estimate_cost
from atrium.streaming.events import EventRecorder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ThreadController — per-thread HITL control state
# ---------------------------------------------------------------------------

class ThreadController:
    """Per-thread control state for Human-in-the-Loop operations."""

    def __init__(self) -> None:
        self._paused = asyncio.Event()
        self._paused.set()  # Not paused initially
        self._cancelled = False
        self._approval_event = asyncio.Event()
        self._approval_result: str | None = None  # "approve" or "reject"
        self._human_input_event = asyncio.Event()
        self._human_input: str | None = None

    def pause(self) -> None:
        self._paused.clear()

    def resume(self) -> None:
        self._paused.set()

    def cancel(self) -> None:
        self._cancelled = True
        self._paused.set()  # Unblock if paused
        self._approval_event.set()  # Unblock if waiting for approval
        self._human_input_event.set()  # Unblock if waiting for input

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    async def wait_if_paused(self) -> None:
        """Block until the thread is unpaused."""
        await self._paused.wait()

    def approve(self) -> None:
        self._approval_result = "approve"
        self._approval_event.set()

    def reject(self) -> None:
        self._approval_result = "reject"
        self._approval_event.set()

    async def wait_for_approval(self) -> str:
        """Wait for human to approve or reject. Returns 'approve' or 'reject'."""
        await self._approval_event.wait()
        self._approval_event.clear()
        return self._approval_result or "approve"

    def submit_input(self, text: str) -> None:
        self._human_input = text
        self._human_input_event.set()

    async def wait_for_input(self) -> str:
        """Wait for human input text. Returns the submitted string."""
        await self._human_input_event.wait()
        self._human_input_event.clear()
        return self._human_input or ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_severity_chart(findings: list) -> list[dict]:
    """Build a simple bar chart from finding severities."""
    counts = {"high": 0, "med": 0, "low": 0}
    for f in findings:
        if not isinstance(f, dict):
            counts["low"] += 1
            continue
        sev = f.get("severity", "low")
        if sev in counts:
            counts[sev] += 1
    return [{"label": k, "value": v} for k, v in counts.items() if v > 0]


# ---------------------------------------------------------------------------
# ThreadOrchestrator
# ---------------------------------------------------------------------------

class ThreadOrchestrator:
    """Runs a complete thread: plan -> execute -> evaluate -> pivot/finalize."""

    def __init__(
        self,
        registry: AgentRegistry,
        recorder: EventRecorder,
        guardrails: GuardrailsConfig,
        llm_config: str,
        require_approval: bool = False,
    ) -> None:
        self._registry = registry
        self._recorder = recorder
        self._guardrails = GuardrailEnforcer(guardrails)
        self._commander = Commander(llm_config=llm_config, registry=registry)
        self._require_approval = require_approval
        self._llm_config = llm_config
        # Per-instance controller registry — no more module-level dict
        self._controllers: dict[str, ThreadController] = {}

    def get_controller(self, thread_id: str) -> ThreadController | None:
        """Return the active ThreadController for *thread_id*, or None."""
        return self._controllers.get(thread_id)

    async def run(self, objective: str, thread_id: str | None = None) -> dict[str, Any]:
        """Execute a full thread lifecycle and return a summary dict."""
        thread = Thread(objective=objective)
        if thread_id is not None:
            thread.thread_id = thread_id
        tid = thread.thread_id

        # Register a controller for this thread so HITL routes can reach it.
        controller = ThreadController()
        self._controllers[tid] = controller

        # Accumulated cost tracking
        total_cost = Decimal("0")

        # Phase 1: Thread creation
        await self._recorder.emit(tid, "THREAD_CREATED", {"objective": objective, "thread_id": tid})
        await self._recorder.emit(tid, "BUDGET_RESERVED", {
            "currency": "USD",
            "allocated": str(self._guardrails.config.max_cost_usd),
            "consumed": "0.00",
            "hard_limit": str(self._guardrails.config.max_cost_usd),
        })

        # Start wall-clock watchdog
        started_at = time.monotonic()
        cancel_event = asyncio.Event()

        async def time_watchdog() -> None:
            while not cancel_event.is_set():
                await asyncio.sleep(1.0)
                elapsed = time.monotonic() - started_at
                try:
                    self._guardrails.check_time(elapsed)
                except GuardrailViolation as exc:
                    logger.warning(
                        "Time guardrail exceeded",
                        extra={"thread_id": tid, "elapsed": elapsed},
                    )
                    await self._recorder.emit(
                        tid, "BUDGET_EXCEEDED",
                        {"code": exc.code, "message": exc.message},
                    )
                    cancel_event.set()
                    controller.cancel()

        watchdog_task = asyncio.create_task(time_watchdog())

        try:
            await self._recorder.emit(tid, "THREAD_PLANNING", {"objective": objective})
            await self._recorder.emit(
                tid,
                "COMMANDER_MESSAGE",
                {"text": "Analyzing objective and selecting agents...", "phase": "planning"},
            )

            # Phase 2: Plan (now returns (Plan, usage))
            plan, plan_usage = await self._commander.plan(objective)
            plan.thread_id = tid

            # Emit real token counts for planning phase
            total_cost = await self._emit_budget_consumed(
                tid, plan_usage, total_cost,
            )

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

            # --- HITL: approval gate ---
            if self._require_approval:
                await self._recorder.emit(tid, "HUMAN_APPROVAL_REQUESTED", {
                    "plan_id": plan.plan_id,
                    "message": "Review the plan and approve or reject.",
                })
                approval = await controller.wait_for_approval()
                if approval == "reject" or controller.is_cancelled:
                    await self._recorder.emit(
                        tid, "PLAN_REJECTED", {"plan_id": plan.plan_id},
                    )
                    await self._recorder.emit(
                        tid, "THREAD_CANCELLED", {"thread_id": tid},
                    )
                    await self._recorder.complete(tid)
                    return {"thread_id": tid, "status": "CANCELLED", "outputs": {}}
                await self._recorder.emit(
                    tid, "PLAN_APPROVED", {"plan_id": plan.plan_id},
                )
            else:
                await self._recorder.emit(
                    tid, "PLAN_APPROVED", {"plan_id": plan.plan_id},
                )

            # --- HITL: check pause/cancel before execution ---
            await controller.wait_if_paused()
            if controller.is_cancelled:
                await self._recorder.emit(
                    tid, "THREAD_CANCELLED", {"thread_id": tid},
                )
                await self._recorder.complete(tid)
                return {"thread_id": tid, "status": "CANCELLED", "outputs": {}}

            # Phase 3: Execute
            await self._recorder.emit(tid, "PLAN_EXECUTION_STARTED", {"plan_id": plan.plan_id})
            await self._recorder.emit(tid, "THREAD_RUNNING", {"plan_id": plan.plan_id})

            graph = build_graph_from_plan(
                plan,
                self._registry,
                self._recorder,
                fail_policy=FailPolicy.STOP_THREAD,
                guardrails=self._guardrails,
            )
            initial_state = {
                "inputs": {s.agent: s.inputs for s in plan.steps},
                "agent_outputs": {},
            }
            final_state = await graph.ainvoke(initial_state)
            outputs: dict[str, Any] = final_state.get("agent_outputs", {})

            # --- HITL: check cancel after execution ---
            if controller.is_cancelled:
                await self._recorder.emit(
                    tid, "THREAD_CANCELLED", {"thread_id": tid},
                )
                await self._recorder.complete(tid)
                return {"thread_id": tid, "status": "CANCELLED", "outputs": outputs}

            # Phase 4: Evaluate (and pivot loop)
            decision = await self._commander.evaluate(objective, outputs)
            total_cost = await self._emit_budget_consumed(
                tid, decision.usage, total_cost,
            )

            pivot_count = 0
            while decision.action == "pivot" and getattr(decision, "new_steps", None):
                self._guardrails.check_pivots(pivot_count + 1)
                pivot_count += 1

                # --- HITL: check pause/cancel between pivots ---
                await controller.wait_if_paused()
                if controller.is_cancelled:
                    await self._recorder.emit(
                        tid, "THREAD_CANCELLED", {"thread_id": tid},
                    )
                    await self._recorder.complete(tid)
                    return {"thread_id": tid, "status": "CANCELLED", "outputs": outputs}

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

                pivot_graph = build_graph_from_plan(
                    pivot_plan, self._registry, self._recorder,
                    fail_policy=FailPolicy.STOP_THREAD,
                )
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
                total_cost = await self._emit_budget_consumed(
                    tid, decision.usage, total_cost,
                )

            # Phase 5: Finalize
            await self._recorder.emit(tid, "PLAN_COMPLETED", {"plan_id": plan.plan_id})

            summary = decision.summary
            if not summary and decision.sections:
                summary = decision.sections[0].get("content", "")[:300]

            await self._recorder.emit(
                tid,
                "EVIDENCE_PUBLISHED",
                {
                    "headline": decision.headline or summary[:60] or "Analysis Complete",
                    "summary": summary,
                    "sections": decision.sections,
                    "recommendations": decision.recommendations,
                },
            )
            await self._recorder.emit(tid, "THREAD_COMPLETED", {"thread_id": tid})
            await self._recorder.complete(tid)

            return {"thread_id": tid, "status": "COMPLETED", "outputs": outputs}

        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            logger.error(
                "Thread failed",
                extra={"thread_id": tid, "error": str(exc)},
            )
            print(f"[ATRIUM] Thread {tid} failed:\n{tb}", flush=True)
            await self._recorder.emit(tid, "THREAD_FAILED", {"error": str(exc), "thread_id": tid})
            await self._recorder.complete(tid)
            return {"thread_id": tid, "status": "FAILED", "error": str(exc)}

        finally:
            cancel_event.set()
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass
            self._controllers.pop(tid, None)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _emit_budget_consumed(
        self,
        thread_id: str,
        usage: dict[str, int],
        running_cost: Decimal,
    ) -> Decimal:
        """Emit BUDGET_CONSUMED with real token counts. Returns updated running cost."""
        if not usage:
            return running_cost

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        step_cost = estimate_cost(
            f"{self._commander._llm.model_key()}",
            input_tokens,
            output_tokens,
        )
        running_cost += step_cost

        # Check cost guardrail
        self._guardrails.check_cost(running_cost)

        await self._recorder.emit(
            thread_id,
            "BUDGET_CONSUMED",
            {
                "currency": "USD",
                "consumed": str(running_cost),
                "step_cost": str(step_cost),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "hard_limit": str(self._guardrails.config.max_cost_usd),
            },
        )
        return running_cost


# ---------------------------------------------------------------------------
# Backward-compat: module-level get_controller for any code still importing it
# ---------------------------------------------------------------------------

def get_controller(thread_id: str) -> ThreadController | None:
    """Deprecated: use orchestrator.get_controller(). Returns None always.

    The controller dict was moved to ThreadOrchestrator instances in Phase 0.
    This shim exists so old imports don't crash; route handlers should be
    updated to call get_orchestrator().get_controller(thread_id) instead.
    """
    return None
