# The deployment knobs, swept — λ is dead; the levers are min_invested × turnover cap

The measured answer to "which reviewed change lets the QP deploy capital",
run 2026-08-09 on real run inputs. Derivation = the committed
`scripts/poc_lambda_sweep.py` machinery with three run-scoped repairs
(zero-width guard; usable-candidate run selection — the orch#931 sigma
drift makes every post-05-21 live run UNUSABLE for this sweep; threshold
60), committed as `data/2026-08-09-deployment-knob-sweep-derivation.py`
with raw output `…-deployment-knob-sweep.json`.

## Result `[VERIFIED — committed JSON; 4 usable runs, 2026-05-18..21, the last full-featured era]`

| scenario | λ=0 | λ=0.01 | λ=0.02 | λ=0.05 | λ=0.1 |
|---|---|---|---|---|---|
| A production (min_inv=0), mean deployed | 0.706 | 0.706 | 0.706 | 0.706 | 0.706 |
| C min_inv ON, loose turnover cap | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

2D (min_inv ON): deployed = 0.706 / 0.755 / 0.856 / 1.000 at turnover cap
0.15 / 0.2 / 0.3 / 0.5 — **identical at every λ**.

1. **λ (qp_cash_drag_lambda) has zero measurable effect at any tested
   value in any scenario** — the min_invested CONSTRAINT dominates the λ
   objective term wherever both act. The #942 framing "λ=0 is the last
   lock" is corrected: the lock is `qp_min_invested_pct = 0`; λ is
   decoration on these inputs.
2. **The lever pair is min_invested_pct (on-switch) × turnover cap
   (throttle)**: switching min_invested on moves deployment 0.706 → 1.0
   under a loose cap; the turnover cap then sets the pace monotonically.
3. **The orch#931 serving drift caps the evidence**: no run after
   2026-05-21 carries the mu/sigma the solver needs — the producer fix is
   a hard prerequisite for ANY current-data deployment evidence.

## What this does not decide

The 2026-05-23 re-enable condition stands verbatim ("re-enable only after
WF shows benchmark-relative alpha survives the strict admission gate") —
this sweep prices the MECHANICS, not the alpha evidence; the committed
script's own scope note stands (simplified constraints, per-name cap only;
the in-pipeline 10-session shadow sweep remains the enable-gating AC).
Proposal shape for when the evidence lands: min_invested restored to its
historical value with turnover cap 0.2-0.3 as the pace dial — a
strategy-104 config PR, one reviewed change.
