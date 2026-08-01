# GOAL-1 — the ack auditor was merged, works, fires 11 findings, and nothing invoked it

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-1 (shadow reliability gates)

## What I did NOT do

I started to write an ack-ledger expiry auditor. **It already exists** —
`ops/renquant104/ack_ledger_audit.py`, merged as `b879f4a0`. The write was refused because
I had not read the file, and reading it is what surfaced that. This is the second time
this session that a rule on the register — *search for the mechanism before building one*
— stopped a re-implementation, and the first time the tooling caught it rather than me.

## The actual gap

`ack_ledger_audit.py` runs, and against the live ledger today it reports **11 findings**
`[本次实测 2026-08-01]`. It is invoked by **nothing** — `grep` over `ops/`, `src/`,
`scripts/` and `Makefile` returns only its own test file. The dark-detector sweep on
2026-07-31 that added five members to `ops_audit` missed it.

**Why running unconditionally matters.** `ack_expiry()` *is* consulted elsewhere — but only
from `rq104_degradation_sentinel.expired_or_unacked()`, which reaches it **only for jobs
whose last exit is nonzero**, inside a sentinel that **skips non-session days**. So an
expired ack on a currently-passing job is never examined, and on a weekend the ledger is
not read at all. An expiry nobody reads is not a reminder.

## The ledger, measured

| | |
|---|--:|
| acks in the ledger | 10 |
| **expired under the sentinel's own rule** | **9** |
| oldest expiry | **12 days** (`2026-07-20`) |
| live | 1 (`rq105-batch-scores-export`, 2026-08-14) |

Expired on `2026-07-20` by a date inside their own `clears_when`: `daily104`,
`shadow-ab-daily`, `weekly-retrain-patchtst`. Expired `2026-07-31` by `acked_at + 14d`:
six more — including `rq104-degradation-sentinel`'s own self-referential row.

The auditor also reports two **expiry cliffs** (3 acks on 07-20, 6 on 07-31): the reminder
arrives as a burst, which is the alarm-fatigue shape.

## A guard rejected my change, and it was right

`test_no_member_writes` **failed** the first attempt: the membership rule is read-only
detectors only, and `ack_ledger_audit.py` had one write — `open(a.json_out, "w")`,
reachable only through a `--json-out` flag that had **no caller anywhere in the repo**.

Documenting an exception would have weakened a guard that was doing its job. **The flag was
deleted instead**; `--json` prints the same payload to stdout, which a caller can redirect.
That is what made the tool schedulable, and it is a simplification rather than a
concession.

## And a test of mine that failed on its own documentation

My regression grepped the source for `"w"` — and matched the **comment explaining the
removal**. Rewritten to walk the AST for `open(..., 'w'/'a')`, `write_text`, `write_bytes`.
A check that fails on its own prose is not checking the object.

## Scope

`ops_audit` now runs **10** detectors instead of 9. Nothing was installed, scheduled or
disabled on the machine; no ack was edited, renewed or removed. **Dispositioning the 9
expired acks is an operator action** — the tool's job is to make the ledger's state
impossible to miss, not to change it.

## Tests

3 new (member present; no write path, checked on the AST; harness code 3 not declared a
finding), plus the existing contract table updated. Suite: **5188 passed, 2 skipped**, run
before the push.
