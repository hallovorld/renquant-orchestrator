# 2026-08-05 — a test paged the operator; tests can no longer reach ntfy

## What happened

The operator forwarded an ntfy alert reading `σ-head _rawlabel CONSUME FAILED …`.
The body named its own source:

```
/private/var/folders/.../pytest-of-renhao/pytest-2550/
   test_a_later_corpus_edit_is_de0/RenQuant/data/alpha158_291_fundamental_dataset.parquet
   … Parquet file size is 5 bytes, smaller than the minimum file footer (8 bytes)
```

A pytest temp directory and a 5-byte stub panel. **This was a test run paging a
human.** `[VERIFIED — the alert body, 2026-08-05]`

Immediate cause: during the first (unconditional-republish) implementation of
orch#798, `RefreshSigmaHeadRawLabelTask` invoked the real base-data writer on
every run, including under pytest against a 5-byte fixture panel. It failed, the
task's isolation path ran, and `post_ntfy` sent for real. That specific behaviour
was already replaced by the repair-only design on the orch#798 branch — a
passthru-verified corpus no longer invokes any writer.

## But the real defect is not that task

**Nothing prevented a test from sending a real notification.** There was no
`tests/conftest.py` at all. Any test reaching any alert path could page the
operator, and several tests exercise alert paths deliberately.

An operator paged by a test learns to distrust the pager. That is how a real
alert gets ignored later. This is the same family as the 2026-07-13
decision-ledger incident, where a test fix wrote to the real production
database: **a test must not be able to reach a production surface by accident,
and the guard belongs at the surface, not in each test.**

## The guard

`tests/conftest.py`, autouse for every test, two layers:

1. `RENQUANT_NO_NOTIFY=1` — the sender's OWN documented switch
   (`renquant_common.notify.notifications_suppressed`). It was always there;
   nothing set it under pytest. This covers the ordinary path, including callers
   that captured `post_ntfy` by value at import time.
2. A transport backstop: `urllib.request.urlopen` raises `AssertionError` for any
   ntfy URL. If something bypasses layer 1, **the test fails and names itself**
   instead of a phone ringing.

The backstop is deliberately narrow — ntfy URLs only. A blanket network block
would make unrelated failures look like notification failures.

Four tests: suppression is on without opting in; the canonical sender returns
`False` and does not reach the network; a bypassed suppression check raises
loudly; non-ntfy URLs are untouched.

Full suite: 5553 passed, 2 skipped, 2 pre-existing failures unrelated to this
change (the drift detectors fixed on orch#804). No test tripped the backstop —
so nothing in the repo was relying on a real send.
