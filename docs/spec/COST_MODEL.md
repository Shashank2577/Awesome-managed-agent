# COST_MODEL.md

## 1. Objectives

Define deterministic cost accounting to enforce budget constraints per thread.

---

## 2. Cost Components

Total thread cost =
- model inference cost
- tool execution cost
- infrastructure surcharge (optional)

### 2.1 Model Inference

For each model call:
- prompt token charge
- completion token charge
- optional reasoning token charge

### 2.2 Tool Cost

Per invocation:
- fixed fee (if configured)
- variable fee (usage/latency based)

---

## 3. Budget Lifecycle

Budget states:
- `active`
- `warning` (>= warning threshold)
- `exhausted` (hard limit reached)
- `closed`

Operations:
- reserve estimate before execution
- consume actual on completion
- release unused reservation

---

## 4. Deterministic Formulas

`estimated_cost = estimated_tokens_in * in_rate + estimated_tokens_out * out_rate + fixed_tool_fees`

`actual_cost = actual_tokens_in * in_rate + actual_tokens_out * out_rate + actual_tool_costs`

All amounts rounded to 6 decimal places.

---

## 5. Enforcement

- If reserve would exceed hard limit: reject dispatch.
- If consumed exceeds hard limit due to async overrun: immediate halt + terminate remaining queue claims.
- Emit budget events for reserve/consume/warning/exhausted.

---

## 6. Reporting

Expose at thread and instance levels:
- cumulative consumed
- reserved
- projected remaining
- top cost contributors

---

END
