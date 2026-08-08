# BEAR exit-side prereg — regime-keyed exit config, every number frozen before its data

G-B's standing decision (operator, 2026-08-07): the BEAR signal routes to the
**exit side** — the strongest measured per-regime signal in the system (the
gate's own `sanity_regime_ic`: BEAR mean_ic +0.277, hit 96.4%, n=55) belongs
to selling discipline, not to new buys, while the buy side stays policy-locked.

This document freezes the candidate config, the evaluation plan, and the
authorization boundary BEFORE any backtest runs — the same
freeze-then-measure discipline as orch#910 §10, applied to an exit rule.

## 1. The measured starting point (2026-08-08 reachability verdict, task #21)

The active exit `task_panel_conviction_xs` is **enabled and invoked daily**,
yet fired zero times in 60 live days. Measured on 48 days × 448 holding-day
rows `[VERIFIED — candidate_scores best-run-per-day join]`:

* holding percentile in the candidate cross-section: **median 0.84, min 0.20**
  → the AND-rule's `pct < 0.20` leg matched **zero** rows;
* holding μ: median +0.0323; `μ ≤ −0.05` (OR-bypass) matched **zero** rows.

**Root cause is a selection tautology, not a defect:** holdings are the
panel's recent top picks, so they sit at the top of the very cross-section
the rule ranks, and `min_holding_days_by_regime = {BULL_CALM: 60, default:
60}` exempts anything younger than the full 60d thesis (deliberate — the
2026-05-24 repair forbids soft exits from cutting the thesis short).

**The lever already exists in the config schema**: `min_holding_days_by_regime`
is regime-keyed; BEAR merely inherits `default: 60`.

## 2. Frozen candidate amendment (values fixed HERE, before any evaluation)

```jsonc
"risk.panel_exit": {
  "min_holding_days_by_regime": { "BULL_CALM": 60, "default": 60, "BEAR": 10 },
  "xs_panel_percentile_floor_by_regime": { "default": 0.20, "BEAR": 0.35 },   // NEW key
  "mu_sell_ceiling_by_regime":  { "default": 0.0,  "BEAR": 0.01 }             // NEW key
}
```

Rationale, fixed now: a BEAR regime invalidates the BULL_CALM 60d-thesis
premise, so holding-period protection loses its reason (10 trading days keeps
whipsaw protection only); the percentile floor loosens to 0.35 and the μ
ceiling to +0.01 because in BEAR the asymmetry inverts — the cost of holding
a decaying name exceeds the cost of an early exit. The two `_by_regime` keys
are NEW and require a small pipeline change (task reads scalars today);
**fallback semantics frozen**: an absent regime key resolves to `default`,
and a config with ONLY the old scalar keys behaves byte-identically to today
(regression required).

**No other values may be tried.** If these fail the evaluation, the answer is
"the exit side stays as it is", recorded as a completed outcome — not a sweep.

## 3. Frozen evaluation plan

* **Data**: the 77 production-HMM BEAR days (2017-2026) plus a 10-day
  post-BEAR tail per episode (an exit rule's payoff realizes after the
  regime flips); episodes are the unit, not days.
* **Estimand**: return-space, the operator's judge — net portfolio return and
  max drawdown of the simulated book under {current config} vs {amended
  config}, same fills, same costs, on BEAR episodes only.
* **Placebo per arm**: the same amendment keyed to a SHUFFLED regime series
  (label permutation across episodes, 200 seeds) — the improvement must
  exceed the placebo's 95th percentile.
* **Shifts**: the regime series lagged +5/+10/+20 days — a real regime rule
  survives small timing error; a lucky-timing artifact does not.
* **Dependence**: episode-level block bootstrap (whole episodes resampled,
  gap ≥ 20 trading days) for every CI.
* **Power, stated honestly**: BEAR n_eff ≈ 4. This evaluation CANNOT reach
  t ≥ 2 significance on any plausible effect. It is a **policy-grade**
  decision with statistics as honest annotation — the same class as the
  operator's standing BEAR no-buy rule. What the gates above kill is
  *artifact* explanations (placebo, timing), not sampling noise.

## 4. Authorization boundary (frozen)

1. This doc + its evaluation run: research only, no grant needed.
2. The pipeline change (reading `_by_regime` keys, default-preserving):
   normal PR + codex review; behaviour-invariance regression mandatory.
3. **Any live `strategy_config.json` change: operator grant, one batch,
   containment rules apply.** Nothing in this line self-activates; the
   evaluation's PASS only earns the amendment the right to be PROPOSED.

## 5. Execution order

1. This prereg merges (codex review = the freeze witness).
2. The evaluation runs exactly as §3; results PR carries the derivation
   artifacts (the #913 reproducibility standard).
3. PASS → proposal to the operator with the measured numbers; FAIL → task
   #21 closes with "exit side stays as-is", a completed outcome.
