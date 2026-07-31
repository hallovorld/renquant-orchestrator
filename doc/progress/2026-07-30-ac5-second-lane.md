# A one-lane silent-refusal sentinel is a one-incident sentinel

**Date:** 2026-07-30 · GOAL-5 AC5 · orchestrator

**Bottom line:** the AC5 sentinel watched **exactly one** job
`[VERIFIED — WATCHED tuple, origin/main]`. This adds a second, measured lane, and —
more importantly — records that the lane was **configured but BLIND** on first
attempt, which every regex test I wrote passed anyway.

## 1. Scoping, and the sweep I threw away

A first sweep matched any log containing `refus|declin|skipping|no-op` and returned
`daily_104` **24/39** and `intraday_104` **21/22** `[VERIFIED — grep, this session]`.
Those are ordinary no-trade sessions. **Building a lane on that would alarm every
day**, which is the fastest way to make a sentinel ignored. Discarded.

The lane that qualifies is one whose *entire purpose* is to produce an artifact, and
which can decline while exiting normally. Both patterns were read off the **real
dated logs** before being written into the module:

| | verbatim source |
|---|---|
| refusal | `batch_scores_export_2026-07-30.log` — *"…refusing to export"* |
| action | `batch_scores_export_2026-07-29.log` — *"exported 85/85 frozen blend scores (coverage 100.0%)"* |

**Not added on the strength of an incident.** The refusal streak is **1** — 07-30
refused, 07-29 exported 85/85 at 100% coverage `[VERIFIED — the dated logs]` — and
this module's own doctrine is that a single refusal is a legitimate gate working.
The lane is for **coverage**: today nothing would notice if that one became twenty.

## 2. The lane was blind, and my tests said it was fine

`_dated_logs` did `dt.date.fromisoformat(p.stem)`, so it required the **whole** stem
to be a date. rq105 writes `batch_scores_export_2026-07-30.log`. Every such file was
skipped: the lane discovered **0** logs `[VERIFIED — running the finder directly]`.

My suite passed because it tested **only the regexes**. A configured-but-blind lane
is **worse than an absent one** — it reads as coverage on the WATCHED list.

Fixed with `log_stem_prefix`, which is required for **two** reasons, not one:

1. **Discovery** — without it the files are invisible.
2. **Attribution** — `logs/rq105/` holds **six** jobs' dated logs. A finder that
   stripped *any* prefix would read a sibling's refusals as this lane's.

After the fix the lane finds **3** dated logs, newest **2026-07-30**
`[VERIFIED — same probe]`.

## 3. A lane that cannot be watched, recorded rather than omitted

`weekly-wf-promote` has a matching refusal line (*"refusing to spend sim compute on
non-comparable WF evidence"*) but its **dated** log surface last wrote **2026-05-24**
`[VERIFIED — ls logs/weekly_wf_promote/]`; it now writes only `stdout.log`/`stderr.log`,
which this sentinel deliberately ignores because an append-only stream cannot be
attributed to a run. Recorded in `UNWATCHABLE_LANES` with the reason — an unwatched
lane nobody wrote down is indistinguishable from one considered and cleared.

## 4. Suite

`tests/test_ac5_second_lane.py` — 11 tests, including the **four controls that would
have caught the blind lane**: every lane must discover at least one real log on this
machine; the prefix must separate jobs sharing a directory; a non-date stem after
stripping is skipped; and an empty prefix must behave exactly as before. Plus a
scoping control that ordinary `no trade` prose is **not** matched by any lane.

With the existing sentinel suite: **32 passed** `[VERIFIED — pytest, this session]`.

## CI fix — the discovery control measured this machine, and my first fix was a tautology

`test_every_lane_actually_DISCOVERS_logs_on_this_machine` reads the real log tree. On a
runner no watched directory exists, so every lane finds nothing and each is reported
"blind" — a red build whose real cause is that there was nothing to discover. Same
shape as #634, #637 and #635.

Split, so the property survives where the logs do not:

* the machine-local control is marked `skipif` on the watched directories existing,
  with a reason naming what covers CI instead. It still earns its place: it catches a
  lane pointed at a directory that is empty or gone **here**.
* `test_every_lane_can_discover_the_log_it_is_supposed_to` runs **everywhere** and
  checks the more likely failure — a malformed `log_stem_prefix`. A prefix typo is
  invisible to the machine-local test on a box where logs still exist under the old
  name.

**My first version of that hermetic test could not fail, and I only found out because
I tried to break it.** It built the fixture filename *from* `lane.log_stem_prefix`, so
corrupting the prefix produced a correspondingly corrupted file and the finder matched
it anyway — a control generated from the value under test, which is precisely the
defect this suite exists to catch, written into the suite. Replaced with
`EXPECTED_LOG_NAMES`, a literal per lane read off the real tree, plus an assertion that
every watched lane has one so a new lane cannot be added without pinning it.

`[VERIFIED — this session]` 15 passed locally; with `RQ_ROOT` pointing nowhere (the CI
case) **14 passed, 1 skipped, 0 failed**. Load-bearing confirmed by corrupting the
prefix two ways — a typo and an empty string — each of which now **fails** the hermetic
control and passes again on restore.
