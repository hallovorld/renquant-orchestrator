# Concentration cap sweep: design flaw audit

**Date**: 2026-07-09
**Status**: VERIFIED — experiment varied a parameter invisible to the active allocator
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

## Recommended updates

1. PR #439's findings doc should note this design flaw for scientific integrity
2. Phase 4 remains NEGATIVE — no need to re-run with the "correct" parameter
3. Future sweeps that touch sizing must verify which allocator path is active
   and vary the parameter that path actually reads
