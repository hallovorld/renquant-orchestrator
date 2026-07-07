# Concentration Cap Research: entry sizing ≠ drift management

**Status**: PROPOSAL — requesting operator review before execution.

## Problem

`max_concentration=12%` caps the Kelly target for both **entry sizing** and
**TopUp**. This number was set by operator mandate (2026-06-09) without A/B
evidence. Combined with `top_up_threshold=5%`, it structurally blocks top-ups
for any position already above 7% — which is most held positions in BULL_CALM.

**Observed**: MU at 9.2% weight, rank=0.617 (top), er=+4.59%, model says
"great" — but TopUp can't add because `kelly_target(12%) - current(9.2%) =
2.8% < threshold(5%)`.

Meanwhile, **Trim is OFF** (correctly — the 2026-04-24 A/B showed trimming
winners costs 12.7pp APY). So we have an asymmetry:

- **Upside**: capped at 12% by Kelly target → TopUp can't add
- **Downside**: no trim → position drifts freely above 12%

This is backwards. A winner running from 9% → 15% via appreciation is the
*best possible outcome* — yet the system can't add to it, while it passively
lets price drift do the same thing. The cap constrains the *deliberate*
action (TopUp) while allowing the *passive* outcome (drift).

## What prior research covers — and what it doesn't

| Question | Covered? | Finding |
|---|---|---|
| Is Kelly σ-horizon the cash-drag cause? | YES (06-03 A/B) | NO — Kelly is a non-binding ceiling; ΔSharpe=0 |
| Should we trim winners? | YES (04-24 A/B) | NO — trim OFF beats trim ON by +12.7pp APY |
| Is max_conc=12% optimal? | **NO** | Set by fiat, no A/B |
| Should entry cap ≠ drift cap? | **NO** | Never studied |
| Is top_up_threshold=5% optimal? | **NO** | Never studied (audit flagged it as "will self-resolve after σ-fix" — but σ-fix was inert) |
| How do these three interact? | **NO** | Never studied |

## Research design

### Core hypothesis

**H1**: Separating entry cap from drift tolerance improves risk-adjusted
returns by letting winners run while controlling initial commitment.

**H2**: `top_up_threshold` should scale with `max_concentration` — a 5%
threshold makes sense at 35% max_conc but is too coarse at 12%.

### Parameter grid

Three-dimensional sweep over the Kelly sizing config:

```
entry_cap     ∈ {0.08, 0.10, 0.12, 0.15, 0.20}   # max_concentration for new buys + TopUp target
drift_cap     ∈ {entry_cap, 0.20, 0.25, 0.30, ∞}  # trim fires only above this (∞ = trim OFF)
topup_thresh  ∈ {0.02, 0.03, 0.05}                 # top_up_threshold
```

Constraints:
- `drift_cap ≥ entry_cap` always (you can't trim below your entry target)
- `drift_cap = ∞` is the current behavior (trim OFF)
- Total: ~50 parameter combinations after constraint pruning

### Implementation

**No new code needed for the sweep itself.** The existing sim A/B harness
(`scripts/run_kelly_sigma_horizon_ab.py` pattern) can run config diffs.
What's needed:

1. **Config wiring**: `max_concentration` already exists. Add
   `drift_concentration_cap` (default = `max_concentration` for backward
   compat) — TrimHeldTask reads this instead of `max_concentration` as its
   trim-to target. TopUp continues to use `max_concentration` as its ceiling.

2. **TrimHeldTask change**: when `trim_enabled=true` AND
   `drift_concentration_cap` is set, trim fires only when `current_pct >
   drift_concentration_cap` (not when `current_pct > kelly_target +
   trim_threshold`). This separates the trim trigger from the Kelly target.

3. **Sweep runner**: generate config variants for the grid, run 27-month OOS
   with ≥3 seeds each, collect per-regime metrics.

### Controls (§7.2 mandatory)

- **A/A**: golden vs golden (seed offset) — must be zero-delta
- **Placebo**: shuffle labels — any lift must disappear
- **Incumbent**: current config (entry=12%, drift=∞, topup=5%) as control arm

### Metrics

Per-regime (BULL_CALM is the primary evaluation regime):
- APY, Sharpe, MaxDD, Calmar
- Cash% (time-weighted)
- Concentration: max single-name weight (peak), HHI(book)
- TopUp firing rate (how often TopUp actually adds)
- Winner-continuation: returns of positions that exceeded entry_cap via drift
  (did letting them run help or hurt?)

### Decision rule

Promote a config to golden (via §7.4 Tier 3) only if:
1. BULL_CALM Sharpe ≥ incumbent (net of transaction costs)
2. MaxDD ≤ incumbent × 1.10 (no more than 10% worse drawdown)
3. Placebo shows no lift (the improvement is signal-driven, not overfitting)
4. The "winner continuation" analysis confirms that un-trimmed drift above
   entry_cap is net positive (otherwise we're just lucky on the test window)

## What this research is NOT

- **Not a case to increase risk.** Entry cap may stay at 12% or go lower.
  The question is whether treating drift differently from entry improves
  risk-adjusted returns.
- **Not re-opening trim.** The 04-24 A/B showed trim hurts when pegged to
  Kelly target. This asks whether trim pegged to a *higher* drift cap
  (e.g., 25%) is different — it might be, because that only fires on extreme
  concentration, not on normal winners.
- **Not changing any live behavior.** Results go through the standard
  §7.4 Tier 3 gate before touching golden.

## Estimated effort

- Config wiring + TrimHeldTask drift_cap: 1 PR (renquant-pipeline)
- Sweep runner script: 1 PR (renquant-orchestrator or umbrella)
- Execution: ~2-4 hours wall clock (50 configs × 3 seeds × 27-month, serial)
- Analysis memo: 1 doc

## Open questions for operator

1. Is 12% entry cap negotiable, or is it a hard risk mandate regardless of
   what the data shows?
2. Should the sweep include `max_concurrent_positions` as a 4th dimension?
   (Currently 8 in BULL_CALM — at 12% each that's 96% max invested, which
   seems fine.)
3. Any prior intuition on where drift_cap should land? The 04-24 A/B
   suggests "don't trim at all" is hard to beat, but that was with the old
   35% max_conc.
