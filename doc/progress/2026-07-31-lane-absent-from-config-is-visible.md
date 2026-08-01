# GOAL-1 — a watched shadow lane vanishing from config reported CLEAN forever

**Date:** 2026-07-31 · `renquant-orchestrator` · shadow-reliability gates (GOAL-1, layer 3)

## The defect, in the deployed sentinel

`_patrol_lane` has a deliberate quiet branch:

```python
if all(records.get(d) is None for d in days):
    print(... "no signal in window ... — liveness domain, skip")
    return 0
```

That is correct for a window with no runs: liveness is another checker's job. But it is
also the window produced when **the watched lane is removed from the task's
`shadow_models`** — because the record the pipeline emits in that case is *task-level*,
carrying `shadow_name == "__task_level__"`, and the reader retains a record only when its
name matches a watched lane:

```
_matches_shadow_lane('__task_level__')  ->  False       [本次实测 2026-07-31]
_matches_shadow_lane('hf_patchtst')     ->  True
```

So the record parses, is dropped one line later, `records` is empty, and the sentinel
prints *"liveness domain, skip"* and returns **0**.

**A shadow lane disappearing from config is the exact failure GOAL-1 exists to catch, and
it was the one shape that reported clean.**

## How this was found — and a correction to my own claim

`renquant-pipeline#240` fixed the producer half: the task-level record used to carry
`shadow_name = None`, which the validator rejects, so it was discarded at *parse* time
(12 `degraded` rows parsed, 4 `no_shadow_models` rows dropped). I then wrote that the PR
was *"verified by RUNNING the consumer, not by reading it."*

Reviewed `[codex on renquant-pipeline#240]`: *"exercising `is_valid_v1_record` alone
tests parsing, not the consumer path the PR claims to repair."* Correct. **I ran one
function of the consumer and called it the consumer path.** The claim is withdrawn on
that PR; this branch is the repair it was missing.

## The change

1. `read_task_level_states(days)` — a **separate** reader for records whose
   `shadow_name` is the task-level sentinel. Kept out of the per-lane map on purpose:
   merging them would make a lane appear to have reported when it did not exist.
2. `_patrol_lane`'s quiet branch now asks, before going quiet, whether the window carries
   task-level `no_shadow_models` evidence. If it does, the window is not silent — it is
   **evidence the lane is absent from config** — and the sentinel alarms with its own
   subject and remedy (*restore the lane, or retire the sentinel*), not the degradation
   message.

**No new status.** `STATUS_OK / EXPECTED_SKIP / FAULT` is a contract shared with
renquant-pipeline, and lane-absence is not a property of a record — it is a property of
the *set* of records found for a window. So it is decided sentinel-side, where the
question "is my lane still there?" actually lives.

**Why `expected_skip` was the wrong answer** (the design question codex raised): nothing
crashed, so it is not a `fault`; but for a sentinel built so a shadow feed cannot silently
die, "my lane is not configured" **is** the failure. The remedy differs too — restore the
lane, do not debug a scorer.

## Tests — end-to-end through the real reader and patrol path

`tests/test_lane_absent_from_config_is_visible.py`, 8 tests, driving `_patrol_lane`
itself rather than `is_valid_v1_record`:

- the task-level record genuinely yields **no** per-lane record (the premise, pinned);
- a lane absent from config **alarms** with `EXIT_ALARM`, naming days and denominator;
- **anti-vacuity, four ways** — a genuinely silent window still defers to liveness; a
  task-level `disabled` state does **not** alarm (a deliberate off switch is not a
  vanished lane); a healthy lane never reaches the branch; an out-of-window record is
  ignored, so an old line in an append-only sink cannot alarm forever;
- a malformed task-level line neither alarms nor crashes.

The record builder **self-checks against `is_valid_v1_record`**. On this file's first run
it emitted records missing `n_scored`, so nothing parsed and the "no per-lane record"
assertions held for the wrong reason. The self-check makes that failure loud instead of
silent.

Suite: **4939 passed, 2 skipped**.

## Scope

Detection only. It does not restore any lane, and it does not decide whether
`hf_patchtst`'s absence would be deliberate — it makes the state visible so that decision
gets made by someone.
