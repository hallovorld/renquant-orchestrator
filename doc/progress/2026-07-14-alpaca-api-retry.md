# Alpaca API retry for rq105 session scheduler

Date: 2026-07-14

## Problem

The rq105 intraday session scheduler crashes on transient Alpaca API errors
(504 Gateway Timeout, read timeouts). The `AlpacaLiveStateSource.snapshot()`
method calls `client.get_account()` and `client.get_all_positions()` without
retry, so a single timeout kills the entire session.

Observed in logs:
- `2026-07-14`: `504 Server Error: Gateway Timeout` on `get_account()`
- `2026-07-13`: `ReadTimeout` on paper-api.alpaca.markets

## Fix (round 1)

Added `_broker_call_with_retry()` — exponential backoff (2^attempt seconds)
with up to 3 attempts for transient errors (timeout, 502/503/504, 429).
Non-transient errors propagate immediately without retry.

Applied to both `get_account()` and `get_all_positions()` calls in
`AlpacaLiveStateSource.snapshot()`.

3 new tests in `test_intraday_session_inputs.py`:
`test_broker_retry_succeeds_after_transient`, `test_broker_retry_raises_on_non_transient`,
`test_broker_retry_exhausted_raises`.

## Fix (round 2)

Round-1 review asked for structured HTTP-status classification instead of
string matching, plus `Retry-After` handling for 429s. Added
`_extract_status_code()` / `_is_transient()` (status-code based, with a
string-matching fallback for exceptions with no `response`), a first cut of
`_extract_retry_after()` (numeric-only), and a 60s total deadline
(`_BROKER_DEADLINE_SECONDS`) tracked across attempts.

## Fix (round 3)

Codex's round-2 review found two real gaps (quoted verbatim in the PR #516
r3 comment):

1. `_extract_retry_after()` only parsed a float; RFC 9110 §10.2.3 also
   allows an HTTP-date form, and the `retry_after or backoff` composition
   silently discarded a valid `Retry-After: 0` (falsy-zero bug).
2. The 60s deadline only bounded the *sleep* between retries, not the
   duration of `fn()` itself — a hung socket call could run (and even
   return successfully) well past the deadline.

Issue 1 was fixed first (commit `2f71b718`): `_extract_retry_after()` now
tries `float(raw)` first, then `email.utils.parsedate_to_datetime(raw)` for
the HTTP-date form; a resolved delay in the past clamps to `0.0`; the call
site composes the wait via `retry_after if retry_after is not None else
backoff` instead of `retry_after or backoff`. A follow-up hardened the
HTTP-date path further (attach `timezone.utc` to a naive parsed result
before subtracting, avoiding a naive-vs-aware `TypeError` for
non-compliant servers) and applies the existing `_BROKER_MAX_RETRY_WAIT`
cap uniformly.

Issue 2 (the harder one) required a real design: added
`_call_with_deadline()`, so each retry attempt runs bounded by the
REMAINING deadline budget (recomputed every attempt), not just checked
between attempts. For real Alpaca calls it patches the client's private
`requests.Session` (`_patch_session_default_timeout()`) so the actual HTTP
request carries a socket-level timeout — alpaca-py's
`get_account()`/`get_all_positions()` take no arguments and its
`RESTClient._one_request()` never sets a `timeout`, so patching the session
is the only hook available. As a backstop for callables reflection can't
reach, the call also runs on a worker thread bounded by
`Future.result(timeout=...)`, so the helper itself can never block (and
therefore return or retry) past the deadline even where session-patching
doesn't apply.

New tests in `test_intraday_session_inputs.py`: HTTP-date Retry-After
(future/past/zero), the zero-vs-`None` regression test, an HTTP-date
retry-loop test, `test_broker_retry_call_bounded_by_remaining_deadline` (a
`fn()` that sleeps 0.6s against a 0.15s deadline must be cut off near the
deadline, not run to completion), and two tests
(`test_call_with_deadline_threads_real_timeout_into_alpaca_session`,
`test_call_with_deadline_updates_timeout_per_attempt_idempotently`) proving
the fix threads through to a realistic Alpaca-client-shaped object (a fake
`TradingClient`/`requests.Session` pair), not just the thread-based
backstop.

## Fix (round 4)

Codex's round-3 review (`[P1]`, quoted verbatim in the PR #516 r4 comment)
found that round 3's "backstop" was not actually safe for a live scheduler:

> `_call_with_deadline()` creates a fresh `ThreadPoolExecutor` for every
> attempt and calls `shutdown(wait=False, cancel_futures=True)` after
> `Future.result(timeout=...)`. That does not stop a callable that has
> already started. A hung broker request therefore leaves a live worker
> behind; repeated failures can accumulate workers, and Python's executor
> shutdown machinery can still wait for them at process exit.

Root cause: `Future.result(timeout=...)` only stops the *caller* from
waiting — Python threads cannot be forcibly interrupted, so if `fn()` had
already entered a blocking call, the abandoned worker thread kept running
that call indefinitely in the background, un-cancelled. Presenting that as
a "hard 60s deadline" was false whenever the real session-patch (mechanism
1) didn't apply.

**Fix: removed the `ThreadPoolExecutor`/`Future.result(timeout=...)`
fallback entirely** (no more `import concurrent.futures` in this module).
`_call_with_deadline()` now has exactly ONE mechanism: patch the callable's
bound client's private `requests.Session` (`_patch_session_default_timeout()`)
so the real HTTP request carries a genuine socket-level timeout — the only
mechanism that is actually cancellation-safe, because `requests`/`urllib3`
raise a timeout error *from inside* the blocking call itself, synchronously,
in the calling thread, when the socket timeout fires. No external canceller
is needed or possible.

If `fn` is not a bound method with a reflectable `_session` (confirmed via
`alpaca.common.rest.RESTClient.__init__`/`_one_request` that this is real
for `client.get_account`/`client.get_all_positions`), `_call_with_deadline`
now raises a new `UnboundedBrokerCallError` (a `TypeError` subclass)
immediately, loudly, instead of running unbounded or falling back to the
non-cancellation-safe thread. This is an explicit architecture decision: a
callable shaped differently needs a real, supported timeout hook added for
it, not a detached-thread race.

Test changes:
- Rewrote the retry/backoff/classification test doubles (`flaky`, `fatal`,
  `rate_limited`, `auth_fail`, `bad_request`, `always_502`,
  `slow_then_fail`, etc.) to route through a new `_as_reflectable_call()`
  helper that wraps them as bound methods of a fake client exposing a
  reflectable `_session`, since `_call_with_deadline` no longer accepts a
  bare, unreflectable callable at all.
- Replaced `test_broker_retry_call_bounded_by_remaining_deadline`'s
  `time.sleep()`-based fake with a `_TransportTimeoutSession` stub that
  mirrors real `requests`/`urllib3` behavior: `.request(timeout=...)`
  raises a timeout error synchronously, from inside itself, once the
  simulated remote would hang past the given timeout — proving the abort
  is a real transport-level mechanism, not a thread/future race, and that
  no worker is left behind (because none is ever created).
- Added `test_call_with_deadline_propagates_transport_level_timeout_not_thread`
  (a would-be-forever hang, `hang_seconds=999`, is cut off at ~the given
  timeout and the exception propagates directly — no thread involved).
- Added `test_call_with_deadline_rejects_callable_without_reflectable_session`
  (a plain callable with no `_session` raises `UnboundedBrokerCallError`,
  not run unbounded, not raced via a thread).
- Added `test_no_thread_pool_fallback_in_module` (structural guard: no
  `import concurrent` and no `ThreadPoolExecutor(` construction anywhere in
  the module — Codex asked for removal, not a workaround alongside it).
- Kept `test_call_with_deadline_threads_real_timeout_into_alpaca_session`
  and `test_call_with_deadline_updates_timeout_per_attempt_idempotently`
  unchanged (already exercised the real mechanism, no thread involved).

## Tests

`tests/test_intraday_session_inputs.py`: 49 passed.

Full suite (this session, local worktree, Python 3.9): 18 failed, 3737
passed, 5 skipped. All 18 failures are pre-existing environment-only
issues unrelated to this change (stale local sibling checkouts missing
`renquant_common.decision_ledger`, a `renquant-pipeline` sibling using
`X | Y` `isinstance` syntax that requires Python ≥3.10, and
real-pinned-live-tree / real-DB tests needing artifacts not present in an
isolated worktree) — verified by stashing this diff and reproducing the
same failures on the unmodified branch. CI (`.github/workflows/ci.yml`)
uses fresh sibling checkouts off `main` and Python 3.10, so these do not
reproduce there; this matches the environment-only failures noted in the
round-3 progress update, now larger only because the local sibling
snapshots have drifted further behind `main` since r3 ran.
