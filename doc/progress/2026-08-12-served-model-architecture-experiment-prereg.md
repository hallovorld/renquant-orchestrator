# served-model architecture experiment — frozen preregistration (orch#799 decider, doc only)

STATUS:    frozen experiment preregistration (design) — commit + codex-approve
           BEFORE any execution. No computation run. This PR changes NO code.

WHAT:      Commit the frozen prereg
           `doc/design/2026-08-12-served-model-architecture-experiment-prereg.md`.
           AMENDED 2026-08-12 (§3 Data/window ONLY — extended fold set for BEAR
           power; arms/metric/decision-rule Δ_BEAR≥+0.03 UNCHANGED; see AMENDMENT
           below). Current sha256
           `7644acddcacbe4d2212d97bd09fe3b5cd2da5ca319330959544632a92e524f41`
           (original authored source was `d36033570b6e4a1fe7190394981761a39b959492fca428bb1b3d7408a4ace7a2`).
           It preregisters the empirical decider for orch#799: is the served
           model better as **solo-xgb** (A0 — revert, unblocks the weekly promote
           + the 25-missing-model coverage, no new subsystem) or the **z-blend**
           (A1 current / A2 weight-reoptimised — justifies funding the blend-WF
           subsystem). Primary metric = BEAR-regime paired IC difference vs A0;
           decision rule FROZEN (retain z-blend iff Δ_BEAR ≥ +0.03 & placebo-clean
           & no bull harm; else revert to A0; underpowered → default A0).

WHY/DIR:   The 08-04 z-blend cutover made prod `kind=blend`, which structurally
           broke the weekly xgb promote (orch#799 — the WF gate can only score a
           solo GBDT, not the blend) and left 25/145 watchlist names un-modelled [VERIFIED — orch#799 feasibility (PR #975/#976 subagents): the WF gate loads ONE solo scorer per fold (run_wf_gate.py / walk_forward/loader.py), cannot assemble the blend; 120/145 models loaded, intraday_104 2026-08-12 log].
           The blend was never validated as OUTPERFORMING solo-xgb OOS. This
           prereg settles that head-to-head by a DATA verdict, not deferral,
           resolving the 8× [ASSUMED — operator-stated complaint count, 2026-08-12] alarm. It is the sibling decider to the option-B
           reference-rule recommendation (`doc/design/2026-08-11-orch799-blend-prod-reference-rule.md`):
           if A0 wins, that subsystem is moot; if A1/A2 wins, it is justified.

AMENDMENT (2026-08-12, §3 only — extend window for BEAR power):
           The 43-fold prod-manifest window (2023-10..2026-03) carries only n_eff
           BEAR = 2 — too weak to test the z-blend's BEAR-regime value. §3 now
           evaluates over the **extended 2019-01-14..2026-03-02 fold set = 125
           recipe-consistent folds** = the 82-fold recipe-consistent backfill
           (`doc/research/data/2026-08-02-jobb-gbdt-depth-extension-run001/window_artifacts/`,
           2019-01-14..2023-09-11) concatenated with the 43-fold prod manifest
           (2023-10-02..2026-03-02); cutoff sets do NOT overlap → no dedup.
           RECIPE-COMPATIBILITY [VERIFIED, read-only, all 125 folds]: byte-identical
           172 `feature_cols` (sha `c1dc4f7f897495fe` both sets), identical model
           params (sha `112fae206d60`; `max_depth=5` in EVERY backfill fold — the
           dir's "depth-extension" name is time-depth, not tree-depth),
           `label_col=fwd_60d_excess`, `lookahead=60`, `embargo=60`,
           `feature_preprocess_version=2`, format `version=3`. Only cross-set delta
           = `config_fingerprint` (f8fb2259 vs 14586756), which differs SOLELY
           because `config_fingerprint_fields.watchlist` (145 vs 142) and
           `sector_map` (144 vs 141) grow with the universe — NOT the recipe.
           Neither set carries a `recipe_fingerprint` field. BEAR power recomputed
           via `RenQuant/kernel/hmm_regime_labels.py` on SPY at all 125 cutoffs =
           15 BEAR fold-cutoffs / 8 contiguous runs / ~6 distinct macro bear
           regimes → **n_eff BEAR ≈ 6–8, up from 2** (same method reproduces the
           prod-only 2 exactly). Still policy/annotation-grade, NOT t≥2.
           momentum_residual PIT-recomputed at every extended cutoff.

EVIDENCE:
  artifact:      `doc/design/2026-08-12-served-model-architecture-experiment-prereg.md`
                 (the frozen prereg, committed verbatim as authored) + this
                 progress record. No code. [VERIFIED — diff vs authored source
                 EMPTY; sha256 identical both sides.]
  prod or exp:   neither — design only; no confirmatory computation. No
                 live-config / production write. The prereg's own §8.2 gate
                 (feasibility: momentum_residual PIT-computability + actual
                 n_folds + BEAR n_eff) is a SEPARATE read-only investigation
                 that must clear before execution.
  existing data: the design's factual claims are backed by prior read-only
                 reads recorded in-transcript — orch#799 gate feasibility
                 (run_wf_gate.py/loader.py single-scorer WF path), the 120/145
                 model-load count (intraday_104 2026-08-12 log), and the
                 125-fold recipe-compat + BEAR n_eff≈6-8 (feasibility subagent
                 2026-08-12); this PR itself writes only the two docs.
  best-known?:   yes among the framings — 3 arms (A0/A1/A2) keep FWER manageable
                 at policy-grade n; the decision rule and window are frozen here,
                 pre-result, so the verdict cannot be outcome-shopped.
  scope:         "this is the served-model-architecture prereg (frozen design,
                 NOT executed and NOT implemented), vs existing best = orch#799's
                 structural stalemate, which returns no verdict. The estimand is
                 'does the z-blend add genuine, placebo-clean BEAR-regime OOS
                 skill over solo-xgb'. It authorizes no run, no promotion, and no
                 live-config change; execution is gated on this feasibility
                 confirm + codex approval + operator authorization."

TESTS:     none — doc-only PR; no code touched.

NEXT:      (1) feasibility confirm (prereg §8.2, read-only) — n_folds and BEAR
           n_eff now RESOLVED in the AMENDMENT above (125 folds, n_eff BEAR ≈ 6–8),
           and the backfill recipe-compatibility VERIFIED; the residual §8.2 item
           is momentum_residual PIT-computability over the 2019-2023 span, exercised
           at execution (a non-PIT/post-cutoff input drops that fold, per §7);
           (2) codex approval of this frozen
           prereg; (3) execution (isolated, no-spend local compute) of the 3 arms
           + placebos, double-audited; (4) verdict → operator-authorized live
           config change (revert-to-solo-xgb, or keep-blend + fund option A).
