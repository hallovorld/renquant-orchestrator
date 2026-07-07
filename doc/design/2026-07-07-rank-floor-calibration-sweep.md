# Rank floor calibration: the #1 cash-drag lever

**Status**: PROPOSAL — requesting review before execution.

## 0. The data-driven diagnosis

Live data from `runs.alpaca.db` (30-day window, 2026-06-22 to 2026-07-06):

| Metric | Value |
|---|---|
| Avg cash % | **80.7%** |
| Candidate block breakdown | |
| — `veto:rank_score_below_floor` | **81.6%** of all 1,215 blocks |
| — `conviction:mu_below_floor` | 7.5% |
| — `candidate_not_selected` | 4.9% |
| — `broker_pending_submitted` | 2.6% |
| — `size_insufficient_cash` | 0.8% (10 blocks) |

**The rank floor is the dominant cash-drag cause by a factor of 10.** All
other interventions (fractional shares at 0.8%, concentration caps, regime
gates) are downstream.

## 1. Why the current floor is too tight

The production config uses `buy_floor: "adaptive_mean_std"`:

```
floor = max(buy_floor_min, mean + std_mult * std)
      = max(0.20, mean(rank_scores) + 1.0 * std(rank_scores))
      ≈ max(0.20, 0.535 + 0.030)
      ≈ 0.565
```

This admits only ~22.7% of non-holding candidates. The design note in the
codebase (`job_panel_scoring.py:1723`) already explains the problem:

> "mean+kσ on a Platt-compressed calibrator (rank_score IQR ~0.04) is
> shape-unstable — skew/kurtosis decide admission, and the rule
> structurally caps breadth at ~16% regardless of edge (Grinold FLAM:
> IR = IC·√BR; throttling BR caps achievable IR)."

**The fix already exists in code** (`adaptive_quantile` mode, line 1721)
but has never been activated in production.

## 2. Theory: Grinold's Fundamental Law

The Fundamental Law of Active Management:

```
IR ≈ IC · √BR
```

Where IR = information ratio, IC = information coefficient, BR = breadth
(number of independent bets).

With `adaptive_mean_std` (mean+1σ):
- BR is structurally capped at ~16-22% of the candidate universe
- Even perfect IC cannot compensate for a 4× breadth throttle
- The floor's tightness is a FUNCTION OF DISTRIBUTION SHAPE (skew/kurtosis),
  not of signal quality

With `adaptive_quantile`:
- BR is directly controlled (top-q% of the cross-section)
- Independent of distribution compression
- The operator chooses the breadth/quality tradeoff explicitly

This is not "loosen the filter to get more trades." It is "stop using a
distribution-shape-sensitive filter and use one that controls breadth
directly."

## 3. What passing vs failing candidates look like

From live data:

| Group | Avg μ | Avg rank_score | Count |
|---|---|---|---|
| Passes floor (≥0.565) | 0.0343 | 0.584 | 200 |
| Fails floor (<0.565) | 0.0058 | 0.526 | 680 |

The floor IS filtering correctly on average — passing candidates have 6×
higher μ. The question is whether the marginal candidates (those just below
0.565) are worth admitting. At floor = 0.540:

| Floor | Pass rate | Newly admitted | Estimated avg μ of newly admitted |
|---|---|---|---|
| 0.565 (incumbent) | 22.7% | — | — |
| 0.540 | 42.3% | +172 | ~0.015 (weak positive) |
| 0.520 | 53.3% | +269 | ~0.010 (barely positive) |

The marginal candidates have positive but weak μ. Whether admitting them
improves portfolio Sharpe depends on how QP/sizing/conviction_gate handle
them — which is exactly what the sweep must measure.

## 4. Research design

### Core hypothesis

**H1**: Switching from `adaptive_mean_std` to `adaptive_quantile` with
an appropriate quantile improves portfolio Sharpe by increasing breadth
without materially degrading candidate quality.

### Parameter grid

One-dimensional sweep over the floor mechanism:

```
floor_config ∈ {
  "adaptive_mean_std" (incumbent, mean+1σ),
  "adaptive_quantile_q90" (top 10%),
  "adaptive_quantile_q80" (top 20% — the coded default),
  "adaptive_quantile_q70" (top 30%),
  "adaptive_quantile_q60" (top 40%),
  "adaptive_mean_std_mult05" (mean+0.5σ — looser mean+kσ),
}
```

6 variants total. Simple, focused, answers one question.

### Why 1D, not combined with concentration cap

The concentration cap sweep (#403) is a separate, orthogonal study.
Combining them would create a 6 × 75 = 450-variant grid that takes
weeks to run and is harder to interpret. Run them independently:

1. Find the right floor first (this study) — it unlocks candidates
2. Then find the right cap/topup parameters (#403) — it sizes positions
3. If both graduate, combine them in a final verification run

### Controls (§7.2 mandatory)

- **A/A**: incumbent re-run with seed-offset resplit
- **Placebo**: supplied via `--placebo-json`
- **Incumbent**: `adaptive_mean_std` with current parameters

### Seed set and verdict rule

Frozen seed set: `{42, 43, 44}` (matching this repo's standard triple).
Unanimity verdict rule — all 3 seeds must independently satisfy every
criterion.

### Metrics

Per-regime AND full-period:
- APY, Sharpe, MaxDD, Calmar
- Cash% (time-weighted)
- Breadth: number of distinct names traded, candidate admission rate
- Turnover, fill count, cost delta vs incumbent
- Winner rate: % of admitted candidates that deliver positive fwd returns

### Decision rule

Promote a floor config to golden only if, for all 3 frozen seeds:

1. BULL_CALM Sharpe ≥ incumbent (net of modeled transaction costs)
2. MaxDD (BULL_CALM) ≤ incumbent × 1.10
3. Full-period Sharpe ≥ incumbent − 0.02
4. Per-regime no-material-regression on EVERY regime (Sharpe ≥ incumbent−0.02,
   MaxDD ≤ incumbent × 1.10, per regime)
5. Turnover ≤ incumbent × 1.25
6. Placebo shows no lift
7. Cash% meaningfully lower (Δcash% ≥ 5pp — the intervention must actually
   reduce cash drag, not just pass gates)

## 5. Implementation

**No pipeline code changes needed.** The `adaptive_quantile` mode is
already implemented in `VetoWeakBuysTask` (job_panel_scoring.py:1721-1763).
The sweep runner generates config variants that differ only in the
`ranking.panel_scoring.buy_floor` and related parameters.

### Sweep runner

Extend the existing sim A/B harness pattern. ~100 lines of config
generation + the same `run_backtest_multi_seed()` executor.

### Estimated effort

- Sweep runner script: 1 PR (orchestrator)
- Execution: ~1-2 hours (6 variants × 3 seeds × 27-month OOS, serial)
- Analysis memo: 1 doc

## 6. What this research is NOT

- **Not loosening risk control.** The floor minimum (0.20) stays. The
  question is whether the ADAPTIVE mechanism should respond to score
  distribution shape or to a fixed percentile.
- **Not overriding the model.** The model's rank scores are unchanged.
  Only the admission threshold changes.
- **Not re-opening conviction gate.** mu_floor (0.03) is a separate gate
  and is not touched.
- **Not deploying to production.** Results go through §7.4 Tier 3.

## 7. Relationship to other cash-drag work

| Intervention | Candidate blocks addressed | Status |
|---|---|---|
| **Rank floor sweep (this)** | **81.6%** | PROPOSED |
| Concentration cap sweep (#403/#405) | ~5% (topup blocks) | APPROVED, runner ready |
| Fractional shares (S-FRAC v2) | 0.8% | Designed, code 90% done |
| SGOV parking sleeve | 0% (residual idle cash) | Designed |

This study should run FIRST because:
1. It addresses the dominant blocker (81.6% vs next-highest 7.5%)
2. It's the simplest (1D, 6 variants, no pipeline code changes)
3. It unblocks the concentration cap study (more candidates →
   concentration management becomes relevant)
