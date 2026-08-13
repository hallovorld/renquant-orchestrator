# orch#799 — FEASIBILITY & POWER FINDING: why the option-B prereg cannot be written yet

STATUS: **NOT a preregistration. This document authorizes nothing.** An earlier
revision was titled and presented as a FROZEN preregistration for the
blend-substitution WF promote gate. It could not be one: the decisive paired
decision rule cannot be frozen today, and the measurement in §3.1 is why.

**Any future option-B implementation needs a NEW, complete, independently
reviewable preregistration. It inherits nothing from this document** — not the
rule sketch, not the thresholds, not the acceptance list. The unclosed findings
recorded here are recorded as *defects*, not as specification.

What this document IS: the measured feasibility result for the option-B
estimand, plus the defects found while attempting to freeze it. It is kept
because that result exists nowhere else in the repo — closing the branch would
strand it, and the conditional reference-rule recommendation
(`doc/design/2026-08-11-orch799-blend-prod-reference-rule.md`, orch#972) neither
carries it nor should, since its scope is the reference *rule* and not the power
of testing it.

## 3.1 THE BLOCKER — the decision rule is not testable at usable power

Measured from the pinned manifest
`backtesting/renquant_104/artifacts/sim/walkforward_manifest_gbdt_prod_recipe_calibrated.json`
(sha256 `4febb6af7155a468…`)
`[VERIFIED — read 2026-08-12; key is `retrains`, not `rows`/`folds`]`:

| | |
|---|---|
| declared `cadence_days` | 21 |
| observed consecutive cutoff gaps | min 21, median 21, max 21 (uniform) |
| span | 2023-10-02 → 2026-03-02, 882 days |
| manifest rows | 43 |
| `lookahead_days` (label horizon `h`) | **60**, on every row |

**21-day spacing against a 60-day forward label means each fold overlaps two to
three neighbours in outcome window, so 43 rows are not 43 independent trials.**
Under a deterministic non-overlapping subsample — start at the earliest cutoff,
greedily take the next cutoff ≥ `h` days later, no phase choice and no tuning:

| | nominal | independent |
|---|---|---|
| n | 43 | **15** |
| one-sided exact sign test, α ≤ 0.05 | k ≥ 28 | **k ≥ 12** |
| actual α | 0.0330 | **0.0176** |
| power at true win-rate 0.65 | 0.56 | **0.17** |
| power at true win-rate 0.80 | 0.99 | **0.65** |

**Power 0.17 at a plausible effect.** An earlier revision of this document
quoted 0.56; that figure assumed 43 independent units and is **retracted**.

**Two escape routes were considered and deliberately NOT taken here**, because
each is a design decision needing its own preregistration rather than a
paragraph in this one:

1. **Block-aware paired resampling** would use the overlapping folds more
   efficiently, but reintroduces the distributional assumptions this repo has
   been bitten by — block length must exceed `h` (a block length equal to the
   horizon is the known defect) and ρ₁ must be estimated, not assumed.
2. **Prospective accumulation** costs ~60 days per additional independent unit,
   so reaching even n_eff = 30 is roughly 2.5 years.

**Consequence.** A promotion gate may legitimately accept under-promotion — its
error is the status quo, which never promotes at all. What it may not do is
present an independence calculation that does not hold as a valid rejection
threshold. Until an inference unit is chosen that respects the overlap, and its
α and power are stated for a declared minimum effect, the option-B gate change
should not be implemented.

## Defects recorded (NOT specification)

- **`W` / `N` are fictions.** An early draft froze "z-blend weights W" and
  "z-normalization params N". `BlendPanelScorer.score` is an *unweighted* sum of
  per-component cross-sectional z-scores, `ddof=0`, computed at scoring time;
  `ranking.blend_weights` is absent from the served config. The object to pin is
  the pipeline commit supplying the combine rule.
- **The evaluation surface is mutable.** `_resolve_manifest` globs
  `walkforward_manifest*.json`, keeps `recipe_validated` ones, and sorts by
  `manifest_rows_checked` **descending** (`run_wf_gate.py:860-877`) — two of the
  four present manifests have 43 rows and two have 39, so a new file changes the
  comparison surface with no code change. Any future prereg must pin the
  manifest by digest, resolved once and stamped in the receipt.
- **The placebo bar was mis-transcribed.** Both placebo verdicts are computed but
  the authoritative one is selected by mode; under `DEFAULT_PLACEBO_MODE =
  "absolute"` the decision rests on the time-shift ceiling alone, while `margin`
  and `real_ic_floor` feed the opt-in `difference` verdict only
  (`run_wf_gate.py:276,500-520`). An early draft listed all three together,
  freezing a hybrid the gate has never applied.

---

*Everything below is the option-B rule sketch as it stood when the attempt to
freeze it was abandoned. It is retained for the next author as background. It is
NOT approved, NOT frozen, and NOT a specification.*

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
- **PASS iff** all of the following hold. These are the existing gate's own pre-declared values, transcribed from the gate rather than chosen here. **They are NOT frozen by this document** (see STATUS) — they are recorded so the next author starts from what the gate actually applies instead of from a pointer they could resolve after seeing results:

  | quantity | value as the gate applies it | source |
  |---|---|---|
  | placebo evaluation mode | **`absolute`** — `DEFAULT_PLACEBO_MODE = "absolute"`; the authoritative verdict is selected by mode, and an unknown mode falls back to absolute | `scripts/run_wf_gate.py:276,500-520` `[VERIFIED — read from the pinned script]` |
  | time-shift placebo ceiling | `\|placebo_ic\| ≤ max(0.005, 0.5 × \|aligned_real_ic\|)` — **the whole of the authoritative placebo bar** | `_placebo_ic_threshold()` |
  | decision statistic | the **paired per-fold difference** `B_cand − B_ref` on the identical fold set | §4.5 |
  | fold/date construction | the **existing WF manifest's** folds, unchanged — this comparison introduces no new fold scheme; a candidate that is not a fold-local WF manifest fails closed (§4.1) | §4.1, §4.5 |
  | degenerate-leg exclusion fraction | **ZERO** — see §4.6 | §4.6 |

  …AND `B_cand` passes the sanity battery (shuffled-label placebo + time-shift placebo) AND the recipe/fingerprint recipe-match guard passes. Else FAIL → **production unchanged** (fail-closed, as today).

  **What is deliberately NOT in this table, and why.** An earlier draft also
  froze `margin = +0.01` and `aligned_real_ic > real_ic_floor`. Those are real
  constants, but they feed the **opt-in `difference` verdict only**: the gate
  computes both verdicts and selects the authoritative one by mode, and under the
  default `absolute` mode the decision rests on the time-shift ceiling alone
  `[VERIFIED — `run_wf_gate.py:264-278,308-333,500-520`]`. Listing all three
  together froze a **hybrid rule the gate has never applied**, which would have
  left the implementer free to read this document as either preserving the
  current bar or quietly upgrading it.

  **This prereg preserves the current bar.** Switching the authoritative mode to
  `difference` would be a deliberate tightening — defensible on its merits, since
  the incremental criterion plus a positive-IC floor is the stronger test — but it
  is a SEPARATE preregistered change with its own justification, not something
  this document smuggles in under "no new threshold".

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
  the momentum_residual leg and the combine rule stay (there is no weight
  object — §3).
- RFC#210 freshness governance, the scorer/calibrator binding gate, and the live
  `strategy_config.json` deploy remain SEPARATE operator-gated steps — a PASS earns
  the leg the right to be pin-proposed, not an automatic live swap.
- Fail-closed everywhere: missing WF manifest, non-fold-local candidate, recipe
  mismatch, sanity-battery fail, or below-threshold → production unchanged.

## 6. Implementation feasibility gate (for the implementer)
Before coding, verify the existing WF gate (`run_wf_gate.py` + the
walkforward_manifest machinery) can evaluate a BLEND config over per-fold blend
artifacts (i.e. construct `B_cand`/`B_ref` per fold from the leg +
momentum_residual under the pinned combine rule, and score the return metric).
If it can, implement §3 as the
reference-resolution + candidate-construction. If it CANNOT without new blend-eval
machinery, STOP and report the gap — do NOT fall back to a bare-leg (option A) or
any banned reference source; the alarm staying is preferable to a scientifically
invalid promote.

## 7. Acceptance (when implemented)
- A dry-run against the current served blend + the latest retrain candidate
  reaches a real PASS/FAIL verdict (no orch#799 refusal), production untouched.
- `B_cand` differs from `B_ref` ONLY in the xgb-leg artifact (fingerprint diff).
- The candidate is rejected fail-closed if it is not a fold-local WF manifest.
- On a synthetic PASS, only component[0] is swapped; the momentum_residual leg
  is byte-identical and the pipeline commit supplying the combine rule is
  unchanged (there is no weight object to compare).
- The weekly not-acting alarm clears (the gate DECIDES instead of refusing);
  a subsequent PASS lets the refreshed leg be pin-proposed via the normal
  retrain→promote→pin path. **No coverage count is asserted** — the earlier
  "25 missing-model names" figure had no reproducible source here and is removed
  with the rest.
