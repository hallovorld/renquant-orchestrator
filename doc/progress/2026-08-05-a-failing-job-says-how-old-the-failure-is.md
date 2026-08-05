# A failing job's alarm says how old the failure is

STATUS: complete. Read-only measurement added to an existing alarm line. No
schedule, no job, no live surface is touched, and nothing is silenced.

WHAT: every row in the sentinel's `launchd job(s) with nonzero last exit` alarm now
carries the age of the evidence, and a failure whose last output is ≥ 7 days old is
labelled **FOSSIL** with the date and a redirection: check whether the job still
fires before debugging the check.

WHY/DIR: operator report, 2026-08-05 — *"the issue has been repeatedly showing up for
months! fix fundamentally asap!"*

`launchctl` retains a job's last exit code until its **next** run. A job that stops
firing therefore keeps re-alarming with a code from the run that last happened —
every day, indefinitely — and the row read **identically** whether the failure was
from last night or from April. There was no number in the alarm that could tell the
reader the *schedule* died rather than the check. That is the reported experience,
exactly: a recurring page about a condition whose age was never stated.

## Measured on the live fleet, 2026-08-05

16 `com.renquant.*` jobs hold a nonzero last exit; 5 acks exist and only 2 of them
cover a currently-failing job, so **14 are undispositioned**
[VERIFIED — `launchctl list` ∩ `git show origin/main:ops/renquant104/sentinel_acks.json`].

Running the changed checker against the real fleet splits those 14 cleanly:

| job | evidence age | last wrote |
|---|---|---|
| retrain-panel104 | **101d** | 2026-04-26 |
| weekly-wf-promote | **80d** | 2026-05-17 |
| monthly-calibrator-refresh | **65d** | 2026-06-01 |
| rq105-shadow-serving | **34d** | 2026-07-02 |
| rq104-scorer-identity | **33d** | 2026-07-03 |
| the other 9 | 0–4d | current |

[VERIFIED — `check_launchd_exits(dt.date(2026,8,5))` called directly so no ntfy was
sent; ages come from the `StandardOutPath`/`StandardErrorPath` mtimes named in each
job's own plist]

**Each of those five last writes lands exactly on that job's own scheduled slot.**
`retrain-panel104` is weekly Sunday 10:00 and last wrote Sunday 2026-04-26 10:00;
`weekly-wf-promote` Sunday 2026-05-17 04:00; `monthly-calibrator-refresh` is monthly
and last wrote the 1st, 2026-06-01 03:00. They fired on schedule, then wrote nothing
on any subsequent slot.

So a third of the standing alarm volume is **fossils**: nine of the fourteen are real
current failures worth triaging, and five are echoes of runs up to 101 days old. Before
this change those two categories were indistinguishable in the page, which is the
mechanism by which a channel becomes noise.

## What this does NOT claim

The age is *"no output on either stream for N days"*, which is what the mtimes
support. It is **not** a claim that the job did not run — a run producing no output
would look the same. That distinction is why the row says "check whether the job
still FIRES" rather than asserting it doesn't. `launchctl print`'s `runs` counter was
examined and deliberately **not** used: it resets on reload, so on this fleet it
reads `2` for a job with fresh logs from this morning and `2` for one silent since
April. It cannot carry the claim.

An age that cannot be established is its own third answer — `evidence age UNKNOWN` —
never folded into "recent". An unreadable plist is the direction that loses evidence,
so it fails toward saying so.

## Nothing is suppressed

Every job that alarmed before still alarms, at the same volume, on the same schedule.
This adds a number to a line. Acking or fixing the five fossils is the follow-up work
the number now makes possible, and it is deliberately not bundled here — a change
that both measures and silences cannot be reviewed for either.

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| failing jobs / acks / undispositioned | 16 / 5 (2 covering) / **14** | [VERIFIED — `launchctl list` + the ledger on origin/main] |
| fossils among them | **5**, at 101/80/65/34/33 days | [VERIFIED — live run of the changed checker] |
| the five last-writes match their own schedules | yes | [VERIFIED — `plutil -p` StartCalendarInterval vs log mtime] |
| new tests | 8 passed, all on tmp_path plists | [VERIFIED — `pytest -q tests/test_failure_evidence_age.py`] |
| neighbouring sentinel suites | 121 passed | [VERIFIED — degradation + ack-exit-codes + ack-expiry + ack-names + receipt] |

NEXT: disposition the five fossils (each needs a fix or a reviewed ack naming the
exit code and an expiry) and triage the nine current failures. `agent-pr-loop`'s is
already in review as orch#830 — its `merge audit failed` is the unsatisfiable gate.
