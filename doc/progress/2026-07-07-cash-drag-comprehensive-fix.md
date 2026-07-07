# 2026-07-07 — Cash drag comprehensive fix design

**PR**: design doc for cash-drag root cause fix (strategies 104/105)

## What

Comprehensive design proposal to solve 81% cash drag in BULL_CALM. Backed
by data from `data/runs.alpaca.db`: 100% of live candidates blocked since
June 1 (45+ trading days).

## Root causes identified (with evidence)

1. **VetoWeakBuys rank floor** (48% of blocks): dynamic mean+1σ floor =
   0.565 passes only 7/35 candidates. PatchTST score dispersion too narrow
   for a 1σ cutoff.
2. **Regime admission gate** (38%): WF metadata gaps cause binary kill-switch
   blocking. No hysteresis / fallback-to-last-good.
3. **Concentration cap × top-up threshold** (affects existing holdings):
   12% cap + 5% threshold blocks top-ups when position > 7% (MU at 9.2%).
4. **Whole-share sizing** (contributing): $374/share AVGO on $10.8k = 3.5%
   minimum increment. Systematic downward bias.

## Prior research confirmed

- Kelly σ-horizon A/B: REJECTED (ΔSharpe = 0, Kelly is non-binding ceiling)
- Trim A/B: OFF wins (+12.7pp APY)
- Cash overlay: DEFERRED (fix pipeline first)

## Proposed layered fix

- P0: Regime admission hysteresis (fallback to last-good, 3d staleness)
- P0: VetoWeakBuys percentile floor (A/B: mean+1σ vs p75 vs p50 vs low)
- P1: Concentration cap sweep (existing PR #405 script)
- P2: max_concurrent_positions increase (conditional on P0/P1)
- DEFERRED: SPY/QQQ fallback overlay (only if pipeline fixes insufficient)

## Success criteria

- Live candidate pass rate: 0% → ≥5%
- BULL_CALM cash %: 81% → ≤50%
- Sim Sharpe: ≥1.54 (no regression)
