# 2026-08-02 — sentinel: task-level removal evidence scoped to the pinned config

STATUS: complete (built stacked on #764, opened after its merge; 4 scoping
regressions + the #240 removal-alarm suite unchanged)

WHAT: `read_task_level_states` gains config-identity scoping (orch#765):
when a config is supplied, a task-level record counts as evidence about THE
PINNED CONFIG only if its `task_config_sha256` (pipeline#257, pinned in
RenQuant#556) matches the config's canonical digest; a mismatch is another
profile's record (excluded); a missing stamp is AMBIGUOUS — returned
separately and printed by the patrol, never silently counted as removal
evidence. With no config supplied the #240 contract is untouched. Digest =
the producer's own recipe (runtime import, identical local recompute as
fallback).

WHY/DIR: GOAL-1, the measured shadow_blend vector (pipeline#256): the
companion job writes a task-level `no_shadow_models` into the shared sink
AFTER the main run every session, and last-record-per-date-wins made that
the per-day state from the WRONG profile — reachable by the
disappeared-from-config clause on any record-less window (momentum on a
skipped day; previous_primary now).

EVIDENCE:
- artifact: this PR's diff; 4 scoping regressions (stamped-matching counts,
  mismatched excluded, unstamped ambiguous-not-evidence, no-config keeps the
  #240 contract); first-draft overreach (no-config also ambiguous) was
  CAUGHT by the existing removal-alarm tests and corrected to
  activate-only-with-identity
- prod or exp: sentinel module + tests only
- existing data: full suite 5468 passed / 14 skipped / 0 failed on this head
- best-known?: yes — the vector, the stamp, and the companion's stamping
  path were all machine-verified earlier tonight (pipeline#256/#257 records)
- scope: `read_task_level_states` + its one consumer; per-lane reading,
  classification, arming window untouched

NEXT: none — Monday's stamped records make the scoping live end-to-end.
