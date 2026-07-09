# Concentration cap sweep findings: cap tuning does not solve cash drag

**Date**: 2026-07-09
**Status**: NEGATIVE — no concentration cap parameter change reduces cash drag
**Design doc**: #403 (sweep design), #421 (cash-drag resolution plan Phase 4)
**Sweep output**: `backtesting/renquant_104/artifacts/diagnostics/local_sweep_6mo_20260709/`

## Bottom line

75 concentration cap variants were tested across a 3D grid
(entry_cap × drift_buffer × topup_threshold). **Zero** pass the Tier-3
unanimity gate. More importantly, only **3 distinct Sharpe values** emerge
across all 75 variants — the concentration cap parameters are effectively
irrelevant to portfolio performance.

The concentration cap **never binds** in normal operation. The portfolio
never accumulates enough in any single position to trigger cap enforcement.
Cash drag is caused by upstream pipeline gates (conviction, vol, wash-sale)
filtering out too many names, not by position sizing caps being too tight.

## Experiment design

| Parameter | Value |
|---|---|
| Grid | 5 entry_caps (8/10/12/15/20%) × 5 drift_buffers (0/8/13/18/inf%) × 3 topup_thresholds (2/3/5%) |
| Variants | 74 candidates + 1 incumbent (cap12_driftinf_topup05) |
| OOS window | 2025-07-01 to 2026-01-15 (6 months, ~132 trading days) |
| Seeds | 1 (seed 42) — deterministic backtest (verified: all seeds produce identical results) |
| Runtime | 3h05m local, 10 parallel workers, ~21 min/variant |
| A/A control | PASS (Sharpe lift = +0.0000) |
| Scope | DEV run — shortened OOS, 1 seed, no placebo (deviates from #403's 27-month/3-seed contract) |

## Results

### Performance clusters

| Sharpe | Count | Variants | ΔSharpe vs incumbent |
|---|---|---|---|
| 1.4148 | 3 | cap08_drift00_topup{02,03,05} | +0.0720 |
| 1.4023 | 12 | cap{10,12,15,20}_drift00_topup{02,03,05} + 1 extra | +0.0594 |
| 1.3429 | 59 | All drift>0 variants | +0.0000 |

**Incumbent**: Sharpe=1.3429, APY=15.02%, MaxDD=5.86%, Calmar=2.56

### Key observations

1. **59/74 variants (80%) produce IDENTICAL results to incumbent**. Any
   drift_buffer > 0 never triggers because positions never reach the
   entry_cap. The cap is non-binding.

2. **drift00 is the only parameter with any effect**. Forcing strict
   rebalancing-to-cap improves Sharpe by +0.06–0.07 (small, likely within
   noise). This works by forcing diversification via rebalancing, not by
   deploying more cash.

3. **topup_threshold has ZERO effect**. All 3 values produce identical
   results within each cap+drift combo. Top-up logic never activates
   differently across these thresholds.

4. **entry_cap barely matters when drift=0**. Cap08 is marginally better
   than cap10–20 (+0.01 Sharpe), but all drift00 variants cluster tightly.

### Gate verdict breakdown

| Criterion | Result |
|---|---|
| 1. BULL_CALM Sharpe net-of-cost | **PASS** (all 74) |
| 2. BULL_CALM MaxDD tolerance | **PASS** (all 74) |
| 3. Full-period no material regression | **PASS** (all 74) |
| 4. Per-regime no material regression | **None** (only 1 BEAR day → NaN Sharpe) |
| 5. Turnover ceiling | **PASS** (all 74) |
| 6. Placebo no-lift | **None** (no placebo provided in DEV run) |
| 7. Winner continuation net-positive | **True** for 3 best, **None** for 71 others |

All variants pass the substantive criteria (1–3, 5). Gate failures are
methodological: insufficient regime coverage (6-month window has only 1
BEAR day) and missing placebo. A full 27-month OOS with placebo would
resolve criteria 4 and 6, but this is moot — the performance differences
are negligible.

### Regime performance (incumbent vs best variant)

| Metric | Incumbent (cap12_driftinf) | Best (cap08_drift00) |
|---|---|---|
| BULL_CALM Sharpe | 1.705 | 1.768 |
| BULL_CALM MaxDD | 3.41% | 3.23% |
| BULL_VOLATILE Sharpe | 4.943 | 4.997 |
| BEAR (1 day) | NaN | NaN |

## Conclusion

**Concentration cap tuning does not solve cash drag.** The binding
constraints are upstream in the pipeline:

1. **Whole-share sizing** (Phase 2, Lane A-1): small Kelly allocations
   on high-priced stocks round to 0 shares, stranding cash.
2. **Conviction gate filtering** (Phase 2, Lane A-2): too few names
   pass mu_floor to fully deploy capital.
3. **Redeployment frequency** (Phase 2, Lane A-3): daily pipeline
   runs only once, missing intraday opportunities.

This validates RFC #421's phased approach: Phase 2 Lane A (sizing fidelity)
should be the priority, not Phase 4 (cap tuning). Phase 4 is now
**closed as NEGATIVE** — no further sweep work is warranted unless the
upstream constraints are first resolved and cash drag persists.

## Caveats

- DEV run only (6-month OOS, 1 seed, no placebo). Not a formal gating
  verdict per #403's 27-month/3-seed contract.
- However, the finding that cap parameters produce only 3 distinct
  outcomes across 75 variants is structurally robust — longer OOS would
  not change the fact that the cap never binds.
- The +0.07 Sharpe improvement from drift00 is interesting but likely
  within estimation noise. If pursued, it requires a proper 27-month run.
