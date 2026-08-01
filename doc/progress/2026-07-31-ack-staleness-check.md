# GOAL-1 — three suppressions have outlived their own stated clearing date, by 11 days

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-1, shadow-reliability gates

## Anchor correction first

The GOAL-1 anchor reads *"ack 台账 4 条过期 10 天"*. Measured
`[本次实测 2026-07-31]`: **3**, not 4 — and **11 days**, not 10. Correcting it here
because a goal anchor that drifts by one row and one day is how a lane's priority gets
argued from a number nobody re-derived.

## What the ledger is, and what was missing

`ops/renquant104/sentinel_acks.json` suppresses a sentinel's last-exit alarm per job. Every
row carries `acked_at` and `clears_when` — a **condition**, not a date, which is correct
under the containment protocol: *"temporary" is not an expiry; "until X is deployed" is.*

**Nothing checked the conditions.** An ack whose clearing date has passed keeps suppressing
its alarm, indefinitely and silently. That is this programme's recurring *guard that passes
forever*, applied to the **suppression ledger itself** — the one place where passing
forever means an alarm never fires at all.

## Measured, 10 acks

**3 name a clearing date already in the past — all 2026-07-20, 11 days ago:**

| job | `clears_when` |
|---|---|
| `com.renquant.daily104` | next NYSE session's 13:55 wrapper run (**2026-07-20**) |
| `com.renquant.shadow-ab-daily` | next NYSE session 14:35 two-arm run (**2026-07-20**) |
| `com.renquant.weekly-retrain-patchtst` | next weekly cycle (review if still failing **2026-07-20+**) |

**7 name an event with no date** — "next VIX-anomaly trigger", "a staged model passes the
WF gate", "task #75". One says so outright: *"open-ended; gate is correct"*.

## What is claimed — and the two opposite errors this avoids

**Claimed:** a **date** written into a clearing condition has passed. A syntactic fact
about the ledger, checkable without touching a job.

**Not claimed — error one, over-reading:** it does *not* mean the condition was met, the
fault is fixed, or the ack should be removed. *"review if still failing 2026-07-20+"* makes
the date a **trigger**, not a verdict. Reading OVERDUE as "clear it" inverts the sentence.

**Not claimed — error two, manufacturing an alarm:** the 7 event-only rows are claimed
**nothing** about. An open-ended condition is a deliberate choice here, and counting it as
stale would produce an alarm out of a design decision. Age alone never promotes an event
row: a test drives a 2020-dated event-only ack and asserts it is still not overdue.

**It never edits the ledger.** Auto-clearing a suppression mutates a reviewed surface and
would need the containment protocol; this only makes the state visible.

## Tests

16. Both directions are covered because both are live risks: a past date is overdue and
carries the right age; a **future** date is not; **today** is not yet past (an off-by-one
would alarm a day early on every dated ack); the **earliest** past date drives the age; an
event-only row is never overdue however old. Ledger integrity: an ack with **no**
`clears_when` is **malformed**, not an event row — a suppression that can never be shown to
have outlived anything is the worst row possible; a non-object entry is malformed, not
skipped; an unparseable `acked_at` does not crash; a **missing** ledger exits **2**,
because "no ledger" must never read as "no stale suppressions". Plus anti-vacuity, the
scope note asserted present, and the **real** ledger asserted to reproduce the counts above
so the document cannot drift from the file.

Suite: **5047 passed, 2 skipped** — run before the push.

## Next

The three overdue rows need a **review**, which is what their own conditions ask for — not
an automatic clear. That review is a separate action and is not taken here.
