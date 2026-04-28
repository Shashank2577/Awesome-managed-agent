"""Converts a Commander Plan into a LangGraph StateGraph."""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Optional, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from atrium.core.models import Plan
from atrium.core.registry import AgentRegistry
from atrium.engine.callbacks import (
    emit_agent_completed,
    emit_agent_failed,
    emit_agent_running,
)
from atrium.engine.retry_utils import async_retry_agent
from atrium.streaming.events import EventRecorder


class FailPolicy(str, Enum):
    STOP_THREAD = "stop_thread"   # raise; the orchestrator marks thread FAILED
    CONTINUE = "continue"         # current behaviour: return {"error": ...}
    RETRY_STEP = "retry_step"     # retry up to max_attempts, then stop_thread


def _merge_dicts(a: dict, b: dict) -> dict:
    """Merge two dicts, with *b* winning on key conflicts."""
    return {**a, **b}


class ThreadState(TypedDict):
    """State passed through the LangGraph execution."""

    inputs: dict[str, dict[str, Any]]
    agent_outputs: Annotated[dict[str, dict[str, Any]], _merge_dicts]


def build_agent_node(
    agent_name: str,
    registry: AgentRegistry,
    recorder: EventRecorder,
    thread_id: str,
    guardrails=None,
    fail_policy: FailPolicy = FailPolicy.STOP_THREAD,
    max_attempts: int = 3,
):
    """Create a LangGraph node function that runs an Atrium agent."""

    async def node_fn(state: ThreadState) -> dict:
        agent = registry.create(agent_name)

        # Wire emitter so agent.say() works
        async def emitter(event_type: str, payload: dict, causation: str | None = None) -> None:
            await recorder.emit(thread_id, event_type, payload, causation_id=causation)

        agent.set_emitter(emitter)

        # Build input: direct inputs for this agent, plus upstream outputs
        agent_input = dict(state.get("inputs", {}).get(agent_name, {}))
        upstream = state.get("agent_outputs", {})
        if upstream:
            agent_input["upstream"] = dict(upstream)

        await emit_agent_running(recorder, thread_id, agent_name)

        async def run_once() -> dict:
            return await agent.run(agent_input)

        try:
            if fail_policy == FailPolicy.RETRY_STEP:
                output = await async_retry_agent(run_once, max_attempts=max_attempts)
            else:
                output = await run_once()
            await emit_agent_completed(recorder, thread_id, agent_name, output)
        except Exception as exc:
            await emit_agent_failed(recorder, thread_id, agent_name, str(exc))
            if fail_policy == FailPolicy.STOP_THREAD:
                raise   # caller (orchestrator) will catch and mark thread FAILED
            output = {"error": str(exc)}

        new_outputs = dict(state.get("agent_outputs", {}))
        new_outputs[agent_name] = output
        return {"agent_outputs": new_outputs}

    return node_fn


def build_graph_from_plan(
    plan: Plan,
    registry: AgentRegistry,
    recorder: EventRecorder,
    checkpointer_db: Optional[str] = None,
    fail_policy: FailPolicy = FailPolicy.STOP_THREAD,
    guardrails=None,
):
    """Compile a Plan into a LangGraph StateGraph."""
    graph: StateGraph = StateGraph(ThreadState)

    # Register a node for every step
    for step in plan.steps:
        node_fn = build_agent_node(
            step.agent,
            registry,
            recorder,
            plan.thread_id,
            guardrails=guardrails,
            fail_policy=fail_policy,
        )
        graph.add_node(step.agent, node_fn)

    # Wire edges: roots connect from START
    roots = [s for s in plan.steps if not s.depends_on]
    for root in roots:
        graph.add_edge(START, root.agent)

    # Dependency edges
    for step in plan.steps:
        for dep in step.depends_on:
            graph.add_edge(dep, step.agent)

    # Leaf nodes (not depended upon by anything) connect to END
    depended_on = {dep for s in plan.steps for dep in s.depends_on}
    leaves = [s for s in plan.steps if s.agent not in depended_on]
    for leaf in leaves:
        graph.add_edge(leaf.agent, END)

    if checkpointer_db:
        checkpointer = SqliteSaver.from_conn_string(checkpointer_db)
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()
