# Progress: shadow-scorer sentinel goes multi-lane (GOAL-1)

STATUS:   delivered (code + 62 tests). Round-2 fix after codex HIGH: the clf
          lane was REGISTERED but had NO observable health signal — no
          producer writes it a `shadow_scorer_health.v1` JSONL record, so
          with `runs_db=None` and nothing else, `read_health_records()`
          returned all `None` and the patrol silently printed "liveness
          domain, skip" forever. Read-only; no launchd change, so no machine
          landing in this PR.

WHAT:     Introduces `WatchedLane` + `watched_lanes()` and threads a lane through the
          record readers, the checks and the patrol loop. `main` now patrols every
          registered lane and tags each finding with the lane that produced it. The
          module-level single-lane constants become the DEFAULT lane's values, so
          every existing call site and test is unchanged. Round 2 adds
          `WatchedLane.mlruns_dir` + `_read_from_mlflow()`: for the clf lane,
          this reuses the SAME `comparison.json` locator
          `rq104_blend_readout.py` already reads daily (one reader, so the
          sentinel and the readout job can never disagree on what counts as
          "this lane was recorded"), with `had_runs` sourced from the
          PRODUCTION runs DB (`data/runs.alpaca.db`) since this lane never
          writes to the shadow DB.

WHY/DIR:  The sentinel watched exactly one lane, `hf_patchtst`. The certified
          top-decile classifier — the only line with a confirmed effect, live in
          shadow and accruing the 120-session forward ledger — was **unwatched**. A
          silent death there would cost the ledger, which is the one piece of
          evidence in this programme that cannot be re-derived after the fact.
          Registering the lane without a working reader would have been
          theatrical monitoring (§7.7): codex, correctly, would not accept
          "registered, never patrolled" as watched.

EVIDENCE:
  artifact:      `ops/renquant104/rq104_shadow_scorer_sentinel.py` +
                 `tests/test_rq104_shadow_scorer_sentinel.py`
  prod or exp:   prod — sentinel/monitoring code path, read-only, no
                 launchd/schedule change in this PR.
  existing data: `[VERIFIED — 2026-07-28 daily log]` the clf leg reports via
                 "logged 82 candidates via MLflow" while the shadow runs DB
                 carries no clf rows — the design's load-bearing detail is
                 that lanes differ in WHERE their evidence lives: the
                 PatchTST lane persists scores to the shadow runs DB (a
                 DB-derived record is a valid fallback for it), but applying
                 that same fallback to the clf lane would derive "no scores
                 collected" every single day and manufacture a permanent
                 FEED DARK alarm out of a healthy lane. `runs_db` is
                 therefore per-lane and may be `None`, pinned by a test
                 asserting the DB is never opened for such a lane.

                 Round 2 (codex HIGH): `runs_db=None` alone left the clf lane
                 with NO reader at all unless a pipeline producer writes it a
                 JSONL record — none does (`[VERIFIED — grep
                 'topdecile_clf_blend_leg' across renquant-pipeline src:
                 zero hits]`). Added `_read_from_mlflow()`, which reuses
                 rq104_blend_readout.py's own `comparison.json` locator
                 (same file-glob-by-mtime logic, same column contract —
                 verified directly against a real production artifact,
                 `mlruns/444804097530090886/.../artifacts/comparison.json`:
                 columns `[ticker, primary_score, shadow_score, diff,
                 primary_rank, shadow_rank, rank_diff]`, no `run_date`/
                 `shadow_name` columns, confirming the mtime-date fallback
                 path is the one that actually fires in production), with
                 `had_runs` sourced from the PRODUCTION runs DB
                 (`data/runs.alpaca.db`) rather than the shadow DB this lane
                 never writes to.
                 `[VERIFIED — pytest tests/test_rq104_shadow_scorer_sentinel.py,
                 this session]` **60 passed, 2 skipped** (the 2 skips are a
                 conditional-import contract test pair that only runs when the
                 producer module is importable in this environment — not a
                 failure, and not something this PR's changes affect): the 54
                 round-1 tests unchanged + 6 new (`TestMlflowFallback`) exercising the real
                 artifact shape end to end — a live day with a recorded
                 comparison table classifies HEALTHY, a live day with none
                 classifies FEED_DARK, a day with no live run at all stays in
                 the liveness checker's domain (empty dict, no false alarm),
                 and a full `_patrol_lane()` run now actually ALARMS on a
                 silently-dark clf lane instead of printing "liveness domain,
                 skip". Also fixed test isolation: `_run()`'s `main()`
                 harness was patching `SHADOW_DB`/`SHADOW_HEALTH_JSONL` but
                 not the new `MLRUNS_DIR`/`PROD_RUNS_DB` constants, so before
                 this fix every `main()`-driving test was silently scanning
                 the REAL production `mlruns/` tree (47,698 `comparison.json`
                 files) and opening the real `data/runs.alpaca.db` — slow and
                 not test-isolated. Both constants are now patched to
                 nonexistent tmp paths in `_run()`'s default seam set.
  best-known?:   n/a — monitoring-code change, not a competing model/signal
                 variant; no IC/Sharpe number is claimed.
  scope:         this PR makes the sentinel patrol both shadow lanes instead
                 of one, and (round 2) gives the second lane an actual
                 working reader instead of a registration with no signal. No
                 model/IC/Sharpe claim is made, so the §4(b) sanity triad
                 does not apply — the claims above are about monitoring-code
                 behaviour (log/DB/artifact shape, test suite), not model
                 quality.

NEXT:     Install nothing new — the existing launchd job picks the second lane up on
          its next patrol once merged and synced. Follow-up: per-lane thresholds are
          plumbed but both lanes currently inherit the module defaults, and the clf
          lane's known-benign `stale_91d` flag (a fwd60 recipe cannot be fresher by
          construction) will page until the horizon-aware rule from orch#588 lands.
