# EXPERIMENT PREREGISTRATION — served-model architecture: solo-xgb vs the served z-blend (orch#799 decider)

STATUS: **FROZEN preregistration (design, doc-only)** — commit + codex-approve BEFORE
any execution. Decides EMPIRICALLY (not by judgment) whether the served model should be
**solo-xgb** (revert → unblocks the weekly promote + the 25-missing-model coverage,
no new subsystem) or **the served z-blend** (justifies funding the blend-WF subsystem,
option B / #975). No value below may change after approval; a change = a new dated
amendment doc, not an edit.

REVISION 2 (2026-08-12, pre-approval — closes codex CHANGES_REQUESTED on #976 HEAD 9d1f606):
1. **Arms corrected to the ACTUAL served blend.** The served blend is a **parameter-free,
   unweighted sum of per-component cross-sectional z-scores** — there are NO per-component
   weights `W` and no tunable z-norm `N`
   `[VERIFIED — renquant-pipeline blend_scorer.py:122-126 ("the combination rule is an unweighted sum of per-component cross-sectional z-scores … Per-component weights are deliberately NOT introduced here — weighting is the MoE stage's own preregistered change (AC5)") + BlendPanelScorer.score() "blend = Σ_components z(component_score)"; .subrepo_runtime pin 4aec0e3; 2026-08-12]`.
   Rev-1's A1 ("z-blend with weights W / z-norm N") and A2 ("weight-reoptimised") described a
   weighted blend that **does not exist in production** — a factual error. Corrected: **A1 = the
   real unweighted z-sum blend**; the weight-reoptimisation arm is **dropped** and deferred to
   the MoE stage's own preregistration (blend_scorer AC5), which is where introducing weights
   is designed to live. Now a **single** comparison A1−A0 (no multiplicity correction needed).
2. **Corpus removed from this repo (boundary fix).** The 82 raw WF fold artifacts (~30MB) that
   rev-1 copied into `renquant-orchestrator` are removed. WF fold artifacts belong in
   `renquant-backtesting` (their generator's repo), not here. This PR keeps only the small,
   digest-only **`fold_manifest.json`** (the window definition + per-fold recipe fingerprints +
   regime labels) as the reference-by-digest anchor. The raw folds are materialized and
   committed to `renquant-backtesting` **at execution** and byte-verified against the manifest's
   recipe digests then (§8).
3. **Momentum feasibility de-asserted.** Rev-1 stated momentum_residual was "PIT-recomputed at
   every one of the 125 cutoffs" — but nothing in this PR demonstrates that (the manifest only
   materialises the xgb leg). Corrected: the momentum_residual leg is PIT-recomputed **at
   execution**, gated by a fail-closed feasibility spot-check that runs FIRST (§3, §8).
4. **Decision rule made executable** — exact placebo correction, episode-block bootstrap over
   the 8 BEAR episodes (not a borrowed 1.96), a numeric PASS inequality, and a numeric
   underpower stop (§5).

## 0. Why this experiment (the decision it settles)
The 2026-08-04 cutover made prod `kind=blend` = **unweighted z-sum**(xgb_leg,
momentum_residual_leg). This structurally broke the weekly xgb promote — the WF gate can only
score a solo GBDT, it cannot assemble/evaluate the blend, so it fail-closes
`[VERIFIED — orch#799 feasibility: the WF gate loads ONE solo scorer per fold (run_wf_gate.py / walk_forward/loader.py), cannot assemble the blend; 2026-08-12]`
— so the model can't refresh and **25/145 watchlist names stay un-modelled**
`[VERIFIED — 120/145 models loaded, intraday_104 2026-08-12 log]`. The blend was never
validated as OUTPERFORMING solo-xgb out-of-sample. This experiment measures that head-to-head;
the winner is the served architecture, decided by a pre-registered rule.

## 1. Hypothesis
H1: the served z-blend's genuine, placebo-controlled OOS skill on the SERVED objective exceeds
solo-xgb's by a pre-declared margin. Null H0: it does not (⇒ revert to solo-xgb).

## 2. Arms (two — for power and to match the served reality)
- **A0 — solo-xgb** (`panel-ltr.alpha158_fund`, the xgb leg / component[0] alone). The revert candidate.
- **A1 — the served z-blend** = `z(xgb_leg_score) + z(momentum_residual_leg_score)`, the
  **unweighted cross-sectional z-sum** the production `BlendPanelScorer` computes
  `[VERIFIED — blend_scorer.py:122-126 + score(); 2026-08-12]`. No weights, no tunable N. The
  status quo, and the "考虑 zblend" the operator asked to test.
- **NOT an arm here — weight-reoptimisation.** Introducing per-component weights is a NEW
  architecture, not the served state, and blend_scorer.py:125-126 designates weighting as the
  MoE stage's own preregistered change (AC5). It is deferred to that prereg (this work is on the
  `design/moe-power-gate-revision` line) — testing it here would both misdescribe production and
  spend power on a non-status-quo object.

Two arms ⇒ a **single** planned comparison (A1 vs A0); no family-wise correction is needed.

## 3. Data / window (FEASIBLE — the "可落地" constraint)
- **Window (FROZEN):** the extended **2019-01-14 .. 2026-03-02 walk-forward fold set = 125
  recipe-consistent folds** `[VERIFIED — fold_manifest.json: n_folds=125, recipe_consistent:true; 2026-08-12]`
  = the 82-fold recipe-consistent backfill (2019-01-14 .. 2023-09-11, from the 2026-08-02
  `jobb-gbdt-depth-extension` run) concatenated with the 43-fold prod xgb WF manifest
  (2023-10-02 .. 2026-03-02). The cutoff sets do NOT overlap → no dedup. The window was extended
  from the prod-only 43 folds **specifically to raise BEAR power** (see the power statement).
- **Reference by digest, not by copy (boundary):** this PR carries `fold_manifest.json` only —
  per-fold `cutoff`, `feature_cols_sha256`, `params_sha256`, `config_fingerprint`, `n_features`,
  `label_col`, `regime_label`, `is_bear`. The RAW fold artifacts live in `renquant-backtesting`
  (their generator's repo); they are materialized + committed there at execution and byte-verified
  against these recipe digests (§8). The manifest pins the **recipe identity** (feature_cols
  sha256 `f17e96b5…`, params sha256 `1d1211ad…`, both common to all 125 folds
  `[VERIFIED — fold_manifest.json; 2026-08-12]`); it does NOT byte-pin individual artifacts (no
  per-file content digest) — recipe-identity is the design-time freeze, byte-materialization is
  the execution step.
- **Recipe consistency (FROZEN):** all 125 folds share 172 `feature_cols` (sha256 `f17e96b5…`),
  identical model params (sha256 `1d1211ad…`; `max_depth=5` in EVERY backfill fold — the dir's
  "depth-extension" label is time-depth, not tree-depth), `label_col=fwd_60d_excess`,
  `lookahead=60`, `embargo=60`. The only cross-set delta is `config_fingerprint`
  (`f8fb2259` backfill / `14586756` prod), which differs SOLELY because the fingerprinted
  watchlist/sector_map grow with the universe over time (145/144 vs 142/141), not the recipe;
  neither set carries a `recipe_fingerprint` field.
- **Both legs fold-local walk-forward:** at each fold cutoff, xgb_leg = that cutoff's WF fold
  artifact; momentum_residual_leg = **PIT-computed at that cutoff** from the price panel. NO
  look-ahead (cutoff + lookahead < eval; reuse the existing loader leakage guard).
- **Momentum feasibility (fail-closed, exercised at execution — NOT yet demonstrated):** the
  momentum_residual leg is a live production component (it scores daily inside the served blend),
  so it is computable today; whether it PIT-recomputes cleanly at the **2019-2023** cutoffs
  (sufficient price history, finite cross-sectional scores) is UNPROVEN here. Execution step 1 is
  a fail-closed spot-check at 3 cutoffs (earliest 2019-01, a COVID-2020 BEAR, a recent). If it
  cannot compute at the early cutoffs, the window is TRIMMED to the span where BOTH legs compute
  and the honest n_BEAR is restated — a non-PIT / post-cutoff / non-finite input drops that fold,
  never imputed (§7).
- **Honest power statement (FROZEN):** n_folds = **125**; BEAR coverage = **15 BEAR fold-cutoffs
  across 8 contiguous BEAR runs** `[VERIFIED — fold_manifest.json: n_bear_folds=15, n_bear_episodes=8; regime labels recomputable from SPY via kernel/hmm_regime_labels.py; 2026-08-12]`
  (2019 vol-spike, COVID 2020-03, Sept-2020, the 2022 bear [H1+H2, split by the summer rally],
  2024-08 carry unwind, 2025-04 tariff selloff) → **n_eff BEAR ≈ 6–8, up from n_eff = 2** on the
  prod-only window. This materially raises BEAR power but is **still policy-grade /
  annotation-grade** (single-digit independent BEAR episodes), **NOT t≥2** — declared up front,
  per [[goal-b-bear-exit-line]] discipline. BEAR is the model's only genuine-edge regime
  ([[pwf-gate-live-diverges-from-kernel-rfc210]]).

## 4. Metric (the SERVED objective)
- **PRIMARY (frozen):** regime-conditional IC — Spearman IC of each arm's score vs forward
  return, computed SEPARATELY per regime (BEAR / BULL_CALM / BULL_VOLATILE / CHOPPY), because the
  served value is BEAR-only. The decision statistic is the **BEAR-regime paired per-fold IC
  difference** A1 − A0.
- **SECONDARY (report, non-gating):** pooled IC; return-space (net Sharpe with costs) of a
  top-decile long book per arm; and each BULL regime's IC (must not be MADE WORSE — a guard, not
  a target).
- **Placebo controls (mandatory):** shuffled-label placebo for EACH arm on the SAME folds; trust
  only placebo-clean DIFFERENCES (the ~+0.04 shuffled-label leakage floor
  `[VERIFIED — [[wf-gate-embargo-leakage-floor]]]`).

## 5. Pre-registered decision rule (FROZEN — chosen before any result; executable)
Definitions (all computed on the SAME 15 BEAR folds, paired per fold):
- Per-arm, per-fold placebo-corrected IC: `IC*_arm,f = IC_arm,f − IC_arm,f^shuffled` (subtract
  that arm's own shuffled-label IC on the same fold).
- Per-fold paired difference: `d_f = IC*_A1,f − IC*_A0,f`.
- **Δ_BEAR = mean over the 15 BEAR folds of `d_f`.**
- **Dependence-aware CI:** the 15 BEAR folds cluster into **8 episodes**; the CI on Δ_BEAR is an
  **episode-block bootstrap** — resample the 8 episodes with replacement (block = whole episode,
  which respects the 60-day-overlap dependence per [[calibrate-on-the-estimands-dependence]] and
  [[block-length-equals-horizon-is-the-defect]]), 10,000 draws, percentile 90% two-sided CI.
  NO borrowed 1.96 / block-agnostic t ([[borrowed-critical-values-on-small-n]]).

**RETAIN the served z-blend (A1)** iff ALL hold:
  (i) `Δ_BEAR ≥ +0.03` `[ASSUMED — pre-registered material-gain threshold, frozen pre-run]`; AND
  (ii) the episode-block-bootstrap 90% CI **lower bound > 0** (the gain is resolved from zero,
       not a point estimate alone); AND
  (iii) A1's shuffled-label placebo IC ≤ **+0.04** floor `[VERIFIED — [[wf-gate-embargo-leakage-floor]]]`
       (placebo-clean); AND
  (iv) A1 does not reduce ANY BULL regime's IC by > 0.02 `[ASSUMED — pre-registered no-bull-harm guardrail, frozen pre-run]`.

**ELSE REVERT to solo-xgb (A0)** — the null outcome (expected-and-clean if the blend adds no
genuine BEAR skill).

**Numeric underpower stop (frozen):** if the episode-block-bootstrap 90% CI **half-width > 0.03**
(the design cannot resolve a ±0.03 MDE), declare the result **underpowered → default to A0**
(the simpler, promotable, coverage-restoring architecture is the null we revert to absent
evidence for the blend).

## 6. Actionable outcome (可落地 — what each result DOES)
- **A0 wins / ties / underpowered → REVERT served model to solo-xgb** (operator-gated live config
  change): the weekly xgb promote immediately works (a same-kind reference exists) → orch#799
  alarm clears, model refreshes, **25 missing models covered**
  `[VERIFIED — 25 = 145 − 120 loaded, intraday_104 2026-08-12 log]` via the normal
  retrain→promote→pin path. NO blend-WF subsystem needed; #975 (option-B prereg) is then moot.
- **A1 wins → fund option B** (the blend-substitution WF subsystem, #975): the experiment
  JUSTIFIES the investment (the served blend has demonstrated genuine BEAR skill worth keeping).
Either way the 8× `[ASSUMED — operator-stated complaint count, 2026-08-12]` alarm is resolved by a
DATA verdict, not deferral.

## 7. Leakage / integrity (fail-closed)
Both legs fold-local; the momentum PIT recompute is cutoff-gated; deterministic (no
outcome-informed arm or window choice — window + arms are frozen here); placebo mandatory; a
non-PIT / post-cutoff / non-finite input → fold dropped, not imputed.

## 8. Build / process (operator: 设计→PR→实行)
1. **This design PR** (frozen prereg, doc-only) → codex approve. It carries the digest-only
   window definition `fold_manifest.json` (125 folds, per-fold recipe fingerprints + regime
   labels, regenerable from SPY via `kernel/hmm_regime_labels.py`) so codex can certify the
   window + power numbers (n_folds=125, recipe_consistent, n_bear_folds=15, n_bear_episodes=8)
   WITHOUT any copied corpus. NO code, NO production/live-config path.
2. **Execution, step 1 — feasibility (fail-closed):** materialize the 82 backfill fold artifacts
   into `renquant-backtesting` (their home repo), byte-verify each against the manifest's recipe
   digests; run the momentum_residual PIT spot-check at 3 cutoffs (§3). If either fails, trim the
   window to where both legs compute and restate n_BEAR before proceeding.
3. **Execution, step 2 — run** (isolated, no-spend local compute): the 2 arms + shuffled-label
   placebos over the frozen 125-fold window; emit the paired Δ_BEAR table + episode-block-bootstrap
   CI + placebo table. **Double-audited** (independent re-derivation).
4. **Verdict → operator-authorized live config change** (revert-to-solo-xgb, or keep-blend + fund
   option B). NO live-config / production write until the verdict + operator authorization.
