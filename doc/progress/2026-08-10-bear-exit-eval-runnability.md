# G-B task #21: the frozen BEAR exit evaluation is NOT runnable today — blockers named, episode list derived per the freeze's own §3

STATUS:    blocker publication for the orch#917 frozen confirmatory run.
           No arm was evaluated; no substitute estimand was invented
           (the freeze's "no other values may be tried" discipline
           applied to the estimand as well). The one run-time
           derivation §3 itself prescribes — the BEAR episode list from
           the production regime artifact — executed and committed.

WHAT:      doc/research/2026-08-10-bear-exit-eval-runnability.md.
           Blockers: B1 the two NEW `_by_regime` keys are unread by the
           pipeline (task_panel_conviction_xs.py:133-134, scalars only;
           §4.2 makes this a renquant-pipeline PR — different repo,
           deliberately not done here); B2 the book simulator has no
           regime-series injection, so the 200-seed placebo and
           +5/+10/+20d shift arms are inexpressible; B3 sim artifacts
           cover 2024-01..2026-03 (39 retrain cutoffs) + aux 2022-04 —
           the 2018 + 2020 episodes hold 43/75 = 57% of production-
           artifact BEAR days and are beyond ANY existing sim artifact;
           B4 the prereg says "production HMM" but production loads a
           legacy GMM (prod/spy-gmm-regime.json) — the choice is
           material (75 days/5 episodes vs 211/17), needs a recorded
           freeze ruling. Earliest runnable = capability-gated, not
           calendar-gated; no future market data needed.

WHY/DIR:   G-B standing decision routes BEAR to the exit side; the
           frozen prereg only earns its verdict authority if executed
           exactly as written. Publishing the precise blocker set +
           the committed episode derivation converts "blocked" into an
           actionable sequence: freeze addendum ruling -> pipeline PR
           -> simulator PR -> scope ruling -> one compute batch.

EVIDENCE:  artifact:      doc/research/data/2026-08-10-bear-exit-episode-
                          derivation.py + …-regime-days.csv (2,412 rows) +
                          …-episodes.csv (22 rows) [VERIFIED — derive run
                          2026-08-10 exit 0 (93s), verify mode REPRODUCED
                          exit 0; production regime functions imported
                          from renquant-pipeline, regime modules byte-
                          identical pin e13cd3eb vs HEAD 69bf7116]
           prod or exp:   read-only research; no production surface
                          touched; no sim executed
           existing data: SPY OHLCV 2016-01-04..2026-08-07 (umbrella
                          parquet), prod/spy-gmm-regime.json,
                          sim/spy-hmm-regime.json, pinned
                          strategy_config.json, sim/walkforward_manifest
                          .json — all pre-existing, none modified
           best-known?:   yes — the note states what the derivation is
                          NOT (no estimand, no arm, no verdict; argmax
                          series ≠ resolved live regime, flagged) and
                          that the GMM row reproduces the prereg's
                          planning estimate (~77/~4 -> 75/5)
           scope:         note + derivation script + 2 CSVs + 7 fixture
                          tests + this doc; the pipeline/simulator
                          changes are named as OTHER repos' reviewed
                          PRs, not smuggled in here

TESTS:     tests/test_bear_exit_episode_derivation.py — 7 passed
           (planted single/adjacent/clipped/terminal episodes, null
           control, coverage-flag boundary, committed-CSV end-to-end
           verify). make test 2026-08-10: 6231 passed, 2 skipped,
           1 pre-existing FAIL — test_twin_parity byte_identical:
           alerts.py, the open orch#886 live-tree drift; measures the
           live checkout, untouched by this additive PR.

NEXT:      (a) operator/freeze addendum ruling on B4 (artifact identity
           + tail-overlap semantics + placebo-keying reading);
           (b) renquant-pipeline `_by_regime` PR with behaviour-
           invariance regression (B1); (c) renquant-backtesting
           regime-series-injection capability PR (B2); (d) B3 scope
           ruling: 2018–2022 artifact backfill vs reviewed window
           addendum; then the single frozen compute batch.
