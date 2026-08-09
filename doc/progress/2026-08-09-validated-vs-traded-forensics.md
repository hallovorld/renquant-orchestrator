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

EVIDENCE:  artifact:      forensics tables [VERIFIED — runs DB mode=ro ⋈
                          replay matrix, this session]: 22 vs 148 recorded
                          widths; 0/15 top-3 overlap; Spearman mean 0.144
                          on intersections; 5 shared dates (replay ends
                          05-07, live starts 04-23). Config facts
                          [VERIFIED — pinned strategy_config read]:
                          kind=blend since 08-04 override; xgb artifact
                          trained 2026-05-09, promoted 06-23.
           prod or exp:   read-only forensics; decision memo for operator
           existing data: candidate_scores (58 live dates), bt#110 replay
                          matrix, pinned config, artifact metadata
           best-known?:   yes — option C's retro-replay in-sample caveat
                          is stated IN the memo, not discovered later
           scope:         step 3 (snapshot module) and step 4 (retro-
                          replay) are the same-day follow-up PRs.

TESTS:     none — measurement doc; every number re-runnable read-only.

NEXT:      open the snapshot-module PR (step 3) and the retro-replay PR
           (step 4) today; operator picks A/B/C (default C if silent, per
           the charge order).
