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
