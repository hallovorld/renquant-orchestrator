# Concentration cap sweep: design flaw audit + sizing architecture review

**Date**: 2026-07-09
**Status**: VERIFIED — three layers of design issues (experiment, QP, Kelly)
**Related**: PR #439 (sweep findings), RFC #421 (cash-drag resolution plan Phase 4)
**Trigger**: operator audit request ("我怀疑 cash drag 试验有效性")

## Bottom line

The 75-variant concentration cap sweep varied `kelly_sizing.max_concentration`
(0.08–0.20), but the active allocator in the sweep's base config is the QP
solver (`JointPortfolioQPJob`, `joint_actions.enabled = true`), which derives
its position upper bound from `regime_params.*.max_position_pct` — a completely
separate config key that was **never varied**. The QP code contains zero
references to `max_concentration`.

The sweep conclusion ("cap tuning does not solve cash drag") is **still correct**
— but for a different reason than PR #439 documented. 59/74 identical results
are not because "the cap never binds"; they are because the swept parameter is
invisible to the primary allocator.

## Evidence chain

### 1. Base config enables QP

Sweep uses `strategy_config.sim_kelly_ab_admoff.json` (line 97 of
`run_concentration_cap_sweep.py`):
- `rotation.joint_actions.enabled = true` → QP is the primary allocator
- `ranking.kelly_sizing.max_concentration = 0.35` (base, overridden by sweep)
- `regime_params.BULL_CALM.max_position_pct = 0.15` (QP upper bound, never swept)

### 2. QP upper bound ignores `max_concentration`

`ComputeQPConstraintsTask` (kernel `portfolio_qp/tasks.py:700-715`):
```python
max_pct = rp.get("max_position_pct", config.get("max_position_pct", 0.20))
hard_cap = np.full(n, max_pct * scale)
ctx._qp_w_upper = hard_cap  # ← NOT from max_concentration
```

Confirmed: `grep -rn "max_concentration" kernel/portfolio_qp/` returns zero hits.

### 3. Pipeline routing when QP enabled

`pp_inference.py:436-446`:
```python
if joint_enabled:
    phase3_jobs = (..., RankingJob(), JointActionJob(), ...)   # QP path
else:
    phase3_jobs = (..., RotationJob(), SelectionJob(), ...)    # greedy path
```

Kelly sizing (`ApplyKellySizingTask`) runs inside `PanelScoringJob` (BEFORE
JointActionJob) and stamps `kelly_target_pct` on candidates. But the QP's
optimization objective uses `_qp_mu` (expected returns) and `_qp_w_upper`
(from `max_position_pct`), not `kelly_target_pct`.

### 4. Swept parameter only reaches post-QP secondary tasks

After JointActionJob, two Kelly-driven tasks run:
- `TopUpHeldTask` (line 486) — reads `kelly_target_pct` (affected by sweep)
- `TrimHeldTask` (line 493) — reads `kelly_target_pct` + `trim_threshold` (affected)

These are post-QP adjustments that rarely fire because the QP has already
sized positions.

### 5. Why drift00 differs

`trim_threshold = 0` forces `TrimHeldTask` to fire every bar when
`current_pct > kelly_target_pct` (any excess). This changes the portfolio
state that the QP sees on the next bar → different allocation trajectory.
At `cap08`, the Kelly target is tighter (8%) → more aggressive trim →
different outcome from `cap10-20`.

## Effect diagram

```
max_concentration (SWEPT: 0.08–0.20)
  → kelly_target_pct on candidates
    → TopUpHeldTask (post-QP, rarely fires)
    → TrimHeldTask  (post-QP, only fires at drift00)

max_position_pct (NOT SWEPT: constant 0.15)
  → _qp_w_upper
    → QP optimization → PRIMARY portfolio allocation
```

## Impact on sweep conclusion

| Question | Answer |
|---|---|
| Is "cap tuning doesn't help" still correct? | **YES** — even the QP's own cap (0.15) is non-binding; positions are far below it |
| Is the experiment methodologically sound? | **NO** — it varied a parameter invisible to the primary allocator |
| Would sweeping `max_position_pct` change the result? | **Almost certainly not** — 69.8% cash means average position ~3%, far below any realistic cap |
| What are the real binding constraints? | Whole-share rounding (`int()` truncation in `_shares_from_dw`, tasks.py:2224), too few names passing conviction gates |
| Does this change Phase 2 Lane A priority? | **No** — reinforces it as the correct next step |

## Deeper issue: QP and Kelly are two disconnected sizing systems

The experiment flaw is a symptom of a deeper architectural problem: the QP and
Kelly paths are TWO PARALLEL SIZING SYSTEMS that don't coordinate.

### QP design issues

**Q1. QP has no awareness of `max_concentration`.**
`ComputeQPConstraintsTask` sets `_qp_w_upper` from `max_position_pct × confidence_scale`.
`ApplyConvictionCapTask` then scales it by `conviction_multiplier(panel_score)` (enabled
in sweep config). But neither reads `max_concentration`. The QP can allocate up to
`max_position_pct` (0.15 in BULL_CALM) even if Kelly says a name should be capped at 8%.

**Q2. `_qp_w_upper` ≠ Kelly target — different formulas, different answers.**
- Kelly: `target = min(max_concentration, max_pct, fractional × μ/σ²)` — per-name
  risk-adjusted, capped at the stricter of two independent limits.
- QP: `w_upper = max_position_pct × confidence × vol_scale × dd_scale × conviction_mult`
  — portfolio-level regime scaling × a panel_score-based multiplier.
- Same `mu` input, but Kelly sizes by `μ/σ²` (Kelly fraction) while QP uses
  Markowitz mean-variance optimization. These produce different targets for the same name.

**Q3. Whole-share truncation kills small QP allocations.**
`_shares_from_dw` (tasks.py:2224): `int(abs(dw) * nav / px)` — `int()` truncates.
For a $30k NAV with QP target Δw=2%, stock at $1000: `int(0.02 × 30000 / 1000) = 0`.
The `min_share_floor` experiment exists (tasks.py:3057-3082) but is **off by default**
(`qp_min_share_floor_pct = 0.0` in sweep base config).

### Kelly design issues

**K1. Kelly targets are computed but mostly discarded when QP is active.**
`ApplyKellySizingTask` runs inside `PanelScoringJob` (before JointActionJob) and
stamps `kelly_target_pct` on every candidate and holding. When `joint_actions.enabled
= true`, the QP makes the primary allocation using its own Markowitz objective —
Kelly's per-name `μ/σ²` targets are thrown away. Only the post-QP `TopUpHeldTask` and
`TrimHeldTask` read them.

**K2. Post-QP Kelly adjustments can fight the QP.**
Scenario: QP allocates 10% to AAPL. Kelly target is 8% (`max_concentration=0.08`).
`TrimHeldTask` (drift00) sees `current(10%) > kelly_target(8%)` → forces sell down
to 8%. Next bar, QP sees AAPL underweight → buys back toward 10%. This is the
mechanism behind the drift00 +0.06 Sharpe: not a "cap effect" but two sizing systems
oscillating against each other, which accidentally improves diversification.

**K3. Kelly's double cap is redundant with QP when both are active.**
Kelly computes `min(max_concentration, max_pct, fractional × f*)`. But when QP is
active, `max_pct` (= `max_position_pct`) is already enforced by the QP's own
`_qp_w_upper`. The Kelly cap is only meaningful if it's TIGHTER than QP's cap,
and even then, only through the post-QP TopUp/Trim channel.

### Architectural incoherence

```
┌─────────────────────────────────────────────────────┐
│ PanelScoringJob                                     │
│   ApplyKellySizingTask:                             │
│     kelly_target = min(max_conc, max_pct, f×μ/σ²)  │ ← computed
│     stamps kelly_target_pct on candidates/holdings  │ ← stored
└────────────────────────┬────────────────────────────┘
                         │ kelly_target_pct on ctx objects
                         ▼
┌─────────────────────────────────────────────────────┐
│ JointActionJob (QP)                                 │
│   w_upper = max_pos_pct × conf × vol × dd × conv   │ ← IGNORES kelly
│   Markowitz: max(μ·w − γ·w'Σw) s.t. w ≤ w_upper   │
│   _shares_from_dw: int(Δw × NAV / px)              │ ← truncation
│   min_share_floor = 0 (OFF)                         │
└────────────────────────┬────────────────────────────┘
                         │ orders emitted
                         ▼
┌─────────────────────────────────────────────────────┐
│ TopUpHeldTask / TrimHeldTask                        │
│   reads kelly_target_pct (from step 1)              │ ← POST-HOC fix
│   can ADD or REMOVE shares vs QP allocation         │ ← FIGHTS QP
└─────────────────────────────────────────────────────┘
```

Two independent sizing philosophies (Kelly f* vs Markowitz MV) run simultaneously.
Kelly computes targets → QP ignores them → TopUp/Trim retroactively apply them.
This is not "defense in depth"; it's two systems with different objectives fighting
over the same portfolio, with the post-hoc system occasionally winning (drift00).

### Cash drag implications

The architectural incoherence CONTRIBUTES to cash drag in two ways:

1. **QP's whole-share truncation is the direct mechanism.** Small QP Δw allocations
   → `int()` rounds to 0 shares → cash stays idle. Kelly might have given the same
   name a LARGER target (higher conviction → larger `f*`), but QP doesn't see it.

2. **QP distributes across more names than Kelly would.** Markowitz diversification
   pushes weight toward many names with small allocations. Kelly concentrates weight
   on high-conviction names (larger `fractional × μ/σ²`). When QP spreads across 20
   names at ~1.5% each, more of them round to 0 shares than if Kelly concentrated
   on 5 names at ~6% each.

### Discussion for Codex

1. Should the QP read `max_concentration` (or Kelly targets) as an additional upper
   bound? This would unify the two systems' caps but wouldn't address the
   MV-vs-Kelly objective difference.

2. Should TopUp/Trim be disabled when QP is active, since they fight the QP?
   The drift00 "accidental diversification" effect might be better achieved by
   tuning `qp_risk_aversion` (γ) directly.

3. Is the `min_share_floor` experiment the correct fix for the whole-share truncation
   cash drag, or should we pursue mixed-integer optimization or fractional shares?

4. The sweep conclusion (Phase 4 NEGATIVE) stands. But it accidentally discovered
   that Trim-vs-QP oscillation improves Sharpe by +0.06. Is that worth investigating
   as a deliberate rebalancing mechanism?

## Recommended updates

1. PR #439's findings doc should note this design flaw for scientific integrity
2. Phase 4 remains NEGATIVE — no need to re-run with the "correct" parameter
3. Future sweeps that touch sizing must verify which allocator path is active
   and vary the parameter that path actually reads
4. Open design discussion on QP/Kelly unification (items 1-3 above)
