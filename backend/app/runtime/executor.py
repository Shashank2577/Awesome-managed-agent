from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from backend.app.agents.base import BaseAgent
from backend.app.models.domain import PlanNode
from backend.app.runtime.guardrails import ExecutionCounters, GuardrailEnforcer


@dataclass(slots=True)
class NodeExecutionResult:
    node_key: str
    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None


class ParallelExecutor:
    def __init__(self, guardrails: GuardrailEnforcer):
        self.guardrails = guardrails

    async def execute(
        self,
        nodes: list[PlanNode],
        agent_factory: Callable[[str], BaseAgent],
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

        async def run_node(node_key: str) -> NodeExecutionResult:
            node = by_key[node_key]
            async with semaphore:
                counters.running_parallel += 1
                self.guardrails.check_parallel(counters)

                agent = agent_factory(node.node_type)
                counters.total_agents_spawned += 1
                self.guardrails.check_spawn(counters)

                payload = dict(node_inputs.get(node.node_key, {}))
                if node.depends_on:
                    payload["upstream"] = {
                        dep: done[dep].output for dep in node.depends_on if done[dep].success
                    }

                try:
                    output = await agent.run(payload)
                    result = NodeExecutionResult(node_key=node_key, success=True, output=output)
                except Exception as exc:  # runtime faults should be captured per node
                    result = NodeExecutionResult(node_key=node_key, success=False, error=str(exc))
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
                        # block failed upstream chains
                        failed_dep = any(not done[d].success for d in by_key[child].depends_on)
                        if not failed_dep:
                            ready.append(child)

            counters.elapsed_seconds = int(time.monotonic() - start)
            counters.cost_usd = Decimal(str(sum(0.001 for r in done.values() if r.success)))
            self.guardrails.check_time(counters)
            self.guardrails.check_cost(counters)

        return done
