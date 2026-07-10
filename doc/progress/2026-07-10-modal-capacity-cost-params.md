# Modal capacity/cost parameters — split from #438 (BLOCKED, draft)

**Date**: 2026-07-10
**Status**: DRAFT — blocked on a durable bounded Modal completion

## Bottom line

Split from #438 per Codex's review: these parameter changes (timeout,
`max_containers`, cost-rate/threshold) are claimed from a round-7 smoke test
but have NOT been re-validated on the reconciled per-seed fan-out code. A
mocked exception (used to validate the sibling PR,
`fix/modal-partial-failure-handling`) cannot validate production-capacity
claims — only a real multi-pod Modal run can. That run is currently blocked
by the standing operator rule: no Modal API/CLI calls until issues are clear
and there's an explicit experiment plan.

**This PR stays draft until that run happens and confirms (or corrects) the
numbers below.**

## Changes (unvalidated pending a durable bounded run)

- `DEFAULT_TIMEOUT_SECONDS` 3600 → 10800: accommodate I/O contention at 30
  concurrent Volume readers.
- `max_containers=30`: balance wall-clock (~4h) vs Volume-read contention.
- `DEFAULT_SECONDS_PER_POD_ESTIMATE` 5558.0 → 3431.0 and
  `MEASURED_COST_PER_POD_SECOND` (replaces the theoretical CPU/mem-rate
  formula): both sourced from the round-7 bounded smoke test
  (2026-07-08, commit 424600b2) — incumbent pod 3042s, A/A pod 3431s, cost
  $0.30 / (6 pods × ~3237s avg). That smoke test predates the per-seed
  fan-out reconciliation; these figures need re-confirmation on the
  reconciled architecture, not just a carry-forward.
- `cost_reasonable` preflight threshold 20.0 → 15.0, tightened alongside the
  measured (lower) per-pod cost estimate.

## Why split from #438 rather than fixed in place

Bundling proven resilience code with unvalidated capacity numbers would have
forced a choice between merging speculative production parameters or holding
back a verified bug fix. Splitting lets the proven half
(`fix/modal-partial-failure-handling`) merge independently while this one
waits on real evidence.

## Test plan

- [x] `tests/test_cloud_modal.py`: 22 passed (parameter values, no behavior
  change to preflight/aggregation logic itself)
- [ ] Durable bounded multi-pod Modal run validating `max_containers=30`,
  the 10800s timeout, and cost under concurrent Volume reads — BLOCKED on
  the no-Modal-calls rule; requires an explicit experiment plan first
- [ ] Codex review (do not merge without it; never self-merge)
