# Modal `.map()` partial-failure handling — split from #438

**Date**: 2026-07-10
**Status**: Mergeable now (no Modal execution required)

## Bottom line

Split from #438 per Codex's review: that PR bundled a proven, mock-verified
resilience fix together with unvalidated Modal capacity/cost parameters
(timeout, `max_containers`, cost-rate/threshold) that need a durable bounded
Modal run to validate — currently blocked by the standing operator rule
("no Modal API calls until there's a clear experiment plan"). This PR carries
only the proven half; the parameter changes move to a follow-up PR that stays
draft until that run happens.

## Changes

- `run_variant_remote.map(..., order_outputs=False, return_exceptions=True)`:
  don't block on dead/slow pods; collect exceptions inline instead of letting
  Modal raise them into the iterator and abort the batch.
- `execute_batch` now checks `isinstance(result_json, Exception)` per item,
  reports it via `on_error`/`n_failed`, logs it, and `continue`s — the batch
  keeps draining every other pod's result.
- Per-pod progress logging (`Pod %d/%d returned`).
- `tests/test_cloud_modal.py::TestPartialFailureHandling`: a deterministic
  mock of Modal's real `.map(return_exceptions=True)` exception-interleaving
  contract (yields the raw exception object, not a JSON string, interleaved
  with normal results) proving `execute_batch` doesn't crash, reports the
  real exception unwrapped, and keeps draining subsequent results. Reverting
  only the source change (keeping the test) makes it fail, confirming it's
  meaningful.

## Explicitly NOT in this PR (moved to the follow-up)

`DEFAULT_TIMEOUT_SECONDS` 3600→10800, `max_containers=30`,
`DEFAULT_SECONDS_PER_POD_ESTIMATE`/cost-rate replacement, and the
`cost_reasonable` threshold 20.0→15.0 — all claimed from a round-7 smoke
test but not re-validated on this reconciled code; Codex's review is correct
that a mocked exception cannot validate production-capacity claims.

## Test plan

- [x] `tests/test_cloud_modal.py`: 23 passed
- [ ] Codex review (do not merge without it; never self-merge)
