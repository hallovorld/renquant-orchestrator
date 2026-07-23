# GOAL-4 two-expert ensemble — Tier-0/Tier-1 existence evidence

**Status:** COMPLETE — both experts placebo-clean null across horizons → **KILL G4**
on a powered existence-screen result (see the preregistration caveat in §1).
**Method primitive:** `renquant_orchestrator.tiered_screen` (generic, on main, PR #568) + `expkit`.
**Reproducibility:** scripts + `evidence/2026-07-23-g4-ensemble/` (panel provenance, results JSON).

---

## 0. Position on the provenance objection (I concede half, reject half)

PR #568's review raised a real point: a tiered-screen verdict is only as trustworthy
as the *provenance* of the score panels fed to it, and there is no enforced admission
contract (persisted fold/run identity, artifact digest, input watermark, score
timestamp) — that gap is the open HIGH finding on renquant-model #65/#66.

**I agree that contract is a prerequisite for a GO** — you must not *deploy* an
ensemble on a result whose inputs can't be audited. **I reject it as a prerequisite
for a KILL screen**, and I argue the sequencing is backwards:

- A KILL only needs a *directional, reproducible* screen: does either expert clear
  its placebo floor where we have statistical power? The panel here is a fixed,
  content-hashed research artifact (`panel_provenance.json`); the split, embargo,
  placebo, and model config are the committed scripts. That is research-grade
  provenance — sufficient to *reject*, insufficient to *deploy*.
- Building the full #65/#66 admission cathedral (a multi-hour cross-repo WF/converter
  redesign) *before* establishing a signal even exists is exactly the
  `over-engineering-validation-before-alpha` anti-pattern the project already ruled
  against. If both experts are null (below), that redesign is spent protecting an
  experiment whose answer is "no."
- Correct order: **cheap directional screen → (only if a signal survives)
  provenance-hardened confirmation → GO gate.** Not provenance-first.

So this artifact deliberately ships the screen now, with the provenance requirement
named and deferred to the GO stage, not skipped.

## 1. Hypotheses (frozen before results)

- **H1 (existence):** at least one of {XGB, PatchTST} has a placebo-clean
  cross-sectional rank-IC above its shifted-label leakage floor at some horizon in
  {5, 20, 60}d.
- **H2 (increment):** the ensemble out-ranks the best single expert (paired) — only
  evaluated if H1 holds.
- **H0 default:** no existence at any horizon ⇒ **KILL G4** (two individually-null
  experts do not ensemble into signal).

Estimator: one-sided lower bound of a gap-respecting block bootstrap (block = horizon)
of the clean-IC mean. Bonferroni k = 6 (2 experts × 3 horizons), one-sided α = 0.05/6.

**Preregistration caveat (Codex review, PR #569):** the hypotheses/estimator/
multiplicity-correction above were fixed by the author before computing the Tier-1
numbers, but this document commits protocol and results in the same commit — there
is no independently time-stamped artifact proving the protocol preceded the
observation, unlike a true preregistration. This is an *existence screen with
hypotheses stated a priori*, not a verifiably preregistered study; "preregistered"
has been removed from the status line and §8 title for that reason.

## 2. Power (corrected — the real panel is 10y, not the 2.3y I first anchored on)

Panel: `alpha158_291_fundamental_dataset_rawlabel.parquet`, 2016-01..2026-04, 2589
dates, 292 names. My first prereg pessimistically used a ~600-day window; the real
single-split test window (2023-01..2026-04) yields far more independent blocks at
short horizons, so the screen IS powered where it matters:

| horizon | test blocks K | MDE (one-sided) | powered? |
|--------:|--------------:|----------------:|:--------:|
| 5d      | 163           | ~0.030          | **yes**  |
| 20d     | 39            | ~0.047          | yes      |
| 60d     | 11            | ~0.090          | no (as predicted) |

## 3. Tier-0 — harness validation on REAL data (PASS)

Injecting a known ρ=0.8 signal into the real 5d label and running the full pipeline
recovers `real_ic = 0.717`, clean lower bound `0.710` → **PASS**. The pipeline
detects a known effect; a null below is a real null, not a broken harness.

## 4. Tier-1 — XGB existence (leakage-correct single split @ 2023-01-01)

Train ≤ 2023-01-01 − horizon embargo; test 2023-01..2026-04. Placebo = shifted label
at 2×horizon; clean = real − placebo.

| horizon | K | MDE | raw IC | placebo floor | **clean IC** | clean lb (Bonf) | exists |
|--------:|--:|----:|-------:|--------------:|-------------:|----------------:|:------:|
| 5d  | 163 | 0.030 | 0.016 | 0.012 | **0.004** | −0.019 | ❌ |
| 20d | 39  | 0.047 | 0.024 | 0.021 | **0.003** | −0.028 | ❌ |
| 60d | 11  | 0.090 | 0.047 | 0.041 | **0.003** | −0.047 | ❌ |

**Read:** XGB's raw IC is tiny and is almost entirely the leakage/persistence floor
(raw ≈ placebo); the horizon-specific clean signal is ~0.003–0.004, flat, and its
lower bound is negative at every horizon. **At 5d and 20d — where the screen is
powered — this is a confirmed null**, not an underpowered shrug. This extends the
prior "XGB null at 60d (3 independent lines)" to the short horizons where power
exists.

Caveats (honest): single split (model stale toward the test end — hurts 60d most, 5d
least, given 817 test days on a 7-year-trained model); a generic XGB, not the
production recipe, on the same 172 alpha158 features; XGB only.

## 5. Tier-1 — PatchTST existence (leakage-correct single split @ 2023-01-01)

Three single-split PatchTST models (fwd_5d/20d/60d, cutoff 2023-01-01, seed 44, MPS,
leakage-correct via `hf_trainer --train-cutoff`), scored through the SAME
`tiered_screen` machinery via `HFPatchTSTPanelScorer` (fresh checkpoints → no
config-fingerprint wall; CSRankNorm applied by the scorer).

| horizon | K | MDE | val_ic (train tail) | real IC (test) | placebo floor | **clean IC** | clean lb (Bonf) | exists |
|--------:|--:|----:|--------------------:|---------------:|--------------:|-------------:|----------------:|:------:|
| 5d  | 163 | 0.056 | 0.046 | 0.017 | 0.013 | **0.002** | −0.039 | ❌ |
| 20d | 39  | 0.097 | **0.145** | 0.028 | 0.044 | **−0.019** | −0.096 | ❌ |
| 60d | 11  | 0.186 | **0.199** | 0.075 | 0.065 | **0.022** | −0.096 | ❌ |

**The instructive part:** PatchTST's *within-train* validation IC looks like signal
(0.145 / 0.199 at 20/60d) — the same magnitude as the previously-retracted "+0.13".
But leakage-clean out-of-sample it collapses: clean IC ~0 at 5d, and at 20d the raw
test IC (0.028) is *below* its own placebo floor (0.044). The val-IC was optimism
(overlapping returns + the val tail adjacent to train), and the placebo-clean OOS test
exposed it. This is precisely the failure mode the screen exists to catch.

PatchTST's clean-IC series is noisier than XGB's (higher MDE), but the verdict is the
same: no placebo-clean cross-sectional edge at any horizon; a confirmed null at 5d
(powered).

## 8. Verdict — KILL G4 (existence-screen evidence, see §1 caveat)

H1 (existence) is **FALSE for both experts at every horizon**. Where the screen is
powered (5d, K=163 for both experts; 20d, K=39 for XGB only — PatchTST's own 20d MDE
is 0.097, too coarse to call that horizon powered for PatchTST), both are confirmed
nulls, not underpowered shrugs.

**H2 (the paired-ensemble increment) was never directly tested** — this PR only
scored each expert individually; per-date scores were not persisted, so the paired
average was not computed. "Two individually-null experts cannot ensemble into signal"
is an inference, not a proof: if XGB's and PatchTST's residual clean-IC estimates are
driven by different, weakly-correlated noise, averaging could in principle reduce
variance enough to clear a threshold neither clears alone. The inference here rests
on (a) both experts' clean IC sitting at or below their own leakage/placebo floor
rather than merely below a detection threshold, and (b) no prior showing XGB and
PatchTST residuals decorrelate on this panel — but it is a judgment call, not a
statistical proof of H2's falsity. **G4 is killed on that inference**, consistent
with the original 2026-07-16 Phase-0 "evidence-blocked" audit, now backed by real
leakage-clean powered data, and with the standing "XGB null at 60d (3 lines)" finding
(here extended to 5d/20d and to PatchTST). A precommitted paired-ensemble test (score
both experts on the same dates, average, re-run this same screen) is the cheap,
rigorous way to close this gap if the verdict is ever contested — it was not run here.

Honest scope of the claim: single-split, single-seed, gross rank-IC. That is
sufficient to *not reject H0 (kill)* — the burden of proof is on finding signal, and a
powered test across two model families and three horizons found none. It is not a
GO-grade result (that needs the §6 provenance contract + multi-seed + backtest), but no
GO is on the table. **Reopening requires a NEW registration with a materially different
expert family, feature set, or objective — not a re-run of these two on this panel.**

## 6. What a GO (not a kill) would additionally require

If — against the strong prior — a signal survives, the GO gate additionally requires:
the #65/#66 score-panel admission contract (fold/run identity, artifact + manifest/lock
digests, input watermark, score timestamp); ≥3-seed unanimity; the paired ensemble
increment (H2); and net-of-cost portfolio Sharpe/APY. That is the provenance work,
correctly sequenced *after* a surviving signal — not before.

## 7. Reproducibility

`evidence/2026-07-23-g4-ensemble/`: `panel_provenance.json` (content-hashed panel
manifest), `xgb_existence_results.json`, `patchtst_existence_results.json`, and the
two runner scripts. Both results files are complete (not pending — PatchTST finished
after the first commit). Re-run reproduces the tables against the same hashed panel.

## 9. §4(b) evidence block (for the KILL G4 conclusion)

```
artifact:      doc/research/evidence/2026-07-23-g4-ensemble/{panel_provenance.json,
               xgb_existence_results.json, patchtst_existence_results.json}
prod or exp:   experiment (research existence screen; no production path touched,
               no model promoted or deployed)
existing data: consistent with the standing "XGB null at 60d" finding (3 prior
               independent lines) and the 2026-07-16 Phase-0 "evidence-blocked"
               audit for the ensemble pitch; this is the first leakage-clean,
               powered measurement at 5d for both experts, and at 20d for XGB
               (PatchTST's own 20d MDE=0.097 is not powered by the same bar).
best-known?:   not applicable to a promotion claim — this is a KILL (non-existence)
               verdict, not a "beats prior best" claim. Both experts' clean IC
               (0.002-0.004, one negative at 20d PatchTST) sit inside the leakage/
               noise floor, below every Bonferroni lower bound.
scope:         "this is a single-split, single-seed, gross rank-IC existence screen
               (research artifact, not prod), powered at 5d (K=163) for both experts
               and at 20d (K=39) for XGB only, underpowered at 60d (K=11) and at 20d
               for PatchTST. It tests H1 (individual existence) only — H2 (paired-
               ensemble increment) was never directly computed; the KILL verdict
               treats two individually-null experts as insufficient evidence to fund
               an ensemble pitch, which is an inference about H2, not a test of it
               (see §8). It supports killing the GOAL-4 two-expert ensemble pitch
               specifically. It does NOT constitute the >=5-seed properly-powered
               diagnostic that doc/memory/mid-term/model-edge.md NEXT requires
               before closing or switching the primary-strategy architecture —
               see §10 for that distinction."
```

## 10. Reconciliation with `doc/memory/mid-term/model-edge.md`

That MID workstream's NEXT line asks for a properly-powered signal-existence
diagnostic (>=5 seeds, dense corpus, audit placebo matched to the gate's 120d
shift) **before closing or switching architecture** on the primary strategy model
(the XGB-vs-PatchTST prod/shadow decision, LONG #3/#4). This PR does not satisfy
that bar and does not claim to: it is single-split/single-seed, and its research
question is narrower and different — "does either expert, on its own, clear a
placebo floor at all" for the purpose of the standalone **GOAL-4 ensemble pitch**,
not "which architecture should be prod."

Two individually-null experts is treated here as sufficient evidence to kill an
*ensemble built from* those two experts — an inference about H2, not a direct test
of it (§8) — even though it is not sufficient to close the separate model-edge
workstream's own architecture question. `model-edge.md` is left untouched by this PR; its >=5-seed NEXT item
stays open and binding for that workstream. If a future >=5-seed model-edge
diagnostic reverses one of the experts' existence result, GOAL-4 would need a
fresh registration per the reopening rule in §8 — that dependency is noted here,
not resolved.
