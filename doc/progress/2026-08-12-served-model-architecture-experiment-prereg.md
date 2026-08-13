# served-model architecture experiment — frozen preregistration (orch#799 decider, doc-only)

STATUS:    frozen experiment preregistration (design) — commit + codex-approve
           BEFORE any execution. No computation run. This PR changes NO code and
           writes NO production/live-config path.

WHAT:      Commit the frozen prereg
           `doc/design/2026-08-12-served-model-architecture-experiment-prereg.md`
           + the digest-only window definition
           `doc/research/data/2026-08-12-served-model-experiment/fold_manifest.json`.
           It preregisters the empirical decider for orch#799: is the served model
           better as **solo-xgb** (A0 — revert, unblocks the weekly promote + the
           25-missing-model coverage, no new subsystem) or **the served z-blend**
           (A1 — justifies funding the blend-WF subsystem, #975). Primary metric =
           BEAR-regime paired IC difference A1−A0; decision rule FROZEN and
           executable (retain z-blend iff Δ_BEAR ≥ +0.03 [ASSUMED — pre-registered
           threshold] AND episode-block-bootstrap 90% CI lower bound > 0 AND
           placebo-clean AND no bull harm; else revert A0; CI half-width > 0.03 →
           underpowered → default A0).

WHY/DIR:   The 2026-08-04 cutover made prod `kind=blend`, which structurally broke
           the weekly xgb promote (orch#799 — the WF gate can only score a solo
           GBDT, not the blend) and left 25/145 watchlist names un-modelled
           [VERIFIED — 120/145 models loaded, intraday_104 2026-08-12 log]. The
           blend was never validated as OUTPERFORMING solo-xgb OOS. This prereg
           settles that head-to-head by a DATA verdict, not deferral, resolving the
           8× [ASSUMED — operator-stated complaint count, 2026-08-12] alarm. Sibling
           decider to option-B (#975): if A0 wins, that subsystem is moot; if A1
           wins, it is justified.

REVISION 2 (2026-08-12, pre-approval — closes codex CHANGES_REQUESTED on HEAD 9d1f606):
  - **Arms corrected to the actual served blend.** The served blend is a
    parameter-free UNWEIGHTED sum of per-component cross-sectional z-scores — no
    weights W, no tunable N [VERIFIED — renquant-pipeline blend_scorer.py:122-126
    + BlendPanelScorer.score(); .subrepo_runtime pin 4aec0e3; 2026-08-12]. Rev-1's
    A1(…,W,N) and A2(weight-reoptimised) described a weighted blend that does not
    exist in production. Corrected: A1 = the real unweighted z-sum blend; the
    weight-reoptimisation arm is DROPPED and deferred to the MoE stage's own prereg
    (blend_scorer AC5). Now a single comparison A1−A0 (no multiplicity correction).
  - **Corpus removed (boundary fix).** The 82 raw WF fold artifacts (~30MB) rev-1
    copied into renquant-orchestrator are removed — WF fold artifacts belong in
    renquant-backtesting. This PR keeps only the small digest-only
    `fold_manifest.json`. At execution the raw folds are read in place from their
    existing renquant-backtesting-owned run — not copied or committed here — and
    recipe-fingerprint-matched against the manifest (recipe-identity, not
    byte/content verification).
  - **Momentum feasibility de-asserted.** Rev-1 claimed momentum_residual was
    "PIT-recomputed at every one of the 125 cutoffs" — nothing here demonstrates
    it. Corrected: PIT-recomputed at execution, gated by a fail-closed 3-cutoff
    feasibility spot-check that runs FIRST; if it fails at early cutoffs the window
    is trimmed and n_BEAR restated.
  - **Decision rule made executable** — exact placebo correction, episode-block
    bootstrap over the 8 BEAR episodes (not a borrowed 1.96), numeric PASS
    inequality (CI lower bound > 0), numeric underpower stop (CI half-width > 0.03).

EVIDENCE:
  artifact:      `doc/design/2026-08-12-served-model-architecture-experiment-prereg.md`
                 (the frozen prereg, rev-2) + the digest-only window definition
                 `doc/research/data/2026-08-12-served-model-experiment/fold_manifest.json`
                 (125 folds: per-fold cutoff, feature_cols_sha256, params_sha256,
                 config_fingerprint, n_features, label_col, regime_label, is_bear;
                 top-level recipe_consistent:true, n_bear_folds=15, n_bear_episodes=8)
                 + this progress record. No raw corpus, NO code.
                 [VERIFIED — fold_manifest.json recipe_consistent:true, n_folds=125,
                 n_bear_folds=15, n_bear_episodes=8; served blend unweighted per
                 blend_scorer.py:122-126; 2026-08-12.]
  prod or exp:   neither — design only; no confirmatory computation, no live-config
                 / production write. Execution (arm run + momentum feasibility
                 spot-check + in-place recipe-fingerprint match of the backfill
                 folds) is a SEPARATE gated step after codex approval.
  existing data: the design's factual claims are backed by read-only reads —
                 orch#799 gate feasibility (run_wf_gate.py/loader.py single-scorer
                 WF path), the 120/145 model-load count (intraday_104 2026-08-12
                 log), the unweighted-blend fact (blend_scorer.py:122-126 +
                 score()), and the 125-fold recipe-compat + BEAR n_eff≈6-8 which
                 are COMMITTED and independently recomputable in THIS PR's
                 `fold_manifest.json` (regime labels regenerable from SPY via
                 `kernel/hmm_regime_labels.py`). No copied corpus; the manifest
                 references the folds by recipe digest.
  best-known?:   yes among the framings — 2 arms (A0 vs the real served A1) match
                 production and avoid spending power on a non-status-quo weighted
                 blend; the decision rule + window are frozen pre-result so the
                 verdict cannot be outcome-shopped. The extended-window choice (125
                 folds for BEAR power) is frozen as a DESIGN commitment; its
                 feasibility evidence (n_folds, recipe-compat, n_bear) is VERIFIED
                 from this PR's manifest, independently recomputable, not deferred.
  scope:         "this is the served-model-architecture prereg (frozen design, NOT
                 executed, NOT implemented), vs existing best = orch#799's
                 structural stalemate, which returns no verdict. The estimand is
                 'does the served unweighted z-blend add genuine, placebo-clean
                 BEAR-regime OOS skill over solo-xgb'. It authorizes no run, no
                 promotion, and no live-config change; execution is gated on the
                 momentum feasibility spot-check + codex approval + operator
                 authorization."

TESTS:     none — doc-only PR; no code touched.

NEXT:      (1) codex approval of this frozen rev-2 prereg; (2) execution step 1 —
           fail-closed feasibility (read the backfill folds in place from their
           existing renquant-backtesting-owned run and recipe-fingerprint-match each
           against the manifest — recipe-identity, NOT byte/content verification; no
           raw WF corpus copied or committed; momentum_residual PIT spot-check at 3
           cutoffs; trim + restate n_BEAR if it fails); (3) execution step 2 — run
           the 2 arms + shuffled-label placebos over the frozen 125-fold window,
           emit the Δ_BEAR table + episode-block-bootstrap CI, double-audited;
           (4) verdict → operator-authorized live config change (revert-to-solo-xgb,
           or keep-blend + fund option B / #975).
