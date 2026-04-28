# Managed Agent Replacement — Plan & Architecture

This folder contains the plan, the code review, and the architectural specification
for turning Atrium into a complete, self-hosted replacement for Anthropic's Claude
Managed Agents service.

## Read in this order

1. [`00-goals-and-non-goals.md`](./00-goals-and-non-goals.md) — what we are and aren't
   trying to replace, and the explicit success criteria.
2. [`01-code-review.md`](./01-code-review.md) — honest review of the current Atrium
   codebase. What's good, what's broken, what needs to change before the harness
   work begins.
3. [`02-gap-analysis.md`](./02-gap-analysis.md) — feature-by-feature comparison
   against Claude Managed Agents and what's missing.
4. [`03-target-architecture.md`](./03-target-architecture.md) — the end-state
   architecture with the harness layer added, including all module boundaries.
5. [`04-harness-integration.md`](./04-harness-integration.md) — exactly how the
   harness package plugs into Atrium. Where files go, what each one does.
6. [`05-api-surface.md`](./05-api-surface.md) — the full external API surface
   so other systems and UIs can connect, including widget endpoints.
7. [`06-roadmap.md`](./06-roadmap.md) — phased delivery plan with concrete
   milestones, ordered by dependency and risk.
8. [`07-decision-log.md`](./07-decision-log.md) — design decisions made during
   this planning round, with the alternatives considered and the rationale.

## TL;DR

Atrium today is a solid **multi-agent DAG orchestrator**. It is not yet a
**single-agent harness** of the kind Claude Managed Agents provides. The plan
adds a `harness` package that wraps an open-source Claude-Code-equivalent loop
(Open Agent SDK or OpenClaude) inside a Docker sandbox, exposes it as a
first-class Atrium agent, and wires the inner harness events back into the
existing event stream and dashboard. Once that lands, Atrium becomes the
*outer* orchestrator and the harness is the *inner* execution engine — together
they fully replace Managed Agents and are model-agnostic by design.

The hard work is not the harness itself (good open-source ones exist). The hard
work is the integration: sandbox lifecycle, session filesystem, event bridging,
MCP gateway, multi-tenant isolation, and a stable external API. The roadmap
walks through this in five phases over roughly 6–8 focused weeks.
