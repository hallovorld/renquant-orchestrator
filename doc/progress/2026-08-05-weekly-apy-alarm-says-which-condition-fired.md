# The weekly-104 page names which condition fired

STATUS: complete. Text and control flow only — no threshold, no schedule, and no
live surface is touched. The `--json` keys are unchanged.

WHAT: `DecideWeeklyAlertTask` now gives the two conditions **distinct** titles,
drops the number the body used to restate, names where the data came from and how
to reproduce, and stops silently discarding a drawdown breach that coincides with
an APY breach.

WHY/DIR: operator report, 2026-08-05 — "this ntfy msg does not make any sense and
not helpful at all ... too long to understand, really meaningless".

Measured on the shipped strings, three separate defects:

| # | defect | evidence |
|---|---|---|
| 1 | both conditions shipped the **identical** title `RenQuant 104 WATCH` | src, lines 160 and 167 before this change |
| 2 | the APY body restated the APY that `summary` already carried | `... APY +37.5% ... (25 rows / APY=+37.5%)` |
| 3 | neither said what to do next | — |

The title is the only part of an ntfy push that is legible without opening it. Two
different problems under one indistinguishable subject is why the channel reads as
noise.

Before and after, same module, same real log, `--alert-threshold 0.99` to force the
breach:

```
BEFORE  RenQuant 104 WATCH: Live rolling 30d APY +37.5% < alert +99.0% (25 rows / APY=+37.5%)

AFTER   104 APY +37.5% below floor +99.0%: 30d rolling over 25 runs.
        Source .../logs/live_104/audit.jsonl.
        Reproduce: python -m renquant_orchestrator.weekly_apy_monitor --json
```

[VERIFIED — both run 2026-08-05 against `RenQuant/logs/live_104/audit.jsonl`, the
second with the working tree stashed to origin/main]

## The `elif` was dropping an alarm

`WeeklyApyContext` carries a **single** alert slot (`alert_title`/`alert_body`), so
`if apy … elif drawdown …` could not represent both. When APY breached, a
simultaneous drawdown breach was discarded with no record.

Measured over the 99 points in the live audit log: **APY-only 51, drawdown-only 0,
both 0**. The loss is latent — never yet observed — and it would have surfaced as a
page that *did not arrive*, which is the least detectable failure an alerting path
has. The APY alert now appends `; ALSO drawdown >X% for Nd`; exit codes and the
single-slot JSON contract are unchanged.

## What this deliberately does NOT do

**The +25% threshold is unchanged.** I previously told the operator it "guarantees
it fires every time" — that was asserted before measuring and it is wrong. Replayed
over the audit log, +25% breaches **51 of 98** evaluations (52%), and the job is
weekly. Changing a threshold on that basis would be tuning by anecdote; the reported
problem was legibility, and legibility is what this changes.

**Retry is not added here.** The operator also asked for retry ("failure should be
retried"). That is correct for the transient `ntfy send failed … read operation
timed out` which has already lost two alarms — it ships separately in
`renquant-common#43` (`notify.send` retries transients with backoff). It is not the
defect on this path: this alarm's verdict is deterministic.

**The RenQuant-side `scripts/weekly_apy_check.py::main()` still carries the old
strings.** It is a second, near-duplicate implementation reached only under
`RQ_WEEKLY_APY_RUNNER=legacy`; the default `multirepo` runner shells out to this
module, which is what the launchd job executes. Worth noting rather than silently
leaving inconsistent — a separate repo's PR, and a candidate for deletion.

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| the launchd job runs THIS module, not the RenQuant script | `RQ_WEEKLY_APY_RUNNER` defaults to `multirepo` → `python -m renquant_orchestrator.weekly_apy_monitor` | [VERIFIED — `scripts/weekly_apy_check.py` entry block; a marker inserted in the RenQuant script never printed] |
| both titles were identical | yes | [VERIFIED — read back from `git show origin/main:src/renquant_orchestrator/weekly_apy_monitor.py`] |
| threshold breach rate | 51/98 = 52% | [VERIFIED — replay over `logs/live_104/audit.jsonl`, 99 points] |
| both-breach coincidences observed | 0 | [VERIFIED — same replay] |
| module tests | 11 passed (3 new/rewritten) | [VERIFIED — `pytest -q tests/test_weekly_apy_monitor.py`] |
| the new tests are load-bearing | all 3 fail against the pre-change module | [VERIFIED — `git stash push src/…`, re-run: 3 failed] |
