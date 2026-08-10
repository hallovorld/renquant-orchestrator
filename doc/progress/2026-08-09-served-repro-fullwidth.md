# Served-model reproduction measured full-width — feature pipeline substantially clean

STATUS:    measurement; read-only on all production surfaces; task #26
           first acceptance table. Follows orch#948 (extension corpus).

WHAT:      doc/research/2026-08-09-served-repro-fullwidth.md — offline
           scoring of the extension panel with the served artifacts,
           through the production transform, joined to
           ticker_daily_state. Clean cell (same artifact, pure panel
           score, 07-20..08-03): median daily Spearman 0.9734, top-5
           overlap 4.0/5 — with 07-27..08-03 at 0.973-0.986. The naive
           full-window 0.684 decomposes into artifact identity (the
           08-02 retrain) + blend-composite semantics
           (blend_scorer.py:315), NOT feature drift.

WHY/DIR:   #26 asks whether the validated system IS the traded system.
           This table shows the serving FEATURE path reproduces the
           panel build almost exactly in the freshest week — so the
           replay-vs-served gap is carried by model family (z-blend vs
           validated WF xgb) and the candidate screen, narrowing where
           repair must happen. REVISES the #931-derived narrative.

EVIDENCE:  artifact:      data/2026-08-09-served-repro-score.py (CLI
                          args; production transform + booster bytes),
                          …-served-repro-daily.csv (36 days),
                          …-served-repro-cleancell.csv (11 days),
                          …-served-repro-summary.json
                          [VERIFIED — both invocations run 2026-08-09,
                          printed tables match committed CSVs]
           prod or exp:   read-only measurement
           existing data: orch#948 extension corpus (bit-for-bit
                          invariant); fundamental merge 172/172 cols;
                          artifact panel-ltr.alpha158_fund.previous.json
                          trained 2026-06-21 = DB cutoff
           best-known?:   yes — §5 caveats: v1-hash recipe not located
                          (identity via trained_date + binding note +
                          byte family); pinned-vs-live transform version
                          unseparated; blend-leg reproduction not done
           scope:         research note + script + 3 CSV/JSON artifacts

TESTS:     make test not run — docs+research-data only; both scoring
           invocations exit 0.

NEXT:      (a) blend-composite reproduction from its legs (the next
           cell); (b) separate data-revision vs serving-fix hypotheses
           for the pre-07-27 step (older OHLCV snapshot or live-tree
           deploy log); (c) fold the clean-cell result into the #26
           acceptance criteria table.
