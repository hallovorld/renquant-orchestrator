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

**The `else` is the fix, not the list.** This is a default inversion, not an
enumeration of known-bad codes: an enumerated deny-list always leaves a fail-open
`else`, which is how the bug arrived. Only "verdict reached" codes are listed;
**every other nonzero is HARNESS by default**, including codes no member uses today.
Declaring the contract per member rather than hardcoding `{1}` globally is likewise
deliberate — a future detector with a different vocabulary must state it instead of
silently inheriting the fail-open.

**Codes cited, not asserted.** Each member's code is recorded in `MEMBERS` with the
file and line it was read from at `b44f735c`, because "measured, not assumed" with no
citation is itself an assertion:

| member | finding exit | read from | unusable codes |
| --- | --- | --- | --- |
| silent-refusal | `1` | `rq104_silent_refusal_sentinel.py:236` `return 1 if findings else 0` | none |
| blind-notifiers | `1` | `blind_notifier_scan.py:95` `EXIT_OK, EXIT_FINDINGS, EXIT_UNUSABLE = 0, 1, 2` | `2` @ :205 |
| undelivered-alerts | `1` | `undelivered_alert_scan.py:159` | none |
| import-resolution | `1` | `import_resolution_check.py:203` | `2` @ :191, :197 |
| umbrella-script-shadow | `1` | `umbrella_script_shadow_check.py:258` | `2` @ :237, :242, :247, :256 |
| launchd-liveness | `1` | `launchd_liveness_scan.py:354` `return 1 if bad else 0` | `2` @ :339, :342 |

A comment citing a line still rots when the member changes underneath it, so
`test_declared_contract_matches_each_member_source` **re-derives** this table from each
member's AST (resolving constants, module-level names like `EXIT_FINDINGS`, and
`return 1 if bad else 0`) and fails if a declared code is one `main()` cannot return.
Derived independently: all six yield `{0,1}`, four also `{2}` — matching the hand-read
citations. `test_the_cited_contract_is_the_one_in_force` pins the table so that
widening any member to `(1, 2)` — which would reintroduce #650 for that member alone —
is a failing diff.

`[VERIFIED — this session]` **23 tests pass** in `tests/test_ops_audit.py` (was 16),
including the regression codex asked for
(`test_a_non_traceback_exit_2_is_HARNESS_not_findings`) and the anti-vacuity pair
(`test_an_IN_CONTRACT_exit_without_a_traceback_is_a_FINDING`,
`test_an_exit_inside_the_contract_is_a_finding`) without which a fix that called
everything HARNESS would pass.

`[VERIFIED — this session]` **Mutation-tested**, three reverts each caught: widening
blind-notifiers to `(1,2)` → 1 fail; declaring an unreachable exit `7` → 2 fails;
restoring `else STATUS_FINDINGS` (the original bug) → 3 fails.

`[VERIFIED — this session]` **Live run** `python3 ops/ops_audit.py` → all 6 members ran:
`ok=1 findings=5 unusable=0 crash=0 timeout=0 missing=0`, aggregate exit **1**. The five
findings are real detector output (silent-refusal streak on `weekly-retrain-patchtst`,
15 ntfy POSTs scanned, a `latin-1` undelivered alarm, an unresolvable
`renquant_artifacts.hash_jsonable`, launchd liveness); `umbrella-script-shadow` exited
`0` with 44 pairs registered. No member landed on `unusable`, so the aggregate is
`findings` and not the harness code — the contract discriminates in production, not
only in tests.

Full suite: `4699 passed, 1 failed`. The failure is
`test_run_surface_drift_check.py::test_committed_manifest_matches_live_surface`, which
fails identically on the untouched base commit (it compares the committed manifest to
this machine's live launchd surface) and is unrelated to this change.
