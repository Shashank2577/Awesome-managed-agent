from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.app.models.domain import PlanNode
from backend.app.runtime.events import InMemoryEventBus
from backend.app.runtime.guardrails import ExecutionCounters, GuardrailEnforcer
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.worker import Worker


@dataclass(slots=True)
class NodeExecutionResult:
    node_key: str
    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None


class ParallelExecutor:
    def __init__(self, guardrails: GuardrailEnforcer, event_bus: InMemoryEventBus | None = None):
        self.guardrails = guardrails
        self.event_bus = event_bus or InMemoryEventBus()

    async def execute(
        self,
        nodes: list[PlanNode],
        registry: AgentRegistry,
        node_inputs: dict[str, dict[str, Any]],
    ) -> dict[str, NodeExecutionResult]:
        start = time.monotonic()
        by_key = {node.node_key: node for node in nodes}
        dependents: dict[str, list[str]] = defaultdict(list)
        dep_count: dict[str, int] = {}

        for node in nodes:
            dep_count[node.node_key] = len(node.depends_on)
            for dep in node.depends_on:
                dependents[dep].append(node.node_key)

        ready = [k for k, count in dep_count.items() if count == 0]
        done: dict[str, NodeExecutionResult] = {}
        counters = ExecutionCounters(total_agents_spawned=0, running_parallel=0)
        semaphore = asyncio.Semaphore(self.guardrails.config.max_parallel)
        worker = Worker(registry=registry, event_bus=self.event_bus)

        async def run_node(node_key: str) -> NodeExecutionResult:
            node = by_key[node_key]
            async with semaphore:
                counters.running_parallel += 1
                self.guardrails.check_parallel(counters)

                counters.total_agents_spawned += 1
                self.guardrails.check_spawn(counters)

                payload = dict(node_inputs.get(node.node_key, {}))
                if node.depends_on:
                    payload["upstream"] = {
                        dep: done[dep].output for dep in node.depends_on if done[dep].success
                    }

                self.event_bus.emit(
                    org_id=node.org_id,
                    thread_id=node.thread_id,
                    event_type="NODE_RUNNING",
                    payload={"node_key": node.node_key, "node_type": node.node_type},
                )

                try:
                    worker_result = await worker.run_node(
                        org_id=node.org_id,
                        thread_id=node.thread_id,
                        node=node,
                        payload=payload,
                    )
                    if worker_result.success:
                        self.event_bus.emit(
                            org_id=node.org_id,
                            thread_id=node.thread_id,
                            event_type="NODE_SUCCEEDED",
                            payload={"node_key": node.node_key},
                        )
                        result = NodeExecutionResult(
                            node_key=node_key, success=True, output=worker_result.output
                        )
                    else:
                        self.event_bus.emit(
                            org_id=node.org_id,
                            thread_id=node.thread_id,
                            event_type="NODE_FAILED",
                            payload={"node_key": node.node_key, "error": worker_result.error},
                        )
                        result = NodeExecutionResult(
                            node_key=node_key, success=False, error=worker_result.error
                        )
                finally:
                    counters.running_parallel -= 1

                return result

        while ready:
            batch = list(ready)
            ready.clear()

            batch_results = await asyncio.gather(*(run_node(node_key) for node_key in batch))
            for result in batch_results:
                done[result.node_key] = result
                for child in dependents[result.node_key]:
                    dep_count[child] -= 1
                    if dep_count[child] == 0:
                        failed_dep = any(not done[d].success for d in by_key[child].depends_on)
                        if not failed_dep:
                            ready.append(child)

            counters.elapsed_seconds = int(time.monotonic() - start)
            counters.cost_usd = Decimal(str(sum(0.001 for r in done.values() if r.success)))
            self.guardrails.check_time(counters)
            self.guardrails.check_cost(counters)

        return done
