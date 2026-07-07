# 2026-07-06 — Concentration cap research proposal

**PR**: research design for asymmetric concentration management

## What

Design document proposing a parameter sweep to determine whether entry sizing
cap (`max_concentration`) should differ from drift tolerance, and whether
`top_up_threshold` is calibrated correctly at the current 12% cap level.

## Why

MU at 9.2% weight, model rank=0.617, er=+4.59% — but TopUp blocked because
`kelly_target(12%) - current(9.2%) = 2.8% < threshold(5%)`. The 12% cap was
set by operator mandate without A/B evidence. Prior research covered σ-horizon
(inert) and trim on/off (OFF wins), but never the cap level itself or the
entry/drift asymmetry.

## Scope

- Design doc only — no code changes in this PR
- Proposes: 3D parameter sweep (entry_cap × drift_buffer × topup_threshold)
- Builds on existing findings: σ-horizon A/B (06-03), trim A/B (04-24)
- Execution requires 1 pipeline PR (drift_buffer config) + 1 sweep script

## Round 2 (codex review)

STATUS: fixed
WHAT: codex found four gaps in the experiment contract — (1) the sweep
confounded "does entry ≠ drift cap help" with "does redefining the trim
trigger's functional form help" by swapping the incumbent's
`kelly_target + trim_threshold` for an unrelated absolute
`drift_concentration_cap`; (2) the promotion gate only checked BULL_CALM,
so a config could win the primary regime while quietly regressing the
full book or the worst regime; (3) the seed rule said ">=3 seeds each"
with no frozen seed set or aggregation rule; (4) transaction-cost/churn
metrics were mentioned in the decision rule's prose ("net of transaction
costs") but not required as reported outputs, making that clause
unenforceable.
WHY-DIR: this sizing/concentration change affects whole-book risk posture,
so the promotion contract needs the same rigor this repo already applies
to other frozen gates (seed unanimity, full-period + worst-regime checks)
rather than a narrower one-regime bar.
EVIDENCE: (1) introduced `drift_buffer` — swept in the exact same
arithmetic slot `trim_threshold` already occupies (`kelly_target +
drift_buffer`), so only parameter values vary, never the trigger's
mechanics; `drift_buffer=∞` reproduces today's trim-OFF behavior exactly.
(2) added full-period (±0.02 materiality band, matching this repo's own
seed-noise convention from `d3-core-shrink-check.md`) and worst-regime
(Sharpe + MaxDD, evaluated against the incumbent's own weakest regime)
no-material-regression criteria to the decision rule. (3) froze the seed
set to `{42, 43, 44}` (matching this repo's standard triple) with an
explicit unanimity verdict rule — all 3 seeds must independently clear
every criterion, no mean/median pooling. (4) promoted turnover, fill
count, and cost-delta-vs-incumbent to required per-config outputs; made
decision-rule criterion 1 explicitly net-of-cost (not gross with cost as
a footnote); added a turnover-ceiling criterion (≤125% of incumbent) so a
win can't come from a cost model blind spot plus 3x the churn.
NEXT: none — ready for operator review / fresh codex pass.

## Round 3 (codex review)

STATUS: fixed
WHAT: codex confirmed the intervention isolation, seed freeze, and cost/churn
clause are all now sound, then found one remaining gap: criterion 4's
worst-regime check was anchored to whichever regime was the INCUMBENT's
historical worst (e.g. BEAR), so a candidate could hold that regime flat,
improve BULL_CALM, and materially damage a *different* regime (e.g.
BULL_VOLATILE) that was never the incumbent's weakest bucket — and still
clear the gate, since only the incumbent's worst regime was checked.
WHY-DIR: this repo's regime taxonomy for this study is exactly three buckets
(BULL_CALM, BEAR, BULL_VOLATILE) — small enough that checking all three
individually is not over-restrictive, and it is the more direct closure of
the gap than a worst-vs-worst or supplementary-clause alternative (codex's
options 2 and 3).
EVIDENCE: rewrote criterion 4 to require no-material-regression checked on
EVERY regime individually — candidate Sharpe in each of {BULL_CALM, BEAR,
BULL_VOLATILE} ≥ incumbent Sharpe in that SAME regime − 0.02, and candidate
MaxDD in that regime ≤ incumbent MaxDD in that same regime × 1.10. Walked
through codex's exact example: incumbent's worst = BEAR; candidate holds
BEAR flat (passes), improves BULL_CALM (passes, also covered by criterion
1), damages BULL_VOLATILE (now FAILS the BULL_VOLATILE-specific check,
whereas the old incumbent-worst-only gate would have missed this entirely
since BULL_VOLATILE was never the incumbent's weakest bucket). Also
rebased onto main (branch had fallen behind — clean merge, no conflicts,
this PR only touches `doc/` files).
NEXT: none — ready for operator review / fresh codex pass.
