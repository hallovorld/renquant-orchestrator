# S3 v3 Gate Promotion Study Design

DATE: 2026-07-04
STATUS: STUDY DESIGN (pre-registration for the v3 promotion experiment)
BLOCKS: D1 (first WF verdict under repaired gate), S4 (substance gate), all SHORT evidence items
DEPENDS: S1/S2 (MERGED), S3 shadow (MERGED, backtesting #61)

## Bottom line

The v2 enforced gate (absolute placebo-IC ceiling) is **structurally unsatisfiable**:
the ~0.04 embargo floor from the 30d embargo gap on 60d labels means every model's
placebo IC exceeds the threshold by construction, regardless of genuine signal.
Replay of 8 staging artifacts confirms: **v2 rejects 8/8, v3 would pass 8/8.**
Promoting v3 (difference test) is the critical path to unblocking D1.

## The v2 → v3 change

| Gate | Test | Threshold | Problem |
|------|------|-----------|---------|
| **v2 (enforced)** | `abs(placebo_ic) < max(0.005, 0.5 * abs(aligned_real_ic))` | Absolute ceiling on placebo IC | The ~+0.04 embargo floor inflates placebo_ic structurally; threshold ≈ 0.043 but floor ≈ 0.053 → permanent FAIL |
| **v3 (shadow-only)** | `genuine_ic = aligned_real_ic − placebo_ic > 0.02` | Difference above 0.02 | Cancels the shared floor; tests whether the model has signal ABOVE the label-persistence artifact |

v3 is the correct test because the embargo floor affects BOTH placebo and real IC
equally. Only their DIFFERENCE isolates model signal. This is the same logic that
makes us trust placebo-clean differences throughout the evidence framework.

## Historical replay (already done)

| Metric | Value |
|--------|-------|
| Artifacts with Layer-1a data | 8 (2026-06-17 → 2026-06-30) |
| v2 verdict | FAIL 8/8 |
| v3 would-be verdict | PASS 8/8 |
| Genuine IC @2× pooled | +0.034 (stable, same model) |
| Aligned real IC | +0.087 |
| Placebo IC | +0.053 |
| Shuffled IC | −0.0004 (< 0.005, clean) |
| n_dates | 388 |

All 8 artifacts evaluate the same model (same training cutoff), so there is
effectively **1 independent observation** with n=388 OOS dates. This is
sufficient to confirm v2's structural failure but NOT to validate v3's threshold.

## What must be established before v3 can be promoted to enforcement

### 1. False-accept rate (Type I error)

**Question:** How often does v3 pass a model that is genuinely confounded
(has no real signal, only embargo persistence)?

**Method:** Construct synthetic "null models" by shuffling the
cross-sectional rank assignment while preserving the temporal structure. These
models should have genuine_ic ≈ 0 by construction. Run them through v3 and
measure the pass rate.

- Generate K=100 null models via cross-sectional permutation
- Compute genuine_ic for each
- v3 false-accept rate = fraction where genuine_ic > 0.02

**Acceptance criterion:** false-accept rate < 5%.

### 2. False-reject rate (Type II error)

**Question:** How often does v3 reject a model that genuinely has signal?

**Method:** Since we only have one primary model (XGB), construct a
"known-good" reference by evaluating the production model on progressively
shorter val windows (reducing n_dates). v3 should still pass as long as the
model has signal, even with noisier estimates.

- Evaluate production model on subsets: n=300, 250, 200, 150, 100, 50 dates
- Record genuine_ic at each
- v3 false-reject rate = fraction where genuine_ic drops below 0.02 despite
  the full-sample genuine_ic being clearly positive

**Acceptance criterion:** false-reject < 10% at n ≥ 100.

### 3. Threshold sensitivity

**Question:** Is 0.02 the right threshold, or should it be adaptive?

**Analysis:**
- Plot the distribution of genuine_ic across the null models (from §1) and
  the production model (from §2)
- Compute the separation: `threshold_at_5pct_false_accept` from the null
  distribution
- If the data-driven threshold differs materially from 0.02, document the
  trade-off and recommend

**Current hypothesis:** 0.02 is conservative (embargo floor ≈ 0.04–0.05
means genuine_ic ≈ 0 for null models), but this must be verified empirically.

### 4. Minimum sample floor

**Question:** Below what n_dates does genuine_ic become too noisy to trust?

**Method:** Bootstrap the production model's per-date IC series:
- For block sizes B=5, 10, 20:
  - Draw 1000 bootstrap samples of size n=50, 100, 150, 200, 250
  - Compute genuine_ic for each sample
  - Record the std(genuine_ic) as a function of n
- The minimum sample floor = smallest n where the 95% CI of genuine_ic
  excludes zero (given the observed genuine_ic ≈ 0.034)

**Acceptance criterion:** n_floor documented; artifacts below this floor get
a WARNING, not a hard FAIL (v3 degrades to "insufficient data" rather than
false-rejecting).

### 5. Per-regime decomposition

**Question:** Does genuine_ic vary by regime, and should the gate be
regime-aware?

**Current data (from staging artifact):**
- BEAR: genuine_ic = +0.355 (n=49)
- BULL_CALM: genuine_ic = −0.011 (n=302)
- BULL_VOLATILE: genuine_ic = −0.077 (n=11)
- CHOPPY: genuine_ic = −0.011 (n=26)

The production model shows genuine signal in BEAR only (where n=49). The
BULL_CALM regime (n=302, the dominant regime) shows genuine_ic ≈ 0.

**Analysis:** This decomposition is informative but should NOT gate v3
promotion — the pooled genuine_ic is the right metric for a pooled model.
Per-regime gates are a future refinement (post-D1).

## Execution plan

| Step | What | Estimated effort | Blocker |
|------|------|-----------------|---------|
| 1 | Null-model false-accept test (§1) | Script + 1h compute | None — can start now |
| 2 | Subsample false-reject test (§2) | Script + 30min compute | None |
| 3 | Threshold sensitivity (§3) | Analysis on §1/§2 data | Needs §1, §2 complete |
| 4 | Bootstrap sample floor (§4) | Script + 30min compute | None |
| 5 | Write promotion PR | Gate code change in backtesting | Needs §1–§4 results |
| 6 | D1 verdict run | Run promoted gate against prod artifact | Needs §5 merged |

Steps 1, 2, 4 can run in parallel. Total wall-clock: ~1 day of scripting +
compute. The scripts should be committed to `renquant-backtesting/scripts/`
alongside the analysis output.

## Pre-registration

- **Primary outcome:** v3 false-accept rate < 5% AND false-reject rate < 10%
  at n ≥ 100 → PROMOTE v3 to enforcement
- **If false-accept > 5%:** raise threshold until false-accept = 5%, document
  the data-driven value
- **If false-reject > 10% at n ≥ 100:** investigate whether genuine_ic
  variance is driven by regime mixing; consider regime-conditioned thresholds
  (future work, does not block D1)
- **Evidence boundary:** this study covers XGB panel models on alpha158 with
  60d fwd labels. PatchTST, different label horizons, and different feature
  sets require their own validation

## Data sources

- Staging artifacts: 8 with Layer-1a data in
  `RenQuant/backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.weekly_*.json`
- Gate runner: `renquant_backtesting.wf_gate.runner` (backtesting repo, main)
- Shift diagnostics: `renquant_backtesting.analysis.analyze_manifest_sanity_placebo`
- v3 shadow code: backtesting PR #61 (merged)
