# EXPERIMENT PREREGISTRATION — served-model architecture: solo-xgb vs z-blend (orch#799 decider)

STATUS: **FROZEN preregistration (design)** — commit + codex-approve BEFORE any
execution. Decides EMPIRICALLY (not by judgment) whether the served model should be
**solo-xgb** (revert → unblocks the weekly promote + the 25-missing-model coverage,
no new subsystem) or the **z-blend** (justifies funding the blend-WF subsystem,
option A). No value below may change after approval; changes = a new dated amendment.

## 0. Why this experiment (the decision it settles)
The 08-04 z-blend cutover made prod `kind=blend` = z-blend(xgb_leg, momentum_residual_leg, W, N).
This structurally broke the weekly xgb promote (orch#799: the WF gate can only score a
solo GBDT; it cannot evaluate the blend — verified), so the model can't refresh and 25/145
watchlist names stay un-modelled [VERIFIED — orch#799 feasibility (PR #975/#976 subagents): the WF gate loads ONE solo scorer per fold (run_wf_gate.py / walk_forward/loader.py), cannot assemble the blend; 120/145 models loaded, intraday_104 2026-08-12 log]. The blend was never validated as OUTPERFORMING solo-xgb
out-of-sample. This experiment measures that head-to-head; the winner is the served
architecture, decided by a pre-registered rule.

## 1. Hypothesis
H1: the z-blend's genuine, placebo-controlled OOS skill on the SERVED objective exceeds
solo-xgb's by a pre-declared margin. Null H0: it does not (⇒ revert to solo-xgb).

## 2. Arms (few, for power)
- **A0 — solo-xgb** (`panel-ltr.alpha158_fund`, component[0] alone). The revert candidate.
- **A1 — current z-blend** (xgb_leg + momentum_residual_leg, CURRENT weights W / z-norm N from the served config). The status quo.
- **A2 — z-blend, weight-reoptimised** (the same two legs, W re-fit on a walk-forward INNER fold only — never on the eval window; a single re-optimisation policy, not a grid, to preserve power). Tests whether a better-weighted z-blend beats both. (Honours operator "考虑 zblend".)
No further arms — 3 [ASSUMED — pre-registered design choice: 3 arms to keep FWER manageable at policy-grade n] keeps FWER manageable at policy-grade n.

## 3. Data / window (FEASIBLE — the "可落地" constraint)
- Evaluate over a **PIT-reconstructable window** where BOTH legs can be computed
  point-in-time: the momentum_residual leg is a momentum-factor residual (cheap to PIT-
  compute from price data at each cutoff — it does NOT need the full 2023–2026 GBDT WF
  corpus). Window (FROZEN, feasibility-confirmed 2026-08-12): the **extended
  2019-01-14 .. 2026-03-02 walk-forward fold set = 125 recipe-consistent folds**
  `[VERIFIED — committed corpus at doc/research/data/2026-08-12-served-model-experiment/ + fold_manifest.json (125 folds, recipe-consistent shas, regime labels recomputable from SPY via kernel/hmm_regime_labels.py); 2026-08-12]` — the
  82-fold recipe-consistent backfill (2019-01-14 .. 2023-09-11) concatenated with the 43-fold
  prod xgb WF manifest (2023-10-02 .. 2026-03-02). The two cutoff sets do NOT overlap
  (backfill ends 2023-09-11, manifest starts 2023-10-02), so no dedup is needed. The window was
  extended from the manifest-only ~2024-01..2026-03 (43 folds) **specifically to raise BEAR
  power** — see the power statement below.
- **Extension provenance (FROZEN)**: the 2019-2023 legs are the recipe-consistent backfill
  **committed in THIS PR** at `doc/research/data/2026-08-12-served-model-experiment/backfill_2019-2023_window_artifacts/`
  (82 verbatim `<cutoff>/panel-ltr.json`, regenerated 2026-08-02 `jobb-gbdt-depth-extension` run)
  — `[VERIFIED — committed corpus at doc/research/data/2026-08-12-served-model-experiment/ + fold_manifest.json (125 folds, recipe-consistent shas, regime labels recomputable from SPY via kernel/hmm_regime_labels.py); 2026-08-12]` same recipe as
  the prod manifest, asserted `recipe_consistent: true` across all 125 folds in the manifest:
  byte-identical 172 `feature_cols` (sha256 `f17e96b56c1220fa…` both sets — full value + hash
  method in `fold_manifest.json`), identical model params (sha256 `1d1211ade4f792ae…`;
  `max_depth=5` in EVERY backfill fold — the dir's "depth-extension" label is time-depth, not
  tree-depth), `label_col=fwd_60d_excess`, `lookahead=60`, `embargo=60`. The only cross-set delta
  is the `config_fingerprint`
  (`f8fb2259` vs `14586756`), which differs solely because the `config_fingerprint_fields`
  watchlist/sector_map grow with the universe over time (145/144 vs 142/141), not the recipe;
  neither set carries a `recipe_fingerprint` field. momentum_residual is
  **PIT-recomputed at every one of the 125 extended cutoffs** (never carried over), same
  cutoff-gated guard as the manifest span.
- **Walk-forward, fold-local both legs**: at each fold cutoff, xgb_leg = that cutoff's fold
  artifact (prod manifest for 2023-10 onward; the recipe-consistent 2019-2023 backfill before
  that); momentum_residual_leg = PIT-computed at that cutoff; W (for A2)
  re-fit only on data preceding the fold. NO look-ahead (cutoff+lookahead < eval, reuse the
  existing loader leakage guard).
- **Honest power statement (FROZEN)**: n_folds = **125**. BEAR coverage `[VERIFIED — committed corpus at doc/research/data/2026-08-12-served-model-experiment/ + fold_manifest.json (125 folds, recipe-consistent shas, regime labels recomputable from SPY via kernel/hmm_regime_labels.py); 2026-08-12 — the manifest computes n_bear_folds=15, n_bear_episodes=8]` = **15 BEAR
  fold-cutoffs across 8 contiguous BEAR runs ≈ 6 distinct macro bear regimes** (2019 vol-spike,
  COVID 2020-03, Sept-2020, the 2022 bear [H1+H2, split by the summer rally], 2024-08 carry
  unwind, 2025-04 tariff selloff) → **n_eff BEAR ≈ 6–8, up from n_eff = 2** on the prod-only
  window (2024-08, 2025-04). This materially raises
  BEAR power but is **still policy-grade / annotation-grade** (single-digit independent BEAR
  episodes), **NOT t≥2** — declared up front, per [[goal-b-bear-exit-line]] discipline. BEAR is
  the model's only genuine-edge regime ([[pwf-gate-live-diverges-from-kernel-rfc210]]).

## 4. Metric (the SERVED objective)
- **PRIMARY (frozen)**: regime-conditional IC — Spearman IC of each arm's score vs forward
  return, computed SEPARATELY per regime (BEAR / BULL_CALM / BULL_VOLATILE / CHOPPY), because
  the served value is BEAR-only. The decision statistic is the **BEAR-regime paired IC
  difference** A1−A0 and A2−A0 (paired per fold).
- **SECONDARY (report, non-gating)**: pooled IC, return-space (net Sharpe with costs) of a
  top-decile long book per arm, and the BULL regimes' IC (must not be MADE WORSE — a guard,
  not a target).
- **Placebo controls (mandatory)**: shuffled-label + time-shift placebo for EACH arm; trust
  only placebo-clean DIFFERENCES (the ~+0.04 `[VERIFIED — measured shuffled-label embargo floor, [[wf-gate-embargo-leakage-floor]]]` shuffled-label leakage floor — [[wf-gate-embargo-leakage-floor]]).

## 5. Pre-registered decision rule (FROZEN — chosen before any result)
Let Δ_BEAR(arm) = paired BEAR-regime IC of (arm − A0), placebo-corrected.
- **Retain the z-blend (A1 or A2)** iff its Δ_BEAR ≥ **+0.03** [ASSUMED — pre-registered threshold, frozen pre-run per the prereg discipline] (a genuine, material BEAR-IC
  gain over solo-xgb) AND its placebo arm is clean (placebo IC ≤ floor) AND it does NOT
  reduce any BULL regime's IC by >0.02 [ASSUMED — pre-registered guardrail, frozen pre-run] (no bull-regime harm). If BOTH A1 and A2 qualify,
  pick the higher Δ_BEAR (FWER: Holm across the 2 blend arms).
- **Else REVERT to solo-xgb (A0)** — the null outcome. This is the EXPECTED-and-clean
  result if the z-blend adds no genuine BEAR skill.
- Ties / underpowered-inconclusive (BEAR n_eff too small to separate) → **default to A0
  (solo-xgb)**: the simpler, promotable, coverage-restoring architecture is the null we
  revert to absent evidence for the blend.

## 6. Actionable outcome (可落地 — what each result DOES)
- **A0 wins/ties/inconclusive → REVERT served model to solo-xgb** (operator-gated live
  config change): the weekly xgb promote immediately works (same-kind reference exists) →
  orch#799 alarm clears, model refreshes, **25 missing models [VERIFIED — 120/145 models loaded = 25 un-modelled, intraday_104 2026-08-12 log] covered** via the normal
  retrain→promote→pin path. NO blend-WF subsystem needed. #975 (option-B prereg) is then moot.
- **A1/A2 wins → fund option A** (the blend-WF subsystem, #975): the experiment JUSTIFIES
  the investment; and A2 winning also tells us the optimal W to bake in.
Either way the 8× [ASSUMED — operator-stated complaint count, 2026-08-12] alarm is resolved by a DATA verdict, not deferral.

## 7. Leakage / integrity (fail-closed)
Fold-local both legs; W/N fit only on inner/pre-fold data; deterministic (no outcome-informed
arm or window choice — the window + arms are frozen here); placebo mandatory; the momentum PIT
recomputation cutoff-gated; a non-PIT or post-cutoff input → fold dropped, not imputed.

## 8. Build / process (operator: 设计→PR→实行)
1. **This design PR** (frozen prereg) → codex approve. It now ALSO carries the durable
   window/power evidence base: the 82-fold backfill corpus
   (`doc/research/data/2026-08-12-served-model-experiment/backfill_2019-2023_window_artifacts/`)
   + the reviewable `fold_manifest.json` (125 folds, per-fold recipe fingerprints + regime labels).
   So codex CAN certify the window + power numbers (n_folds=125, recipe_consistent, n_bear_folds=15,
   n_bear_episodes=8) from THIS PR — they are no longer deferred.
2. **Feasibility (residual)**: n_folds + BEAR n_eff are now COMMITTED and independently
   recomputable in `fold_manifest.json` (regime labels regenerable from SPY via
   `kernel/hmm_regime_labels.py`); the only residual feasibility item is the momentum_residual
   PIT recompute over the 2019-2023 span, exercised at execution (a non-PIT / post-cutoff input
   drops that fold, per §7 — never imputed). If BEAR n_eff were ~0 the design would say so and
   default to A0; the manifest shows n_eff BEAR ≈ 6-8, not ~0.
3. **Execution** (isolated, no-spend local compute): run the 3 arms + placebos over the frozen
   window, emit the paired Δ_BEAR table + placebo table. Double-audited (independent re-derivation).
   The window + power evidence base (the 125-fold manifest, per-fold recipe fingerprints + regime
   labels, regenerable from the repo's SPY data via `kernel/hmm_regime_labels.py`) is committed HERE
   and independently reviewable now; execution certifies only the Δ_BEAR / placebo RESULT, not the
   window/power numbers (already certifiable from this PR's manifest).
4. **Verdict → operator-authorized live config change** (revert-to-solo-xgb, or keep-blend + fund A).
No live-config / production write until the verdict + operator authorization.
