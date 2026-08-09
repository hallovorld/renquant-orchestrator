# L3 dataset — regime joins by run identity (the only causal construction)

STATUS:    delivered for review (orch#930). Resolves the P0 on the classifier
           prereg (orch#929): the prereg's regime feature is gated on this
           merging.

WHAT:      src/renquant_orchestrator/l3_candidate_dataset.py — regime joins
           live_state_snapshots by RUN_ID (the same run's snapshot, whose
           regime that run computed BEFORE scoring its candidates); rows
           carry regime_snapshot_created_at and regime_source =
           same_run_snapshot | absent. Plus 2 new tests (run-identity beats
           same-date; no-own-snapshot is absent).

WHY/DIR:   Both same-DATE joins are wrong in opposite directions:
           * date-latest snapshot LEAKS — a later same-day snapshot postdates
             the scoring (the codex P0);
           * timestamp-inequality VOIDS the field — snapshots are written at
             run END (fixture with realistic times: run created 14:05,
             snapshot 21:00 → every comparison fails).
           The causal source is structural, not temporal: the snapshot's
           run_id ties it to the exact process whose scoring it precedes.

EVIDENCE:  artifact:      read-only build against runs.alpaca.db this session
           prod or exp:   experiment — read-only over prod data
           existing data: the merged builder (orch#928) used the date-latest
                          join this PR replaces
           best-known?:   yes — regime_source distribution under the causal
                          join: {same_run_snapshot: 2184, absent: 4983} of
                          7167 rows [VERIFIED — module run this session;
                          independently reproduced by codex's own read-only
                          validation on the PR head]. The split maps ~1:1 to
                          live (2,189) vs sim (4,978) rows: SIM RUNS WRITE NO
                          SNAPSHOTS, so regime is honestly a live-only
                          feature — recorded absent elsewhere, never invented.
           scope:         one module + tests; no production surface. The
                          classifier prereg (relocating to renquant-model per
                          its P1) freezes regime/confidence GATED on this
                          construction.

TESTS:     7 passed — incl. another run's same-day snapshot must NOT supply
           regime (run-identity, not date), and a run without its own
           snapshot is absent.

NEXT:      merge; then the prereg relocation commit on the orch#929 branch
           points its regime-feature contract at this construction.
