# Log mtimes cannot tell you when a job last RAN

STATUS: **refuted measurement, recorded so it is not rebuilt.** No code ships. The
change this documents was opened as orch#838 and closed by its author the same day.

## The claim, and why it was attractive

`launchctl` retains a job's last exit code until its **next** run, so a job that stops
firing keeps re-alarming with an old code forever. The alarm row reads identically on
day 1 and day 101. Operator report 2026-08-05: *"the issue has been repeatedly showing
up for months."* The missing number is obviously the age of the failure.

I measured it from the mtimes of the `StandardOutPath` / `StandardErrorPath` files
named in each job's plist, and labelled anything ≥ 7 days a FOSSIL. It produced a
clean, quotable result: five of the fourteen undispositioned failing jobs at 101, 80,
65, 34 and 33 days, each last write landing exactly on that job's own scheduled slot.

**Every one of those five figures is wrong.**

## The refutation

The wrapper scripts redirect their own output:

- `RenQuant/scripts/retrain_panel.sh:39` — `exec >> "$LOG" 2>&1`
- `RenQuant/scripts/weekly_wf_promote.sh:184` — the same

Everything after that line goes to a dated log in the job's own directory. The launchd
stream files therefore stay empty and stale **by design**, and their mtime is fixed at
the moment launchd first opened them — which is why each "last write" lined up so
neatly with a scheduled slot. That coincidence read as corroboration and was the
opposite: it was the signature of a file that is written once and never again.

| job | claimed | truth, from the dated log the job writes |
|---|---|---|
| retrain-panel104 | FOSSIL 101d (2026-04-26) | **2026-08-02 — 3d** |
| weekly-wf-promote | FOSSIL 80d (2026-05-17) | **2026-08-04 — 1d** |
| monthly-calibrator-refresh | FOSSIL 65d (2026-06-01) | **2026-08-01 — 4d** |

[VERIFIED — newest `\d{4}-\d{2}-\d{2}\.log` per directory, read with `python`/`stat`;
the first pass used the shell's `ls --sort newest`, which is aliased to `eza` on this
host and returned the entries out of order]

All three run normally. The change would have broadcast a confident, precise, wrong
diagnosis into the alarm channel — the exact failure it was written to fix.

## The obvious repair is also unsound

Widening to "newest file anywhere in the job's log directory" makes all 13 read 0–4
days and no fossils at all. But `logs/rq104/` holds 63 files shared by **five** jobs
(model-freshness, risk-budget, scorer-identity, silent-refusal, run-surface-drift) and
`logs/rq105/` is shared by two. **One job writing makes the directory look fresh for
every job that shares it** — a fail-open version of the same wrong-object error.

Neither rule works, in opposite directions:

| rule | failure |
|---|---|
| launchd stream mtime | false FOSSIL on any self-redirecting script |
| log-directory mtime | false FRESH on any shared log directory |

Swapping one unsound rule for another while keeping the conclusion is not a
correction. The conclusion had to go.

## What the measurement would actually require

A **per-job liveness receipt**. `ops/renquant104/sentinel_receipt.py::write_receipt`
already exists and `ops/run_surface_drift_check.py` already consumes one. Extending it
to every scheduled job yields a per-job "last ran at" that no sibling job can forge and
no output convention can hide. That is a design with a real cost, and it should be
argued on its own merits rather than smuggled in as a heuristic.

## What survives

**16 `com.renquant.*` jobs hold a nonzero last exit; 5 acks exist and only 2 cover a
currently-failing job — 14 are undispositioned.**
[VERIFIED — `launchctl list` ∩ `ops/renquant104/sentinel_acks.json` on origin/main,
2026-08-05]

That number does not depend on any mtime and is still the thing worth acting on. The
dispositioning is per-job triage, not a detector.

## Why this file exists

The refuted version was seductive: it fit the operator's report, produced round
numbers, and had eight passing tests — all of which tested the arithmetic on synthetic
plists and none of which could see that the subject was the wrong file. A green suite
over a wrong object is the recurring shape here, and the cheapest defence is that the
next person to reach for log mtimes as a liveness proxy finds this first.
