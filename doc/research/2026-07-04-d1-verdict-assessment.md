# D1 First Definitive WF-Gate Verdict — Assessment

DATE: 2026-07-04
STATUS: VERIFIED (extracted from existing production gate metadata)
TAGS: D1, S1-S3, WF gate, regime IC, verdict

## Bottom line

**D1 is MODEL-BLOCKED, not gate-blocked.** S1-S3 gate code is all merged and has
already evaluated the production XGB model. The gate produces a FAIL verdict due
to regime-level IC:

- **BULL_CALM** genuine IC = 0.017 (< 0.02 bar) — this regime is ~78% of trading time
- **CHOPPY** genuine IC = 0.002 (≈ zero — signal IS the placebo)

No amount of gate engineering changes this result. The next D1 unblock requires a
model retrain that demonstrates genuine predictive power in BULL_CALM.

## Source

Extracted from WF gate metadata on the active production model artifact:
`panel-ltr.alpha158_fund.json` (XGB, trained 2026-06-21, re-promoted 2026-06-23).

## Gate Results

### Overall
- Gate version: v2 (absolute ceiling)
- Overall passed: `True` BUT `diagnostic_only: True`
- Gate verdict without override: `False`
- Reason: `passed=false solely from skipped_required_gates=[trade_monotonicity_pass_open_allowed]`

### Walk-Forward Performance (3 cuts, 27 months)

| Cut | Sharpe | APY | SPY Sharpe | SPY APY | Beat SPY? |
|-----|--------|-----|------------|---------|-----------|
| 2024-01 → 2024-12 | 0.972 | 11.7% | 1.778 | 20.5% | No |
| 2024-07 → 2025-06 | 0.943 | 8.1% | 0.715 | 6.1% | Yes |
| 2025-04 → 2026-03 | 0.177 | 1.3% | 0.749 | 5.0% | No |

- 3/3 positive Sharpe (barely — 0.177 in latest cut)
- 1/3 beat SPY Sharpe
- 0/3 beat SPY APY
- Structural underperformance: declining Sharpe trajectory (0.97 → 0.94 → 0.18)

### Sanity Battery

| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Shuffled-label IC | −0.00039 | < 0.005 | PASS |
| Placebo/Real ratio | 0.453 | < 0.5 | PASS (barely) |
| S3 genuine IC | 0.0415 | > 0.02 | PASS (shadow) |

### Regime-Level IC (the FAIL)

| Regime | Mean IC | Placebo IC | Genuine IC | n | Pass? |
|--------|---------|------------|------------|---|-------|
| BEAR | 0.335 | 0.088 | 0.247 | ≥30 | PASS |
| BULL_CALM | 0.023 | 0.006 | 0.017 | ≥30 | **FAIL (< 0.02)** |
| BULL_VOLATILE | 0.025 | 0.010 | 0.015 | 19 | Ineligible (n < 30) |
| CHOPPY | 0.026 | 0.024 | 0.002 | ≥30 | **FAIL (≈ 0)** |

## Implications

1. **The gate is working correctly.** S1-S3 repairs are all landed and producing
   the expected results. The placebo-clean difference test (S3 shadow) correctly
   identifies that the model's BULL_CALM predictive power is marginal (0.017) and
   CHOPPY is zero (0.002).

2. **D1 verdict = FAIL is an HONEST assessment**, not a gate bug. The model genuinely
   lacks regime-specific edge in the dominant regime.

3. **S3 v3 promotion is still valuable** — replacing the v2 absolute-ceiling gate
   (which has the structural +0.04 embargo floor problem) with the v3 placebo
   difference test would make the gate more honest, even though the current model
   would still fail at regime level.

4. **Next steps for D1 clearance:**
   - A new retrain must demonstrate genuine IC > 0.02 in BULL_CALM
   - The WF gate infrastructure is ready — this is a model quality problem
   - Consider whether the CHOPPY genuine IC ≈ 0 should inform trading policy
     (fail-close in CHOPPY regimes vs continuing with a no-edge model)

5. **This is consistent with the existing evidence base:**
   - Win rate is backtest not live (memory)
   - Canonical price-trend has no stable multi-day edge (memory)
   - The contrarian XGB picks (OXY forensics) carry this trust problem

## Cross-references

- S1-S3 gate repair: backtesting PRs #48-#51, #57-#58, #61, #64
- WF-gate embargo leakage floor: ~+0.04 shuffled-label floor (memory)
- WF-promote chronic reject: config tangle, not one root cause (memory)
