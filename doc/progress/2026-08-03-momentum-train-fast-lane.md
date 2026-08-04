# Weekly momentum job trains the v1_fast shadow lane — second, NON-FATAL step (model#199 item 2)

**Date:** 2026-08-03 · `renquant-orchestrator` · GOAL-8 fast arm

STATUS: reviewed-surface change only. The wrapper is the merged-but-dark →
now-installed weekly job's source in THIS repo; the RUNNING copy is the
orchestrator-run checkout, so this change is dark until that checkout syncs
(merged is not deployed). Nothing is installed/booted here; no manifest or
plist change (program_args untouched — the wrapper path IS the program, so
the manifest digest is unchanged by construction).
WHAT: `ops/renquant104/momentum_train_weekly.sh` runs the SAME pinned TRAIN
CLI a second time after the v0 step:
`--params-version v1_fast --out-root <serving root>/artifacts/momentum_fast`
— its own publish set + its own independent digest-chained ledger (the path
the s104 `momentum_fast_v1_shadow` entry pins, #199 item 3).
Contract decisions, each pinned by a test in
`tests/test_momentum_train_job_surface.py`:
- V0 INVOCATION FLAG-FREE: byte-identical to the pre-#199 reviewed command,
  so the prod-MoE-bound lane's meaning cannot change under an old OR new
  pinned CLI (an old pinned CLI simply refuses the fast step with argparse
  exit 2 — loud in the dated log, invisible to the v0 rc).
- FAST LANE NON-FATAL: runs after v0 regardless of v0's outcome; `fast_rc`
  is logged in the end marker but NEVER propagated — launchd records the v0
  verdict, a fast failure can never block or mask the slow artifact. A dead
  fast lane stays loud downstream: the s104 fast shadow entry's daily health
  record goes unresolved/stale (the shadow-scorer sentinel's surface).
- EVIDENCE: same dated log (`momentum_train_<date>.log`, exec-redirect-first
  contract unchanged); both lanes write their own verdict lines and the end
  marker carries `rc=<v0> fast_rc=<fast>`.
- SHARED DATED BASENAME: both lanes publish `<cutoff>/momentum_residual_v0.json`
  — the pipeline loader hardcodes that basename
  (`momentum_residual_scorer.MOMENTUM_DATED_ARTIFACT_BASENAME`
  `[VERIFIED — read this session]`); identity is the artifact's
  kind/params_version/content_sha256 (v1_fast in the fast set), never the
  filename. Pipeline follow-up: derive the basename from the ledger row.
WHY: model#199 build order item 2 — the weekly Saturday job produces BOTH
artifacts, v0 then v1_fast, each into its own ledger; the fast lane is the
operator's daily-ntfy shadow patrol, explicitly not prod-bound.

Tests updated/added (same file, existing patterns): the invocation allowlist
is now EXACTLY TWO `$PYTHON` runs (v0 flag-free, then v1_fast), out-root
convention covers `artifacts/momentum_fast`, argv is the full two-invocation
reviewed sequence, rc pass-through re-pinned as "the wrapper's exit IS the v0
code", plus two lane-independence behavior tests (fast fails 9 → wrapper 0
with the fast verdict in the log; v0 fails 3 → fast still runs, wrapper 3).

EVIDENCE:

```
tests:  5502 passed / 2 skipped / 0 failed, full suite, this worktree.
        [VERIFIED — this session]
deploy: run surface = orchestrator-run checkout + pinned model runtime;
        the fast step goes live only when (a) this repo's run checkout
        syncs past this PR and (b) the umbrella model pin advances past the
        model-side --params-version PR. Until (b), Saturday logs will show
        the designed fast-step exit-2 refusal while v0 is untouched.
scope:  "one wrapper + its test file + this doc; manifest/plist untouched;
         nothing installed, no artifact written by agent hands."
```

## Revert

git revert restores the single-lane wrapper; the fast ledger (if any was
published by then) simply stops growing — the append-only store needs no
cleanup, and v0 is untouched on every path.
