# Modal map() resilience + timeout/concurrency fixes

**Date**: 2026-07-09
**Branch**: `feat/modal-per-seed-fanout-v2`
**Fixes**: rounds 8-10 failures from the Modal sweep retrospective

## Changes

### modal_app.py
- `DEFAULT_TIMEOUT_SECONDS`: 3600 -> 10800 (3h). With 30 concurrent Volume
  readers, I/O contention can push a ~19min pod past 1h. 3h provides 3x
  headroom.
- `max_containers=30`: caps concurrent pods to avoid account limits while
  keeping wall-clock time acceptable (~4h for 225 tasks).

### modal_executor.py
- `order_outputs=False`: results arrive as they complete, not blocked on the
  slowest/dead pod. Without this, a single dead pod hangs the entire iterator.
- `return_exceptions=True`: failed pods yield exception objects instead of
  raising — the sweep collects partial results instead of crashing.
- Progress counter: logs "Pod N/M returned" for visibility.
- Cost estimate: uses measured rate from round-7 smoke test ($0.00001545/pod-sec)
  instead of theoretical CPU+MEM rates.
- Cost gate: $20 -> $15 (tighter now that we have measured per-pod costs).

### test_cloud_modal.py
- Mock `map()` accepts `**extra` kwargs (order_outputs, return_exceptions).
- Default timeout assertion updated to 10800.

## Rationale

Each fix addresses a specific failure mode documented in the retrospective
(doc/progress/2026-07-08-modal-sweep-retrospective.md §3b):

| Round | Root cause | Fix |
|-------|-----------|-----|
| 8 | `order_outputs=True` default + no container limit → hang | `order_outputs=False`, `return_exceptions=True`, `max_containers=30` |
| 9 | 1h timeout < I/O-contention-inflated pod time | `DEFAULT_TIMEOUT_SECONDS = 10800` |
| 10 | `max_containers=10` → 13h wall-clock | `max_containers=30` (timeout now accommodates contention) |
