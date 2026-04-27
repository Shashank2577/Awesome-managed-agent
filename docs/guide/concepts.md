# Core Concepts

## Thread

A Thread is a single execution of a user objective from start to finish. When you submit "Research the top 3 cloud providers and compare pricing", Atrium creates a Thread with a unique ID, runs the Commander to plan it, executes the agents, and ends in a terminal state: `COMPLETED`, `FAILED`, or `CANCELLED`. All events, agent outputs, and budget usage are attached to the Thread. Threads are persisted in SQLite, so they survive server restarts and can be replayed in the dashboard.

## Agent

An Agent is a Python class that does one thing well. It has a name, a description, a list of capabilities, and a `run()` method. The framework knows nothing about what an agent does internally — it just calls `run(input_data)` and expects a `dict` back. Agents can call external APIs, run LLMs, query databases, or do pure computation. The key constraint is that they are stateless across runs: all input comes in through `input_data`, all output goes out through the return value.

## Plan

A Plan is the Commander's output: a structured list of steps that maps agents to a specific execution order with declared dependencies. Each step names an agent, provides its inputs, and lists which other steps it depends on. Steps with no dependencies run in parallel. The Plan is visible in the dashboard as a DAG (directed acyclic graph) where nodes update color in real-time as agents start, complete, or fail.

## Commander

The Commander is Atrium's LLM-powered planner. It reads the registry of available agents (their names, descriptions, capabilities, and schemas) and the user's objective, then generates a Plan. After all agents complete, the Commander evaluates the outputs and decides whether to finalize — synthesizing a report — or to Pivot and re-plan. The Commander never executes code itself; it only decides what to run and in what order.

## Pivot

A Pivot is when the Commander decides, after reviewing agent outputs, that the current results are insufficient and a new round of planning is needed. The Commander issues a revised Plan with different or additional agents, and execution restarts. Pivots are bounded by `GuardrailsConfig.max_pivots` (default: 2) to prevent runaway loops. Each pivot is visible in the dashboard as a "Pivot Requested" event with the Commander's reasoning.

## Guardrails

Guardrails are hard limits that protect against runaway execution. Five independent checks run continuously: maximum number of agents spawned in a thread, maximum agents running in parallel at once, maximum total wall-clock time, maximum LLM cost in USD (Commander calls only), and maximum number of pivots. Any violation raises a `GuardrailViolation`, immediately halts execution, emits a `BUDGET_EXCEEDED` event, and marks the Thread `FAILED`. Guardrails are configured per-application via `GuardrailsConfig`.

## Event Stream

The Event Stream is the append-only log of everything that happens inside a Thread. Every agent start, completion, failure, LLM call, pivot, and human action emits a typed event with a payload, sequence number, and timestamp. Events are persisted to SQLite as they're emitted and streamed to the dashboard via Server-Sent Events (SSE). The event stream is the source of truth for the Thread's history — the dashboard is a real-time view of it.

## Dashboard

The Dashboard is Atrium's built-in web UI, served at `/dashboard`. It shows registered agents, active and historical threads, the live event feed for each thread, the plan DAG with real-time status updates, agent thought streams (from `self.say()` calls), and budget consumption. It also provides human-in-the-loop controls: pause, resume, cancel, approve, and reject. No configuration needed — it's available as soon as you run `app.serve()`.
