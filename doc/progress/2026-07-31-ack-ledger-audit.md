# GOAL-1 — the ack ledger's clock is stamped with the wrong event, and it expires all at once

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-1 (issue #622)

## Bottom line

Two measured defects in `ops/renquant104/sentinel_acks.json`, both found by running the
sentinel's **own** expiry rule against the ledger's **own** git history
`[VERIFIED — python3 ops/renquant104/ack_ledger_audit.py --today 2026-07-31, at f59d4609]`:

1. **Nearly the whole ledger is expired.** 9/10 acks (see the correction at the end), under the sentinel's own
   `expiry <= today`. Four expired on 2026-07-20; the other six expire **today**.
2. **`acked_at` records when a row was *created*, not when it was last *reviewed*** —
   and `ack_expiry()` reads it as the latter. `com.renquant.rq104-degradation-sentinel`
   was rewritten on **2026-07-30** and still declares `acked_at: 2026-07-17`: a
   stale stamp of **13 days as measured on this branch** — the figure is history-dependent, see the second correction below.

Nothing here changes a suppression. This lands a read-only audit that measures both.

## Why (2) matters in both directions

| direction | what it looks like | consequence |
|---|---|---|
| stamp **older** than the real edit | re-disposition rewrites `reason`, leaves `acked_at` | expiry fires **early** — noisy, safe. This is what the live ledger has. |
| stamp **newer** than its introducing commit | timestamp **chronology corruption** — a future-dated stamp or a backdated commit | expiry fires **late**. **NOT a re-stamp detector** — see the correction below |

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

---

## Correction — 9/10, not 10/10, and the difference is the point

This doc was written when every ack in the ledger was expired. `a32f397c`
(*"the batch-export ack described a failure that is no longer the failure"*) then
**re-stamped** `com.renquant.rq105-batch-scores-export` on 2026-07-31, so it is live
until 2026-08-14 and the audit now reports **9 expired of 10**
`[VERIFIED — A.audit(2026-07-31) on this branch, this session]`.

The count moved because the **ledger** moved, not because the audit changed. Pinning
`10` would have pinned a ledger that no longer exists — and a re-stamp is precisely the
event this audit exists to make visible, so the test now **names the live ack** rather
than counting the expired ones. The next re-stamp shows up here as a changed name, not
as an off-by-one.

`[VERIFIED — this session]` 17 tests pass.

## Correction — the silent-direction claim is WITHDRAWN

An earlier version of this audit reported a negative lag as *"an ack re-stamped without a
re-review suppresses Nd longer than earned"*. Codex raised it as a BLOCKER on #654 and I
**verified it empirically before accepting** `[本次实测 2026-08-01]`:

| scenario | `acked_at` | `last_edited` | lag | findings |
|---|---|---|---:|---:|
| a genuine re-review | 2026-07-20 | 2026-07-20 | **0** | **0** |
| an unreviewed re-stamp | 2026-07-20 | 2026-07-20 | **0** | **0** |

> **Identical evidence.** Both human actions write today's `acked_at` in today's commit.
> The audit **cannot** distinguish them, and the claim named an event the mechanism
> cannot see — the guards-that-validate-the-wrong-object shape, committed *inside the
> audit built to catch that shape*.

What a negative lag **does** identify is a stamp dated **after** the commit that
introduced it: chronology corruption. Worth reporting, under its own name, as a
different event.

The finding is relabelled, and
`test_a_re_review_and_an_unreviewed_re_stamp_are_INDISTINGUISHABLE` pins the limit so the
claim cannot be re-added without failing a test. **The noisy stale-stamp measurement is
untouched and remains valid.**

## Second correction — and my first fix to this test missed it

CI went red again on the same test, at a different assertion:
`stamp_lag_days == 13` reported **14**.

`stamp_lag_days = last_edited - acked_at`, and `last_edited` comes from **git
history**. So it differs between this branch (13) and CI, which tests the merge with
main and sees a later ledger commit (14) — **same code, same ledger contents, different
answer.** Any literal there is a value that moves whenever anyone touches the ledger,
on a schedule nobody controls.

**I fixed one stale pin in this test and left another of the same kind two lines
below.** That is the sweep-the-file lesson arriving inside a single function.

The day count is no longer pinned. What the audit is *for* survives history: this job's
stamp is stale — edited well after its `acked_at` claims — ~~and it is **the only one**.
That is asserted as a property, plus a `>= 13` floor so a *fresher* stamp fails rather
than passing quietly~~ **— WITHDRAWN 2026-07-31, see ROUND 4 below.** `orch#641` rewrote
every row and the count went to **nine**, so "the only one" and the `>= 13` floor were
both pins on a moving subject, one level up from the day count this paragraph is about.

**I wrote that sentence in the paragraph explaining why not to pin things.** Codex caught
it, one section above my own correction — the review-surface shape, committed while
documenting a correction.

`[VERIFIED — this session]` 18 pass; the property held at 13, 14 and 20.

## 2026-08-01 — "expired" and "expired for longer than an ack may live"

The audit computed `days_to_expiry` and printed it, but emitted **no finding** for a
long-lapsed ack. Those are different facts:

- expired **yesterday** → the reminder just fired, working exactly as designed;
- expired **longer ago than `ACK_MAX_AGE_DAYS`** → a **full review cycle** has passed
  since it lapsed and nobody lifted or renewed it, so the alarm has been returning
  **unheeded** — the state this ledger exists to prevent.

**The threshold is derived, not chosen:** it is the ledger's own review cadence. A
literal here would be one more constant nobody could re-derive.

### The live ledger, measured 2026-08-01

| | |
|---|---:|
| acks | **10** |
| expired | **9** |
| expiring on 2026-07-20 | **3** |
| expiring on 2026-07-31 | **6** ← the cliff |
| still live (re-stamped 07-31) | 1 |

| audit date | long-expired findings |
|---|---:|
| **2026-08-01 (today)** | **0** |
| 2026-08-04 | **3** |
| 2026-08-15 | **9** |

So it is a tripwire that fires in **three days**, not one that fires now. Stated as a
**forecast from a measurement**, and pinned as a test rather than left as a claim.
`[VERIFIED — 本次实测 2026-08-01]`


---

## ROUND 4 2026-07-31 — orch#641 landed and took the stale-stamp count from 1 to 9

`orch#641` added `acked_exit_codes` to **every** row of the ledger. `last_edit_dates` is
value-based per key, so every row's current value now dates from 2026-07-31 while every
`acked_at` still says 2026-07-17 — and this audit reports **nine** stale stamps where it
reported one `[VERIFIED — ack_ledger_audit.audit(2026-07-31)]`.

**The audit is right about all nine.** What it cannot see is that the edit was a **schema
migration, not a re-diagnosis** — which is this PR's own established limit, now
demonstrated at ledger scale instead of on a single row.

**Restamping the nine would be the wrong repair.** Adding a field is not a re-review, so
a fresh `acked_at` would assert a review that never happened — exactly the unreviewed
re-stamp this PR's evidence says is indistinguishable from a real one. The stale lag is
the honest state and is left standing.

So the test stops pinning WHICH rows are stale — a set that moves whenever anyone touches
the ledger for any reason — and pins the properties instead: every stale row is reported
with its lag; the one row genuinely re-stamped on 07-31
(`rq105-batch-scores-export`, lag 0) is **not** reported, so the signal still carries
information about a row rather than merely "the file was touched"; and the stale and
fresh sets partition the ledger, so no row is silently dropped.
