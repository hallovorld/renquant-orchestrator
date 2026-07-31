# Half the currently-failing scheduled surface cannot be dated from its own output

**Bottom line `[本次实测 2026-07-31]`.** Of the **14** `com.renquant.*` jobs whose
`launchctl` last exit is nonzero, **7 produce dated evidence and 7 do not**. And
**0 of 14** plists give their `StandardOutPath` a dated filename — the launchd stream
layer is undated across the **entire** failing surface.

| | |
|---|---:|
| failing jobs | **14** |
| attributable (wrapper writes a date-stamped log) | **7** |
| **not attributable** (append-only flat file only) | **7** |
| plists whose `StandardOutPath` carries a date | **0 / 14** |

## Why "not attributable" is the right word

`launchctl` retains a job's last exit **until its next run**. So the exit code alone
dates nothing — it cannot distinguish *"failed this morning"* from *"failed three weeks
ago and has not run since."* When the only other artefact is a flat append-only file, no
line in it can be attributed to a run either.

> That is not a theoretical concern in this repo. It produced the `rq105-shadow-serving`
> misdiagnosis earlier tonight — a 0-byte `.err` last written 07-02 read as *"has not
> run"*, when dated logs proved it ran on 07-06, 07-07 and 07-13 (orch#674). Here the
> same shape is measured across the whole failing surface instead of one job.

## Two corrections I made mid-measurement

1. **My first pass reported "14/14 have no dated log."** That was my *glob* failing —
   I matched on the launchd label (`rq105-shadow-serving`) while the file is named after
   the wrapper (`shadow_serving_2026-07-13.log`). I knew that file existed, which is the
   only reason I caught it. **A zero-row extraction is not a zero-count finding** — the
   second time that rule saved a false publication today.
2. **My second pass classified `run-surface-drift` as writing no log at all.** It writes
   to **stdout**, and the plist redirects. Classifying evidence by reading only the
   wrapper misses the plist layer entirely, so the measurement now reads **both**.

## What is deliberately NOT done

I did **not** add this as a new alarm to the run-surface drift scan. #675 already adds
**6** problems to that scan today; seven more in the same night is the alarm-fatigue
shape this repo has an ack-ledger *expiry cliff* finding about. The measurement is
recorded and testable; converting it into a gate is a separate, reviewable decision —
and if it becomes one, it should emit **one** line ("N of M failing jobs have no dated
evidence path"), not N.

Tests: 5, including a control that `attributable = yes` must trace to a concrete
mechanism and a check that the one unclassifiable wrapper is recorded as such rather
than counted as fine.
