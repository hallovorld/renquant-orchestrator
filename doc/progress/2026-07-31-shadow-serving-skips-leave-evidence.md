# The shadow feed did not silently die — it never lived, and left no trace saying so

**Bottom line.** `com.renquant.rq105-shadow-serving` runs on schedule, takes a
deterministic early exit, and writes **nothing to disk**. GOAL-1 exists to stop a
shadow feed dying silently; this one has been *stillborn* silently, which the run
surface cannot distinguish from *not running at all*.

## What the anchors say, and what is actually true `[本次实测 2026-07-31]`

The anchor reads *"105 四作业静默 28 天，shadow-serving 退出 1"*. Measured:

| claim | measured |
|---|---|
| silent since 2026-07-02 | that is the **`launchd_shadow-serving.err/.out`** mtime — both **0 bytes**. Dated logs exist for **07-06, 07-07 and 07-13**, all written at 13:45. **The job ran.** |
| exit 1 | true, but `launchctl` retains the last exit **until the next run**, so the code alone dates nothing |
| newest evidence | `shadow_serving_2026-07-13.log` — **18 days** before today, on a Mon–Fri schedule |

Reading a 0-byte `.err` as "did not run" is the append-only attribution trap again,
in its mirror image: **the wrapper redirects into dated files, so the launchd streams
being empty is the normal case, not a symptom.**

## The actual chain

The wrapper has three early exits. Two returned `1` **without writing a dated log**;
the third wrote one.

```
data/rq105/feature_snapshot_*.json   ->  ZERO files exist
data/rq105/batch_scores_*.json       ->  present through 2026-07-29
```

The wrapper's own comment on the second guard says it: *"No producer for this file
exists yet (Stage-3 wiring, tracked separately) — skip cleanly rather than invoke a
binary whose required argument we cannot supply."*

> So guard 1 passes (scores exist), **guard 2 is taken on every single run**, and it
> is the branch that writes nothing. The job cannot succeed today by construction,
> and the run surface says only "exit 1", which is what a *broken* job says.

## What landed

1. **Every exit path leaves one timestamped line** in the dated log. `skip_log`
   stamps each line itself — a line without its own timestamp cannot be attributed
   to a run.
2. **A job that CANNOT succeed is not a job that FAILED.** The not-wired branch now
   exits **4**, not 1. The ack ledger can disposition the two separately, using the
   `acked_exit_codes` support added in #671 — the fix from two rounds ago is what
   makes this distinction actionable rather than cosmetic.

## Corrections I made to myself along the way

- I first read the 07-07 log's repeated `error: the following arguments are required:
  --feature-snapshot-json` as the root cause. **Wrong** — the wrapper *does* pass that
  flag (line 62), and the guard above it exists precisely to avoid the call. Those
  errors predate the 07-16 wrapper change.
- I assumed the run-checkout copy might differ from the repo copy. **Measured
  identical** — no vintage split here.
- One test compared `log.split()[1]`, which is `"SKIP"` on both branches, and asserted
  `'SKIP' != 'SKIP'`. My indexing error, not the wrapper's.

**Not done, needs authorization:** nothing here changes the deployed run checkout. The
job keeps exiting until Stage-3 wiring (#221) produces a feature snapshot.

Tests: 5. Suite: **4792 passed / 2 skipped**.
