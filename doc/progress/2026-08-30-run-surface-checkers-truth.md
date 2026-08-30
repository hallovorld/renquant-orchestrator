# Run-surface checkers tell the truth — pinned-runtime import resolution, dirty ≠ mismatch in the dawn preflight, boot catch-up for dawn / drift

STATUS:    delivered — code + tests + reviewed surface (plists, manifest) in
           this PR only. Nothing installed, no `launchctl`, no write to
           `~/Library/LaunchAgents`, no live-tree or `-run` checkout mutation.
           Landing (two `bootout`/`bootstrap` + the `-run` sync) is the operator
           action in §Landing. All measurements below are read-only and from
           this session unless tagged otherwise.

WHAT:      Three run-surface checkers are made to report the truth: (1) the
           drift scan's import-resolution check now establishes the pinned
           runtime's package roots itself, at the PYTHONPATH position, and
           flags any `renquant_*` symbol resolved from outside that root
           (`resolved_from_unpinned_path`); (2) the dawn preflight separates
           `PIN_MISMATCH` (abort) from `TREE_DIRTY` (docs/README/generated
           allow-list → WARN + continue) and `TREE_DIRTY_BLOCKING` (abort), and
           notifies on either abort; (3) the boot catch-up guard is shared
           (`ops/catchup_guard.sh` + `ops/catchup_cutoff.py`) and wired into
           the dawn preflight (0605, `session`) and a new drift-scan wrapper
           (0700, literal `2400`), with `RunAtLoad=true` in both `deploy/`
           plists and the manifest intents. File-by-file table in §What changed.

WHY/DIR:   MID workstream `doc/memory/mid-term/serving-reliability.md`
           (addendum 2026-08-30, defect #6, updated in this PR): a checker that
           measures the wrong object passes forever. Three false "unresolvable"
           alarms every morning, 7 silent dawn aborts over one dirty README,
           and a boot-dropped slot with no catch-up are the same class as #1087
           (rq105 catch-up) and the earlier run-surface drift-scan work; this
           PR binds each checker to the object the PRODUCTION path actually
           uses and makes its verdict name that object.

EVIDENCE:  §4(b) block — ops-surface claim, no model/data claim.
           artifact:      `ops/import_resolution_check.py`,
                          `ops/renquant104/dawn_pin_identity_check.py`,
                          `ops/catchup_guard.sh` (this branch); read-only
                          inputs `logs/rq104/launchd_run_surface_drift.out`,
                          `logs/rq104/dawn_pin_identity_*.json`
           prod or exp:   prod run surface (launchd jobs in `ops/` + `deploy/`);
                          nothing deployed by this PR
           existing data: drift log 2026-08-30T07:00:06 — three
                          `ModuleNotFoundError` lines; dawn receipts 08-19..08-27
                          all `ok=false` with the single row `renquant-model
                          pinned=true dirty=true`; zero `2026-08-28` drift-log
                          lines vs 39/41/40 on 08-27/29/30 (all quoted in
                          §Bottom line and §Evidence below)
           best-known?:   not a model variant — n/a; the checker outputs are
                          compared before/after on the same tree (§Evidence)
           scope:         "this is the run-surface checker set, prod ops
                          surface, vs the origin/main checkers on the same
                          inputs; no IC / Sharpe / APY number is claimed"

NEXT:      operator executes §Landing (bootout/bootstrap of the two `deploy/`
           plists + `renquant-orchestrator-run` ff-sync); then a follow-up PR
           deletes the two `PENDING_INTENT_INSTALL` entries and the
           `PENDING_PROGRAM_ARGS_INSTALL` entry in
           `tests/test_run_surface_drift_check.py` (the exact-equality tests
           force it).

## Bottom line

Three run-surface checkers were reporting something other than the truth, all
[VERIFIED] read-only on 2026-08-30:

1. **The drift scan's import-resolution check measured the wrong tree and
   raised three false alarms every day.** `ops/run_surface_drift_check.py`
   calls `irc.verify(pins)` directly; only `import_resolution_check.main()`
   established the daily's package roots, so the scheduled scan ran on the
   plist's orchestrator-only PYTHONPATH and printed
   `renquant_backtesting.BacktestPipeline`, `renquant_execution.get_broker`,
   `renquant_execution.BrokerExecutionPipeline` "unresolvable
   (ModuleNotFoundError)" `[VERIFIED — logs/rq104/launchd_run_surface_drift.out,
   2026-08-30T07:00:06 lines]`. Worse: the roots the CLI path did establish
   were APPENDED behind site-packages, and the umbrella venv carries editable
   `.pth` entries for four packages pointing at the mutable sibling checkouts —
   so `renquant_common`, `renquant_artifacts`, `renquant_base_data`,
   `renquant_model_gbdt` resolved from `/Users/renhao/git/github/<repo>/src`
   while the pinned runtime sat at sys.path index 9+ (site-packages at 4)
   `[VERIFIED — probe under RenQuant/.venv with `_ensure_daily_resolution()`,
   printed `__file__` per package]`. Package-relative pins cannot see that.
   **Now** `verify()`/`emit()` establish the resolution themselves
   (idempotent), insert the chosen root's paths at the PYTHONPATH position
   (after caller exports, BEFORE stdlib/site — the precedence `current.env`
   gives the daily), and assert every `renquant_*` symbol's defining file AND
   import module lie under that root; otherwise `resolved_from_unpinned_path`.
   After the fix, both the CLI path and the drift-scan path resolve all 14
   symbols from `.subrepo_runtime/repos` with 0 problems, and a caller
   PYTHONPATH naming a sibling is flagged on 8 symbols
   `[VERIFIED — three in-session runs under RenQuant/.venv, quoted in §Evidence]`.
2. **The dawn preflight called a dirty README a pin mismatch and went dark for
   8 sessions.** `dawn_pin_identity_check.py` folded "HEAD != lock" and "any
   porcelain line" into one `ok`; the wrapper printed "runtime pins not
   aligned to subrepos.lock.json". Receipts 08-19..08-27 (7 sessions) are all
   `ok=false` with exactly one row `renquant-model pinned=true dirty=true`
   `[VERIFIED — logs/rq104/dawn_pin_identity_*.json, 14 receipts parsed; 08-10..08-18 ok]`;
   the drift scan named the file: `runtime/renquant-model: 1 uncommitted
   tracked change(s): M README.md` (24 lines, first 08-19)
   `[VERIFIED — grep of launchd_run_surface_drift.out]`; the 08-28 slot was then
   dropped by the boot (no 08-28 receipt). The order path this monitor claims
   to mirror does NOT abort on a dirty tree when pinned:
   `subrepo_assemble._ensure_repo` returns as soon as `_is_pinned` holds and
   consults `_is_dirty` only on the un-pinned sync path
   `[VERIFIED — RenQuant/scripts/subrepo_assemble.py:55-83]`; `daily_104` printed
   "Subrepo checkouts aligned to pins." on 08-26/27/28 `[VERIFIED — logs/daily_104/2026-08-2{6,7,8}.log:10]`.
   **Now** separate verdicts: `PIN_MISMATCH` (rc 1, abort, unchanged),
   `TREE_DIRTY` (rc 0, WARN naming the files, continue — only for the explicit
   allow-list: `*.md`/`*.rst`, `README*`, `doc/`/`docs/`, `__pycache__`/`*.pyc`,
   never under `src/`/`configs/`, never `.py`/`.json`/`.yaml`/`.toml`/`.sh`…),
   `TREE_DIRTY_BLOCKING` (rc 2, abort). The receipt (`dawn_pin_identity_v2`)
   carries `verdict`, `pin_mismatch`, `tree_dirty`, `tree_dirty_blocking`,
   `dirty_files`, `blocking_dirty_files`. The wrapper maps each rc to its own
   message (no "not aligned" for dirt) and **notifies on either abort** — a
   fail-closed monitor that fails silently is dark, which is what 7 silent
   aborts were.
3. **The 08-28 boot also dropped the dawn preflight (06:05) and the drift scan
   (07:00), and nothing caught up.** Zero `2026-08-28` lines in the drift
   scan's log vs 39/41/40 on 08-27/29/30; no `dawn_pin_identity_2026-08-28.json`
   `[VERIFIED — grep -c per date; ls]`; boot 10:38:03 `[VERIFIED — sysctl kern.boottime]`.
   Same class #1087 fixed for the two rq105 jobs. **Now** the guard + cutoff
   helper are SHARED (`ops/catchup_guard.sh` `launchd_catchup_guard`,
   `ops/catchup_cutoff.py`, moved from `ops/renquant105/`), with a per-job
   cutoff argument: `session` (NYSE session close, refuses non-session days —
   rq105 + dawn, whose plists are Mon–Fri) or a literal `HHMM` (the drift
   scan runs EVERY calendar day; it passes `2400`, consults no calendar, and
   keeps its calendar-day behaviour — only the missed-slot-after-boot
   catch-up is new). Wired into `dawn_funnel_preflight.sh` (slot 0605, after
   the pinned PYTHONPATH export, before the pin check so a skip never
   re-writes the receipt) and the new `ops/run_surface_drift_scan.sh` (slot
   0700, tees the scan into `run_surface_drift_<date>.log`, the idempotency
   witness; launchd's `.out` surface unchanged). `RunAtLoad=true` in both
   `deploy/` plists; manifest `run_at_load` intents + the drift job's new
   `program_args` / sha256.

Decision needed from the operator: execute §Landing.

## What changed (files)

| file | change |
|---|---|
| `ops/import_resolution_check.py` | `_ensure_daily_resolution()` inserts at the PYTHONPATH position (not append), records root / `runtime_materialized` / preloaded `renquant_*` names, idempotent; `verify()`/`emit()` call it; `resolve()` carries `abs_source_file`/`abs_module_file` (stripped from emitted pins); `_unpinned_path_problem()` → `resolved_from_unpinned_path`; `resolution_summary()` |
| `ops/run_surface_drift_check.py` | INFO line names the tree (`resolution_summary()`); comment on why |
| `ops/renquant104/dawn_pin_identity_check.py` | two verdicts, explicit allow-list (`classify_dirty_path`, closed by default), `porcelain_paths` (renames), receipt v2, exit 0/1/2; `_git(raw=True)` for porcelain (a stripped ` M README.md` read as `EADME.md` — caught by the test) |
| `ops/renquant104/dawn_funnel_preflight.sh` | shared guard (0605 `session`) after `export PYTHONPATH=`, before the pin check; rc-mapped abort messages; `rq_notify` on abort |
| `ops/catchup_guard.sh`, `ops/catchup_cutoff.py` | moved from `ops/renquant105/rq105_catchup_{guard.sh,cutoff.py}`; function `launchd_catchup_guard <job> <date> <now> <slot> <session\|HHMM> <guard_log> <outputs>…`; env `RQ_ROOT` (+ `CATCHUP_CUTOFF_HELPER`, `PYTHONPATH` in session mode) |
| `ops/renquant105/run_batch_scores_export.sh`, `run_session_scheduler.sh` | source the shared guard, export `CATCHUP_CUTOFF_HELPER`, pass `session`; behaviour unchanged |
| `ops/run_surface_drift_scan.sh` (new) | wrapper: guard (0700, `2400`) + `tee -a` into the dated log + rc line |
| `deploy/com.renquant.rq104-dawn-preflight.plist` | `RunAtLoad` false → true |
| `deploy/com.renquant.run-surface-drift.plist` | `ProgramArguments` → the wrapper; `RunAtLoad` true; schedule/env unchanged |
| `ops/launchd_manifest.json` | dawn: `run_at_load: true`; drift: new `program_args`, sha256 `97ef0267…` (was `bbd8f472…`), `run_at_load: true`; rq105 comments point at the shared guard |
| `ops/renquant105/README.md`, the two rq105 plist comments | paths |
| tests | see §Tests |

## Evidence — in-session runs (read-only, `PYTHONDONTWRITEBYTECODE=1`)

```
# BEFORE (origin/main checker, RenQuant/.venv, no PYTHONPATH, after _ensure_daily_resolution()):
renquant_common      -> /Users/renhao/git/github/renquant-common/src/renquant_common/__init__.py
renquant_artifacts   -> /Users/renhao/git/github/renquant-artifacts/src/renquant_artifacts/__init__.py
renquant_base_data   -> /Users/renhao/git/github/renquant-base-data/src/renquant_base_data/__init__.py
renquant_model_gbdt  -> /Users/renhao/git/github/renquant-model/src/renquant_model_gbdt/__init__.py
renquant_execution   -> /Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-execution/src/renquant_execution/__init__.py
renquant_backtesting -> /Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-backtesting/src/renquant_backtesting/__init__.py
site idx: [4] runtime idx: [9, 10] len 17
# AFTER, CLI:  import-resolution OK — 14 symbols resolve as reviewed (resolved against the pinned runtime /Users/renhao/git/github/RenQuant/.subrepo_runtime/repos)  rc=0
# AFTER, drift-scan path (plist PYTHONPATH, irc.verify() direct): problems: []  — all six packages -> .subrepo_runtime/repos/...
# AFTER, caller PYTHONPATH=/Users/renhao/git/github/renquant-common/src: 8 problem(s); first: renquant_common.Pipeline: resolved_from_unpinned_path — .../renquant-common/src/renquant_common/__init__.py, .../pipeline.py is not under the pinned runtime ...
```

Dawn receipts: `08-10..08-18 ok; 08-19..08-27 FAIL [('renquant-model', pinned=True, dirty=True)]`; no 08-28.
Drift log lines per date: `08-26 41 · 08-27 39 · 08-28 0 · 08-29 41 · 08-30 40`.
Runtime `renquant-model` porcelain at 10:22 today: clean (the README had been restored between the 07:00 scan and this session) — the fix does not depend on it.

## Tests

- `tests/test_import_resolution_check.py`: fake runtime tree + "editable sibling" in `tmp_path` (`renquant_fakeprobe_t`): sibling-only → `resolved_from_unpinned_path` naming both paths; runtime + sibling → runtime wins, clean; `verify()` without `main()` establishes the roots; inserted roots precede the interpreter's entries and follow the caller's; stdlib stand-ins outside the assertion; root chosen once; fallback summary; a module cached from an unpinned path is named as cached; the drift-scan quiet test now runs OUT of process with no PYTHONPATH (the plist's shape) — in-process, pytest's own sibling imports are exactly the state the check flags.
- `tests/test_dawn_pin_identity_check.py`: clean → rc 0 `OK`; dirty README only → rc 0 `TREE_DIRTY`, WARN, files listed, no "not aligned"; dirty `src/` file → rc 2 `TREE_DIRTY_BLOCKING`; drifted HEAD → rc 1 `PIN_MISMATCH`; mismatch + dirty README → rc 1 with both fields; docs-dirty in one repo + untracked `src/` file in another → rc 2; missing repo / non-repo dir / unreadable lock → rc 1; 22 allow-list cases (closed by default: `requirements.txt`, `Makefile`, `doc/notes.py` block); porcelain renames; wrapper rc mapping + notify.
- `tests/test_dawn_preflight_wrapper.py`: rc mapping, no "not aligned", notify between the abort and the bridge, guard after `export PYTHONPATH=` and before the pin check.
- `tests/test_catchup_guard_shared.py` (new): literal cutoff runs on Sat/Sun/Labor Day, never calls the helper, needs only `RQ_ROOT`; window edges; idempotent on an EMPTY dated file; per-mode env requirements; unknown cutoff spec and the old 6-argument signature → rc 2; one session-mode run through the shared paths with the real calendar; dawn/drift wrapper wiring; the drift wrapper passes `check_wrapper_pythonpath_roots` and runs END TO END under bash with a stub checker (both surfaces, rc line, second run = one-line skip); manifest ↔ plists; no stale `rq105_catchup_*` references.
- `tests/test_rq105_liveness_serving_chain.py` §6: retargeted to the shared guard (same 46 guard tests + wrapper text).
- `tests/test_run_surface_drift_check.py`: `PENDING_INTENT_INSTALL` is now `label -> previous disk value` (the dawn plist was reviewed with an explicit `RunAtLoad=false`, which is `disk=False`, not `disk=None`); new bounded `PENDING_PROGRAM_ARGS_INSTALL` (`label -> previous reviewed sha256`) relaxed ONLY while the installed digest equals the recorded previous one, with its exact-equality test and a test that the recorded digest is not the current one; the committed-manifest intent test covers all four jobs.

Focused suites — the six files listed above, exact command to rely on (run from
a detached worktree of this head; `PYTHONDONTWRITEBYTECODE=1`, `<wt>` = the
worktree path):

```
PYTHONPATH=<wt>/src:<wt>/ops:/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-common/src \
  /Users/renhao/git/github/RenQuant/.venv/bin/pytest -q \
  tests/test_import_resolution_check.py tests/test_dawn_pin_identity_check.py \
  tests/test_dawn_preflight_wrapper.py tests/test_catchup_guard_shared.py \
  tests/test_rq105_liveness_serving_chain.py tests/test_run_surface_drift_check.py
```
→ **199 passed, 1 skipped** `[VERIFIED — re-run 2026-08-30 on head 00bd7a61 in
`/private/tmp/rq-fix-orch-pr1098`, 29.4 s; matches codex's r1 rerun of the same
command on the same head]`. (Corrects the earlier "8 files: 249 passed" line —
that count came from an unlisted, wider selection and is withdrawn; see
§Corrections.)
`make test` (RenQuant/.venv, sibling `*_SRC` overrides — the worktree is not a sibling): **7128 passed, 6 failed, 10 skipped** (334 s) `[VERIFIED — scratchpad/make_test_branch.log]`;
clean `origin/main` worktree (06ceb310), same command: **7066 passed, 6 failed, 10 skipped** (330 s) `[VERIFIED — scratchpad/make_test_main.log]`, the IDENTICAL 6 (`comm` of the two FAILED lists is empty both ways; also re-run selected: 6 failed in 5.48s) — `test_cli::test_parking_sleeve_cli_computes_allocation`, `test_goal3_public_export_resolution::test_the_RECORD_names_the_revision_that_was_actually_measured`, 2× `test_g2v3_stage_i2_binding` (checkout-at-another-path), 2× `test_shadow_serving_skips_leave_evidence` — all pre-existing and environmental (sibling checkouts' git state / worktree path), none touch a file in this PR.

## Corrections (visible, per LONG row 10)

- r1 (codex, 2026-08-30): the C5 header lacked the literal `WHAT:` / `WHY/DIR:`
  / `EVIDENCE:` / `NEXT:` fields — added above; the narrative sections are
  unchanged.
- r1 (codex, 2026-08-30): "Focused suites (8 files): 249 passed, 1 skipped"
  did not match the six suites listed; the durable figure is now the exact
  six-file command and its result, **199 passed, 1 skipped**, re-measured in
  session on this head.

## Landing (operator; one grant; NOT executed by this PR)

Preconditions: this PR merged; `renquant-orchestrator-run` ff-synced to that main
(merged ≠ deployed — every job here runs from `-run`). Until the `-run` sync the
running checkers are the old ones; after the sync and before the plist install
the daily scan alarms `ProgramArguments CHANGED` on **itself** and `RunAtLoad
intent NOT installed` on dawn + drift (containment protocol c — the designed
reminder). `bootstrap` fires `RunAtLoad` immediately: between the slot and the
cutoff with today's output missing the guard WILL run the job right then.

```bash
UID_NUM="$(id -u)"
for p in rq104-dawn-preflight run-surface-drift; do
  launchctl bootout "gui/$UID_NUM/com.renquant.$p" || true
  cp /Users/renhao/git/github/renquant-orchestrator-run/deploy/com.renquant.$p.plist ~/Library/LaunchAgents/
  launchctl bootstrap "gui/$UID_NUM" ~/Library/LaunchAgents/com.renquant.$p.plist
done
# verify (read-only)
launchctl print "gui/$UID_NUM/com.renquant.run-surface-drift" | grep -iE "run at load|program"
cat /Users/renhao/git/github/RenQuant/logs/rq104/catchup_guard_*_"$(date +%F)".log
/Users/renhao/git/github/renquant-orchestrator-run/ops/run_surface_drift_scan.sh   # guard skips if today's scan ran; else scans
```

Then a follow-up PR deletes `com.renquant.rq104-dawn-preflight` and
`com.renquant.run-surface-drift` from `PENDING_INTENT_INSTALL` and the
`PENDING_PROGRAM_ARGS_INSTALL` entry (the exact-equality tests force it).

**Revert** (restore the calendar-only plists; `<sha>` = this PR's merge-base):

```bash
UID_NUM="$(id -u)"
for p in rq104-dawn-preflight run-surface-drift; do
  launchctl bootout "gui/$UID_NUM/com.renquant.$p" || true
  git -C /Users/renhao/git/github/renquant-orchestrator show <sha>:deploy/com.renquant.$p.plist > ~/Library/LaunchAgents/com.renquant.$p.plist
  launchctl bootstrap "gui/$UID_NUM" ~/Library/LaunchAgents/com.renquant.$p.plist
done
```
and `git revert` the merge commit (restores the appended resolution, the single
dawn verdict, the rq105-local guard paths and the old manifest entries
together), then ff-sync `-run`.

## Not done / limits

- The dirty-tree allow-list is a judgement: docs/README/generated only, closed
  by default. A dirty `requirements.txt` or `Makefile` BLOCKS (they are not
  import paths, but they are not docs either); widen the list in a reviewed
  change if that ever pages for the wrong reason.
- The dawn preflight's `session` cutoff is the session close (13:00 PT), not
  13:55: a preview after the close previews a run that already happened.
- The drift wrapper's dated log lives next to the launchd `.out`; no
  `evidence_glob` is declared for it (the liveness scan's attribution surface
  is a separate decision).
- `import_resolution_check` still hard-codes the umbrella path for
  `current.env`; the env override (`RENQUANT_SUBREPO_ROOT`) is what tests use.
