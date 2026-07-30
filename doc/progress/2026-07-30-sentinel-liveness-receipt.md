# A crashed sentinel and an alarming sentinel are now different things   (PR pending)

STATUS:    delivered
WHAT:      The rq104 degradation sentinel exits 1 on alarms — by design, and the ack
           ledger acks it on that basis — while an uncaught exception ALSO exited 1.
           Internal errors now exit 3, every firing writes a liveness receipt, and
           the run-surface drift scan (a SEPARATE launchd job) checks that receipt.
WHY/DIR:   GOAL-1 exists to stop a shadow feed dying silently. Issue #622 defect 2
           is that the guard's OWN failure was un-diagnosable by construction: a
           crashed sentinel and an alarming one produced the identical observable,
           and the ack ledger's self-referential row acked both. That is why nobody
           could tell whether the rq105 shadow-serving alarm had been firing
           unheeded for 28 days or the sentinel was simply dead.
EVIDENCE:  §1 (the exit-code collision, the three cases now separable, suite A/B).
NEXT:      Establish which of the two it actually was for `rq105-shadow-serving`
           (#621), now that the question is answerable. Deploying this to the run
           checkout is a live-surface action and needs its own authorised batch.

## §1 EVIDENCE

### The collision, in one line each

`main()` returned `1` when `problems` was non-empty
`[VERIFIED — ops/renquant104/rq104_degradation_sentinel.py:526 at 679af192]`, and
Python exits `1` on an uncaught exception. `launchctl` records only the last exit
code, and `sentinel_acks.json` demotes this label's nonzero exit to an INFO line
permanently, with the reason *"exit 1 IS the sentinel's alarm-delivered signal (by
design); self-referential row"*
`[VERIFIED — ops/renquant104/sentinel_acks.json at 679af192]`. So one ack covered
two different events and there was no third signal to separate them.

### Three cases, now separable

| what happened | before | now |
|---|---|---|
| alarms present (designed) | exit 1, acked | exit 1, acked — **unchanged** |
| sentinel crashed | exit 1, acked → invisible | **exit 3**, not acked, plus a receipt with `outcome=internal_error` |
| sentinel never ran | stale `launchctl` code, invisible | **receipt absent or stale → LOUD** in the drift scan |

`EXIT_ALARMS` is deliberately still `1`. Renumbering it would silently change what
every existing ack in the ledger means, so only the previously-colliding crash case
gets a new code. A test pins that.

### Why the check lives in the drift scan and not in the sentinel

A process cannot attest to its own liveness — if it is dead it is not running to
notice. `check_sentinel_receipt()` therefore sits in
`ops/run_surface_drift_check.py`, which runs as `com.renquant.run-surface-drift`, a
separate launchd job `[VERIFIED — ops/launchd_manifest.json]`. An alarming sentinel
is reported there as **INFO only**, because it already delivers its own alert and
double-alarming trains the reader to ignore both.

### Where the receipt is written, and two paths deliberately rejected

Default `~/.renquant/sentinel/rq104_degradation_receipt.json`, override
`RQ_SENTINEL_RECEIPT`.

- **Not** beside the ack ledger in `ops/renquant104/`: that directory lives in the
  run checkout, and runtime state written there would leave it dirty, which makes
  pin-align abort.
- **Not** under the umbrella tree: that is not a scratch space.

The receipt writer **never raises** — it returns an error string the caller prints
as a warning. A liveness mechanism that can take down the process it instruments is
worse than none, and a test proves an unwritable receipt leaves the verdict
unchanged.

### Suite

| tree | result |
|---|---|
| `origin/main` @ 679af192, separate worktree | 5 failed, 4457 passed, 5 skipped |
| this branch | 5 failed, **4480** passed, 5 skipped |

`[VERIFIED — python3 -m pytest -q in both worktrees, all sibling checkouts on PYTHONPATH]`.
Same 5 pre-existing failures; delta is exactly the 23 tests added.

## §2 Tests — and the one I initially forgot

23 new. The important group is the four that exercise the wrapper itself, and I
added them only after noticing the first 19 tested the receipt and its reader while
never testing **the thing #622 is about**: that an exception inside the sentinel no
longer exits 1. `test_an_exception_inside_the_sentinel_exits_3_not_1` is the actual
regression; `test_a_normal_alarm_run_still_exits_1_and_records_it` is its negative
case, proving the new code is reached only by the crash path.

Every LOUD branch is paired with a quiet one so the check is not merely noisy:
`test_a_long_weekend_does_NOT_alarm` pins the 4-day bound (a Friday firing plus a
Monday holiday legitimately leaves the newest receipt 4 days old — tightening below
4 would cry wolf every long weekend), and `test_systemexit_propagates_untouched`
keeps `--help` from being swallowed into exit 3.

`test_unparseable_timestamp_is_LOUD_not_silently_skipped` and
`test_receipt_with_no_written_at_is_LOUD` exist because the recurring defect shape
on this programme is a guard that passes when its input is absent.

## §3 Not claimed

This does **not** establish what was wrong with `com.renquant.rq105-shadow-serving`
(exit 1, 0-byte stdout, last written 2026-07-02). It makes the question answerable;
it does not answer it. Nor is anything deployed — the sentinel runs from
`renquant-orchestrator-run`, and syncing that checkout is a live-surface action
requiring its own authorised batch. Until then this is merged-not-deployed, and the
receipt will be absent, which the drift scan will correctly call LOUD once *it* is
also deployed. Sequencing the two is part of that batch, not this PR.

## §4 Live-surface impact of the merge itself

None. `program_args` are unchanged for both jobs, so `program_args_sha256` in
`ops/launchd_manifest.json` still matches and the drift scan will not report
manifest drift from this change.
