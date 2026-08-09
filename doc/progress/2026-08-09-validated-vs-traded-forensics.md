# Phase-1 forensics: the validated system and the traded system are different

STATUS:    measurement + decision memo; no production surface touched.

WHAT:      doc/research/2026-08-09-validated-vs-traded-forensics.md — the
           full root-cause of orch#937's 0/15 divergence: (1) different
           model families (live = fixed-vintage z-blend since the 08-04
           operator override; backtest = per-fold walk-forward xgb),
           (2) the candidate screen records only ~22/148 names,
           (3) feature stamping drift (orch#931). Plus the three-option
           decision memo; recommendation C (converge from both ends:
           full-universe scoring snapshot + caveated retro-replay).

WHY/DIR:   Operator re-planning 2026-08-09: fix the flaws before better
           models; all evidence backtest-now. This is Phase 1 steps 1-2.

EVIDENCE:  artifact:      doc/research/data/2026-08-09-validated-vs-traded-
                          rows.csv (the committed per-shared-date table) +
                          .../2026-08-09-validated-vs-traded-derivation.py
                          (the rerun contract) [VERIFIED — derivation rerun
                          clean 2026-08-09]: widths 22.0 vs 147.8 on the 5
                          shared dates; 0/15 top-3 overlap; Spearman mean
                          0.144 (0.09/−0.42/0.67/0.18/0.20); 58 live dates
                          04-23..08-07. Config facts [VERIFIED — git show
                          aa775931:configs/strategy_config.json,
                          renquant-strategy-104, by the same script]:
                          ranking.panel_scoring.kind=blend;
                          _2026_06_23_xgb_promotion note;
                          panel-ltr "trained 2026-05-09" note.
           prod or exp:   read-only forensics; decision memo for operator
           existing data: /Users/renhao/git/github/RenQuant/data/
                          runs.alpaca.db (sqlite mode=ro: candidate_scores
                          ⋈ pipeline_runs, run_type='live',
                          role='candidate', run_date<=2026-08-07); bt#110
                          replay matrix digest-pinned ×1685 by doc/research/
                          data/2026-08-09-l2-backtest-inputs.manifest.json
           best-known?:   yes — option C's retro-replay in-sample caveat
                          is stated IN the memo, not discovered later
           scope:         step 3 (snapshot module) and step 4 (retro-
                          replay) are the same-day follow-up PRs.

TESTS:     data/2026-08-09-validated-vs-traded-derivation.py run twice
           (emit, then verify-vs-committed-CSV): asserts every published
           number; refuses on replay-matrix digest drift.

NEXT:      open the snapshot-module PR (step 3) and the retro-replay PR
           (step 4) today; operator picks A/B/C (default C if silent, per
           the charge order).
