# 2026-08-05 — a zero-risk reproduction for the P0, and one more number

STATUS:   delivered.
WHAT:     ships `ops/renquant104/trace_sizing_preflight.py` (4 tests), which traces every
          `compute_position_size` call (args + return) during the dry-run dawn preflight so the
          effective `max_pct` is observed, not inferred; shows the same formula reproduces exactly
          on 2026-08-05 (3/3) and misses by up to 140x on 2026-08-03 (0/3), always oversizing the
          weakest candidates.
WHY/DIR:  P0 sizing-twin follow-up (goal5) — proves the defect is observable without touching
          money (the dry-run dawn preflight reproduces the same oversized decisions the live
          07-28 orders showed) and refutes the earlier "sub-one-share" hypothesis: PYPL at $57.21
          was oversized too, nowhere near the sub-share region.
EVIDENCE: on 08-03, one constant target notional ([$2,689, $2,713), ~25% of PV) explains all three
          oversized fills (AMZN 9@$271.32, MRK 20@$130.22, PYPL 47@$57.21) across conviction 0.03
          to 0.37; on 08-05, the same `max_pct = regime_cap(0.12) x confidence(0.57) x conviction x
          sigma_mult` formula matches actual share counts exactly for APH/ROST/GRMN (conviction
          saturated at 1.00 on strong candidates). GOOG's low 3.3% allocation is corrected from an
          earlier claim of "conviction applied" to cash-starvation (`remaining_cash=$615` after
          the other 3 orders spent 97% of available cash). `[VERIFIED — this session, dawn
          preflight logs + traced sizer run this session]`
NEXT:     the tracer is caveated — sizing is only reached with an open funnel slot, so an
          instrumented run on a full book legitimately traces nothing; the fuller root cause is
          filed under orch#854 (P0 sizing-twin missing clamp), which this reproduction supports
          with independent evidence.

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

## The formula fits one day PERFECTLY and misses the other by 100×

`max_pct = regime_cap(0.12) × confidence(0.57) × conviction × sigma_mult`,
applied to two consecutive preflight days `[推导 — on VERIFIED log values]`:

**2026-08-05** — calibrated scores **+3.54 / +1.62 / +1.46**, conviction **1.00**:

| name | max_pct | target | intended | ACTUAL |
|---|---:|---:|---:|---:|
| APH | 0.0404 | $444 | **2** | **2** ✓ |
| ROST | 0.0609 | $670 | **2** | **2** ✓ |
| GRMN | 0.0486 | $534 | **1** | **1** ✓ |

**Three for three.** The sizing stack is correct and reproduces exactly.

**2026-08-03** — calibrated scores **+0.586 / +0.567 / +0.561**, conviction
**0.37 / 0.11 / 0.03**:

| name | max_pct | target | intended | ACTUAL |
|---|---:|---:|---:|---:|
| AMZN | 0.0220 | $237 | **0** | **9** ✗ |
| MRK | 0.0075 | $81 | **0** | **20** ✗ |
| PYPL | 0.0018 | $19 | **0** | **47** ✗ |

Same formula, same regime, same confidence. **Zero for three**, off by up to
**140×** on notional.

### What separates the two days

The candidates. On 08-05 they were **strong** (calibrated ≫ 1 → conviction
saturates at 1.00) and the sizer worked. On 08-03 they were **weak**
(calibrated ≈ 0.56 → conviction 0.03–0.37) and the sizer was bypassed, each
name taking ~25 % of the book.

> **The weaker the candidate, the larger the position it received.**

That is precisely backwards, and it is now demonstrated rather than inferred:
one formula, two days, three-for-three on one and zero-for-three on the other.

### One correction to my previous reading

I wrote that GOOG (conv = 0.03, 3.3 %) proved conviction was being applied
somewhere. It does not: `remaining_cash` was **$615** by GOOG's turn — after
AMZN, MRK and PYPL had taken $8,092 of the $8,350 available. **GOOG was
cash-starved, not correctly sized.** The four orders spent **97 % of available
cash**.

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
