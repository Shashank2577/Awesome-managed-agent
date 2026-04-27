# Event Taxonomy

All events are AtriumEvent instances with type, payload, and monotonic sequence number.

## Thread Lifecycle
| Event | Payload | When |
|---|---|---|
| THREAD_CREATED | objective, thread_id | Thread starts |
| THREAD_PLANNING | objective | Commander begins planning |
| THREAD_RUNNING | plan_id | Execution starts |
| THREAD_PAUSED | by | Operator pauses |
| THREAD_COMPLETED | thread_id | All done |
| THREAD_FAILED | error, thread_id | Unrecoverable error |
| THREAD_CANCELLED | thread_id | Operator cancelled |

## Plan Lifecycle
| Event | Payload | When |
|---|---|---|
| PLAN_CREATED | plan_id, plan_number, rationale, graph | Commander creates plan |
| PLAN_APPROVED | plan_id | Human approves (if require_approval=True) |
| PLAN_REJECTED | plan_id | Human rejects |
| PLAN_EXECUTION_STARTED | plan_id | Graph execution begins |
| PLAN_COMPLETED | plan_id | All agents done |

## Agent Lifecycle
| Event | Payload | When |
|---|---|---|
| AGENT_HIRED | agent_key, role, objective, depends_on | Plan includes this agent |
| AGENT_RUNNING | agent_key | Agent starts executing |
| AGENT_COMPLETED | agent_key | Agent finished successfully |
| AGENT_FAILED | agent_key, error | Agent threw exception |
| AGENT_MESSAGE | agent_key, text | Agent called self.say() |
| AGENT_OUTPUT | agent_key, output | Agent returned results |

## Commander
| Event | Payload | When |
|---|---|---|
| COMMANDER_MESSAGE | text, phase | Commander thinking/explaining |
| PIVOT_REQUESTED | rationale | Evaluator decides to pivot |
| PIVOT_APPLIED | added_agents | New agents added after pivot |

## Budget
| Event | Payload | When |
|---|---|---|
| BUDGET_RESERVED | currency, allocated, consumed, hard_limit | Thread starts |
| BUDGET_CONSUMED | currency, consumed, hard_limit | After LLM call |

## Evidence
| Event | Payload | When |
|---|---|---|
| EVIDENCE_PUBLISHED | headline, summary, findings, recommendations, chart | Final report |

## HITL
| Event | Payload | When |
|---|---|---|
| HUMAN_APPROVAL_REQUESTED | plan_id, message | Waiting for approval |
| HUMAN_INPUT_RECEIVED | input | Human provided input |
