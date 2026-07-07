# 2026-07-07 — Sizing-fidelity diagnostic + cash-drag root-cause data

**PR**: add `scripts/check_sizing_fidelity.py`

## What

Diagnostic script that measures whole-share quantization error and
decomposes candidate blocking reasons from `runs.alpaca.db`. Provides the
Phase 1 (S-FRAC) baseline measurement.

## Key findings from live data (30-day window)

| Metric | Value |
|---|---|
| Avg cash % (10 sessions) | **80.7%** |
| Latest cash % | 78.1% |
| #1 blocker | `veto:rank_score_below_floor` **81.6%** of all blocks |
| #2 blocker | `conviction:mu_below_floor` 7.5% |
| `size_insufficient_cash` | **0.8%** (10 blocks: BLK×4, ASML×3, AVGO×2, CAT×1) |

## Implication for cash-drag resolution

Fractional shares (S-FRAC Phase 1) addresses only 0.8% of candidate blocks.
The dominant cash-drag cause is VetoWeakBuys rank floor (81.6% of blocks) —
the rank_score floor (mean+1σ = 0.565) rejects ~80% of candidates that pass
all other gates.

This validates PR #406's layered approach but suggests the **rank floor
calibration** is the highest-leverage intervention, not fractional shares.
The rank floor is a policy/calibration question that needs A/B evidence.

## Scope

- New diagnostic script only, no behavior changes
- Exit 0 = healthy, exit 1 = problems found
