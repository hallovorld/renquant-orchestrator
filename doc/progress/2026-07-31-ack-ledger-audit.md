# GOAL-1 — the ack ledger's clock is stamped with the wrong event, and it expires all at once

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-1 (issue #622)

## Bottom line

Two measured defects in `ops/renquant104/sentinel_acks.json`, both found by running the
sentinel's **own** expiry rule against the ledger's **own** git history
`[VERIFIED — python3 ops/renquant104/ack_ledger_audit.py --today 2026-07-31, at f59d4609]`:

1. **The whole ledger is expired.** 10/10 acks, under the sentinel's own
   `expiry <= today`. Four expired on 2026-07-20; the other six expire **today**.
2. **`acked_at` records when a row was *created*, not when it was last *reviewed*** —
   and `ack_expiry()` reads it as the latter. `com.renquant.rq104-degradation-sentinel`
   was rewritten on **2026-07-30** and still declares `acked_at: 2026-07-17`: a
   **13-day** stale stamp.

Nothing here changes a suppression. This lands a read-only audit that measures both.

## Why (2) matters in both directions

| direction | what it looks like | consequence |
|---|---|---|
| stamp **older** than the real edit | re-disposition rewrites `reason`, leaves `acked_at` | expiry fires **early** — noisy, safe. This is what the live ledger has. |
| stamp **newer** than the real edit | someone bumps `acked_at` without re-reviewing | expiry fires **late** — **silent**, and unobservable from the file alone |

Only the first is present today. The audit reports both, because a check that only
catches the safe direction is not a check on the dangerous one.

## The expiry cliff

Staggered expiry is what makes the reminder usable: one suppression resurfaces, is
judged, is lifted or renewed. All 10 acks were written on 2026-07-17, so they expire in
two clumps — **4 on 07-20 and 6 on 07-31**. A burst is the alarm-fatigue shape: the
ledger gets ignored wholesale, which is the exact failure the ledger exists to prevent.

## No twin implementation

Expiry is **not** recomputed. `ack_expiry` and `ACK_MAX_AGE_DAYS` are imported from
`rq104_degradation_sentinel`, and a test asserts this module defines neither. A copy
would agree on the day it was written and drift silently afterwards — the failure this
repo already keeps a registry for.

## A defect in the audit itself, found by its own test

The first version took the ledger from `--ledger` and the git history from wherever the
process happened to run — dating one repo's acks against another repo's commits, and
reporting the mismatch as *"unreadable"*. A checker validating the wrong object, in the
tool written to catch checkers validating the wrong object. The root is now resolved
**from the ledger**, and a ledger outside it is a **harness failure**, never a finding.

## Tests — 17

Controls, not just positives:

- a **clean** ledger produces **no** findings (without it, a tool that flags everything
  passes every positive test below);
- **staggered** acks are **not** a cliff (otherwise "cliff" degenerates to "more than
  one ack");
- expiry comes from the sentinel — asserted by source inspection, not by comment;
- the **boundary** matters: `expiry == today` is EXPIRED, `expiry == today + 1` is not;
- the live ledger's numbers are **pinned in a test**, so this document cannot rot.

## Not done here

Re-acking. Every one of the 10 needs a real disposition — fix the job, or re-ack with a
fresh stamp and a condition. That is a judgment per job, not a sweep, and doing it in the
same PR as the instrument that measures it would let the instrument be tuned to the
answer.
