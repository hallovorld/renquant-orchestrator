# qp evidence runner (PR B) — join-only consumer with committed rehearsal controls

STATUS:    implementation of the MERGED freeze's orchestrator half
           (orch#955 §7); the REAL run awaits PR A's hash-pinned
           artifacts (renquant-model qp_evidence_scorer, in flight).
           No real numbers produced here.

WHAT:      doc/research/data/2026-08-10-qp-evidence-runner.py — sha-
           asserts PR A's scores CSV + stamps JSON + the frozen corpus
           against the manifest; applies the designed admission on the
           FROZEN stamps fail-closed (missing/ineligible/failed regime
           ⇒ gate-starved, coverage-recorded); computes the frozen
           statistic (K=5, top-5 label-z minus labelled-universe mean)
           and inference (stationary bootstrap block 10 / B 2000 /
           seed 99, drawn PER FOLD SEGMENT — no block crosses a fold
           boundary or wraps); asserts EXACT score coverage against
           the manifest's expected_schedule (off-schedule aborts;
           missing days = fail-closed coverage rows); one regime per
           (fold,date) asserted; turnover resets at fold boundaries;
           top-K by explicit (−score, ticker) ordering; the frozen
           corpus pin 870f68eb… is the runner's own constant
           (fixture-mode relaxes only it, recorded in the summary);
           emits the §6 verdict enum exactly
           (PASS/FAIL/POWER_INSUFFICIENT, floor 700 days) and the
           report-only cost companion. tests/test_qp_evidence_runner.py
           = the committed rehearsal fixture on the REAL code path:
           11 controls (planted PASS / null FAIL / starvation
           POWER_INSUFFICIENT / determinism / sha-mismatch dies /
           real-mode rejects non-pin corpus / missing-day coverage /
           mixed-regime dies / two-fold turnover reset / two-fold
           bootstrap determinism / all-tied membership) — 11 passed.

WHY/DIR:   §7 requires rehearsal-with-committed-fixture before the real
           run and the model/orchestrator boundary (training internals
           in renquant-model; join+report here). Landing PR B first
           lets the real run execute the moment PR A's artifacts merge.

EVIDENCE:  artifact:      doc/research/data/2026-08-10-qp-evidence-runner.py +
                          tests/test_qp_evidence_runner.py
                          [VERIFIED — pytest 11 passed, 2026-08-10]
           prod or exp:   experiment tooling; no real inputs consumed
           existing data: the merged freeze (orch#955) is the sole
                          authority; PR A's schema per the build spec
           best-known?:   yes — the runner refuses non-manifest inputs;
                          fixture-mode exercises the identical code path
           scope:         runner + tests + this doc; the real execution
                          and its evidence files are a follow-up on
                          this branch once PR A merges

TESTS:     pytest tests/test_qp_evidence_runner.py — 11 passed.

NEXT:      PR A merges → run against its committed artifacts → commit
           verbatim evidence files + the verdict on this branch (or a
           successor PR if this one has merged).
