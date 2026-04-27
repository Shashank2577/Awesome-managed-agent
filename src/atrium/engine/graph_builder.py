"""Converts a Commander Plan into a LangGraph StateGraph."""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from atrium.core.models import Plan
from atrium.core.registry import AgentRegistry
from atrium.engine.callbacks import (
    emit_agent_completed,
    emit_agent_failed,
    emit_agent_running,
)
from atrium.streaming.events import EventRecorder


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

        try:
            output = await agent.run(agent_input)
            await emit_agent_completed(recorder, thread_id, agent_name, output)
        except Exception as exc:
            await emit_agent_failed(recorder, thread_id, agent_name, str(exc))
            output = {"error": str(exc)}

        new_outputs = dict(state.get("agent_outputs", {}))
        new_outputs[agent_name] = output
        return {"agent_outputs": new_outputs}

    return node_fn


def build_graph_from_plan(
    plan: Plan,
    registry: AgentRegistry,
    recorder: EventRecorder,
):
    """Compile a Plan into a LangGraph StateGraph."""
    graph: StateGraph = StateGraph(ThreadState)

    # Register a node for every step
    for step in plan.steps:
        node_fn = build_agent_node(step.agent, registry, recorder, plan.thread_id)
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

    return graph.compile()
