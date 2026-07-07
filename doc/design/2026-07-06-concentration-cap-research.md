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

### Isolating the intervention (round 2 — Codex review)

The original design of this sweep varied two things at once: (a) whether
entry and drift caps differ at all, and (b) the *functional form* of the trim
trigger itself — swapping the incumbent's `current_pct > kelly_target +
trim_threshold` (a buffer measured from the Kelly target, which moves
session-to-session) for `current_pct > drift_concentration_cap` (a fixed
absolute ceiling with no buffer concept). Those are two different
hypotheses, and a win could not be attributed to either one specifically.

**Fix: freeze the trigger's functional form to the incumbent's, for this
first sweep.** Instead of introducing a new absolute `drift_concentration_cap`
parameter, the sweep varies **`drift_buffer`** — a value added on top of
`kelly_target`, in exactly the same arithmetic position `trim_threshold`
already occupies today:

```
TrimHeldTask fires when:  current_pct > kelly_target + drift_buffer
```

This is *not* a new mechanism — it is the existing mechanism with
`trim_threshold` (today fixed at an implicit value that keeps trim
effectively OFF) replaced by a swept parameter. `drift_buffer = ∞` reproduces
today's trim-OFF behavior exactly. No new code path, no new trigger logic —
only the buffer's value changes across the grid. This isolates H1/H2 (do the
cap *values* matter) from any question of trigger *mechanics* (which remains
untouched and is explicitly out of scope for this study, per "What this
research is NOT" below).

`effective_drift_cap = entry_cap + drift_buffer` for interpretability when
reading sweep results (e.g., entry_cap=0.12, drift_buffer=0.13 ⇒ trim fires
above 25% weight).

### Parameter grid

Three-dimensional sweep over the Kelly sizing config:

```
entry_cap     ∈ {0.08, 0.10, 0.12, 0.15, 0.20}   # max_concentration for new buys + TopUp target
drift_buffer  ∈ {0.0, 0.08, 0.13, 0.18, ∞}        # added to kelly_target; trim fires above kelly_target + drift_buffer; ∞ = trim OFF (incumbent)
topup_thresh  ∈ {0.02, 0.03, 0.05}                 # top_up_threshold
```

Total: 5 × 5 × 3 = 75 parameter combinations (no pruning needed — every
combination is a valid, distinct configuration under the frozen trigger
form).

### Implementation

**No new code needed for the sweep itself.** The existing sim A/B harness
(`scripts/run_kelly_sigma_horizon_ab.py` pattern) can run config diffs.
What's needed:

1. **Config wiring**: `max_concentration` already exists and continues to
   govern entry sizing + TopUp ceiling, unchanged. Add `drift_buffer` (default
   = current implicit `trim_threshold` value, for backward compat) —
   `TrimHeldTask` reads `kelly_target + drift_buffer` as its trim trigger,
   which is the SAME expression it already evaluates today (`kelly_target +
   trim_threshold`); `drift_buffer` simply becomes a config-swept name for
   the same slot `trim_threshold` already fills. No new comparison operator,
   no new code path in `TrimHeldTask`.

2. **Sweep runner**: generate config variants for the grid, run 27-month OOS
   with the frozen seed set below, collect per-regime AND full-period
   metrics.

### Controls (§7.2 mandatory)

- **A/A**: golden vs golden (seed offset) — must be zero-delta
- **Placebo**: shuffle labels — any lift must disappear
- **Incumbent**: current config (entry_cap=0.12, drift_buffer=∞,
  topup_thresh=0.05) as control arm

### Seed set and verdict rule (round 2 — Codex review)

Per this repo's established gate-design convention (`doc/research/2026-07-03-d3-core-shrink-check.md`
§ seed unanimity; `doc/design/2026-07-03-expkit.md`: "seeds are robustness,
never extra looks"), a single-seed or loosely-aggregated multi-seed read is
under-powered: the relevant statistics here move by roughly ±0.02 across
training seeds, which is not small relative to plausible effect sizes.

**Frozen seed set**: `{42, 43, 44}` (3 seeds, matching this repo's standard
triple used in `d3-core-shrink-check`). No seed may be added, dropped, or
substituted after this doc is approved.

**Verdict rule (unanimity, not mean/median)**: a candidate config clears the
decision rule below only if **all 3 seeds** independently satisfy every
numbered criterion. If even one seed fails any criterion, the config's
verdict is NULL for that criterion (not "average out" or "2-of-3
majority") — matching the D3/M8 convention that seeds are a robustness
check, not additional statistical power to be pooled.

### Metrics

Per-regime (BULL_CALM, BEAR, BULL_VOLATILE — the full regime taxonomy used
elsewhere in this repo, not just the primary regime) AND full-period/full-OOS
pooled:
- APY, Sharpe, MaxDD, Calmar
- Cash% (time-weighted)
- Concentration: max single-name weight (peak), HHI(book)
- TopUp firing rate (how often TopUp actually adds)
- Winner-continuation: returns of positions that exceeded entry_cap via drift
  (did letting them run help or hurt?)

**Transaction-cost / churn metrics — required outputs (round 2 — Codex
review)**: `top_up_threshold` is explicitly a churn-control knob, and the
decision rule below requires Sharpe "net of transaction costs" — that claim
is only auditable if churn is itself a first-class reported metric. Every
config run must additionally report:
- **Turnover**: sum of |Δweight| per rebalance, annualized
- **Fill count**: number of TopUp/Trim/entry fills over the 27-month window
- **Cost delta vs incumbent**: modeled transaction cost (existing sim cost
  model) in bps, compared to the incumbent config's modeled cost over the
  same window

### Decision rule

Promote a config to golden (via §7.4 Tier 3) only if, **for all 3 frozen
seeds** (per the unanimity rule above):

1. BULL_CALM Sharpe ≥ incumbent, using returns that already have the modeled
   transaction cost subtracted (i.e., criterion 1 is evaluated on net-of-cost
   Sharpe, not gross Sharpe with cost reported as a footnote)
2. MaxDD (BULL_CALM) ≤ incumbent × 1.10 (no more than 10% worse drawdown)
3. **Full-period/full-OOS Sharpe ≥ incumbent − 0.02** (no material
   regression on the pooled book-level metric; the 0.02 materiality band
   matches this repo's ±0.02 seed-noise convention, so a full-period
   "regression" smaller than seed noise is not grounds for rejection, but
   anything larger is)
4. **Worst-regime Sharpe ≥ incumbent's worst-regime Sharpe − 0.02, AND
   worst-regime MaxDD ≤ incumbent's worst-regime MaxDD × 1.10** — evaluated
   against whichever of {BULL_CALM, BEAR, BULL_VOLATILE} is worst for the
   INCUMBENT (a candidate cannot win by improving the regime that was already
   the incumbent's best while quietly degrading the regime that was already
   weakest)
5. **Turnover does not exceed incumbent's turnover by more than 25%** (a
   config that wins on net-of-cost Sharpe by churning 3x more is not a clean
   win — this bounds how much of criterion 1's edge is allowed to come from
   a cost model that may itself be imperfectly calibrated)
6. Placebo shows no lift (the improvement is signal-driven, not overfitting)
7. The "winner continuation" analysis confirms that un-trimmed drift above
   entry_cap is net positive (otherwise we're just lucky on the test window)

## What this research is NOT

- **Not a case to increase risk.** Entry cap may stay at 12% or go lower.
  The question is whether treating drift differently from entry improves
  risk-adjusted returns.
- **Not re-opening trim.** The 04-24 A/B showed trim hurts when pegged to
  Kelly target with the incumbent buffer. This asks whether a *wider* buffer
  above the Kelly target (i.e., a bigger `drift_buffer`, up to and including
  ∞ = off) changes that conclusion — it might, because a wide buffer only
  fires on extreme concentration, not on normal winners. It explicitly does
  NOT ask whether a *different trigger mechanism* (e.g., a fixed absolute
  cap independent of the moving Kelly target) would do better — that is a
  separate, out-of-scope hypothesis that would need its own staged/factorial
  design if pursued later.
- **Not changing any live behavior.** Results go through the standard
  §7.4 Tier 3 gate before touching golden.

## Estimated effort

- Config wiring + TrimHeldTask `drift_buffer`: 1 PR (renquant-pipeline)
- Sweep runner script: 1 PR (renquant-orchestrator or umbrella)
- Execution: ~3-6 hours wall clock (75 configs × 3 frozen seeds × 27-month, serial)
- Analysis memo: 1 doc

## Open questions for operator

1. Is 12% entry cap negotiable, or is it a hard risk mandate regardless of
   what the data shows?
2. Should the sweep include `max_concurrent_positions` as a 4th dimension?
   (Currently 8 in BULL_CALM — at 12% each that's 96% max invested, which
   seems fine.)
3. Any prior intuition on where `drift_buffer` should land? The 04-24 A/B
   suggests "don't trim at all" (i.e., `drift_buffer = ∞`) is hard to beat,
   but that was with the old 35% max_conc.
