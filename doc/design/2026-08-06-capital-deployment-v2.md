# DESIGN v2 — why 47 % sits in cash, and why v1 was wrong   (PR)

STATUS:   design — decided recommendations, none implemented. No production surface touched.
WHAT:     Replaces the "three separate defects" framing of orch#848 with a single
          measured causal chain, and names the one config value that is the
          dominant cause today.
WHY/DIR:  GOAL-5 P0, operator-escalated. orch#848 was written before three things
          were known: the in-flight blind spot (orch#866), that the oversized TSLA
          order actually FILLED (retraction on orch#854), and the sizing cascade
          measured below. Its Defect A treated `10 > 8` as an unchosen config
          value; it is a control failure.

EVIDENCE:
artifact:      `.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`,
               `.../renquant-pipeline/src/renquant_pipeline/kernel/{sizing.py,pipeline/task_selection.py}`,
               `data/runs.alpaca.db`, Alpaca account + filled-order API
prod or exp:   prod
existing data: orch#848 named three defects but decided none; orch#866 found the
               in-flight blind spot; orch#872 found all four count guards share it.
best-known?:   yes — the cascade below reproduces all six live 2026-08-04 orders to
               the logged precision.
scope:         this is the live book at equity $10,943 on 2026-08-06, prod, against
               no prior best — it is a mechanism claim, not a return claim. No IC,
               Sharpe or P/L improvement is asserted anywhere in this document.

## The chain, measured end to end

```
regime cap                                              12.00 %
  × confidence_to_size_multiplier(0.57)   HARD-CODED     6.84 %   ← always fires
  × conviction_multiplier                 0.28 … 1.00
  × sigma_multiplier                      0.55 … 1.00    (penalty only, ceiling 1.0)
  → int(target_$ / price)                                        ← up to 39 % lost
```

Replayed against the six live 08-04 orders, every realised % reproduces the logged
value: DDOG 2.62 %, SOFI 1.53 %, NVDA 1.93 %, GOOG 3.40 %, WELL 6.31 %, VLO 5.59 %.

**The 12 % regime cap never binds. Nothing has ever been sized against it.**

## The dominant cause is one stale config value

`conviction_multiplier` is configured `{floor: 0, ceiling: 0.3, min_mult: 0}` —
calibrated for the XGB `rank:pairwise` raw score scale (~0.02–0.15). The 2026-08-04
z-blend switch replaced `panel_score` with a z-composite. Measured on run
`2026-08-05-live-2d99f969`, n=94:

```
panel_score   min −2.657   med −0.036   max +4.053
  39.4 % of the universe  ≥ 0.30  → conviction = 1.00   (saturated)
  52.1 % of the universe  ≤ 0     → conviction = 0.00   → max_pct = 0 → UNBUYABLE
  ~8.6 % lands in the (0, 0.3) ramp
```

**Half the universe is unbuyable by arithmetic, not by decision.** A graded sizer
became a near-binary gate the moment the scorer's scale changed, and nothing
re-calibrated it.

## Two structural facts that make it permanent

1. **Entry weight is terminal.** `TopUpHeldTask` returns at `task_topup.py:130`
   because `kelly_sizing.enabled = false`, and `rotation.joint_actions.enabled = false`
   disables QP resizing. **No path can grow a position toward the cap.**
2. **The count cap binds before any value cap.** 10 held vs `max_concurrent_positions = 8`.
   The book is **slot-limited, not capital-limited**: 9 slots average 3.3 % against a
   12 % allowance, while TSLA alone holds 23.6 %.

## Why v1 (orch#848) was wrong

| orch#848 said | measured |
|---|---|
| "the slot cap is a NAME count, and its value was never chosen" | the value is not the problem — the book is **over** it because of the in-flight blind spot (orch#866) |
| Defect C: "TSLA is 23.5 % against a 12 % cap" — listed as a sizing-config question | TSLA **entered** at 23.4 % via the unclamped fallback and **filled** (orch#854 retraction); no rebalancer exists to trim it |
| three independent defects | one chain: stale conviction calibration → sub-1-share targets → either skip (cash) or fallback (oversize) |

## Recommendations, ordered by (effect ÷ risk)

| # | change | where | effect |
|---|---|---|---|
| **R1** | re-calibrate `sizing.ceiling` from `0.3` to the z-composite scale (e.g. p60–p80 of the live distribution) | strategy-104 config | restores conviction as a *graded* sizer; ends the 52 % unbuyable set |
| **R2** | subtract in-flight accepted-unfilled buys from `open_slots` | pipeline#269 | stops the book exceeding its own count cap |
| **R3** | expose `confidence_to_size_multiplier`'s floor as config | pipeline | 43 % is currently removed by a hard-coded mapping with no knob |
| **R4** | give the book a rebalancer, or re-enable one | strategy-104 | today entry weight is terminal and TSLA can only be trimmed by an exit |

**R1 is the highest-leverage and the cheapest.** It is a config value, it is provably
mis-scaled, and it gates half the universe.

## What I am NOT recommending

- **Not raising `max_concurrent_positions`.** The book is over the current cap; raising
  it hides the control failure R2 fixes.
- **Not enabling fractional shares or the one-share floor.** Both are deliberately off
  with documented preconditions; flooring is second-order (median 5.5 % of budget lost)
  and does not explain the 12 % → 6.84 % collapse.
- **No number for expected return.** Nothing here estimates whether deploying the idle
  47 % would make or lose money. That is a separate question and this document does
  not touch it.

NEXT:     R1 needs the live z-composite percentile distribution frozen as evidence
          before a value is chosen — a prereg-style step, not a guess. R2 is
          pipeline#269. Both are repo-boundary changes requiring operator authorisation.
