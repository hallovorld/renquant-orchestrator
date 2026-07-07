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
