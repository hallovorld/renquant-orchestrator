# Momentum pipeline slice 5 — the REVIEWED-SURFACE half of the weekly TRAIN job (merged-but-dark)

STATUS: planned (the reviewed surface merges now and is deliberately DARK;
nothing runs until the one-grant deployment batch below — model#195 build
order item 5, grant ordering fixed by model#197).
WHAT: `com.renquant.momentum-train-weekly` declared on the reviewed launchd
surface: `ops/renquant104/momentum_train_weekly.sh` (wrapper),
`ops/renquant104/com.renquant.momentum-train-weekly.plist` (Saturday 05:00),
the `ops/launchd_manifest.json` entry (42 -> 43 jobs
`[VERIFIED — json.load, this session]`) with the
`_pending_install_comment` declaration mirroring the
`com.renquant.rq104-model-freshness` precedent, and the label added to the
bounded `PENDING_INSTALL` set in `tests/test_run_surface_drift_check.py`
(the 2026-07-31 retarget precedent: bound the named
declared-but-not-yet-installed state in tests; the liveness scan keeps
reporting UNJUDGEABLE_NO_PLIST as the designed reminder). New per-job suite
`tests/test_momentum_train_job_surface.py` pins the surface's self-agreement
and the wrapper's behavior contract.
WHY/DIR: the merged momentum-pipeline design (model#195) makes the weekly
TRAIN job build-order item 5, operator-gated; model#197 (build-order
amendment) fixes the serving-path convention — the JOB publishes
`artifacts/momentum/<cutoff>/momentum_residual_v0.json` + the append-only
ledger under the strategy serving root, written by the job at run time, never
by agent hands — and orders the grant batch so slice 4's s104 `shadow_models`
config never references an unresolvable path (the AC1 static resolve gate).
Landing the reviewed surface first gives the install something to be checked
against, exactly the rq104-model-freshness shape.

Wrapper design decisions (each pinned by a test):
- ONE deterministic root (#675/#751 rule): model code from the PINNED runtime
  checkout `/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-model`
  (governed by the umbrella pin; the job is only as fresh as the run-surface
  sync), `PYTHONPATH` exported to its `src/`, NO `[ -d ... ] || VAR=` fallback
  — asserted with the drift scan's own `_FALLBACK_RE` plus an anti-vacuity
  fixture, and by running `_scan_wrapper_text` over the wrapper source.
- exec-redirect FIRST (the conditional-retrain silent-pre-exec-death lesson,
  orch#754 trail), deliberately the inverse of
  `run_model_freshness_monitor.sh`'s #638 ordering: the only pre-exec step is
  `mkdir -p` of the log dir, so every refusal lands in the dated log
  (`logs/rq104/momentum_train_<date>.log`) with a REFUSED line and a terminal
  rc marker. The #638 concern (fresh evidence for a run that never happened)
  is answered by CONTENT: log existence proves the wrapper fired; the log body
  carries the verdict. Regression-tested: a missing TRAIN CLI refuses rc 64
  AND leaves the dated log naming the unmet precondition.
- exit codes: 64 = wrapper refusal (distinct from every CLI code); the TRAIN
  CLI's codes pass through unswallowed (0 trained | 2 usage | 3 surfaces
  missing | 4 artifact exists | 5 ledger refused
  `[VERIFIED — read from model goal7/momentum-train-package
  tools/momentum_train_run.py, this session]`).
- invocation allowlist: exactly ONE `$PYTHON` command runs and it is the TRAIN
  CLI with `--asof $(date +%F) --out-root <serving root>/artifacts/momentum`;
  the wrapper itself writes nothing outside the log dir (tree-diff test).

Schedule: Saturday 05:00 (Weekday=6). WHY: the design fixes a weekly cadence
"aligned with the WF world"; `weekly-wf-promote` and
`weekly-fundamental-refresh` both fire Saturday 04:00 `[VERIFIED — plutil read
of the installed plists, 2026-08-02]`, so 05:00 trains over fresh
Friday-close surfaces after that refresh hour, and stays clear of Saturday
05:30 — the slot the retiring `weekly-retrain-patchtst` still occupies until
its #755 bootout grant executes — so the two grants stay uncoupled.

Serving root ground truth: s104 `artifact_path` values (`artifacts/prod/...`,
`artifacts/shadow/...`) resolve under
`/Users/renhao/git/github/RenQuant/backtesting/renquant_104`
`[VERIFIED — both directories exist there and the served shadow artifact
panel-clf.top-decile.fwd60.json lives at
backtesting/renquant_104/artifacts/shadow/, read 2026-08-02]`; the wrapper's
out-root is therefore `backtesting/renquant_104/artifacts/momentum` and the
CLI appends `<asof>/momentum_residual_v0.json` + the ledger itself.

EVIDENCE:
  artifact:      ops/renquant104/momentum_train_weekly.sh +
                 ops/renquant104/com.renquant.momentum-train-weekly.plist
                 (plutil -lint OK `[VERIFIED — this session]`) +
                 ops/launchd_manifest.json (43 jobs, digest re-derived with
                 program_args_digest `[VERIFIED — test, this session]`) +
                 tests/test_momentum_train_job_surface.py (20 tests) +
                 tests/test_run_surface_drift_check.py (PENDING_INSTALL + 1)
  prod or exp:   prod-adjacent but merge-inert — the reviewed surface only; no
                 plist is installed, no launchd job/config/artifact/state is
                 touched by this merge; the wrapper is scheduled by NOTHING
                 until the grant.
  existing data: touched suites 120 passed, 0 failed `[VERIFIED — pytest over
                 the six drift/wrapper/manifest/liveness suites, this
                 session]`; full suite baseline before this change 5419
                 passed / 14 skipped; after: see PR body (measured at the
                 same commit as submission). The exact-equality
                 declared-but-uninstalled test passes against the LIVE
                 ~/Library/LaunchAgents with the new label included
                 `[VERIFIED — this session, operator machine]`.
  best-known?:   yes — mirrors the repo's two reviewed precedents exactly:
                 PENDING_INSTALL (2026-07-31 retarget; rq104-model-freshness
                 `_pending_install_comment`) for declared-not-yet-installed,
                 and #755's PENDING_UNINSTALL for the mirror state; plus the
                 #638 install-precondition comment shape for the two
                 bootstrap preconditions (run-checkout wrapper + pinned model
                 CLI).
  scope:         2 new ops files + 1 manifest entry + 1 test-set line + 1 new
                 test file + this doc. No src/ change; no production input
                 touched.

## Deployment grant checklist — ONE operator grant batch (SKELETON; the grant
## is NOT requested by this PR)

Ordering per model#197: job installed -> first artifact published -> s104
config merged -> pin advance. Pin set: model + s104 + run-checkout. Each item
names its revert. Until (b), the liveness scan's UNJUDGEABLE_NO_PLIST on this
label is the designed reminder.

(a) PRECONDITIONS (the manifest's `_install_precondition_comment`):
    model#196 merged (it is OPEN and blocked on #195's merge order as of
    2026-08-02) and the umbrella model pin advanced past it; run surfaces
    synced. Verify BOTH, literally:
    `test -f /Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-model/tools/momentum_train_run.py`
    `test -x /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant104/momentum_train_weekly.sh`
    Revert: restore the prior model pin via the standard flow; no machine
    state changes in this item.

(b) INSTALL the plist (literal commands):
    `cp /Users/renhao/git/github/renquant-orchestrator-run/ops/renquant104/com.renquant.momentum-train-weekly.plist ~/Library/LaunchAgents/`
    `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.renquant.momentum-train-weekly.plist`
    Revert:
    `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.renquant.momentum-train-weekly.plist && rm ~/Library/LaunchAgents/com.renquant.momentum-train-weekly.plist`

(c) FIRST ARTIFACT: wait for the Saturday 05:00 fire (or
    `launchctl kickstart gui/$(id -u)/com.renquant.momentum-train-weekly`);
    verify the dated log ends `train CLI exit=0` and the artifact + ledger row
    exist under
    `backtesting/renquant_104/artifacts/momentum/<cutoff>/`.
    Revert: none for the artifact itself (append-only store — a disputed
    artifact is investigated via its ledger row, never deleted); stopping
    further fires is (b)'s revert.

(d) MERGE the s104 slice-4 `shadow_models` config PR (prepared and reviewed in
    advance per model#197 — it rides THIS grant batch, not its own).
    Revert: `git revert` of that merge.

(e) ADVANCE the s104 pin + sync the run checkout(s) so the daily run reads the
    new config and the AC1 static resolve gate sees a resolvable
    `artifacts/momentum/...` path at every point (merged != deployed).
    Revert: restore the pin via the same flow + re-sync.

NEXT: (1) after (b), `test_declared_but_uninstalled_jobs_are_exactly_the_named_set`
goes red with `resolved=['com.renquant.momentum-train-weekly']` — the designed
prompt to DELETE the PENDING_INSTALL entry in a small follow-up PR (the #755
follow-up shape; the relaxation cannot outlive the state it names). (2) the
slice-4 s104 config PR itself (separate repo, prepared pre-grant). (3) slice 3
(the recurring TEST harness) proceeds independently in renquant-model.

AC6 gate-design rule: N/A — no capital-admission gate is added or tightened;
this declares a shadow-lane training job that cannot take a name or the book
out of tradeable.
