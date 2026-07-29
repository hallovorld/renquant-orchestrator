# Progress: shadow-scorer sentinel goes multi-lane (GOAL-1)

STATUS:   delivered (code + 66 tests). Round-4 fix after codex MED: the
          per-check alert BODIES (feed-dark / load-failure / degraded) still
          interpolated the module-global `SHADOW_NAME` regardless of which
          lane was patrolling, so a clf-lane failure paged with a title
          naming the clf lane but a body claiming `hf_patchtst` died —
          misidentifying the broken feed. Round-2 fix after codex HIGH: the clf
          lane was REGISTERED but had NO observable health signal — no
          producer writes it a `shadow_scorer_health.v1` JSONL record, so
          with `runs_db=None` and nothing else, `read_health_records()`
          returned all `None` and the patrol silently printed "liveness
          domain, skip" forever. Round-3 fix after codex HIGH: the
          round-2 locator could not actually verify `shadow_name` (production
          `comparison.json` carries neither `run_date` nor `shadow_name` as
          payload columns) and dated candidates by file mtime, so a
          touch/copy/retry or an unrelated lane's artifact could pass as a
          match; it also scanned only the 20 most-recently-modified files, so
          a genuine older record could be missed. Read-only; no launchd
          change, so no machine landing in this PR.

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
          writes to the shadow DB. Round 3 replaces that locator's primary
          match with the producer's own MLflow run tags (`as_of_date` /
          `shadow_name`, written by `_log_shadow_run` in renquant-pipeline
          via `mlflow.set_tags`) — a content-based record read from
          `<run_dir>/tags/<name>`, checked across every candidate
          `comparison.json` under `mlruns` (no 20-file cap), decisively
          excluding any tagged run whose date/lane doesn't match rather than
          falling through to the mtime heuristic for it. The old
          column/mtime heuristic survives only as a fallback for runs with no
          tags at all.

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
                 this session]` round 2: **60 passed, 2 skipped** (the 2 skips are a
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

                 Round 3 (codex HIGH): the round-2 locator's date/lane match
                 depended on `comparison.json` payload columns that don't
                 exist in production and, absent those, fell back to file
                 mtime for the date and skipped the `shadow_name` check
                 entirely — a touch/copy/retry could produce a false HEALTHY
                 or false FEED_DARK, and the 20-file mtime-sorted cap could
                 silently miss a genuine older record. `_mlflow_shadow_scores_for`
                 now reads each candidate run's own `as_of_date`/`shadow_name`
                 MLflow tags (`<run_dir>/tags/<name>`) as the primary,
                 content-based match, scanned across every candidate (no
                 cap); the old column/mtime heuristic remains only as a
                 fallback for untagged (pre-tag or non-standard) runs, capped
                 at 20 as before.
                 `[VERIFIED — pytest tests/test_rq104_shadow_scorer_sentinel.py,
                 this session]` **63 passed, 2 skipped**: the 60 round-1/2
                 tests unchanged + 3 new — a tagged record with the oldest
                 mtime in a tree of 20 newer untagged decoys is still found
                 (closes the 20-file-cap gap); an unrelated lane's tagged
                 record for the same date is correctly rejected as FEED_DARK
                 instead of silently borrowed (closes the missing-lane-check
                 gap); and a tagged record wins over an untagged decoy whose
                 mtime coincidentally matches the target date (closes the
                 mtime-is-not-immutable gap). All 3 verified to fail against
                 the pre-fix locator before the fix landed.
                 Round 4 (codex MED): `check_feed_dark_streak`,
                 `check_load_failure_streak`, and `check_degraded_streak`
                 built their alert-body text from the module-global
                 `SHADOW_NAME` constant, not the lane actually being
                 patrolled — so a clf-lane LOAD FAILURE alert's title said
                 `[topdecile_clf_blend_leg]` but its body said `shadow
                 scorer 'hf_patchtst' LOAD FAILURE`, sending an operator to
                 debug the wrong feed. Threaded `lane.name` through all
                 three check functions (`lane_name` param, default
                 `SHADOW_NAME` for backward compatibility with any direct
                 caller) and `_patrol_lane`'s call site.
                 `[VERIFIED — pytest tests/test_rq104_shadow_scorer_sentinel.py,
                 this session]` **66 passed** (54 round-1 + 6 round-2 +
                 3 round-3 + 1 new `TestMultiLane` regression asserting the
                 clf lane's LOAD FAILURE alert body contains
                 `'topdecile_clf_blend_leg'` and NOT `'hf_patchtst'`,
                 verified to fail against the pre-fix code first). The 2
                 conditional-import tests ran (not skipped) in this
                 environment; not affected by this change.
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
