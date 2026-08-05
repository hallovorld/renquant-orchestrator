# 2026-08-05 — P0 SOLVED: the umbrella's sizing twin has the fallback but not its clamp

## Root cause

`compute_position_size` exists **twice**:

| copy | used by | has the 25 % fallback | has the clamp |
|---|---|---|---|
| `RenQuant/backtesting/renquant_104/kernel/sizing.py` | **`live.runner` — the live book** | ✅ | ❌ |
| `renquant-pipeline/.../kernel/sizing.py` | the reviewed pipeline | ✅ | ✅ |

Both contain an **oversize fallback**: when the sized target buys less than one
whole share, try `0.25 * portfolio_value` instead. The pipeline copy then puts
it back under the cap:

```python
cap_shares = int(target_dollars / price)
if shares > cap_shares:
    shares = cap_shares          # -> 0 when the target is sub-one-share
```

The clamp landed in the pipeline on **2026-07-03 (`6de6219`)**. **The umbrella
twin never received it** `[VERIFIED — the string `cap_shares` does not appear in
that file]`.

## Consequence

Any candidate whose target buys **less than one share** is silently allocated
**25 % of the portfolio** — regime cap, Kelly target, conviction and σ all
bypassed.

And the trigger is **inverted with respect to conviction**: the weaker the
candidate, the smaller its target, the more likely it falls under one share —
so **the weakest candidates receive the largest positions.**

## Reproduced 7 / 7 `[VERIFIED — this session]`

Feeding the umbrella copy the inputs recorded on the orders themselves:

| date | name | umbrella copy says | actually placed |
|---|---|---|---|
| 07-28 **LIVE** | TSLA | **8** (23.4 %) | **8** ✓ |
| 07-28 **LIVE** | EME | **3** (21.1 %) | **3** ✓ |
| 07-28 **LIVE** | SPG | **1** (2.2 %) | **1** ✓ |
| 08-03 dry-run | AMZN | **9** (22.7 %) | **9** ✓ |
| 08-03 dry-run | MRK | **20** (24.2 %) | **20** ✓ |
| 08-03 dry-run | PYPL | **47** (25.0 %) | **47** ✓ |
| 08-03 dry-run | GOOG | **1** (3.3 %) | **1** ✓ |

The **same inputs through the pinned copy** give `0, 0, 1 / 0, 0, 0, 1`.

**That is why five rounds of reproduction failed: I was running the fixed twin.**
Every "impossible" result was correct — about the wrong file.

SPG is the control that makes it airtight: its target bought a whole share, the
fallback never fired, and **both copies agree on 1**. That is exactly why one of
the three orders that day was correctly sized.

## Scope of the divergence

Over an 864-case grid `[VERIFIED]`: **191 divergent**, worst notional gap
**$24,940**, largest umbrella allocation **24.9 % of portfolio value**. In every
divergent case the umbrella sizes **larger** — the defect has one direction, and
a test pins that so a reverse divergence cannot be folded silently into this
record.

## What lands here, and what does NOT

`ops/renquant104/sizing_twin_conformance.py` — compares the two implementations
over the grid and **fails on any divergence**. Plus 11 tests, including each
live order reproduced by name, the pinned copy refusing them, and an assertion
on the *source* that the clamp is present in one file and absent in the other.

**The fix itself is one line in the umbrella**, and this repo does not write to
the umbrella. The exact change:

```python
# RenQuant/backtesting/renquant_104/kernel/sizing.py, after the MIN-1-SHARE block
cap_shares = int(target_dollars / price)
if shares > cap_shares:
    shares = cap_shares
if shares < 1:
    return 0.0, 0
```

i.e. **port `6de6219` into the twin** — or better, delete the twin and import
the pipeline's. The twin is the disease; the missing clamp is only this
instance of it.

## The wider finding

This is the **twin-implementation** defect (GOAL-3, orch#833) landing on the
money path. A fix reviewed and merged in one copy simply did not reach the copy
that trades. Every guard in this repo that reasons about "the pinned code" was
reasoning about a file the live runner does not import.

Suites: 11 tests · full suite green.
