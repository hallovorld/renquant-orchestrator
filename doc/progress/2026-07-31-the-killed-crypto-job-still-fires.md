# A killed programme's job keeps firing, and every run fails in 0.1s

**Bottom line.** `com.renquant.crypto-session` is still loaded and scheduled. Its target
was deleted when G2 crypto was killed on 2026-07-18, so every firing since has failed
instantly with `Errno 2`.

**The numbers live in `doc/research/evidence/2026-07-31-crypto-session-dead-job/evidence.json`,
not in this prose.** Reviewed `[codex on #700]`: *"the asserted live state is not auditable
from this PR… while 'today' becomes stale immediately."* Correct, and it was already true
when he wrote it — the first draft of this document said **883 runs**; the capture below,
taken hours later, reads **900**. A run count is a
moving quantity, so it belongs in a timestamped record with the command that produced it.

| | captured `2026-08-01T06:40:16Z` |
|---|---|
| `runs` | **900** |
| `last exit code` | **2** |
| stderr | 168,300 bytes, **900 lines, 1 distinct** |
| target in dev checkout | **False** |
| target in run checkout | **False** |
| still in the reviewed manifest | **True** |

Every one of the 900 lines is byte-identical:

```
$HOME/git/github/RenQuant/.venv/bin/python: can't open file '$HOME/git/github/renquant-orchestrator/scripts/cr
```

The record carries the capture timestamp, the exact commands, the plist's own sha256, the
stderr file's sha256/mtime/size, both checkout HEADs and the manifest digest — so a later
operator can tell **the state they observe** from **the state this document narrates**
before touching a live job. Paths are redacted to `$HOME`.

## Why this is not just noise

Its permanently-nonzero last exit is one of **13** nonzero jobs on the
sentinel's surface, and one of the **8** carrying no ack at
all — both counts now in the record (`alarm_surface`) with the ack ledger's own digest, so
they age visibly instead of silently. So a killed programme is
consuming a slot in the daily alarm surface, forever, for a failure nobody intends to
fix. Alarms that can never clear are how a reader learns to skim the list.

## The mirror of a guard we already built

`ops/plist_install_preflight.py` (orch#667) refuses to **bootstrap** a plist whose target
is absent from the run checkout. Nothing refuses to keep **running** a job whose target
has since vanished. Same predicate, opposite end of the lifecycle — and the uninstall end
is the one with 900 failures behind it `[record: `launchctl.runs`, captured 2026-08-01T06:40:16Z]`.

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
