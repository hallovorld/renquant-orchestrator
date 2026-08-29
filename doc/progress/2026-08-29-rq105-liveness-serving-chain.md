# Progress: rq105 liveness now covers the SERVING CHAIN; boot catch-up for the calendar-only jobs (orch#1085)

2026-08-29. Tracking issue: hallovorld/renquant-orchestrator#1085. Code + docs
only — nothing installed, no `launchctl`, no write to `~/Library/LaunchAgents`,
no live-tree or `-run` mutation. Installation is the operator landing action
in §Landing.

## Bottom line

- **On 2026-08-28 the rq105 serving chain did not run and the liveness check
  said OK.** The host booted 10:38 local; launchd never fired the 06:15
  batch-score export or the 06:25 scheduler (a `StartCalendarInterval` slot
  missed across a boot is never backfilled); no bundle, shadow serving exited
  `SKIP upstream` on line 1, no serving rows — `rq105 liveness OK 2026-08-28`.
- **The comparison that would have failed:** `meta.session_date == today` on
  `data/rq105/batch_scores_<today>.meta.json`. The file did not exist, and
  nothing compared it. `rq105_liveness_check.py` looked only at the three tick
  collectors' wrapper logs and data files (`_WRAPPER_LOGS`, `_data_outputs`).
- **Now:** the check compares the export bundle (`export_missing`), the
  serving log + serving rows for the session date (`serving_noop`), and the
  scheduler (`scheduler_dark` when armed; `scheduler DISARMED` named in the OK
  line when the arming file is absent; `arming_invalid` for a present-but-
  refused file), through the same urgent ntfy path and exit code as a dead
  collector. Re-run read-only against the real umbrella for 2026-08-28:
  `rc=1`, `export_missing` + `serving_noop`
  `[VERIFIED — this session, notify stubbed, stdout quoted in §Evidence]`; for
  2026-08-27: `rq105 liveness OK 2026-08-27 [scheduler DISARMED: arming file
  absent (...)]`, `rc=0` `[VERIFIED — same run]`.
- **Boot catch-up:** `RunAtLoad=true` in the two reviewed plists +
  `ops/renquant105/rq105_catchup_guard.sh` sourced by both wrappers (run iff
  the date is an NYSE session, slot ≤ local time < that session's ACTUAL local
  close from `rq105_catchup_cutoff.py` — r2 —, today's output missing;
  otherwise one stamped line in a guard log that lies OUTSIDE the manifest's
  evidence globs).
- **Drift scan now compares declared launchd intents** (`run_at_load`,
  `keep_alive`) against the installed plists. After this PR reaches the `-run`
  checkout the daily scan WILL alarm `RunAtLoad intent NOT installed` on both
  jobs until the operator bootouts/bootstraps the reviewed plists — that alarm
  is the CONTAINMENT PROTOCOL (c) reminder, by design.
- **Decision needed from the operator:** execute §Landing (two `bootout` +
  `bootstrap`), then delete the two `PENDING_INTENT_INSTALL` entries in
  `tests/test_run_surface_drift_check.py` in a follow-up PR (the exact-equality
  test goes red on the operator machine the moment the install lands).

## Incident timeline (all read-only, 2026-08-29)

| when (local PT) | fact | evidence |
|---|---|---|
| Fri 08-28 10:38:03 | host booted | `[VERIFIED — sysctl kern.boottime = 1787938683 = Fri Aug 28 10:38:03 2026]` |
| 06:15 / 06:25 | export + scheduler slots fell before the boot; calendar-only plists, no `RunAtLoad` | `[VERIFIED — ops/renquant105/com.renquant.rq105-{batch-scores-export,session-scheduler}.plist at 64238032 (StartCalendarInterval only); installed copies byte-identical (`diff` vs `~/Library/LaunchAgents`, read-only)]` |
| all day | no `data/rq105/batch_scores_2026-08-28.{json,meta.json}`; no `logs/rq105/batch_scores_export_2026-08-28.log` | `[VERIFIED — ls data/rq105: 08-26 and 08-27 bundles at 06:15 each, nothing for 08-28; ls logs/rq105: export logs 08-24..08-27 only]` |
| 13:45:05 | shadow serving fired and exited on line 1: `2026-08-28T20:45:05Z SKIP upstream: no frozen batch-score export (...)` | `[VERIFIED — logs/rq105/shadow_serving_2026-08-28.log, 1 line, 230 bytes]` |
| — | `logs/renquant105_pilot/shadow_realtime_serving.jsonl` last `session_date` = 2026-08-27 (318 rows, mtime 08-27 13:45:29) | `[VERIFIED — tail scan, this session]` |
| — | scheduler DISARMED since 08-27: arming file absent; `session_scheduler_2026-08-27.log` = 99 bytes (`not armed — absent: …/intraday_decisioning.armed.json`); `intraday_decisions_shadow.jsonl` last session 2026-08-26 (32 ticks) | `[VERIFIED — ls data/rq105 (no armed file); tail scan]` (#1067) |
| 14:00 | `rq105 liveness OK 2026-08-28` | `[VERIFIED — prior read-only investigation; reproduced by the pre-fix code path: `_WRAPPER_LOGS` at :116 / :663-666, `_data_outputs` at :201-208 never name `batch_scores_`, `shadow_realtime_serving`, `intraday_decisions_shadow` or `session_scheduler_` (grep)]` |

Timing note for the new serving check: the liveness job fires at 14:00 local,
shadow serving at 13:45. The serving job completes within ~30 s of its fire
`[VERIFIED — shadow_serving_2026-08-2{5,6,7}.log mtimes 13:45:27 / 13:45:33 /
13:45:29]`, so at 14:00 the serving rows are on disk.

## What the check now compares (`ops/renquant105/rq105_liveness_check.py`)

| surface | comparison | fails as |
|---|---|---|
| batch-score export | `data/rq105/batch_scores_<d>.json` AND `.meta.json` exist AND `meta.session_date == d` (`check_batch_scores_export`) | `export_missing` — reason names whether `batch_scores_export_<d>.log` exists (absent = launchd never fired: the boot-missed-slot shape) |
| shadow serving | `logs/rq105/shadow_serving_<d>.log` exists, its first line does not carry the wrapper's `SKIP upstream` stamp, AND `shadow_realtime_serving.jsonl` tail has a `session_date == d` row (`check_shadow_serving`) | `serving_noop` — the row is load-bearing: producer refusal (rc=4), producer failure (rc=5), pin refusal and crashes all write a log and no rows |
| session scheduler | arming file absent or `"armed": false` → DISARMED (expected dark; ALWAYS printed in the OK line). Armed (validated by the wrapper's own `rq105_arming.evaluate_arming_file`) → `intraday_decisions_shadow.jsonl` tail has a `session_date == d` record of kind `intraday_decision_shadow_tick` / `intraday_session_manifest` (`check_session_scheduler`) | `scheduler_dark`; a present-but-refused arming file → `arming_invalid` (looks armed, runs dark) |

Non-session days keep the early `not an NYSE session day — skip`. Paths are the
wrapper literals (`run_shadow_serving.sh` `--shadow-log` / `--scheduler-log` /
`$SCORES` / `$META`, `run_session_scheduler.sh` `ARMING_FILE`), and
`test_path_literals_match_the_wrappers_and_module_resolvers` binds each to the
wrapper text and to the producing module's own resolver
(`shadow_realtime_serving.default_shadow_log_path`,
`intraday_session_scheduler.default_shadow_log_path`). Tail reads are bounded
(1 MiB); both files are append-only in session order
`[VERIFIED — ShadowTickWriter.append; serving appends per as_of]`.
`main()` takes an optional date (default today) so the 08-28 state can be
reconstructed in `tmp_path`.

## Boot catch-up (`rq105_catchup_guard.sh`, wrappers, plists, manifest)

- Rule, applied to EVERY invocation (calendar or load): RUN iff `<date>` is
  an NYSE session AND `slot <= HHMM < <that session's local close>` AND at
  least one named output is missing; else exit 0 after exactly one stamped
  line. Export: slot 0615, outputs = the bundle pair. Scheduler: slot 0625,
  output = `session_scheduler_<d>.log` (written on every real run, armed or
  not; a mid-session start is the scheduler's designed self-gated case). The
  close comes from `rq105_catchup_cutoff.py` (§r2): 13:00 PT on a normal
  session, 10:00 PT on an early-close session, REFUSED on a weekend/holiday.
  A "pre-market frozen" vector exported after the session would be a
  post-hoc artifact.
- The guard log is `logs/rq105/catchup_guard_<job>_<d>.log`, never the
  wrapper's evidence log; `test_guard_logs_never_match_the_manifest_evidence_globs`
  proves a load-time skip cannot read as "the job fired today".
- Guard return 2 (usage / missing wrapper environment) is FATAL in the
  wrappers, never a silent skip. The guard runs AFTER the pinned-common
  resolver and the `PYTHONPATH` export (r2; r1 had it before, "a skip needs
  no pin" — a skip that needs no pin cannot know the session's close).
- Plists: `RunAtLoad=true` added; `ProgramArguments` unchanged, so
  `program_args_sha256` in `ops/launchd_manifest.json` is unchanged; the
  manifest entries record `run_at_load: true` + why.
- Drift scan (`ops/run_surface_drift_check.py` `INTENT_KEYS`,
  `_intent_problems`): a manifest entry that declares `run_at_load` /
  `keep_alive` is now compared against the installed plist. The quote logger's
  `keep_alive` (declared 2026-07-22) compared equal on this machine
  `[VERIFIED — tests/test_run_surface_drift_check.py::TestManifestGeneration::test_NO_residual_problem_of_any_other_kind, residual == []]`.

## r2 — codex round 1 (2026-08-29): catch-up eligibility bound to the exchange calendar

Codex, verbatim: "the catch-up window is not session-calendar aware. Both
wrappers pass a fixed `1300` PT cutoff and the guard only distinguishes
weekdays. On NYSE early-close sessions, the market closes at 10:00 PT, so a
boot/bootstrap between 10:00 and 13:00 will create the supposedly frozen
batch export after the session has ended and can start the scheduler after
there is no session left."

Correct. Measured against the primitive itself `[VERIFIED — this session,
`renquant_common.market_calendar.default_session_calendar().session_bounds`
under `TZ=America/Los_Angeles`]`: 2026-11-27 and 2026-12-24 close 13:00 ET =
**1000** PT; 2026-09-07 (Labor Day, a Monday) and 2026-07-03 (a Friday) are
**not sessions**; a normal session closes 1300 PT. Under r1 a boot at 10:38 on
2026-11-27 would have exported a "pre-session" bundle 38 minutes after the
close, and a boot at 09:00 on 2026-09-07 would have started the scheduler for
a session that does not exist.

- **`ops/renquant105/rq105_catchup_cutoff.py` (new, fail-closed).** `--date
  YYYY-MM-DD` → stdout `HHMM` of that date's ACTUAL close in the process-local
  clock (the same clock as the wrapper's `$(date +%H%M)`), rc 0; a non-session
  date → the reason, rc 1; a bad date / calendar import or backend failure / a
  close that does not fall on the requested local date → the reason, rc 2.
  The calendar is `renquant_orchestrator.intraday_quote_logger.
  default_session_calendar` — the exact re-export that
  `rq105_liveness_check._session_calendar` and the scheduler's own gate
  resolve (`renquant_common.market_calendar`, `pandas_market_calendars` NYSE).
  NO `sys.path` bootstrap, NO fallback: it imports whatever `PYTHONPATH`
  names, and refuses when that fails.
- **`rq105_catchup_guard.sh`.** Signature is now `<job> <date> <now HHMM>
  <slot> <guard_log> <output>...` — the weekday number and the cutoff
  argument are gone. It runs the helper as `$RQ_ROOT/.venv/bin/python` under
  the wrapper's `PYTHONPATH`; the helper's stderr appends to the guard log.
  Any answer other than "rc 0 and four digits" is a REFUSAL: one stamped
  `SKIP calendar refused catch-up for <date> (helper rc=N: <reason>)` line,
  the same line on stderr, return 1 → the wrapper exits 0. A missing
  `RQ105_OPS_DIR` / `RQ_ROOT` / `PYTHONPATH` is return 2 → FATAL, never a
  skip. The guard log is still `catchup_guard_<job>_<date>.log`, outside the
  evidence globs; the idempotency rule (run only when a named output is
  missing) is unchanged.
- **Both wrappers.** The guard block moved to just AFTER
  `rq105_resolve_common_src` and `export PYTHONPATH=…`, so the cutoff helper
  imports the calendar from exactly the pinned code the job runs. Consequence:
  a pin mismatch at load is FATAL (exit 1) on any day instead of a silent
  skip — the same verdict the calendar fire would get. `1300` and
  `$(date +%u)` no longer appear in either wrapper; `"$TS"` is the date.
- **Cutoff = the session's actual close, not close-minus-margin.** The
  boundary the guard enforces is "the session is still open" — a frozen
  pre-session vector stamped with a session that has ended is a post-hoc
  artifact — not "enough session left to be useful". Neither consumer needs
  lead time from the guard: shadow serving reads the bundle at 13:45 local,
  after every close, and the scheduler self-gates on this same calendar and
  exits at the close, so a start at close-minus-one-minute writes its
  manifest stamp and no ticks (its designed self-gated case) and still
  leaves the wrapper-log line liveness looks for. A finer usefulness
  threshold would be the consumer's rule, not the guard's.
- **Untouched:** plists, `program_args_sha256`, the drift scan; the two
  manifest `_run_at_load_comment` strings now describe the session-calendar
  bound. **No live installation is needed for this correction** (codex): the
  wrappers and the helper run from the `-run` checkout once synced; §Landing
  is unchanged.

Tests (`tests/test_rq105_liveness_serving_chain.py` §6, 46 tests, all under
`bash` / `subprocess`): **6a** the shell guard with a STUBBED helper — RUN on
a session day / at the slot (and the helper was called with `--date <date>`
under the wrapper's `PYTHONPATH`); before-slot and at/after-cutoff skips;
early-close stub `1000`: 0930 runs, 1000 / 1038 / 1259 refuse (1259 would
have RUN under r1); six non-answers (non-session rc 1, weekend rc 1, calendar
error rc 2, traceback-only rc 2, `13:00`, empty) all refuse with the reason
stamped and the traceback in the guard log; idempotent pair; usage rc 2
including the r1 weekday number; a missing `PYTHONPATH` / `RQ105_OPS_DIR` /
`RQ_ROOT` → rc 2. **6b** the real helper against the real NYSE calendar:
2026-08-31 / 08-28 → `1300`; 11-27 / 12-24 → `1000`; 09-07 / 07-03 / 08-29 /
08-30 → rc 1 `non-session`; `TZ=America/New_York` → `1600`, `UTC` → `2000`;
bad date rc 2; a raising stub package first on `PYTHONPATH` → rc 2
`calendar error … calendar backend down`; `local_close_hhmm` raises on a
close off the requested local date. **6c** guard + real helper + real
calendar end to end: normal session before/at its close, early close before /
at / after its 10:00 PT close (the 10:38 boot hour is REFUSED on 11-27),
Christmas Eve mid-morning refused, Labor Day refused, Saturday / Sunday
refused, idempotency preserved. Wrapper text: `"$TS"` + reviewed slots, no
`1300`, no `date +%u`, guard AFTER the resolver and the `PYTHONPATH` export;
the helper's import bound (AST) to the liveness check's primitive with no
`sys.path` edit and no direct calendar-backend import.

## Tests

`tests/test_rq105_liveness_serving_chain.py` (64 tests after r2): the 08-28 filesystem
reconstruction → `export_missing` + `serving_noop`, urgent alert, DISARMED
named in the body; stale-stamped bundle → `export_missing`; green day → OK
line with `[scheduler DISARMED: arming file absent …]`; explicit
`"armed": false` → DISARMED; serving log present without rows / log missing →
`serving_noop`; armed-but-dark → `scheduler_dark` with the boot diagnosis;
armed + ticking → OK `[scheduler ARMED: operator=… ; N tick record(s)]`;
manifest-kind record counts, foreign kinds do not; 3 invalid arming payloads →
`arming_invalid`; non-session day unchanged; literals bound to wrappers +
resolvers; record kinds bound to the scheduler module; the shell guard and
its calendar helper (§r2, 46 tests); guard logs outside evidence globs;
plists carry `RunAtLoad` and stay Mon–Fri.
`tests/test_run_surface_drift_check.py`: 5 intent tests + the bounded
`PENDING_INTENT_INSTALL` relaxation with its exact-equality test.
`tests/test_rq105_liveness.py`: the existing alert-shape test stubs
`check_serving_chain` so it stays hermetic from the operator's disk.

`make test` (Makefile interpreter `RenQuant/.venv`, sibling `*_SRC` overrides
because the worktree is not a sibling): **6828 passed, 17 failed, 11 skipped**
`[VERIFIED — scratchpad/make_test2.log, 183 s]`. The 17 failures are the
identical set on a clean `origin/main` worktree at d5a8bb12
(`test_cli`, `test_goal3_public_export_resolution`, 13× `test_shadow_ab_daily_script`,
2× `test_shadow_serving_skips_leave_evidence`) `[VERIFIED — same 17 selected,
"17 failed in 4.51s"]` — environmental (sibling checkouts' git state), not this
change. Targeted suites for every touched file: 216 passed.

## Evidence — real-data dry run (read-only, notify stubbed)

```
export_missing: batch_scores_export: batch-score bundle missing for 2026-08-28: …/batch_scores_2026-08-28.json, …/batch_scores_2026-08-28.meta.json [wrapper log ABSENT — launchd never fired the 06:15 export today (boot after the slot? StartCalendarInterval is not backfilled across a boot)]
serving_noop: shadow_serving: shadow serving skipped upstream for 2026-08-28: '2026-08-28T20:45:05Z SKIP upstream: no frozen batch-score export (…' (no frozen batch-score export — the serving chain no-op'd)
scheduler: [scheduler DISARMED: arming file absent (…/data/rq105/intraday_decisioning.armed.json)]
--> 2026-08-28 rc=1 alerts_sent_to_stub=1
rq105 liveness OK 2026-08-27 [scheduler DISARMED: arming file absent (…)]
--> 2026-08-27 rc=0 alerts_sent_to_stub=0
```

## Landing (operator; one grant; NOT executed by this PR)

Preconditions: this PR merged; `renquant-orchestrator-run` ff-synced to that
main (merged ≠ deployed — the 14:00 liveness job and the drift scan both run
from `-run`, so until the sync the OLD check runs). `bootstrap` fires
`RunAtLoad` immediately: on an NYSE session day between the slot and that
session's local close with today's output missing the guard WILL run the job
right then (designed catch-up); land outside that window, or accept it.

```bash
UID_NUM="$(id -u)"
for p in batch-scores-export session-scheduler; do
  launchctl bootout "gui/$UID_NUM/com.renquant.rq105-$p" || true
  cp /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/com.renquant.rq105-$p.plist ~/Library/LaunchAgents/
  launchctl bootstrap "gui/$UID_NUM" ~/Library/LaunchAgents/com.renquant.rq105-$p.plist
done
# verify (read-only): RunAtLoad loaded, guard stamped exactly one line, drift scan clean
launchctl print "gui/$UID_NUM/com.renquant.rq105-batch-scores-export" | grep -iE "run at load|runs"
cat /Users/renhao/git/github/RenQuant/logs/rq105/catchup_guard_*_"$(date +%F)".log
/Users/renhao/git/github/RenQuant/.venv/bin/python /Users/renhao/git/github/renquant-orchestrator-run/ops/run_surface_drift_check.py
```

Then a follow-up PR removes the two labels from `PENDING_INTENT_INSTALL`
(the exact-equality test forces it). Record the grant in `doc/progress` /
memory per the containment protocol.

**Revert** (restore the calendar-only plists):

```bash
UID_NUM="$(id -u)"
for p in batch-scores-export session-scheduler; do
  launchctl bootout "gui/$UID_NUM/com.renquant.rq105-$p" || true
  git -C /Users/renhao/git/github/renquant-orchestrator show 64238032:ops/renquant105/com.renquant.rq105-$p.plist > ~/Library/LaunchAgents/com.renquant.rq105-$p.plist
  launchctl bootstrap "gui/$UID_NUM" ~/Library/LaunchAgents/com.renquant.rq105-$p.plist
done
```
and `git revert` the merge commit (drops the manifest intents, the guard
sourcing and the serving-chain checks together), then ff-sync `-run`.

## Not done / limits

- The check is ADDED coverage, not a new alert channel: same topic, same
  urgent priority, same exit code. A day on which the producer legitimately
  refuses (rc=4) now pages `serving_noop` — that is a serving chain that did
  not serve, which is what the operator asked to hear about.
- `RunAtLoad` also fires at every login/bootstrap, not only at boot; the guard
  bounds every such fire to the window and to missing output.
- The check reads the arming file; it never writes it (operator-owned, #1067).
- The `-run` sync and the plist landing are separate operator actions; until
  both land the running system is unchanged.
