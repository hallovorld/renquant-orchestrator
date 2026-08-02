# #758: the scorer sentinel watches the momentum lane — and stays quiet until the lane can exist

STATUS: complete (batch prerequisite for strategy-104#77; blocks the slice-5
batch, not the held config PR).
WHAT: `rq104_shadow_scorer_sentinel.watched_lanes()` REMOVES the retired
PatchTST lane (operator retire decision; config removal merged as s104#75) and
ADDS `momentum_residual_v0_shadow` (config kind `momentum_residual`, the
s104#77 entry) as an MLflow+JSONL lane shaped like the clf leg (`runs_db=None`,
`mlruns_dir=MLRUNS_DIR`, name overridable via `RQ104_MOMENTUM_LANE_NAME`).
Because the lane is watched BEFORE its config entry merges, `_patrol_lane`
gains a PRE-ACTIVATION GATE: it skips — loudly, never silently — only when a
CLEANLY-READ strategy config does not declare the lane AND the lane has never
written a health record here. `main()` feeds the gate the declared name set
(None when the config is absent/unreadable, so "could not read" never
impersonates "not declared").
WHY/DIR: issue #758 — once the shadow config is pinned, a feed-dark or
load-failed momentum lane would have had no sentinel alert or acknowledgement
trail, defeating the lane's data-collection purpose. Without the gate, the
watch-first ordering would false-page FEED DARK daily in the pre-merge window
(the MLflow fallback fabricates dark records out of live-run days for a lane
that cannot have evidence yet). The full derive-from-config alternative stays
rejected per orch#702's pinned rationale (a lane REMOVED from config would
leave the watch list with it); the gate's ever-reported clause is what keeps
the orch#689 ABSENT-FROM-CONFIG alarm intact for removals, proven by test.
EVIDENCE:
  artifact:      ops/renquant104/rq104_shadow_scorer_sentinel.py
                 (watched_lanes, _patrol_lane gate, main declared-set wiring);
                 tests/test_rq104_shadow_scorer_sentinel.py (mechanics fixture
                 pinned to an explicit legacy-shaped lane + new
                 TestMomentumTransition / TestMomentumAckTrail, 12 new tests);
                 tests/test_config_declares_a_lane_nobody_watches.py (patrol
                 signature + a BOUNDED retired-lane transition allowance)
  prod or exp:   prod — the deployed launchd sentinel
                 (com.renquant.rq104-shadow-scorer-sentinel); merged is not
                 deployed: it goes live at the batch's run-checkout sync
  existing data: read-only rehearsal on the live machine (alert stubbed),
                 2026-08-02: with today's lagging run-checkout config the
                 retired patchtst lane raises the DECLARED-BUT-UNWATCHED drift
                 alarm (bounded — clears at the batch's s104 checkout sync, and
                 is the truthful "config still serves a retired lane"
                 reminder); with the pinned post-retirement config the run is
                 drift-clean and the momentum lane takes the printed
                 pre-activation skip — NO false FEED DARK on either side. The
                 pre-existing clf malformed-coverage alarm is unchanged by this
                 PR. `[VERIFIED — stubbed-alert main() runs on this branch,
                 2026-08-02]`
  best-known?:   yes — the only sentinel change targeting s104#77; designed
                 against the pinned pipeline's `not_yet_published`
                 expected-skip (pipeline#253), which classifies quiet through
                 the existing status axis with no schema change here
  scope:         one ops file + two test files; touched suites 103/103; full
                 suite 5447 passed, 14 skipped, 6 failed — the same 6 fail on
                 pristine origin/main (stashed re-run), all unrelated files
                 `[VERIFIED — pytest, 2026-08-02]`
NEXT: the slice-5 batch merges s104#77 and syncs the run checkouts, at which
point the config declares the lane and the patrol arms itself (no further
sentinel change needed); the follow-up that lands the batch shrinks the
RETIRED_IN_FLIGHT allowance in
tests/test_config_declares_a_lane_nobody_watches.py back to empty. The
fallback-contract literal for `not_yet_published` is PR #759's change, not
duplicated here. AC6 gate-design rule: N/A — monitoring only, no
capital-admission gate.
