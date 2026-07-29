# Progress: shadow-scorer sentinel goes multi-lane (GOAL-1)

STATUS:   delivered (code + 56 tests, 50 of them pre-existing and unchanged).
          Read-only; no launchd change, so no machine landing in this PR.

WHAT:     Introduces `WatchedLane` + `watched_lanes()` and threads a lane through the
          record readers, the checks and the patrol loop. `main` now patrols every
          registered lane and tags each finding with the lane that produced it. The
          module-level single-lane constants become the DEFAULT lane's values, so
          every existing call site and test is unchanged.

WHY/DIR:  The sentinel watched exactly one lane, `hf_patchtst`. The certified
          top-decile classifier — the only line with a confirmed effect, live in
          shadow and accruing the 120-session forward ledger — was **unwatched**. A
          silent death there would cost the ledger, which is the one piece of
          evidence in this programme that cannot be re-derived after the fact.

EVIDENCE: the design's load-bearing detail is that lanes differ in WHERE their
          evidence lives: the PatchTST lane persists scores to the shadow runs DB, so
          a DB-derived record is a valid fallback; the clf lane logs to MLflow and
          writes nothing there `[VERIFIED — 2026-07-28 daily log: the clf leg reports
          via "logged 82 candidates via MLflow" while the runs DB carries no clf
          rows]`. Applying the DB fallback to it would derive "no scores collected"
          every single day and manufacture a permanent FEED DARK alarm out of a
          healthy lane — so `runs_db` is per-lane and may be None, pinned by a test
          asserting the DB is never opened for such a lane. Suite 56/56
          `[VERIFIED — pytest tests/test_rq104_shadow_scorer_sentinel.py]`, of which
          6 are new multi-lane tests and 50 are the pre-existing single-lane tests
          passing unchanged (the refactor is behaviour-preserving for lane 1). No
          model/IC claim is made, so the §4(b) triad does not apply.

NEXT:     Install nothing new — the existing launchd job picks the second lane up on
          its next patrol once merged and synced. Follow-up: per-lane thresholds are
          plumbed but both lanes currently inherit the module defaults, and the clf
          lane's known-benign `stale_91d` flag (a fwd60 recipe cannot be fresher by
          construction) will page until the horizon-aware rule from orch#588 lands.
