# 02 — Gap Analysis vs Claude Managed Agents

A feature-by-feature comparison of what Anthropic's Managed Agents service
provides against what Atrium provides today.

## Legend

- ✅ Fully present and working in Atrium today.
- 🟡 Partially present — the bones exist but it's not production-ready.
- ❌ Absent — needs to be built.
- N/A — Atrium has chosen a different model.

## Comparison

| Capability | Managed Agents | Atrium today | Action |
|------------|---------------|--------------|--------|
| Stateful container per session | Yes | ❌ | Build `harness` package + Docker runner |
| Bash tool | Yes | ❌ | Provided by inner SDK (Open Agent SDK / OpenClaude) |
| File read/write/edit | Yes | ❌ | Provided by inner SDK |
| Web fetch | Yes | 🟡 (HTTP agent) | Provided by inner SDK; can also wrap as Atrium agent |
| Code execution | Yes | ❌ | Provided by inner SDK |
| MCP client | Yes | ❌ | Add to harness; expose Atrium-side MCP gateway |
| Computer use | Yes | ❌ | Out of scope for v1 |
| Long-running session (hours) | Yes | ❌ | Requires checkpoint + resume + persistent thread store |
| Resumable after restart | Yes | ❌ | Event log persists, thread record doesn't — fix in phase 1 |
| Per-session filesystem | Yes | ❌ | Mount per-session volume into harness container |
| Context compaction | Yes (model-tuned) | ❌ | Use inner SDK's compaction |
| Prompt caching | Yes (Claude-only) | 🟡 (provider-dependent) | Pass through when available |
| Streaming events | Yes | ✅ | Already SSE |
| Plan visualization | Limited | ✅ | Already a DAG view |
| HITL pause/resume/cancel | Yes | ✅ | Already implemented |
| HITL approval gates | Yes | ✅ | Already implemented |
| Cost guardrails | Yes (per-session-hour billing) | 🟡 (defined, not enforced) | Wire real token tracking + container-time tracking |
| Time guardrails | Yes | 🟡 (defined, not enforced) | Wire wall-clock check + container kill |
| Multi-agent | Research preview only | ✅ | Atrium's Commander/DAG is its first-class model |
| Multi-model | No (Claude only) | ✅ | Atrium is multi-provider by design |
| External API for sessions | Yes | 🟡 (threads exist) | Rename + extend; add /sessions, /artifacts, /messages |
| External webhook delivery | Yes | ❌ | Add webhook config + delivery worker |
| Embeddable widgets | No | ❌ | Build widget endpoints (live feed, plan, budget, report) |
| Auth / API keys | Yes | ❌ | Add API key middleware in phase 1 |
| Multi-tenant isolation | Yes (Anthropic-managed) | ❌ | Workspace scoping, per-tenant registries |
| Tracing / observability | Yes | 🟡 | Event log is good; add OpenTelemetry export |
| On-prem deployment | No (Anthropic cloud only) | ✅ | This is one of our headline advantages |
| Data residency control | Limited | ✅ | We control the deployment |
| Session cost (excl. tokens) | $0.08/session-hour | Free + container time | Headline cost win |

## What this tells us

Atrium has **already built the harder half** of what people think of as the
"managed agents" experience: the dashboard, the event stream, the plan DAG,
HITL controls, multi-provider support, persistence (mostly), and a clean
extensibility model. These are the parts that are tedious to build well.

What it lacks is the **inner agent loop** — the long-running, sandboxed,
tool-using loop that Claude Managed Agents wraps a single Claude in. That
loop is exactly what Open Agent SDK and OpenClaude already provide. The work
is integration, not invention.

The other thing it lacks is **production polish**: real auth, real
multi-tenancy, real budget enforcement, real retry, real artifact storage.
These need to land before the harness is useful externally, but they're
tractable, well-understood problems.

## Why this works strategically

The combination of Atrium's existing strengths with a harness layer produces
something Anthropic's service genuinely cannot match:

1. **Multi-agent DAGs that include single-agent harness sessions.** A
   Commander can decide to spin up a harness for the "research the codebase"
   step while running a parallel HTTP agent for the "fetch the latest PR
   comments" step. Managed Agents does not do this.
2. **Model-portable harness sessions.** Same harness configuration runs on
   Claude, GPT, Gemini, or local models. Switch by changing config.
3. **Embeddable widgets.** Other internal Taazaa products (CIVI dashboard,
   Master CRM) can drop in a live event feed widget pointing at an Atrium
   session. Managed Agents has no embed surface.
4. **On-prem.** CIVI cannot use a cloud-only service. Atrium can run inside
   the City of Dublin's network or on Taazaa's EKS without data leaving the
   tenancy.

The replacement isn't 1:1; it's better-fit for our actual workload because
we're not bound to Anthropic's product decisions about what an "agent"
should look like.
