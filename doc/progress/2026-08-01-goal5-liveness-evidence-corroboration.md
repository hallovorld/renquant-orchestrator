# GOAL-5 P0 — the liveness scanner's alarm bucket was 100% noise, in two separable ways

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-5 (daily-run reliability)

## Bottom line

`ops/launchd_liveness_scan.py` reported **21 of 43** manifested jobs as
`NO_EVIDENCE_STALE`. Checked against each job's own log directory `[本次实测 2026-08-01]`:
**21 of 21** had newer material there. The entire alarm bucket was noise — which is worse
than useless, because it trains its reader to skip the one entry that matters.

After the two fixes below:

| | before | after |
|---|--:|--:|
| `EVIDENCE_FRESH` | 17 | **19** |
| `NO_EVIDENCE_STALE` | **21** | **1** |
| `STALE_AMBIGUOUS_SHARED_LOG_DIR` | — | 9 |
| `STALE_BUT_SIBLING_FILE_IS_NEWER` | — | 9 |

**One job now needs attention: `com.renquant.daily103`, whose newest log of any name is
94 days old.**

## Defect 1 — the verdict read a file most of these jobs never write

Liveness is judged from the plist's `StandardOutPath`. Most of these jobs write a **dated**
log beside it (`logs/<job>/2026-07-31.log`), leaving the declared file empty and frozen
forever. `com.renquant.weekly-wf-promote` was reported stale since **2026-05-17** while its
directory holds **60 dated logs, newest 2026-07-31**.

**The corroboration deliberately does not promote anything to `EVIDENCE_FRESH`.** The
declared surface still shows nothing; all that is established is that *something* wrote in
that directory. And where a directory serves several manifested jobs, nothing there can be
attributed at all — `rq104-risk-budget` and `rq104-scorer-identity` both "corroborate"
against `silent_refusal_2026-08-01.log`, which belongs to neither. Those 9 report
`STALE_AMBIGUOUS_SHARED_LOG_DIR`, whose fix is to declare the `evidence_glob` the tool
already supports.

## Defect 2 — `Day` was never implemented, so every monthly job was judged as daily

`expected_firings` honoured `Weekday` and **silently ignored `Day`**. A plist reading
`{Day: 1, Hour: 3}` — fire on the 1st — was counted as firing every day:

```
monthly-calibrator-refresh   reported "60 scheduled firings have elapsed"
                             over an interval containing 2 real firings
```

So every monthly job went stale two days after each successful run. Both monthly jobs move
to `EVIDENCE_FRESH` once `Day` is honoured — they were never stale.

**The default is now inverted.** An unrecognised `StartCalendarInterval` key raises rather
than being skipped. Enumerating the keys you know and ignoring the rest is exactly the
shape that produced this — `Month` was missing too — and an ignored constraint inflates
the count, while an inflated count reads as a dead job.

## A fail-open I introduced and caught before the PR

The first corroboration moved **every** job with any newer sibling out of the stale bucket
— which rescued `daily103`, whose newest file is **94 days old**. A corpse newer than the
headstone is not liveness. The sibling must itself be within tolerance, measured with the
job's own cadence, and a test pins exactly that case.

## Scope

Read-only; no job was installed, modified, disabled or unloaded; the manifest is
untouched. This changes what the scanner *reports*, not what runs.

## Not claimed

That the 9 ambiguous jobs are running — they are **unattributable**, which is a third
answer, and the remedy is an `evidence_glob`, not a verdict. That `daily103` is broken
rather than deliberately retired; it is 94 days dark and that is a question for the
operator, not a conclusion here.

## Tests

13, including the size of defect 2 pinned as a number (the same interval yields 1 firing
monthly and 60 daily) and the fail-open case above. Suite: **5164 passed, 2 skipped**, run
before the push.
