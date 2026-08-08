# BEAR exit-side prereg — regime-keyed exit config, every number frozen before its data

G-B's standing decision (operator, 2026-08-07): the BEAR signal routes to the
**exit side** — the strongest measured per-regime signal in the system (the
gate's own `sanity_regime_ic`: BEAR mean_ic +0.277, hit 96.4%, n=55
`[VERIFIED — RenQuant/backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json
::metadata.wf_gate_metadata.sanity_regime_ic.per_regime.BEAR, read 2026-08-08:
mean_ic +0.2767, hit_rate 0.9636, n_dates 55]`) belongs to selling
discipline, not to new buys, while the buy side stays policy-locked.

This document freezes the candidate config, the evaluation plan, and the
authorization boundary BEFORE any backtest runs — the same
freeze-then-measure discipline as orch#910 §10, applied to an exit rule.

## Corrections (2026-08-08, review r1)

The reachability figures first quoted here (48 days / 448 rows / median 0.84
/ min 0.20 / μ median +0.0323) came from a session join whose exact script
was not persisted; per LONG #10 they were re-measured in-session under a
frozen, committed definition and are superseded by §1's numbers (43 days /
200 rows / median 0.89 / min 0.20 / μ median +0.0351). The verdict is
unchanged: zero fires on either trigger leg, holdings pinned to the top of
their own cross-section. Derivation + row-level data:
`doc/research/data/2026-08-08-bear-exit-reachability-{derivation.py,rows.csv}`
(default mode re-verifies every §1 number from the committed CSV alone).

## 1 · The measured starting point (2026-08-08 reachability measurement)

The active exit `task_panel_conviction_xs` is **enabled and invoked daily**
`[VERIFIED — renquant-strategy-104/configs/strategy_config.json
::risk.panel_exit.enabled=true; the task first-gates on `enabled`
(CrossSectionalPanelExitTask.run)]`, yet fired zero times over the last 60
live run-dates (2026-05-15..2026-08-07): zero `panel_conviction`/xs exits
among the window's 42 live sells `[VERIFIED — runs.alpaca.db trades ⋈
pipeline_runs, live sells grouped by exit_reason]`. Measured on 43 days ×
200 holding-day rows (best-run-per-day join; window has 60 live run-dates,
43 carry a full candidate cross-section ≥ min_universe)
`[VERIFIED — doc/research/data/2026-08-08-bear-exit-reachability-rows.csv;
verifier reproduces every number below from the CSV alone]`:

* holding percentile in the day's panel cross-section: **median 0.89,
  min 0.20**; replaying the task's own threshold arithmetic, 7 rows sat at
  or below the bottom-20% threshold — every one with μ > 0;
* holding μ: median +0.0351; `μ ≤ 0` (AND-rule leg 2) matched 1 row — not
  in the bottom quintile; the two legs **never coincided** (AND-rule fires:
  0); `μ ≤ −0.05` (OR-bypass) matched **zero** rows.

**Root cause is a selection tautology, not a defect:** holdings are the
panel's recent top picks, so they sit at the top of the very cross-section
the rule ranks, and `min_holding_days_by_regime = {BULL_CALM: 60, default:
60}` `[VERIFIED — pinned strategy_config.json::risk.panel_exit]` exempts
anything younger than the full 60d thesis (deliberate — the 2026-05-24
repair forbids soft exits from cutting the thesis short).

**The lever already exists in the config schema**: `min_holding_days_by_regime`
is regime-keyed; BEAR merely inherits `default: 60`.

## 2 · Frozen candidate amendment (values fixed HERE, before any evaluation)

```jsonc
"risk.panel_exit": {
  "min_holding_days_by_regime": { "BULL_CALM": 60, "default": 60, "BEAR": 10 },
  "xs_panel_percentile_floor_by_regime": { "default": 0.20, "BEAR": 0.35 },   // NEW key
  "mu_sell_ceiling_by_regime":  { "default": 0.0,  "BEAR": 0.01 }             // NEW key
}
```

The three BEAR values — 10 trading days / 0.35 / +0.01 — are
`[ASSUMED — frozen policy choice, fixed before any evaluation data exists]`;
the non-BEAR values reproduce the pinned production config
`[VERIFIED — renquant-strategy-104/configs/strategy_config.json::risk.panel_exit]`.

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

## 3 · Frozen evaluation plan

* **Data**: the production-HMM BEAR days 2017-2026 — ~77 days grouping into
  ~4 contiguous episodes `[ASSUMED — planning estimate from the 2026-08-08
  recon (production HMM argmax over SPY history); not re-measured in-session;
  the evaluation re-derives the episode list from the production regime
  artifact at run time and the results PR commits it as a derivation
  artifact]` — plus a 10-trading-day post-BEAR tail per episode
  `[ASSUMED — frozen policy choice]` (an exit rule's payoff realizes after
  the regime flips); episodes are the unit, not days.
* **Estimand**: return-space, the operator's judge — net portfolio return and
  max drawdown of the simulated book under {current config} vs {amended
  config}, same fills, same costs, on BEAR episodes only.
* **Placebo per arm**: the same amendment keyed to a SHUFFLED regime series
  (label permutation across episodes), 200 seeds
  `[ASSUMED — frozen policy choice]`.
* **Shifts**: the regime series lagged +5/+10/+20 days
  `[ASSUMED — frozen policy choice]` — a real regime rule survives small
  timing error; a lucky-timing artifact does not.
* **Dependence**: episode-level block bootstrap (whole episodes resampled,
  gap ≥ 20 trading days `[ASSUMED — frozen policy choice, = the exit rule's
  whipsaw horizon scale]`) for every CI.
* **Power, stated honestly**: BEAR n_eff ≈ 4 `[DERIVED — ~77 BEAR days /
  ~20d mean episode length ≈ 4 independent episodes]`. This evaluation
  CANNOT reach t ≥ 2 significance on any plausible effect. It is a
  **policy-grade** decision with statistics as honest annotation — the same
  class as the operator's standing BEAR no-buy rule. What the gates below
  kill is *artifact* explanations (placebo, timing), not sampling noise.

### 3.1 · Frozen PASS rule (deterministic — no judgement after results exist)

Per arm, on identical fills, costs, and universe:

* `R(arm, series)` = compounded net portfolio return over the concatenated
  BEAR episode windows (episode = contiguous production-HMM BEAR days +
  10-trading-day tail) under regime `series`;
* `DD(arm, series)` = worst peak-to-trough NAV drawdown within any single
  episode window;
* `ΔR(series) = R(amended, series) − R(current, series)`;
  `ΔDD(series) = DD(amended, series) − DD(current, series)` (≤ 0 = amended
  no worse).

**PASS requires ALL five legs. Any leg FAIL ⇒ overall FAIL ⇒ "the exit side
stays as-is" (a completed outcome). There is no weighing, no combination
score, no discretionary override: return and drawdown are separate mandatory
legs, and a disagreement between them is a FAIL by construction.**

| leg | rule | frozen threshold |
|---|---|---|
| D1 effect sign | `ΔR(true series) > 0` | strict inequality `[ASSUMED — frozen policy choice]` |
| D2 placebo | `ΔR(true series)` > the 95th percentile of the 200-seed placebo `ΔR` distribution (placebo = the amendment keyed to an episode-block-permuted regime series, seeds 1..200, same simulator) | p95, 200 seeds `[ASSUMED — frozen policy choice]` |
| D3 drawdown non-inferiority | `ΔDD(true series) ≤ +1.0 pt` (absolute NAV percentage points) | +1.0 pt `[ASSUMED — frozen policy choice]` |
| D4 all shifts | for EACH shift s ∈ {+5, +10, +20} days: `ΔR(s) > 0` AND `ΔDD(s) ≤ +1.0 pt`. All three must pass; one failure fails the leg. | same thresholds as D1/D3 `[ASSUMED — frozen policy choice]` |
| D5 bootstrap support | episode-level block bootstrap (episodes resampled whole, gap ≥ 20 trading days, 10,000 resamples, seed 20260808): the share of resamples with `ΔR > 0` must be ≥ 0.75 | 0.75 / 10,000 / seed 20260808 `[ASSUMED — frozen policy choice]` |

The bootstrap 90% CI for `ΔR` is REPORTED as annotation; with n_eff ≈ 4 it
is expected to span 0 and does **not** itself gate — that is a frozen
power-honesty rule decided now (§3 "Power"), not a post-hoc concession. D5
is the binding bootstrap leg.

## 4 · Authorization boundary (frozen)

1. This doc + its evaluation run: research only, no grant needed.
2. The pipeline change (reading `_by_regime` keys, default-preserving):
   normal PR + codex review; behaviour-invariance regression mandatory.
3. **Any live `strategy_config.json` change: operator grant, one batch,
   containment rules apply.** Nothing in this line self-activates; the
   evaluation's PASS only earns the amendment the right to be PROPOSED.

## 5 · Execution order

1. This prereg merges (codex review = the freeze witness).
2. The evaluation runs exactly as §3/§3.1; results PR carries the derivation
   artifacts (the #913 reproducibility standard).
3. PASS → proposal to the operator with the measured numbers; FAIL → task
   #21 closes with "exit side stays as-is", a completed outcome.
