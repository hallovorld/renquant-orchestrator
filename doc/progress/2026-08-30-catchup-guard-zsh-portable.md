# catchup_guard.sh is zsh/sh/bash portable — the rq105 wrappers run /bin/zsh (regression from #1098; Monday 06:15 export would fail)

STATUS:    delivered — fix-forward in `ops/catchup_guard.sh` + a cross-shell
           test file, this PR only. Nothing installed, no `launchctl`, no
           write to `~/Library/LaunchAgents`, no live-tree or
           `renquant-orchestrator-run` mutation. The plists reviewed in #1098
           are CORRECT and need no change; landing is ONLY the `-run` ff-sync
           (§NEXT).

WHAT:      `ops/catchup_guard.sh` (the shared boot catch-up guard #1098 moved
           out of `ops/renquant105/rq105_catchup_guard.sh`) is SOURCED by the
           two rq105 wrappers `ops/renquant105/run_batch_scores_export.sh`
           and `run_session_scheduler.sh`, whose shebang AND plist
           ProgramArguments are `/bin/zsh`, under `set -u`. #1098's required-
           env check was `for req in $required; do eval "val=\${$req:-}"`:
           zsh does not word-split an unquoted `$var`, so the loop ran ONCE
           over the whole name list, the eval became
           `${RQ_ROOT CATCHUP_CUTOFF_HELPER PYTHONPATH:-}` (zsh: "bad
           substitution"), `val` was never assigned, `set -u` killed the
           wrapper → both rq105 jobs exit 1 (the wrapper's `*) FATAL … exit 1`
           arm never even ran: the shell died inside the function). The
           bash-shebang sourcers (`ops/run_surface_drift_scan.sh`,
           `ops/renquant104/dawn_funnel_preflight.sh`) were unaffected; #1098's
           tests ran the guard under bash only. Fix: the env check is now
           explicit NAME + `"${VAR:-}"` pairs through a tiny `_require_env`
           helper — no `eval`, no indirect expansion, no name-list splitting —
           and the guard's header states the portability contract (common
           subset of zsh/bash/POSIX sh under `set -u`). Semantics are
           unchanged: RUN iff slot ≤ HHMM < cutoff AND an output is missing;
           SKIP with exactly one stamped line; rc 2 FATAL on missing env, same
           messages, same order (RQ_ROOT, then CATCHUP_CUTOFF_HELPER,
           PYTHONPATH in `session` mode only).

WHY/DIR:   MID `doc/memory/mid-term/serving-reliability.md` (addendum
           2026-08-30, defect #6 → this is #6's own regression, recorded
           there). A guard that protects the serving chain from a boot-dropped
           slot must not itself be the reason the slot fails; and a test
           suite that exercises a SOURCED file under one shell while its
           production callers run another is the "green check that covered
           nothing" class (memory: green-check-that-covered-nothing,
           assumed-tree-is-not-the-running-tree). The test now runs the
           decision matrix under every shell a caller uses and pins each
           caller's shebang to that set, so a future caller in a fourth shell
           fails the test rather than the 06:15 job.

EVIDENCE:  §4(b) block — ops-surface claim, no model/data claim.
           artifact:      `ops/catchup_guard.sh` (this branch), the four
                          sourcing wrappers (unchanged), stub cutoff helper
                          in tmp_path
           prod or exp:   prod run surface (rq105 launchd jobs); NOT deployed
                          by this PR
           existing data: reported by the operator session
                          `[VERIFIED 2026-08-30 11:29 PT, after landing the
                          #1098 plists]` — the rq105 wrappers under zsh die
                          with, verbatim:
                              (eval):1: bad substitution
                              launchd_catchup_guard:25: val: parameter not set
           best-known?:   yes — this branch's guard is the only known variant
                          that passes the decision matrix under all three
                          shells; `origin/main`'s guard (#1098, 2ed9d962) is
                          the WORSE one (bash/sh OK, zsh dies). No competing
                          variant exists.
           scope:         "this is `ops/catchup_guard.sh` + its four sourcing
                          wrappers, prod run surface (rq105 launchd jobs), vs
                          existing best `origin/main` 2ed9d962 = dies under
                          zsh; branch = rc/stdout/stderr/log byte-identical
                          under zsh/bash/sh (26/26 matrix)". Ops-surface
                          claim only: no model/data/IC claim, nothing
                          deployed (no `-run` sync, no plist change).
           reproduced:    `[VERIFIED 2026-08-30 11:31 PT]` in this worktree,
                          `origin/main` guard, `env -i … /bin/zsh -c 'set -u;
                          . ops/catchup_guard.sh; launchd_catchup_guard
                          batch-scores-export 2026-08-31 0620 0615 session
                          <log> <missing>'` → the same two lines, no `rc=`
                          echoed (the shell died); `/bin/bash` and `/bin/sh`
                          → `rc=0` + one RUN line.
           after fix:     same command under `/bin/zsh`, `/bin/bash`,
                          `/bin/sh` → `rc=0`, identical RUN line; usage / bad
                          cutoff / missing `CATCHUP_CUTOFF_HELPER` → identical
                          stderr, `rc=2` under all three.
           tests:         `tests/test_catchup_guard_shell_portability.py`
                          against `origin/main`'s guard = **14 failed / 12
                          passed** (the 12 are the pre-loop usage errors,
                          identical in every shell); against this branch =
                          **26 passed**. Focused suite
                          (`test_catchup_guard_shell_portability.py`,
                          `test_catchup_guard_shared.py`,
                          `test_rq105_liveness_serving_chain.py`,
                          `test_dawn_preflight_wrapper.py`) = **118 passed**.
                          `make test` = see §Tests.

NEXT:      operator: ff-sync `renquant-orchestrator-run` to `main` after this
           merges, BEFORE Mon 2026-08-31 06:00 PT (the 06:15 batch export and
           06:25 scheduler source the guard from the `-run` checkout). No
           plist change, no `bootout`/`bootstrap`: the #1098 plists already
           landed are correct. Then Monday's
           `logs/rq105/catchup_guard_batch-scores-export_2026-08-31.log`
           should carry ONE `SKIP … already present` line (calendar fire ran
           it) or one `RUN` line (a boot caught it up), never a FATAL in
           `batch_scores_export_2026-08-31.log`.

## Bottom line

`ops/catchup_guard.sh` was POSIX-correct and bash-correct but NOT zsh-correct,
and its two most important callers run zsh. One construct (`for … in
$name_list` + `eval` indirection) did it. Removed; the env check is now three
explicit `${VAR:-}` reads. The tests now execute the guard under the shells its
callers actually use and assert byte-identical behaviour across them.

## What changed (files)

| file | change |
|---|---|
| `ops/catchup_guard.sh` | env check = explicit `_require_env NAME "${NAME:-}"` calls; no `eval`, no `$required` loop; header gains the PORTABILITY contract. Decision logic untouched. |
| `tests/test_catchup_guard_shell_portability.py` (new) | 17-row decision matrix × {`/bin/zsh`, `/bin/bash`, `/bin/sh`} (absent shell = skip, bash mandatory), byte-identical rc/stdout/stderr/log across shells + expected verdict; `set -u` with only the required env; two calls in one shell don't leak state; the rq105 export wrapper's literal guard block (from `CATCHUP_CUTOFF_HELPER=` through `esac`) replayed under `/bin/zsh` + `set -u` with a fake `date +%H%M`; every wrapper that sources the guard has a shebang in the tested set (exact set of four sourcers pinned); a source grep forbids `eval`, `${!`, `local -n`, `[[`, `$'`, `read -a`, `declare`, `typeset`, `setopt`, `shopt` and `for x in $var`. |
| `doc/memory/mid-term/serving-reliability.md` | addendum 2026-08-30 defect #6: regression + lesson line. |
| `doc/progress/2026-08-30-catchup-guard-zsh-portable.md` | this file. |

## Tests

- Focused: 118 passed (four files above) `[VERIFIED 2026-08-30 11:35 PT]`.
- Regression proof: new file vs `origin/main` guard 14 failed / 12 passed;
  vs branch 26 passed `[VERIFIED 2026-08-30 11:36 PT]`.
- `make test` (worktree, `PYTHON=` the RenQuant venv interpreter,
  `PYTHONDONTWRITEBYTECODE=1`): **11 failed / 7149 passed / 10 skipped** in 324s `[VERIFIED 2026-08-30 11:48 PT]`. All 11 fail IDENTICALLY on an `origin/main` (2ed9d962) baseline worktree in the same environment (`11 failed in 4.78s`), so none is caused by this PR: 2 are the `test_run_surface_drift_check.py` `PENDING_INTENT_INSTALL` / `PENDING_PROGRAM_ARGS_INSTALL` exact-set tests that #1098 §NEXT said would flip once the operator landed the plists (they landed 11:29 PT; follow-up PR deletes the entries); the other 9 are environment/path-bound (`test_cli` FileNotFound in the worktree path, `test_g2v3_stage_i2_binding` ×2 `inputs.spy_daily.sha256 != file on disk`, `test_goal3_public_export_resolution` pipeline-revision record, `test_recapture_emitter_contract` ×2 + `test_rq104_silent_refusal_sentinel` `scripts/weekly_wf_promote.sh:714` contract line drift, `test_shadow_serving_skips_leave_evidence` ×2) — a superset of the 6 known pre-existing, none in files this PR touches.

## Not done / limits

- The CI runner has no zsh: the zsh column of the matrix runs only on the
  operator's Mac (it is a `skip`, visibly, on CI — never a silent pass). The
  dash column (`/bin/sh` on ubuntu) is stricter than macOS's `/bin/sh`
  (bash-in-POSIX-mode) and is what CI does exercise.
- `run_session_scheduler.sh` is covered by the shebang test and by the matrix
  row `session-scheduler … 0625`; only the export wrapper's literal block is
  replayed under zsh (the scheduler's block is the same four lines with the
  slot and outputs changed — asserted verbatim by
  `test_rq105_liveness_serving_chain.py §6`).
- Not deployed: `-run` sync is the operator's (§NEXT).
