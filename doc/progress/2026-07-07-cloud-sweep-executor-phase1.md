# 2026-07-07 — cloud sweep executor Phase 1: abstraction layer + SQLite store

**PR**: feat(cloud): BacktestExecutor protocol + SQLite result store + local backend

## Problem

The concentration cap sweep writes results as a single atomic JSON at
completion — a crash at variant 73/74 loses everything. No resume capability.
The sweep runner is tightly coupled to ProcessPoolExecutor with no backend
abstraction, blocking cloud execution.

## Change

Phase 1 of the cloud burst execution design (PR #429):

1. `cloud/executor.py` — `BacktestExecutor` protocol (execute_batch with
   streaming callbacks, preflight, sync_data) + `BacktestRequest`/
   `BacktestResult`/`BatchSummary` data objects
2. `cloud/result_store.py` — SQLite-backed `ResultStore` with per-variant
   INSERT on receipt (crash-safe), WAL mode, sweep_runs / variant_results /
   seed_metrics / regime_metrics tables, resume via `completed_variants()`
3. `cloud/local_executor.py` — `LocalExecutor` wrapping ProcessPoolExecutor
   (or ThreadPoolExecutor for test contexts) behind the protocol

## Verification

- 19 new tests (result store: insert, resume, crash recovery, verdict,
  finalize, idempotent init; executor: checksum, batch streaming, error
  handling, preflight, sync)
- Full suite: 3214 passed (1 pre-existing snapshot-stale failure)

## Round 2 (Codex review on `scripts/run_sweep_modal.py` + `cloud/`)

STATUS: fixed
WHAT: three blocking issues on the Phase 2 CLI (`feat(cloud): BacktestExecutor
+ Modal sweep pipeline`).
1. `scripts/run_sweep_modal.py` called `ResultStore` with a constructor,
   `init_sweep`, `completed_variants`, `insert_variant`, `insert_error`, and
   `finalize` signature that did not match the real class in
   `cloud/result_store.py` (e.g. `ResultStore(db_path)` vs the real
   `ResultStore(sweep_id, base_dir)`; `insert_variant(sweep_id, result)` vs
   the real `insert_variant(variant_name, role, config_fingerprint,
   per_seed, ...)`). This would fail before or immediately after dispatch.
   Every unit test of `ResultStore` in isolation and of the executor
   protocol in isolation still passed, because none exercised the two
   integrated.
2. `artifact_manifest_fingerprint` was populated with `bundle_fp` — the
   *source-code* bundle fingerprint from `bundle_subrepos()` — not a
   model/walk-forward-artifact fingerprint. `sync_data.py`'s `commit_id`
   was a wall-clock timestamp taken after `vol.commit()`, which proves
   nothing about content identity (two syncs of identical data a second
   apart would wrongly report different commit_ids).
3. Scope check on `bundle.py`'s 9-repo list and the generic
   `BacktestExecutor`/`LocalExecutor`/`ModalExecutor` layer: verified
   against `doc/design/2026-07-07-cloud-backtest-compute.md` §9's approved
   Phase 1/2 plan — this abstraction is the design's own explicit deliverable
   (shared local/Modal interface for W1/W4), and `bundle.py`'s repo list is
   hardcoded to exactly `run_concentration_cap_sweep.py`'s own
   `SUBREPO_IMPORT_ORDER`, not an arbitrary/generic bundler. Also verified
   `run_sweep_modal.py` reuses the sweep script's canonical `build_grid_variants`
   / `build_aa_variant` / `unanimity_verdict` / `_mean` / `AA_MAX_ABS_SHARPE_LIFT`
   via direct import rather than reimplementing them — it is not a diverging
   parallel sweep runner. The concrete, addressable gap was that this
   scope-anchoring was implicit; both modules now document the W1/W4-only
   boundary explicitly, and a test proves `bundle.py`'s repo list stays
   synced with the sweep script's own dependency list rather than silently
   drifting.
WHY-DIR: (1) is a real integration bug — the advertised CLI flow could not
run end to end. (2) is the exact provenance contract #429 was already
corrected to require (full pinned-multirepo assembly, not a single
fingerprint standing in for the wrong thing) not actually being honored in
code. (3) is the same split-brain/silent-drift concern this session has
repeatedly found elsewhere, this time on which repos+scope a shared
abstraction is allowed to grow into.
EVIDENCE:
- `run_sweep_modal.py`'s execution logic (steps 4-8) extracted into a
  standalone `run_sweep(executor, store, ...)` function so it can be driven
  by a fake in-memory executor against a REAL `ResultStore` in
  `tests/test_run_sweep_modal.py` — not mocked-apart pieces. Confirmed via
  `git stash` that this test module fails to even import against the
  pre-fix code (`run_sweep` didn't exist), then passes fully post-fix (2/2).
  Covers: variant persistence, per-seed/per-regime rows reaching the store,
  error recording, verdict computation + `update_verdict` persistence,
  `finalize` totals, and resume (`completed_variants()` genuinely skips
  already-persisted variants — proven via a recording fake executor that
  asserts the incumbent is never re-dispatched).
- `artifact_manifest_fingerprint` now hashes the actual walk-forward
  manifest file (`args.manifest_path`, resolved against `strat_dir`) — the
  same file the WF gate/pipeline already treats as the model/artifact
  provenance anchor — instead of the source-code bundle fingerprint.
- `sync_data.py` gets a new `compute_manifest_commit_id()` (same
  sorted-JSON-sha256 pattern as `bundle.py::compute_bundle_fingerprint`,
  applied to the synced-files manifest); both the "no changes" and
  "synced" branches now compute it fresh from actual content.
  `test_commit_id_is_content_coupled_not_a_timestamp` proves the id changes
  iff content changes.
- `test_subrepo_names_stays_synced_with_sweep_scripts_own_dependency_list`
  asserts `bundle.SUBREPO_NAMES == run_concentration_cap_sweep.SUBREPO_IMPORT_ORDER`.
- Full suite: 3224 passed, 3 skipped, 1 pre-existing unrelated failure
  (`test_parking_sleeve_cli_computes_allocation`, confirmed reproducing on
  a clean main checkout, unrelated to this change).
NEXT: none on this round's three points. A future round could physically
merge `run_sweep_modal.py`'s CLI into `run_concentration_cap_sweep.py`
behind a `--backend {local,modal}` flag (the design doc's literal Phase 2
step 6) rather than a separate script — deferred since the current script
already reuses the canonical variant/criteria functions rather than
diverging, and `run_concentration_cap_sweep.py` is an actively-running
script in production use, so a structural merge deserves its own
change/review rather than folding it into this fix.
