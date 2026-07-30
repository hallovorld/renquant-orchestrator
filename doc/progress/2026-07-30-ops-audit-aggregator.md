# One scheduled surface for detectors that were merged and never run

**Date:** 2026-07-30 · GOAL-5, issue #649 · orchestrator

**Bottom line:** `ops/` carried **24** runnable tools and **7** were referenced by a
launchd job `[VERIFIED — tree + manifest parse, origin/main]`. The 17 unscheduled
included GOAL-5's **AC5** sentinel, which had **never run**: absent from the
manifest, absent from `launchctl list`, and with **no `*refusal*` log anywhere**.
The ledger read *"AC5 = #619 merged"* — true about the merge, silent about the
deployment. I added a second watched lane to that sentinel earlier the same day.

## 1. What running them once immediately surfaced

`ops/ops_audit.py`, first run `[VERIFIED — this session]`: **6 detectors, 5 with
findings**, aggregate exit **1**.

| detector | first line |
|---|---|
| silent-refusal | `weekly-retrain-patchtst` has not acted on **4** non-acting runs |
| blind-notifiers | 15 ntfy POSTs, delivery unobservable in 15 |
| **undelivered-alerts** | **`[PERMANENT]` `'rq104 blend 假想前10 — 2026-07-28'` — `'latin-1' codec can't encode characters in position 12-14`** |
| import-resolution | `renquant_backtesting.BacktestPipeline: unresolvable` |
| launchd-liveness | 41 manifested jobs scanned |
| umbrella-script-shadow | OK — 44 pairs, 26 diverged |

The third is worth stating plainly: **the blend readout's alarm title contains
Chinese characters, HTTP header values are latin-1, so the whole notification was
discarded — and it is `PERMANENT` because the title is hardcoded.** The blend ledger
has never been able to reach the operator. That is the same class as the 🚨 title
bug, in a lane the operator asked about by name today.

## 2. One job, not nine

Nine launchd entries are nine machine landings and nine plists to keep in step with
the manifest, on a fleet where a single plist already drifted undetected (#639). One
aggregator: **one entry, one plist, one authorisation** — and a detector added later
joins by being listed in `MEMBERS`, a reviewed code change rather than a machine
landing.

## 3. Membership rule, enforced not promised

A member must be **read-only** and **self-terminating**.
`test_no_member_writes` greps every member for `open(...,'w'/'a')`, `write_text`,
`json.dump`, `mkdir`, `shutil`, `os.remove`, `os.rename` — currently **zero hits
across all six** `[VERIFIED — sweep, 2026-07-30]`. A tool that mutates state does not
belong here however useful its output.

## 4. Exit codes aggregated, never collapsed

- a member's **nonzero exit without a traceback** is a **finding** — its delivered
  signal, not a fault;
- a member with a **traceback on stderr** is a **crash**;
- **a harness problem OUTRANKS a finding.** A detector that could not run is not a
  detector that found nothing, so one crash is not masked by five clean members.

That distinction is #622's, relocated: an uncaught exception also exits 1, and
collapsing the two is how a dead detector reads as a working one.

## 5. Suite — 9 tests

Clean / finding / crash / timeout / missing each map to the right status; a harness
problem outranks a finding; **every member must exist in this checkout** (a renamed
detector would otherwise report `MISSING` forever while the audit looked busy); no
member writes; and the manifest carries the job.

## 6. Not done

The plist is **not installed** — machine landing, separate authorisation, and
bootstrap must first verify the RUN checkout carries this wrapper. Until then the
liveness scan will report `UNJUDGEABLE_NO_PLIST` for this label, which is the
correct reading and the designed reminder.

## Round 1 — the aggregator reproduced the defect it was built to prevent

Codex: the exit aggregation did not preserve the finding-versus-harness distinction it
claims. `status = CRASH if traceback else OK if rc == 0 else FINDINGS` classifies
**every** nonzero exit lacking a Python traceback as a detector finding.

That is #622's crash-vs-alarm confusion, one layer up, inside the control built to stop
it — and it is not hypothetical for these six members `[VERIFIED — read each member's
`main()` on this branch, 2026-07-30]`:

* `blind_notifier_scan` exits **2** when its source directory is absent
  (`EXIT_OK, EXIT_FINDINGS, EXIT_UNUSABLE = 0, 1, 2`);
* `umbrella_script_shadow_check` exits **2** for `UNVERIFIABLE` — the state added on
  #634 precisely so "could not check" could not read as "checked and found nothing".
  The aggregator would have turned it back into a finding;
* `import_resolution_check` and `launchd_liveness_scan` both use **2** the same way;
* `argparse` exits **2** with no traceback, so a typo in a member's argv tail would
  have reported as a finding.

A scheduled control that says "a detector found something" when the detector had
nothing to look at is worse than no control: it manufactures alarms that cannot be
actioned and, once they are ignored, hides the real ones.

**Fix — an explicit per-member finding-exit contract.** `MEMBERS` gains a fourth field
listing the exit codes that mean *a verdict was reached*. Classification is now:
traceback → `crash`; `0` → `ok`; **in the contract** → `findings`; **anything else
nonzero** → new status `unusable`, which sits on the harness side of the severity
ordering, so it outranks findings for the aggregate exit.

The codes were **measured, not assumed**: all six members use `1` for findings, four
also use `2` for unusable. Declaring the contract per member rather than hardcoding
`{1}` globally is deliberate — a future detector with a different vocabulary must state
it, instead of silently inheriting the fail-open.

`test_every_member_declares_a_finding_contract` fails if a member is added without one.

`[VERIFIED — this session]` 16 tests pass, including the regression codex asked for
(`test_a_non_traceback_exit_2_is_HARNESS_not_findings`). Load-bearing confirmed by
restoring the old classification in a copy: the same exit-2 stub flips `unusable` →
`findings`.
