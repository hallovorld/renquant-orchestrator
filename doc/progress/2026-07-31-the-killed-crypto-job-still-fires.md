# A killed programme's job has fired 883 times, and each one fails in 0.1s

**Bottom line.** `com.renquant.crypto-session` is still loaded and scheduled. Its target
was deleted when G2 crypto was killed on 2026-07-18, so every firing since has failed
instantly with `Errno 2`. **883 identical lines**, 161 KB, most recent **today**
`[VERIFIED — the job's StandardErrorPath, 2026-07-31 19:13]`:

```
/…/.venv/bin/python: can't open file
  '/…/renquant-orchestrator/scripts/crypto_session_runner.py': [Errno 2]
```

`[VERIFIED — launchctl print gui/<uid>/com.renquant.crypto-session]`: `runs = 883`,
`last exit code = 2`. The script is absent from **both** checkouts — `main` and the run
checkout — and the job is still in the reviewed manifest pointing at it.

## Why this is not just noise

Its permanently-nonzero last exit is one of the **13 jobs currently alarming** on the
rq104 sentinel, and one of the **8 that carry no ack at all**. So a killed programme is
consuming a slot in the daily alarm surface, forever, for a failure nobody intends to
fix. Alarms that can never clear are how a reader learns to skim the list.

## The mirror of a guard we already built

`ops/plist_install_preflight.py` (orch#667) refuses to **bootstrap** a plist whose target
is absent from the run checkout. Nothing refuses to keep **running** a job whose target
has since vanished. Same predicate, opposite end of the lifecycle — and the uninstall end
is the one with 883 failures behind it.

## What this PR deliberately does NOT do

**It does not remove the manifest entry.** That was the obvious change and it is wrong on
its own, measured rather than assumed:

| where | effect of removing the entry alone |
|---|---|
| this machine (plist still installed) | `check_launchd_surface` reports `unmanifested com.renquant job on disk`, and **2 tests fail** — `test_no_unmanifested_job_runs_on_disk`, `test_NO_residual_problem_of_any_other_kind` |
| CI (no `~/Library/LaunchAgents`) | **no unmanifested row at all** — every job reads `missing from disk`, so the removal is invisible there |

So removing it first ships a change that is **red on the operator's machine until an
operator command runs**, and green in CI — the worst combination, since CI would approve
it and the local suite would go red with no reviewer watching.

## The correct order, one operator action then one line

1. **Operator:** `launchctl bootout gui/$(id -u)/com.renquant.crypto-session` and remove
   `~/Library/LaunchAgents/com.renquant.crypto-session.plist`. This is a live run-surface
   mutation, so it is not mine to make — CONTAINMENT PROTOCOL, and the ask-first rule for
   jobs.
2. **Then:** a one-line PR removing the entry from `ops/launchd_manifest.json`. At that
   point the manifest and the disk agree and nothing goes red.

Doing it in that order means the drift scan never has to carry a finding that is really
an instruction.

## A defect in my own verification, recorded because it is the seventh today

My first "CI simulation" set `D.LAUNCH_AGENTS` on the module after import and called
`check_launchd_surface()`. **The default argument was bound at `def` time**, so the
override did nothing and the scan read this machine's real directory — I was measuring
the operator's disk while writing the section about not doing that. The numbers above
come from passing `agents_dir=` explicitly.

That is the same shape six other findings this week are about, committed in the act of
checking. A late-bound default is not a seam; passing the parameter is.
