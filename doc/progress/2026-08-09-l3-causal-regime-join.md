# L3 regime joins by RUN IDENTITY — the only causal construction   (PR #930)

STATUS:    delivered for review. Read-only over the runs DB; no production
           surface.

WHAT:      src/renquant_orchestrator/l3_candidate_dataset.py regime join
           changed from "latest live_state_snapshots row of the run_date" to
           a join by run_id: THE SAME RUN's snapshot — whose regime that run
           computed before scoring its candidates — is the only snapshot a
           row may take. Rows now carry regime_snapshot_created_at, and
           regime_source = same_run_snapshot | absent. +2 tests (7 total).

WHY/DIR:   Codex P0 on the classifier prereg (orch#929): the date-latest
           join can leak — a later same-day snapshot postdates the scoring.
           The obvious alternative, a created_at <= run-time inequality,
           fails the OTHER way: snapshot rows are written at run END, so the
           inequality voids the field entirely (a fixture with realistic
           times pins this — run at 14:05, its own snapshot at 21:00 must
           still be usable, another run's 09:00 snapshot must not). The
           causal source is structural, not temporal: run identity. This
           unblocks freezing regime features in the L3 prereg.

EVIDENCE:  artifact:      real-DB rebuild via
                          renquant_orchestrator.l3_candidate_dataset
                          .build_candidate_rows over
                          RenQuant/data/runs.alpaca.db (opened mode=ro)
                          [VERIFIED — in-session stdout, this fix session]:
                          regime_source = 2,184 same_run_snapshot / 4,983
                          absent; run_type split of the same_run rows: 2,184
                          live / 0 sim — regime is honestly a live-only
                          feature (sim runs write no snapshots; 5 live rows
                          lack their own run's snapshot and are recorded
                          absent, never invented). regime_snapshot_created_at
                          populated on all 2,184 same_run rows.
           prod or exp:   experiment — read-only build, CSV/manifest under
                          /tmp only
           existing data: pre-fix module joined by run_date (last snapshot
                          of the date wins) — the leaky construction the
                          prereg review flagged; manifest re-measured after
                          the fix [VERIFIED — same in-session run]: 7,167
                          rows / 523 dates / 1,275 excluded / live 2,189 /
                          sim 4,978 / selected 135 / win rate 0.6307 —
                          identical to the merged #928 record (the join
                          changes regime columns only, never row selection).
           best-known?:   yes — the only construction that is causal by
                          construction; both same-date alternatives are
                          wrong in opposite directions (latest leaks;
                          timestamp-inequality voids the field).
           scope:         "this is the L3 candidate dataset's regime
                          columns, experiment, vs the #928 date-join
                          baseline — row counts and labels unchanged"

TESTS:     7 passed [VERIFIED — pytest -q tests/test_l3_candidate_dataset.py,
           this session] — including the two new guards: another run's
           same-day snapshot must NOT supply regime (run identity, not
           date), and a run without its own snapshot records absent.

NEXT:      orch#929 re-freezes the classifier prereg with regime features
           gated on this PR's merge.
