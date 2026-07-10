# Cash drag binding constraints — updated analysis

**Date**: 2026-07-09
**Status**: Research memo; no behavior change

## Bottom line

Diagnostic evidence memo (working diagnosis, hypotheses pending replay) for the
60-70% cash drag on $10.7k equity. Revised per Codex r1/r2: outage/fallback days
separated from normal-flow days, rotation claims restated on candidate-minus-incumbent
net advantage, sequential funnel rates labeled non-causal. Knob-level Lane A framing
retired — evidence now feeds the sizing-architecture redesign (Deployment Governor
RFC, in progress). Tactical knob PRs #47/#48 (strategy-104) closed as superseded.

## Changes

- `doc/research/2026-07-09-cash-drag-binding-constraints-update.md` — diagnostic
  funnel evidence (8 normal-flow + 3 outage days split), net_adv distribution from
  ROTATION_TREE logs, QP dead-code finding, supersession disposition

## Key findings (hypothesis status unless marked)

1. [VERIFIED] A-1 (`qp_cash_drag_lambda`) is dead code — QP path disabled in production
2. [VERIFIED] Average cash 65% on the 8 normal-flow days (survives the outage split)
3. VetoWeakBuys adaptive floor (mean+1σ≈0.575) shows 75-80% sequential attrition —
   marginal deployment effect unmeasured (needs end-of-chain replay)
4. 0 rotations in 6 eligible days; max observed net_adv 0.043 < threshold 0.06; on
   3 of 6 days tax drag or tiny edge (not the threshold) was binding
5. Whole-share quantization blocked 2 of top-3 slots on 07-02 (BLK $995, AVGO $360)
6. Structural root: no component owns the deployment decision — bottom-up
   multiplicative sizing with no portfolio-level capital target

## Context

Also this session: tournament retrain completed (142/142 CERTIFIED, 0 timeout,
`live_train_end=2026-06-23`). Tomorrow's daily-104 staleness gate will pass,
restoring candidate generation. Structural cash drag remains.
