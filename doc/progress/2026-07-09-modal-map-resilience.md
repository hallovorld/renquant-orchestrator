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

## Round 2 (Codex requires bounded multi-pod execution evidence)

STATUS: attempted — partial evidence only, not fully resolved
WHAT: codex flagged that the test plan (`make test` + 1-pod validation)
does not exercise the actual behaviors this PR changes: `order_outputs=False`
+ `return_exceptions=True` semantics under concurrent dispatch, and
`max_containers=30`/timeout sizing under real I/O contention. Codex asked
for a bounded multi-pod (>1 pod) remote run demonstrating results streaming
back without ordering assumptions and partial failures surfacing as
collected exceptions rather than a hang.

Ran a bounded 2-variant × 3-seed (6-pod) validation on this branch, in an
isolated worktree, three separate times:
1. Attempt 1 (`ap-n7yNaWdBTREjWCxCLbUJV4`, 2026-07-09 01:09-01:28 PDT):
   dispatched via the harness's tracked background-task mechanism. Ran
   ~19min, reached 6/6 pods dispatched and executing (concurrent
   `SimAdapter`/`ApplyScoresTask` log interleaving from multiple pods
   confirmed via `modal app logs`), then the local process disconnected;
   Modal's own log shows "Stopping app - local client disconnected...
   Runner terminated." — not a code exception.
2. Attempt 2 (`ap-tnWoBfg4rXFo3cobgP6OZg`, 01:29-01:54 PDT): relaunched via
   manual `nohup`+`disown` to survive the same disconnection. Local process
   died almost immediately this time (log stopped advancing right after
   launch) — the manual-background approach does not actually survive this
   tool environment's own execution-scope teardown the way the harness's
   native background-task tracking does.
3. Attempt 3 (`ap-Bis4rGKlmesb2SVpqwnrsp`, 02:04-02:43 PDT): relaunched via
   the harness's tracked background mechanism again (the approach that
   worked best in attempt 1). Ran ~39min — longer than attempts 1-2 and
   past where the round-7 smoke test's own per-pod cost/timing was
   measured (3042-3431s ≈ 51-57min per pod) not yet reached — then the
   harness itself reported the background task as killed/stopped (not a
   timeout or exit code from the script). Stopped the now-orphaned Modal
   app manually to avoid pointless further spend once no local collector
   remained to receive results.

WHY-DIR: none of the three failures were caused by the code under test.
All three were this specific validation environment failing to keep a
long-lived (>50min) background process/connection alive — likely
exacerbated by heavy concurrent system load observed during this window
(multiple unrelated Modal apps from other sessions terminating within the
same ~2.5min window as attempt 1; system memory pressure measured at
43-47GB used with as little as 62MB free during these attempts). This is
an execution-environment constraint on validating from here, not evidence
against the PR's fix.
EVIDENCE:
- Confirmed 3x: deterministic data-contract preflight passes clean (237
  checks, 0 failures) against this branch's code.
- Confirmed 2x (attempts 1 and 3, via `modal app list`/`modal app logs`):
  multiple pods (3 and 6 respectively) genuinely dispatch and execute
  concurrently on Modal under this branch's `order_outputs=False` — real
  evidence the concurrent-dispatch path works, not just unit-mocked.
- Confirmed 0x: a single pod reaching completion, `return_exceptions=True`
  actually catching a real pod failure, or final cost/timing numbers from
  this branch's code. The ~50-57min single-pod runtime (per round-7's own
  measured figures this PR cites) exceeds what this validation environment
  could keep a local collector alive for across all three attempts.
NEXT: either (a) accept the partial evidence above (data contract +
concurrent dispatch confirmed, full-run completion not yet observed) as
sufficient given the specific, reproducible environmental cause, (b) run
the same bounded validation from an environment that can sustain a >1hr
background connection (e.g. the operator's own terminal, or a session with
lower concurrent load), or (c) wait and retry once system load in this
environment drops. Not re-attempting a 4th blind retry under the same
conditions since the last check showed memory pressure had gotten worse,
not better, between attempts.

## Round 3 (deterministic unit test for `return_exceptions=True`, no Modal required)

STATUS: fixed
WHAT: codex's r2/r3 review on #438 asked for "one short, intentionally
failing bounded batch to directly validate the `return_exceptions=True`
claim" without waiting on a full >50min pod completion. Operator has since
put a hard rule in place (no Modal API/CLI calls until the open questions
across the cash-drag PR family are resolved and there's an explicit
experiment plan), so a real cloud-side failing-pod run is not available
right now. The claim is fully deterministic given Modal's own documented
`.map(return_exceptions=True)` contract (failed pods yield the raised
exception object in place of a result, not a wrapper) — that's exactly
what a mock can prove without touching the network.
WHY-DIR: `ModalExecutor.execute_batch`'s iteration loop (modal_executor.py)
checks `isinstance(result_json, Exception)` before attempting
`json.loads()`. Whether that specific branch actually fires end-to-end
(reports the real exception via `on_error`, increments `n_failed`, and
keeps draining subsequent pods) was previously asserted only by code
reading, not exercised by any test — every existing `.map()` mock returned
only well-formed JSON strings.
EVIDENCE:
- New test `TestPartialFailureHandling::test_exception_item_is_reported_not_raised_and_batch_keeps_draining`
  (`tests/test_cloud_modal.py`): fake `.map()` yields
  `[success(seed=42), RuntimeError("pod task-b died: OOMKilled"), success(seed=44)]`
  — mirroring Modal's real interleaving of exception objects with normal
  results. Asserts `execute_batch` does not raise, `on_error` receives the
  *actual* exception instance (not a rewrapped one), `summary.n_failed == 1`,
  and both successful seeds (42 and 44) still reach the final aggregated
  result — proving the batch keeps draining past the failure instead of
  abandoning it.
- Confirmed the test is meaningful, not tautological: reverted only
  `modal_executor.py` to its pre-#438 state (test kept post-fix) and reran
  — it fails, and not just by crashing: the pre-fix code's generic
  `except Exception` around `json.loads()` silently converts the failure
  into `TypeError("the JSON object must be str, bytes or bytearray, not
  RuntimeError")`, losing the real pod-failure reason
  (`RuntimeError('pod task-b died: OOMKilled')`) entirely. The fix isn't
  just crash-prevention — it's the difference between reporting the true
  cause of a pod failure and reporting a misleading parse error.
- Full suite: 3263 passed, 3 skipped, 0 failed (`make test` equivalent,
  run with the multi-repo `PYTHONPATH` — same as CI).
NEXT: this closes the `return_exceptions=True` half of codex's ask via a
fast, deterministic unit test. The remaining half — one durable multi-pod
*completion* on Modal from an environment that can sustain the run — is
still blocked on the operator's standing no-Modal-calls rule and is not
attempted here.
