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
  Mon–Fri, slot ≤ local time < 13:00, today's output missing; otherwise one
  stamped line in a guard log that lies OUTSIDE the manifest's evidence globs).
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

- Rule, applied to EVERY invocation (calendar or load): RUN iff weekday AND
  `slot <= HHMM < 1300` AND at least one named output is missing; else exit 0
  after exactly one stamped line. Export: slot 0615, outputs = the bundle pair.
  Scheduler: slot 0625, output = `session_scheduler_<d>.log` (written on every
  real run, armed or not; a mid-session start is the scheduler's designed
  self-gated case). 13:00 = NYSE close in local PT: a "pre-market frozen"
  vector exported after the session would be a post-hoc artifact.
- The guard log is `logs/rq105/catchup_guard_<job>_<d>.log`, never the
  wrapper's evidence log; `test_guard_logs_never_match_the_manifest_evidence_globs`
  proves a load-time skip cannot read as "the job fired today".
- Guard return 2 (usage) is FATAL in the wrappers, never a silent skip. The
  guard runs BEFORE the pinned-common resolver so a skip needs no pin.
- Plists: `RunAtLoad=true` added; `ProgramArguments` unchanged, so
  `program_args_sha256` in `ops/launchd_manifest.json` is unchanged; the
  manifest entries record `run_at_load: true` + why.
- Drift scan (`ops/run_surface_drift_check.py` `INTENT_KEYS`,
  `_intent_problems`): a manifest entry that declares `run_at_load` /
  `keep_alive` is now compared against the installed plist. The quote logger's
  `keep_alive` (declared 2026-07-22) compared equal on this machine
  `[VERIFIED — tests/test_run_surface_drift_check.py::TestManifestGeneration::test_NO_residual_problem_of_any_other_kind, residual == []]`.

## Tests

`tests/test_rq105_liveness_serving_chain.py` (29 tests): the 08-28 filesystem
reconstruction → `export_missing` + `serving_noop`, urgent alert, DISARMED
named in the body; stale-stamped bundle → `export_missing`; green day → OK
line with `[scheduler DISARMED: arming file absent …]`; explicit
`"armed": false` → DISARMED; serving log present without rows / log missing →
`serving_noop`; armed-but-dark → `scheduler_dark` with the boot diagnosis;
armed + ticking → OK `[scheduler ARMED: operator=… ; N tick record(s)]`;
manifest-kind record counts, foreign kinds do not; 3 invalid arming payloads →
`arming_invalid`; non-session day unchanged; literals bound to wrappers +
resolvers; record kinds bound to the scheduler module; the shell guard under
`bash` (run / exact slot / 6 skip shapes / idempotent pair / usage rc=2);
wrappers call the guard with the reviewed slots before the pin resolver;
guard logs outside evidence globs; plists carry `RunAtLoad` and stay Mon–Fri.
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
`RunAtLoad` immediately: on a weekday between the slot and 13:00 with today's
output missing the guard WILL run the job right then (designed catch-up);
land outside that window, or accept it.

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
