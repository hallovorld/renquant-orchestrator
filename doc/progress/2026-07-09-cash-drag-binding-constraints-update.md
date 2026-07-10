# Cash drag binding constraints — updated analysis

**Date**: 2026-07-09
**Status**: Research memo; no behavior change

## Bottom line

Quantified the 3 binding constraints causing 60-70% cash drag on $10.7k equity.
Updated Lane A priority: A-1 (QP λ) is dead code (QP disabled), VetoWeakBuys
floor and rotation threshold are the primary levers (not in original Lane A plan).

## Changes

- `doc/research/2026-07-09-cash-drag-binding-constraints-update.md` — full analysis
  with 11-day funnel data, parameter decomposition, and revised A-0/A-0b/A-3 priority

## Key findings

1. VetoWeakBuys adaptive floor (mean+1σ≈0.575) kills 80% of candidates — too
   aggressive for the XGB panel scorer's calibrated [0.45, 0.65] range
2. Rotation threshold 0.06 > model max ER 0.051 — structurally unreachable, no
   rotation possible regardless of candidate quality
3. Kelly × sigma_sizing → 2-7% positions ($200-750), whole-share blocks high-price
   stocks (BLK $995, AVGO $360)
4. A-1 (`qp_cash_drag_lambda`) is dead code — QP path disabled in production

## Context

Also this session: tournament retrain completed (142/142 CERTIFIED, 0 timeout,
`live_train_end=2026-06-23`). Tomorrow's daily-104 staleness gate will pass,
restoring candidate generation. Structural cash drag remains.
