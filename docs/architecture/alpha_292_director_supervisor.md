# ATLAS ZERO Alpha 2.9.2 — Director Supervisor

## Fixed architectural rule

Director AI is the only component allowed to issue the final project decision.

The kernel:
- executes modules;
- resolves dependencies;
- manages cache and state;
- reports results.

The Director Supervisor:
- evaluates aggregated runtime results;
- issues `APPROVE`, `REWORK`, `REJECT`, or `ESCALATE`;
- requests targeted recomputation;
- records every decision and its reason.

## Deliberately excluded from Alpha 2.9.2

To avoid premature complexity, this release does **not** introduce:
- Director Council;
- multiple internal director agents;
- autonomous self-learning;
- event bus;
- persistent long-term memory.

`DecisionLog` is only an append-only foundation for future Director Memory.

## Runtime contract

The supervisor depends on one minimal interface:

```python
runtime.run(targets: Sequence[str] | None) -> Any
```

## Rework safety

Repeated rework is bounded by `max_rework_cycles`.
When the limit is reached, the supervisor emits `ESCALATE` instead of looping indefinitely.
