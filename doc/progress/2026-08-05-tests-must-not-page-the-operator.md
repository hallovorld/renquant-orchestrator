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

## Review round 2 (codex on orch#806)

The guard was installed only in the autouse fixture, which **does not run while
pytest COLLECTS** — it imports every test module first, and a module-level call
into an alert path would fire before any fixture exists. Nothing about the
mechanism that paged the operator required the send to be inside a test BODY, so
that window was real.

Both layers now install at `conftest.py` IMPORT time, which happens before the
modules it collects. The autouse fixture stays, so a test that mutates either one
gets it back afterwards.

`tests/test_import_time_notification_guard.py` closes the window with a test
rather than a comment: it calls `notify.send(...)` at MODULE level and asserts,
in the test bodies, that suppression was already on during collection and that
the call returned `False` (a `True` would mean a real POST). A third test proves
the import-time `urlopen` swap is the guarded one, not merely that the env var
happened to be set.

## Other production surfaces a test could still reach (named, NOT fixed here)

Codex was asked to enumerate; recording so the next pass has a list:
the broker API, the real runs/decision-ledger SQLite databases, and live state
files under the umbrella. The 2026-07-13 decision-ledger incident was exactly the
DB case. Each deserves the same surface-level guard; none is in scope for this PR.

7 guard tests · 5555 passed, 2 skipped.

## Review round 3 (codex on orch#806) — two escapes, one closed, one recorded

Codex confirmed the collection-time fix works, then found two ways a test can
still page the operator, both reproduced from that head:

1. **A pytest plugin loaded with `-p` runs before `tests/conftest.py`**
   (`plugin_send True`, attempted `https://ntfy.sh/renquant-plugin-probe`).
   **NOT CLOSED.** I first added a ROOT `conftest.py` and claimed this fixed it.
   Codex re-ran the repro against that head and it still printed
   `PLUGIN_IMPORT env None` before collection: a `-p` plugin is imported before
   ANY conftest, root included. **Nothing committed to this repo can run before
   a plugin the invoker names on the command line.** The root conftest stays —
   it is the earliest hook a repository *can* install, and it delegates to the
   idempotent `install_notification_guard()` rather than carrying a second copy
   — but the claim it was added to support was wrong and is withdrawn.

2. **Subprocesses.** Partially closed, and the first version of this note
   overclaimed it. The guard sets `RENQUANT_NO_NOTIFY` in `os.environ`, so a
   child inherits suppression **for senders that honour it** — anything going
   through `renquant_common.notify.send`; a test asserts a real subprocess
   reports `suppressed True` / `sent False`. A child does **NOT** inherit the
   transport backstop (it is a separate interpreter), so a child that calls
   `urllib.request.urlopen` at an ntfy URL **directly**, or that scrubs the
   variable, can still page. Codex reproduced the direct-transport case
   (`env 1`, `suppressed True`, `urlopen urlopen`). **NOT CLOSED**, and not
   closeable from inside the parent process.

**The claim is scoped, in the PR title and in the root conftest's docstring, to
what is actually true: from conftest import onward, tests do not page the
operator through `notify.send`.** Every test module, fixture and subprocess is covered; a `-p`
plugin's own import time is not. The earlier scoping ("any path pytest controls
in-process") was still an overclaim — a `-p` plugin IS pytest-controlled
in-process code — and codex was right to reject it.

A test now fails if either the root conftest or this document stops naming the
`-p` residual. It does not close the gap; it makes the gap un-forgettable.

### Residual, recorded not fixed

- a pytest plugin loaded with `-p`, at its own import time (reproduced by codex);
- a subprocess that scrubs `RENQUANT_NO_NOTIFY`, or that calls the ntfy
  transport DIRECTLY rather than through `notify.send` (a child does not inherit
  the in-process urlopen backstop);
- other production surfaces a test can still reach by accident: the broker API,
  the real runs/decision-ledger SQLite databases, live state files under the
  umbrella. The 2026-07-13 decision-ledger incident was the DB case; each
  deserves the same surface-level treatment and none is in scope here.

10 guard tests.

## Review round 5 — a stray probe file, for the SECOND time

`test_subprocess_probe_XXXX.py` (a reviewer's ad-hoc diagnostic, left at the repo
root) was swept into this PR by `git add -A`. Its name starts with `test_`, so
pytest would have collected a file with no assertion and no contract.

This is the second stray file `git add -A` has pulled into a PR tonight — the
first was a 3,064-line `persistence_backup_check.py` in renquant-pipeline#268.
Both were caught in review, neither by me. **The rule I am adopting: stage
explicitly (`git add <path> …`), never `-A`, in any repo I did not personally
leave clean.**
