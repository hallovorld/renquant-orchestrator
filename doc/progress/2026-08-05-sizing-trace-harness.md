# 2026-08-05 — a zero-risk reproduction for the P0, and one more number

## Why a harness instead of an answer

Four rounds of static analysis could not reproduce the 2026-07-28 oversized
buys. Every value recorded on the trade rows — `max_pct`, conviction,
`sigma_mult`, portfolio value, cash, the Kelly flag — is **internally consistent
and yields zero shares** through the deployed `compute_position_size`. Three of
my own hypotheses died against evidence already on disk.

The thing that broke the deadlock was not more arithmetic. It was `grep` over
`logs/`.

## The dawn preflight reproduces it, and places nothing

`logs/rq104/dawn_funnel_preflight_*.log` — a scheduled dry run whose own
attestation is `{"ordered": false, "persisted": false, "notified": false}` —
shows the same oversized decisions on **07-27, 07-28, 08-03 and 08-04**
`[VERIFIED]`:

```
08-03  AMZN   9 sh @ 271.32  ($2442, 22.7 %, conv=0.37)
08-03  MRK   20 sh @ 130.22  ($2604, 24.2 %, conv=0.11)
08-03  PYPL  47 sh @  57.21  ($2689, 25.0 %, conv=0.03)
08-03  GOOG   1 sh @ 356.45  ($ 356,  3.3 %, conv=0.03)
```

**So the defect is observable without touching money.**

## One more number, and it kills the "sub-one-share" theory too

Solving the floor arithmetic for a single target notional consistent with all
three oversized 08-03 fills `[推导 — exact, on VERIFIED fills]`:

| name | fill | implied target notional |
|---|---|---|
| AMZN | 9 @ $271.32 | `[$2,442, $2,713)` |
| MRK | 20 @ $130.22 | `[$2,604, $2,735)` |
| PYPL | 47 @ $57.21 | `[$2,689, $2,746)` |
| **intersection** | | **`[$2,689, $2,713)` ≈ 25.0–25.2 % of PV** |

**One constant target notional explains all three** — across prices from $57 to
$271 and conviction from **0.03 to 0.37**.

That refutes my own "sub-one-share" characterisation from two rounds ago: PYPL
at $57.21 is nowhere near the sub-one-share region, and it was oversized anyway.
And it shows conviction is **not being applied at all** on that path — GOOG, at
the *same* conv=0.03, got 3.3 %.

## What lands

`ops/renquant104/trace_sizing_preflight.py` — runs the preflight with every
`compute_position_size` call traced (arguments **and** return), so the effective
`max_pct` at the emit site is *observed* rather than inferred.

**Caveat, stated because it bit me immediately:** sizing is only reached when
the funnel has an **open slot**. Today the book was full, so the instrumented
run reached its decision without calling the sizer and the trace was
legitimately empty. That is not a harness failure — but the answer arrives on
the next day with an open slot, not on demand.

I also wrote the tracer wrong first: I patched a module attribute that does not
exist, assuming `task_selection` bound the symbol at import time. It imports it
**inside `run()`**, so patching the defining module is sufficient. A test now
asserts that, and fails if the import ever moves to module scope — because **a
tracer that silently traces nothing is the same failure as a guard that silently
passes.**

Suites: 4 tests · full suite green.
