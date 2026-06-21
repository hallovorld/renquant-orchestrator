# PatchTST edge-recovery — partial verdict (Exp B 2-seed only) + methodology caveats

Narrow result for the pre-registered experiment (`2026-06-19-...-experiment.md`).
**This does NOT complete the prereg** (which requires >=2 seeds *per arm*): Exp A is **seed44
only**; only **Exp B** has 2 seeds. So this is a focused verdict on the **Exp B branch**, not a
closure of the broader pruning line.

## Verdicts run so far (production WF gate, 60d)

| arm | seed | aligned_real_ic | placebo_ic | threshold | monotonicity | VERDICT |
|---|---|---|---|---|---|---|
| Exp A (prune STD/MIN/IMIN) | 44 | +0.0046 | +0.0317 | 0.0050 | FAIL BULL_CALM | FAIL |
| Exp B (+ pure-placebo) | 44 | +0.0079 | +0.0059 | 0.0050 | FAIL BULL_CALM | FAIL |
| Exp B (+ pure-placebo) | **45** | **-0.0085** | -0.0100 | 0.0050 | FAIL BULL_CALM | FAIL |

`[VERIFIED -- /tmp/exp_A_gate.log, /tmp/exp_B_gate.log, /tmp/exp_B45_gate.log, ephemeral]`

## What is defensible (narrow)
- **The Exp B prune recipe does not show a stable edge across its 2 seeds:** aligned_real_ic is
  **+0.0079 (s44) vs -0.0085 (s45)** -- sign-unstable, indistinguishable from zero.
- **No promotable model exists on any completed run.** No promotion is justified; the gate is
  correctly blocking (not bypassed).

## What is NOT established (do not overclaim)
- **The broader "pruning line" is NOT closed.** Exp A is single-seed; the prereg >=2-seeds-per-arm
  is not executed. "Falsified" / "CLOSED" (earlier wording) was an overclaim, corrected here.
- **Causal attribution** ("those families are the placebo drivers") remains provisional.

## Methodology caveats (self-audit -- these limit how much any of this means)
1. **All ICs are in the noise band** (|aligned_real_ic| = 0.0046-0.0085, all < 0.01). The gate's
   placebo threshold = `0.5x|aligned_real_ic|` **floored at 0.0050**, so the floor dominated in
   every run -> the placebo-ratio test is **ill-conditioned when the real IC ~ 0**. The seed44
   "near-miss" (0.0059 vs 0.0050) was a difference between two noise-band numbers.
2. **Sparse corpus for speed:** builds used `--cadence-days 360` (**4 cutoffs**), chosen for
   turnaround, not rigor -- fewer WF windows = noisier gate IC. B2's original "+0.024 val IC" was
   a *different* measurement (single-model val, val_days=126), so Exp A does **not** cleanly
   reproduce it; val-IC and gate-IC were partly conflated.
3. **Audit/gate placebo mismatch:** the `feat_ic_audit` that chose Exp B's extra prune used a
   per-ticker `shift(-60 rows)` placebo, while the gate uses a **120d (2xhorizon) time-shift**.
   So Exp B's prune-target selection rests on a placebo metric that **does not match the judge**.
4. **BULL_CALM monotonicity undiagnosed:** it fails in all runs, but I have **not** verified it is
   a real model failure vs a **low-sample artifact** (the gate needs >=30 trades/regime; the
   sparse corpus may starve BULL_CALM). Asserting it as a confirmed "second wall" is premature.

## Next (proposed; pending operator/Codex)
Before declaring any line dead or switching architecture: a **properly-powered signal-existence
diagnostic** -- >=5 seeds, dense corpus, audit placebo matched to the gate's 120d shift, and an
understanding of the near-zero-IC threshold behaviour -- plus a **BULL_CALM monotonicity diagnosis**
(real vs low-n). The IC is near-zero across *every* horizon+recipe, which *points* upstream
(signal/label) rather than at the horizon -- but that itself needs the powered test, not this
underpowered set, to assert.
