# 2026-07-07 — Fix rq105 shadow-serving argparse crash

**PR**: orchestrator fix

## Problem

`shadow_realtime_serving` CLI crashes at argparse with:
```
error: the following arguments are required: --feature-snapshot-json
```

`run_shadow_serving.sh` never passes this arg because no producer for the
feature-snapshot file exists yet.

## Round 1 (reverted — see round 2)

Made `--feature-snapshot-json` optional (`required=True` → `default=None`),
falling back to a bootstrap `daily_features` map (empty values) when absent.

## Round 2 (codex review — fixed)

STATUS: fixed
WHAT: codex correctly rejected round 1 — it weakened the module's Codex #221
provenance contract (every logged row must bind to immutable feature state)
without restoring any actual functionality. Investigation confirmed: (a)
`main()`'s `if scorer is None: return 2` fires unconditionally for every CLI
invocation, since the CLI has no mechanism to inject a real `ShadowScorer`
at all — Stage-3 `feature_matrix_fn` wiring doesn't exist yet, so making the
feature-snapshot argument optional could never let the script reach
`run_shadow_serving()` regardless; (b) even if a scorer *were* injected, the
downstream `RunProvenance.validate()` (Codex #221's own fail-closed check)
would reject a bootstrap/no-provenance snapshot before logging anything,
since `feature_snapshot_digest` would be empty — so no row would ever
actually get polluted. Round 1's change bought nothing operationally while
muddying the CLI's documented contract.
WHY-DIR: the real root cause is that `run_shadow_serving.sh` invokes a
binary whose required argument it structurally cannot supply (no producer
exists) — the same class of prerequisite-missing case the script already
handles gracefully for the `$SCORES`/`$META` bundle at the top. The fix
belongs at the caller, not by loosening the callee's contract.
EVIDENCE: reverted `shadow_realtime_serving.py` to be byte-identical to
`origin/main` (confirmed via `git diff origin/main` — empty). Added a
`$FEATURE_SNAPSHOT` existence check to `run_shadow_serving.sh` mirroring the
existing `$SCORES`/`$META` skip-with-notify pattern, and wired
`--feature-snapshot-json "$FEATURE_SNAPSHOT"` into the actual invocation
(previously never passed at all). The script now exits cleanly with a clear
notification ("no feature-snapshot producer yet") instead of an argparse
traceback, 4x/day, until Stage-3 wiring lands. 17/17 module tests pass
(`bash -n` confirms shell syntax).
NEXT: both remain genuinely separate, unbuilt follow-up items — not
addressed here: (1) a feature-snapshot producer that materializes
`data/rq105/feature_snapshot_<date>.json`, (2) Stage-3
`feature_matrix_fn`/scorer-injection wiring so the CLI can construct a real
`ShadowScorer` via `load_pinned_panel_scorer`. Shadow-serving remains an
inert, observe-only collector until both land — this fix only stops the
shell script from crashing on a call it can never satisfy today.

## Scope

`src/renquant_orchestrator/shadow_realtime_serving.py` — reverted to main
(no change). `ops/renquant105/run_shadow_serving.sh` — added the
feature-snapshot prerequisite check + wired the flag.
