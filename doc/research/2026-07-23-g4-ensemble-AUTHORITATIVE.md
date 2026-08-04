# GOAL-4 two-expert ensemble — AUTHORITATIVE verdict (corrected + 3-way cross-audited)

**Disposition: KILL G4 on current evidence — with an explicit, cheap reopening path.**
Both experts and the direct ensemble are placebo-clean null at every horizon on
*corrected* models; the result is leakage-clean, reproduced by two independent
auditors, and positive-control-validated. It is a single-split/single-seed **powered
screen**, not a production walk-forward final gate — so the kill is the right
*disposition* (burden of proof is on finding an edge; none was found across 2 model
families × 3 horizons × the ensemble), gated to reopen on one bounded WF confirmation.

Supersedes the original 2026-07-23 existence note, which was **correctly WEAKENED** by
independent verification (a PatchTST training bug) — now fixed and re-run.

---

## 1. The corrected data (all leakage-correct single-split @ 2023-01-01, Bonferroni α/6)

Per-expert existence (clean IC = real − shifted-label placebo floor; `exists` iff
one-sided bootstrap lower bound > 0):

| arm | 5d (K=163) clean / lb | 20d (K=39) clean / lb | 60d (K=11) clean / lb | exists |
|---|---|---|---|---|
| **XGB** | +0.004 / −0.019 | +0.003 / −0.028 | +0.003 / −0.047 | ❌ all |
| **PatchTST** (fixed `--cut all`) | −0.015 / −0.031 | −0.022 / −0.096 | +0.005 / −0.083 | ❌ all |
| **ENSEMBLE** (equal-wt z-score, direct) | −0.008 / −0.031 | −0.011 / −0.077 | +0.019 / −0.069 | ❌ all |

**The ensemble was directly tested (not inferred).** At 60d the raw decorrelation
boost is visible — ensemble real IC 0.072 > either expert (XGB 0.047, PatchTST 0.043),
cross-sectional corr(XGB,PatchTST) ≈ 0.04 — **but the placebo floor rose in lockstep to
0.060**, so the placebo-clean increment is +0.019 (lb −0.069), still null. Mechanism:
equal-weight averaging diversifies the leakage/persistence signal identically to any
real signal, so no *clean* diversification lift survives.

## 2. The correction that this report rests on

The original kill was WEAKENED because PatchTST's `--train-cutoff` did not override the
default `cut1_covid` split: models trained only to 2019-10 and selected best_val_ic on
the **2020 COVID-crash window** (that produced the seductive val_ic 0.046/0.145/0.199).
Retrained with `--cut all` (train 2016→2022, validation = a 2022 tail, OOS ≥ 2023),
the honest val_ic collapses to **0.014 / −0.044 / −0.057** and OOS clean IC is null —
i.e. a *properly-trained* PatchTST is null, not better. **Fixing the bug strengthened
the kill.**

## 3. Three independent cross-audits (the operator distrusted the data)

| auditor | lens | verdict |
|---|---|---|
| **A** | methodology & leakage | **WEAKENED** (2 gaps) |
| **B** | PatchTST training-correctness | **KILL-SOUND** |
| **C** | statistics / power / multiplicity | **KILL-SOUND** (power-overclaim corrected) |

**Unanimous:** train strictly precedes test + horizon embargo (max feature|corr| vs
label = 0.030; labels excluded from X); XGB numbers reproduced to the digit by A and C;
positive control passes (inject ρ=0.8 → recover 0.717 → the null is not a dead
pipeline); XGB genuinely null; cut1_covid bug real and the fix genuine (B recomputed
the broken val_ic from `val_preds.parquet` on the actual 2020-crash dates).

**A's two gaps, resolved:**
- *Gap 1 — the ensemble was never tested on the fixed models.* **CLOSED** by §1: direct
  ensemble null at all 3 horizons, no clean diversification lift.
- *Gap 2 — fixed PatchTST 20d/60d under-trained (val_ic −0.044/−0.057), so their null is
  uninformative.* **B rebuts:** correct training makes val_ic *worse*, not better; a
  ~0/negative in-sample val IC means "little to fit," not "failed to fit a real signal"
  (an undercapacity model would still capture *some* in-sample signal if present).
  A's caution is not fully eliminated — it is exactly what the residual experiment (§5)
  closes — but B's argument is the stronger one.

**C's honest correction (adopted):** "POWERED null" is only literally true for XGB-5d
against a *strong* edge (recomputed MDE_Bonf = 0.039, power 0.83 at IC 0.04 but only
~0.54 at 0.03, ~0.23 at 0.02); PatchTST/ensemble (σ≈0.28, MDE≈0.07) and 60d are
under-powered against a *modest* edge. **What licenses the kill is that every point
estimate is indistinguishable from zero and real≈floor everywhere** — low power only
bites when you fail to reject a *promising* estimate, and there is none.

## 4. What is established (hard)

Leakage-clean, reproduced, positive-control-validated: **XGB, PatchTST, and their direct
ensemble each contribute no placebo-clean cross-sectional rank skill beyond the
embargo-leakage floor, at 5/20/60d, on this panel.** Single-split staleness biases IC
*downward* (conservative toward kill). The kill is robust to the alternate placebo
convention (shift = h).

## 5. Honest residual + the one bounded experiment

This is a **powered screen, not the production WF gate.** Two residuals remain before
"definitive":
1. **Multi-seed × purged-embargoed-K-fold × full walk-forward** — the single bounded run
   all three auditors gate for. Single seed=44, best_epoch 3–4, a 2022-only regime-
   confounded validation split leave a small chance a *modest* (IC 0.02–0.03) edge is
   masked by selection noise. Given in-sample val IC ≈ 0, the prior on this is low.
2. **The ceiling is the FEATURE FAMILY, not the model** (B): only price-derived daily
   features — consistent with the standing "canonical price-trend has no stable
   multi-day edge" finding. A real edge would come from a *different* feature set
   (analyst / fundamental / orthogonal), i.e. a different experiment, not a PatchTST
   knob (more seeds/epochs/capacity would not plausibly flip a ~0 in-sample signal).

## 6. Disposition & reopening

**KILL G4** as the 2-expert (XGB+PatchTST) price-feature ensemble: no clean edge in
either expert or the ensemble, on a powered screen, across 3 horizons. **Reopening is
cheap and pre-specified:** either the §5.1 WF confirmation (if someone wants
definitive-grade), or — more promisingly — a NEW registration with a materially
different **feature family**. Not a re-run of these two experts on price features.

## 7. Evidence (reproducible)

`evidence/2026-07-23-g4-ensemble/`: `xgb_existence_results.json`,
`patchtst_existence_FIXED_results.json`, `h2_ensemble_FIXED_results.json`,
`panel_provenance.json`, and the runner scripts. Method = `renquant_orchestrator.expkit`
+ `tiered_screen` (per-date IC, shifted-label placebo, gap-respecting block bootstrap).
