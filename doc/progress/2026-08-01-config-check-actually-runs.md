# GOAL-1 — the drift check I merged an hour ago never ran

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-1, shadow-reliability gates

## The finding, about my own merged work

`orch#702` added the config-lane drift check behind `--config`, **with no default**.
Measured `[本次实测 2026-08-01]`:

- `RQ104_STRATEGY_CONFIG` appears **only** in that file's own default and its own
  *"not requested"* message — `git grep` over `ops/` and `src/` returns nothing else;
- it is set in **no** installed plist.

**So the check has never run.** Merged and never invoked is worth exactly nothing — a rule
this repo has, and one I had applied to five *other* detectors in `orch#701` earlier the
same session.

## The fix

`--config` now defaults to a resolved path, using the same chain shape as the ops-audit
wiring:

1. `RQ104_STRATEGY_CONFIG`
2. `<github root>/renquant-strategy-104/configs/strategy_config.json`, derived from the
   file's own location

**It stops at the PINNED config on purpose** — twin-registry **R5** records that the runner
reads the pinned subrepo copy, not the umbrella one, and a drift check pointed at the wrong
surface would answer a different question.

**An unresolvable default returns `""`**, which `main` still reports as *NOT REQUESTED* and
keeps quiet. A machine without the pinned checkout must not acquire a permanent alarm, and
**quiet-when-absent and quiet-when-clean are different states — both are printed.**

## Verified against the live surface

With the default resolving, the *NOT REQUESTED* line is **gone** (the check runs) and no
lane-drift finding appears (**0 unwatched lanes**, as measured when #702 landed).

**The sentinel's exit code is 8 either way, and that is not from this change.** Run with
`--config ""` it is also 8. The alarms are pre-existing and live:

```
[hf_patchtst]              DEGRADED — stale_625d_limit_28d   (2 consecutive sessions)
[topdecile_clf_blend_leg]  DEGRADED — stale_94d_limit_28d    (2 consecutive sessions)
```

**Both watched shadow lanes are stale past the 28-day limit.** The 625-day one is the
PatchTST checkpoint already traced in orch#688; the **94-day clf lane is separate**, and its
`effective_train_cutoff_date` of 2026-04-28 is consistent with it.

## Tests

Three added: the default **resolves to the pinned config** (skipping loudly where the
checkout is absent); the **env var still wins**; and an **unresolvable** default stays
quiet rather than alarming.

One existing test was pointed at the *path* rather than the default — it called `main`
with no `--config` to exercise the not-requested branch, which the resolving default would
otherwise have bypassed. Relying on a default being empty would have made it assert the
absence of the very wiring this file's other tests now require.

Suite: **5096 passed, 2 skipped**.
