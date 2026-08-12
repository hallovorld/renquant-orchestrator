# orch#799 — FROZEN PREREGISTRATION: blend-substitution WF promote gate (option B)

STATUS: **FROZEN preregistration** — the design record that must be committed +
codex-approved BEFORE the umbrella `weekly_wf_promote.sh` / `run_wf_gate.py` gate
change implements it. Supersedes the rejected option A (#589, bare-leg reference).
No value below may change after this doc is approved; a change = a new dated
amendment doc, not an edit.

## 1. The problem (verified 2026-08-12)
Served prod primary = a **z-blend**: `kind=blend`,
`ranking.panel_scoring.components = [xgb_leg (panel-ltr.alpha158_fund), momentum_residual_leg]`
combined by an **unweighted** sum of per-component cross-sectional z-scores. The weekly retrain
produces a fresh **xgb leg**. The WF promote gate only accepts a top-level
`kind=xgb` config as the production reference → with a blend prod it refuses
(orch#799), so the weekly promote chain returns no verdict and the served model
cannot be refreshed.

No count of stuck jobs or uncovered names is asserted here. An earlier draft
carried "3 jobs" and "25/145 un-modelled watchlist names (17% coverage gap)";
this document has no reproducible source for either, and a prereg is the last
place an unsourced number should sit — it would read as frozen evidence. If the
scale of the blockage is load-bearing, it belongs in the document that measures
it, cited from there with its artifacts.

## 2. Why NOT option A (bare-leg) — codex-correct rejection of #589
Comparing the candidate xgb leg vs the current xgb leg **in isolation** evaluates
an object that is NOT served. A leg's standalone WF metric need not describe its
contribution inside the blend (a leg that scores better solo can combine WORSE
with momentum_residual — e.g. by raising correlation and cutting diversification).
Promoting on a standalone-leg metric is a scientifically invalid promotion
criterion for a served blend. REJECTED.

## 3. Option B — the blend-substitution rule (THE gate)
Promote the fresh xgb leg **iff it improves the SERVED BLEND**, measured directly:

- **Reference (control) = the current served blend** `B_ref = Σ z(xgb_leg_cur), z(momentum_residual_leg)`.
- **Candidate (treatment) = the leg-swapped blend** `B_cand = Σ z(xgb_leg_new), z(momentum_residual_leg)` — the xgb leg replaced by the candidate; the **momentum_residual leg and the combine rule held FIXED** (single-factor change → the measured Δ attributes to the leg swap **on non-degenerate folds**; see §4.6).

  **There is no weight vector and no stored z-normalization state to hold fixed.** `BlendPanelScorer.score` is an *unweighted* sum of per-component cross-sectional z-scores, `ddof=0` over each component's finite-scored universe, computed at scoring time; per-component weights are deliberately not introduced (they are the MoE stage's own preregistered change, AC5), and `ranking.blend_weights` is **absent** from the served config `[VERIFIED — pinned `renquant_pipeline/kernel/panel_pipeline/blend_scorer.py`; served `strategy_config.json` at strategy-104 `e00d935`; recorded in doc/design/2026-08-11-orch799-blend-prod-reference-rule.md]`. **The object to pin is therefore the PIPELINE COMMIT supplying that module**, recorded in the run receipt — not a config value. An earlier draft of this prereg froze `W` and `N`; both are fictions and are removed.
- **Metric**: the SAME return-space WF metric + §5.2 sanity battery the existing gate applies to a solo config, evaluated on `B_ref` and `B_cand` over the SAME walk-forward folds/manifest (paired, per-fold).
- **PASS iff** all of the following hold. These are the existing gate's own pre-declared values, transcribed here so this document freezes them rather than pointing at "whatever the gate uses" — a pointer a later implementation could still resolve after seeing results:

  | quantity | frozen value | source |
  |---|---|---|
  | incremental-edge margin | `aligned_real_ic − placebo_ic > margin`, **margin = +0.01** | `scripts/run_wf_gate.py` pre-registered config default `[VERIFIED — read from the pinned script]` |
  | real-IC floor | `aligned_real_ic > real_ic_floor` (pre-registered config value; the incremental criterion ALONE is unsafe — it passes a negative-IC model whenever the placebo is more negative) | same |
  | time-shift placebo ceiling | `\|placebo_ic\| ≤ max(0.005, 0.5 × \|aligned_real_ic\|)` | `_placebo_ic_threshold()` |
  | placebo evaluation mode | **`absolute`** (the default, reproducing the §5.2 ceiling exactly). The opt-in `difference` mode is NOT used by this gate | same |
  | decision statistic | the **paired per-fold difference** `B_cand − B_ref` on the identical fold set | §4.5 |
  | fold/date construction | the **existing WF manifest's** folds, unchanged — this comparison introduces no new fold scheme; a candidate that is not a fold-local WF manifest fails closed (§4.1) | §4.1, §4.5 |
  | degenerate-leg exclusion fraction | **ZERO** — see §4.6 | §4.6 |

  …AND `B_cand` passes the sanity battery (shuffled-label placebo + time-shift placebo) AND the recipe/fingerprint recipe-match guard passes. Else FAIL → **production unchanged** (fail-closed, as today).

## 4. No-leakage protocol (the load-bearing methodology codex required)
1. **Fold-local walk-forward legs.** The candidate xgb leg MUST be walk-forward
   retrained: each fold's leg trained ONLY on data with cutoff < that fold's eval
   window, matching the discipline of the reference blend's WF manifest artifacts.
   A single today-trained leg scored over historical folds is LOOK-AHEAD and is
   FORBIDDEN — the gate must FAIL CLOSED if the candidate is not a fold-local WF
   manifest (reuse the existing `manifest recipe mismatch` fail-closed path).
2. **Fixed combine rule.** There are no blend parameters to fix or refit — the
   combine rule is code, not config (§3). Both arms MUST run under the SAME
   pipeline commit, recorded in the run receipt; a differing commit invalidates
   the comparison. momentum_residual leg = the served one, unchanged.
3. **Deterministic candidate selection.** Exactly one candidate leg per run (the
   week's retrain output); no outcome-informed choice among reconstructions.
4. **Recipe/fingerprint parity.** `B_cand` and `B_ref` share every recipe field
   except the xgb-leg artifact; the model-relevant config fingerprint (excl.
   `panel_scoring.kind`/`components` labels) must match the WF manifest recipe, so
   a mismatched recipe still fails closed — no silent cross-recipe comparison.
5. **Paired, same folds.** Both arms evaluated on the identical fold set; the
   decision statistic is the paired per-fold difference.
6. **Degenerate-leg exclusion — ZERO tolerance, and why zero is not an invented
   number.** `BlendPanelScorer` gives a leg with `std == 0` or fewer than 2
   finitely scored names a contribution of **0**, recording
   `component{i}[…]_n_lt_2` / `_std_zero` in `metadata["degraded_reason"]` and
   failing SOFT inside the composite. On such a fold `blend == z(xgb)` alone, so
   a blend-vs-blend comparison there measures the leg swap **unblended** — a
   different estimand silently averaged in.

   **Any fold carrying a `degraded_reason` token for either leg invalidates the
   run: the comparison FAILS CLOSED. It does not proceed on the surviving folds.**
   Every other tolerance would need a calibration this document does not have
   (how much contamination is acceptable is a power question, not a taste
   question), and a fraction chosen without one would read as preregistered while
   being improvised. **Zero is the only value that requires no calibration to
   defend.** If practice shows it is too strict, that is a dated amendment doc
   carrying the evidence — not an edit to this one.

## 5. Scope / what this does NOT change
- No new threshold, no new estimand beyond "does the served blend improve"; the
  bar is the existing gate's.
- Structure unchanged: only component[0] (the xgb leg) is swapped on PASS;
  momentum_residual + weights + blend recipe stay.
- RFC#210 freshness governance, the scorer/calibrator binding gate, and the live
  `strategy_config.json` deploy remain SEPARATE operator-gated steps — a PASS earns
  the leg the right to be pin-proposed, not an automatic live swap.
- Fail-closed everywhere: missing WF manifest, non-fold-local candidate, recipe
  mismatch, sanity-battery fail, or below-threshold → production unchanged.

## 6. Implementation feasibility gate (for the implementer)
Before coding, verify the existing WF gate (`run_wf_gate.py` + the
walkforward_manifest machinery) can evaluate a BLEND config over per-fold blend
artifacts (i.e. construct `B_cand`/`B_ref` per fold from the leg + momentum_residual
+ W/N and score the return metric). If it can, implement §3 as the
reference-resolution + candidate-construction. If it CANNOT without new blend-eval
machinery, STOP and report the gap — do NOT fall back to a bare-leg (option A) or
any banned reference source; the alarm staying is preferable to a scientifically
invalid promote.

## 7. Acceptance (when implemented)
- A dry-run against the current served blend + the latest retrain candidate
  reaches a real PASS/FAIL verdict (no orch#799 refusal), production untouched.
- `B_cand` differs from `B_ref` ONLY in the xgb-leg artifact (fingerprint diff).
- The candidate is rejected fail-closed if it is not a fold-local WF manifest.
- On a synthetic PASS, only component[0] is swapped; momentum_residual + W + N
  byte-identical.
- The weekly not-acting alarm clears (the gate DECIDES instead of refusing);
  a subsequent PASS lets the refreshed leg be pin-proposed → unblocks the 25
  missing-model coverage via the normal retrain→promote→pin path.
