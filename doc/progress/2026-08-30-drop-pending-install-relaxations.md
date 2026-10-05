# Drop the PENDING_* install relaxations (plists landed 2026-08-30); the drift-manifest tests are hermetic

STATUS:    delivered — test file + manifest comments + MID addendum, this PR
           only. Nothing installed, no `launchctl`, no write to
           `~/Library/LaunchAgents`, no live-tree or `renquant-orchestrator-run`
           mutation. The one real-disk action in this session was the drift
           scan run READ-ONLY (§Drift scan), with the ntfy send suppressed
           (`RENQUANT_NO_NOTIFY=1`, honoured at `renquant_common/notify.py:151`)
           so the operator was not paged twice for the standing issue.

WHAT:      (1) The four `PENDING_INTENT_INSTALL` entries (rq104-dawn-preflight,
           run-surface-drift, rq105-batch-scores-export,
           rq105-session-scheduler) and the one `PENDING_PROGRAM_ARGS_INSTALL`
           entry (run-surface-drift, previous digest `bbd8f472…`) are deleted
           from `tests/test_run_surface_drift_check.py` — the exact-equality
           tests #1087/#1098 wrote to FORCE this went red the moment the
           operator landed the plists (11:29 PT), exactly as designed. The
           dicts stay, EMPTY, with their history condensed. (2) The tests that
           read `~/Library/LaunchAgents` are replaced by hermetic ones: the
           COMMITTED manifest is exercised against fixture plists under
           `tmp_path` in both directions — installed == manifest (all 40 jobs,
           intents included; plus the five committed reviewed plists copied in
           verbatim) and installed != manifest (the pre-landing disk replayed:
           four absent `RunAtLoad` keys → exactly four intent alarms; the dawn
           preflight's previous explicit `false`; the quote logger's
           `KeepAlive` dict vs `true`; the drift job's PREVIOUS
           ProgramArguments → exactly one `ProgramArguments CHANGED`; missing +
           unmanifested presence). The real-disk partition survives as ONE
           explicitly-marked opt-in smoke class, skipped unless
           `RENQUANT_DRIFT_DISK_TESTS=1`. (3) The five manifest comments record
           the landing and point at the fixture test that now carries the
           alarm-on-rollback proof.

WHY/DIR:   MID `doc/memory/mid-term/serving-reliability.md` (addendum
           2026-08-30 defect #6, updated: landing recorded, remaining operator
           item named). A unit test that measures the operator's disk is
           skipped on every other machine (CI never ran it) and red on the
           operator's for the whole merge→bootstrap window — a red default
           suite trains its reader to ignore red (memory:
           tests-that-measure-the-operators-disk; the 2026-07-31 lesson). The
           SCHEDULED drift scan is the instrument for disk != manifest; the
           tests' job is to prove the scan alarms on every shape the
           relaxations used to name, without a disk.

EVIDENCE:  §4(b) block — ops-surface claim, no model/data claim.
           artifact:      `tests/test_run_surface_drift_check.py`,
                          `ops/launchd_manifest.json` (comments only — the
                          non-comment content is asserted byte-equal before /
                          after by the edit script), `doc/memory/mid-term/
                          serving-reliability.md`
           prod or exp:   prod run surface (launchd jobs); nothing deployed by
                          this PR
           existing data: reported by the operator session `[VERIFIED
                          2026-08-30 11:29 PT]`: the four plists landed
                          (bootout / cp / bootstrap; `launchctl print` runs=1)
           reproduced:    `[VERIFIED 2026-08-30 11:47 PT, read-only, this
                          worktree]` installed plists vs manifest for all four
                          labels: ProgramArguments sha256 equal
                          (743f3a9e…/97ef0267…/ab2385c2…/4321312e…),
                          `RunAtLoad=True` on all four, plist mtimes 11:29:46;
                          the read-only drift scan (§Drift scan) reports ONE
                          issue, the standing watchlist-trainability line, and
                          ZERO launchd-surface issues.
           tests:         focused file `[VERIFIED 2026-08-30 11:55 PT]`:
                          default env **43 passed, 5 skipped** (the 5 = the
                          opt-in disk class); `RENQUANT_DRIFT_DISK_TESTS=1 -k
                          OperatorDisk` on the operator's disk **5 passed**.
                          `make test` = §Tests.
           scope:         "the drift-manifest test file and the manifest's
                          comment strings, on main at 52b16b3d; no IC / Sharpe /
                          APY number is claimed"

NEXT:      operator: ff-sync `renquant-orchestrator-run` (at 2ed9d962 = #1098,
           now 2 behind main: #1096 + #1099, which merged 12:02 PT while this
           PR was built — this branch is rebased onto f89f1519) BEFORE Mon
           2026-08-31 06:00 PT — #1099's zsh-portable guard is what the
           06:15/06:25 rq105 wrappers source. No plist action remains. Anyone
           wanting the real-disk reading runs
           `RENQUANT_DRIFT_DISK_TESTS=1 pytest tests/test_run_surface_drift_check.py -k OperatorDisk`.

## Bottom line

The relaxations did their job: they were bounded by exact-equality tests that
turned red when the operator landed the plists, and this change deletes them.
It also stops the test file from reading the operator's disk by default — the
committed manifest is now proven in both directions against fixture plists, on
any machine.

## What changed (files)

| file | change |
|---|---|
| `tests/test_run_surface_drift_check.py` | `PENDING_INTENT_INSTALL` = `{}` (was 4 entries), `PENDING_PROGRAM_ARGS_INSTALL` = `{}` (was 1). New hermetic class `TestCommittedManifestAgainstFixtures` (9 tests): every sha is its args' digest; installed == manifest for all 40 jobs; the 5 committed reviewed plists (`deploy/` dawn + drift, `ops/renquant105/` export + scheduler + quote-logger) copied into a tmp agents dir → clean; the four landed labels declare `run_at_load`; absent `RunAtLoad` on those four → exactly 4 `intent NOT installed (manifest=True != disk=None)`; explicit `false` → `disk=False`; `KeepAlive=true` vs the dict → 1 alarm; the drift job's previous ProgramArguments (`.venv/bin/python … run_surface_drift_check.py`, digest pinned = `bbd8f472…` ≠ manifest) → exactly 1 `ProgramArguments CHANGED` naming the wrapper; missing + unmanifested. The real-disk partition (`PENDING_INSTALL` / `PENDING_UNINSTALL` / intent / program-args buckets, residual == []) moved to `TestOperatorDiskSurface`, `@operator_disk` = `skipif(os.environ.get("RENQUANT_DRIFT_DISK_TESTS") != "1")`; a machine-independent test pins that the class is marked and the variable name. The previous-digest-is-not-the-reviewed-one guard stays machine-independent (iterates the now-empty dict). |
| `tests/test_momentum_train_job_surface.py` | its cross-file import of `PENDING_INSTALL` (`test_the_pending_install_state_is_fully_retired_for_this_job`) now reads `TestOperatorDiskSurface`, where the set moved; docstring's "exact-equality set against launchctl" claim updated to name the daily scan + the opt-in test. Found by the first `make test` (AttributeError), fixed, full suite re-run. |
| `ops/launchd_manifest.json` | comments only: the four `_run_at_load_comment`s and drift's `_program_args_comment` gain a `LANDED 2026-08-30 11:29 PT` sentence naming the fixture test that carries the alarm. `program_args` / `program_args_sha256` / intents untouched (asserted). |
| `doc/memory/mid-term/serving-reliability.md` | addendum 2026-08-30 defect #6: landing recorded `[VERIFIED]`, relaxations deleted, tests hermetic, remaining operator item = `-run` sync. |
| `doc/progress/2026-08-30-drop-pending-install-relaxations.md` | this file. |

## Drift scan (read-only, real disk) `[VERIFIED 2026-08-30 11:47 PT]`

Run from this worktree exactly as the launchd job runs it — the installed
`com.renquant.run-surface-drift.plist` sets `RQ_ROOT=/Users/renhao/git/github/RenQuant`,
`RQ_ORCH_ROOT=/Users/renhao/git/github/renquant-orchestrator-run`,
`PYTHONPATH=<-run>/src:<-run>/ops`, and `ops/run_surface_drift_scan.sh`
restates the same and calls `$RQ_ROOT/.venv/bin/python ops/run_surface_drift_check.py`
— plus `RENQUANT_NO_NOTIFY=1` (no page) and `PYTHONDONTWRITEBYTECODE=1`:

```
$ RENQUANT_NO_NOTIFY=1 RQ_ROOT=/Users/renhao/git/github/RenQuant \
  RQ_ORCH_ROOT=/Users/renhao/git/github/renquant-orchestrator-run \
  PYTHONPATH=/Users/renhao/git/github/renquant-orchestrator-run/src:/Users/renhao/git/github/renquant-orchestrator-run/ops \
  /Users/renhao/git/github/RenQuant/.venv/bin/python ops/run_surface_drift_check.py
2026-08-30T11:47:17 INFO: umbrella deploy lag: none (main == origin/main 3e854ec6), fetched 0.0d ago
2026-08-30T11:47:17 INFO: launchd: 0 of 40 manifested job(s) are NOT loaded
2026-08-30T11:47:17 INFO: import-resolution OK — 14 symbols resolve as reviewed (resolved against the pinned runtime /Users/renhao/git/github/RenQuant/.subrepo_runtime/repos)
2026-08-30T11:47:17 INFO: checkout-freshness RenQuant: SKIPPED_UMBRELLA (- behind)
2026-08-30T11:47:17 INFO: checkout-freshness renquant-orchestrator-run: FRESH (1 behind)
… 27 `INFO: pythonpath com.renquant.<job>: declares a deterministic root` lines …
2026-08-30T11:47:17 INFO: pythonpath: 16 of 31 manifested wrapper(s) inspected here + 15 inspected read-only across a declared boundary; 0 out of scope; 0 unowned
2026-08-30T11:47:17 INFO: watchlist-trainability: served=145 trained=142 unaccounted=3
2026-08-30T11:47:17 watchlist-trainability: 3 served ticker(s) are absent from the training watchlist and can never receive a per-ticker artifact — CRWV, RKLB, SPCX. They will be skipped `no_artifact` every session. Fix: add them to /Users/renhao/git/github/RenQuant/backtesting/renquant_104/strategy_config.json, or remove them from the served watchlist; a ticker cannot be declared non-trainable while absent from the training universe (orch#1020).
EXIT=1
```

Issue list: **1** — the standing `watchlist-trainability` CRWV/RKLB/SPCX line
(orch#1020, not this PR's). No `ProgramArguments CHANGED`, no `intent NOT
installed`, no missing / unmanifested job: the drift scan's own
ProgramArguments (`97ef0267…`, the wrapper) and `RunAtLoad` are installed, so
the two alarms #1098 §Landing predicted for the pre-install window are gone.
(Also visible: the import-resolution check now reports OK against the pinned
runtime — #1098's fix, running from `-run` at 2ed9d962.)

## Tests

- Focused: `tests/test_run_surface_drift_check.py` default env **43 passed,
  5 skipped**; `RENQUANT_DRIFT_DISK_TESTS=1 … -k OperatorDisk` **5 passed**
  `[VERIFIED 2026-08-30 11:55 PT]`.
- `make test` (worktree on 52b16b3d + this change, `PYTHON=` the RenQuant venv
  interpreter, absolute `*_SRC` sibling paths, `PYTHONDONTWRITEBYTECODE=1`):
  **7 failed / 7164 passed / 15 skipped** in 333s `[VERIFIED 2026-08-30 12:03 PT]` (first run, before the `test_momentum_train_job_surface.py` importer fix: 8 failed / 7163 passed — the extra one was the AttributeError on the moved `PENDING_INSTALL`). The 2 `PENDING_INTENT_INSTALL` / `PENDING_PROGRAM_ARGS_INSTALL` exact-set failures from the known-11 list (`doc/progress/2026-08-30-catchup-guard-zsh-portable.md`, measured on 2ed9d962) are GONE. The 7 that remain are all on that list and environment/path-bound, none in files this PR touches: `test_cli` FileNotFound (worktree path), `test_g2v3_stage_i2_binding` ×2 (`spy_daily.sha256` vs disk), `test_goal3_public_export_resolution` (pipeline-revision record), `test_recapture_emitter_contract` ×2 + `test_rq104_silent_refusal_sentinel` (`scripts/weekly_wf_promote.sh` contract-line drift). The list's other 2 (`test_shadow_serving_skips_leave_evidence` ×2) did not fail in this run; no fresh baseline on 52b16b3d was taken, so that delta is unattributed (not this PR's files).

## Not done / limits

- The opt-in disk class is now the ONLY place the real disk is read by a test,
  and it is skipped by default everywhere — so the "goes red the moment the
  install lands" forcing function fires only when someone opts in. The
  scheduled drift scan remains the daily reminder for the pre-install window
  (containment protocol c), which is the instrument that was always meant to
  carry it.
- The `-run` sync is the operator's; this PR does not touch that checkout.
