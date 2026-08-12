# orch#799 — FROZEN PREREGISTRATION: blend-substitution WF promote gate (option B)

STATUS: **FROZEN preregistration** — the design record that must be committed +
codex-approved BEFORE the umbrella `weekly_wf_promote.sh` / `run_wf_gate.py` gate
change implements it. Supersedes the rejected option A (#589, bare-leg reference).
No value below may change after this doc is approved; a change = a new dated
amendment doc, not an edit.

## 1. The problem (verified 2026-08-12)
Served prod primary = a **z-blend**: `kind=blend`,
`ranking.panel_scoring.components = [xgb_leg (panel-ltr.alpha158_fund), momentum_residual_leg]`
with fixed z-blend weights W and z-normalization params N. The weekly retrain
produces a fresh **xgb leg**. The WF promote gate only accepts a top-level
`kind=xgb` config as the production reference → with a blend prod it refuses
(orch#799) → 3 jobs (weekly-wf-promote, retrain-panel104, conditional-retrain104)
cannot promote, cycle after cycle; the served model cannot be refreshed, and the
25/145 un-modelled watchlist names (17% coverage gap) cannot be covered.

## 2. Why NOT option A (bare-leg) — codex-correct rejection of #589
Comparing the candidate xgb leg vs the current xgb leg **in isolation** evaluates
an object that is NOT served. A leg's standalone WF metric need not describe its
contribution inside the blend (a leg that scores better solo can combine WORSE
with momentum_residual — e.g. by raising correlation and cutting diversification).
Promoting on a standalone-leg metric is a scientifically invalid promotion
criterion for a served blend. REJECTED.

## 3. Option B — the blend-substitution rule (THE gate)
Promote the fresh xgb leg **iff it improves the SERVED BLEND**, measured directly:

- **Reference (control) = the current served blend** `B_ref = z-blend(xgb_leg_cur, momentum_residual_leg, W, N)`.
- **Candidate (treatment) = the leg-swapped blend** `B_cand = z-blend(xgb_leg_new, momentum_residual_leg, W, N)` — the xgb leg replaced by the candidate; **momentum_residual leg, weights W, and z-norm N held FIXED from the served config** (single-factor change → the measured Δ attributes cleanly to the leg swap; z-blend-attribution caveat honoured).
- **Metric**: the SAME return-space WF metric + §5.2 sanity battery the existing gate applies to a solo config, evaluated on `B_ref` and `B_cand` over the SAME walk-forward folds/manifest (paired, per-fold).
- **PASS iff**: `B_cand` beats `B_ref` by the existing pre-declared gate threshold (the same ΔSharpe/IC bar the solo-xgb gate used — NO new threshold invented here) AND `B_cand` passes the sanity battery (shuffled-label placebo + time-shift placebo) AND the recipe/fingerprint recipe-match guard passes. Else FAIL → **production unchanged** (fail-closed, as today).

## 4. No-leakage protocol (the load-bearing methodology codex required)
1. **Fold-local walk-forward legs.** The candidate xgb leg MUST be walk-forward
   retrained: each fold's leg trained ONLY on data with cutoff < that fold's eval
   window, matching the discipline of the reference blend's WF manifest artifacts.
   A single today-trained leg scored over historical folds is LOOK-AHEAD and is
   FORBIDDEN — the gate must FAIL CLOSED if the candidate is not a fold-local WF
   manifest (reuse the existing `manifest recipe mismatch` fail-closed path).
2. **Fixed blend parameters.** W and N are read from the served blend config and
   held constant across both arms and all folds; they are NOT refit on the eval
   data. momentum_residual leg = the served one, unchanged.
3. **Deterministic candidate selection.** Exactly one candidate leg per run (the
   week's retrain output); no outcome-informed choice among reconstructions.
4. **Recipe/fingerprint parity.** `B_cand` and `B_ref` share every recipe field
   except the xgb-leg artifact; the model-relevant config fingerprint (excl.
   `panel_scoring.kind`/`components` labels) must match the WF manifest recipe, so
   a mismatched recipe still fails closed — no silent cross-recipe comparison.
5. **Paired, same folds.** Both arms evaluated on the identical fold set; the
   decision statistic is the paired per-fold difference.

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
