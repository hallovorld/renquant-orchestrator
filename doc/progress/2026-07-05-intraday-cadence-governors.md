# 2026-07-05 Intraday Cadence + Governors

Roadmap item #26: intraday risk-reaction cadence with governors and validation.

## What

New module `src/renquant_orchestrator/intraday_governors.py` implementing the
cadence checkpoint + governor framework for renquant105 intraday decisioning.

## Components

### Cadence checkpoints

Named session evaluation checkpoints (e.g., open+30min, midday, power hour)
that supplement the fixed-interval tick cadence. Checkpoints resolve from
calendar-aware session bounds so early closes scale naturally.

### Four governor checks

All independent, all shadow-evaluated, all report every tripped reason:

1. **Max actions per session** — cap on total entries + exits per session.
2. **Max turnover fraction** — cap on intraday portfolio turnover as fraction of equity.
3. **Per-ticker cooldown** — minimum seconds between actions on the same ticker.
4. **Post-loss cooldown** — pause entries after a realized loss exceeding a threshold.
   Exits are NEVER blocked (the exits-always-allowed invariant).

### Integration seams

- `GovernorEvaluator`: stateful per-session evaluator wired into the session
  scheduler's tick loop.
- `GovernorShadowObserver`: plugs into the scheduler's `tick_observer` seam
  (same pattern as `ShadowEntryTimingEvaluator`).
- `GovernorConfig`: loaded from `intraday_governors` section in pinned
  strategy config. Absent section => disabled (all intents pass).

## Safety

- Default OFF: absent config section => all governors disabled.
- Shadow-evaluated only: governors annotate intents but never suppress shadow data.
- No trading strategy, sizing, or signal logic.
- No production data writes.
- Testable in isolation: pure functions, injected state, no wall-clock, no network.

## Test results

57 tests, all passing:
- Config loading (9 tests): valid, invalid, absent, malformed values
- Cadence checkpoints (7 tests): resolution, sorting, half-day scaling, activation
- Governor checks (17 tests): each check independently + multi-block + disabled
- State accumulation (5 tests): action recording, loss tracking, turnover fraction
- Batch evaluation (4 tests): intent annotation, read-only state invariant
- Evaluator lifecycle (2 tests): evaluate + record + summary
- Shadow observer (4 tests): tick processing, state accumulation, edge cases
- Fingerprint (3 tests): stability, sensitivity, format
- Verdict serialization (2 tests)
- End-to-end session (1 test): full lifecycle across multiple ticks

## Files

- `src/renquant_orchestrator/intraday_governors.py` (new)
- `tests/test_intraday_governors.py` (new)
- `doc/progress/2026-07-05-intraday-cadence-governors.md` (this file)

## Round 2 (codex review)

STATUS: fixed
WHAT: `GovernorShadowObserver.on_tick()` evaluated each tick's intents (producing
a `governor_blocked` verdict per intent) but then looped over the *original*,
unannotated `intents` list to call `record_action()` — unconditionally, for
every intent, regardless of its verdict. A shadow-blocked intent therefore
still advanced `action_count`, `cumulative_turnover_notional`, and
`last_action_by_ticker` as if it had actually executed.
WHY-DIR: once one governor trips on a tick, that intent's phantom state feeds
into every later tick's evaluation — cascading into false blocks on
subsequent, otherwise-fine intents. For a shadow-evaluation control-plane
module whose entire purpose is measuring "how often would this governor
block a live session," that self-contamination systematically overstates
blocking, invalidating the measurement codex flagged.
EVIDENCE: fixed by iterating the `annotated` list (which carries
`governor_blocked`) instead of raw `intents`, skipping `record_action()` for
any intent the governor itself blocked. Added
`test_blocked_intent_does_not_advance_turnover_state` (a blocked $4,000
intent must not push cumulative turnover from $4,000 to $8,000, which would
then falsely block a later $500 intent that fits the cap on its own) and
`test_blocked_intent_does_not_advance_ticker_cooldown_state` (a blocked
intent must not stamp a per-ticker cooldown timestamp). Both confirmed to
fail against the pre-fix code (`git stash` verification) and pass after.
Also regenerated `data/strategy_snapshot.json` (pre-existing, unrelated
staleness on this branch — `intraday_governors` module was missing from the
baseline). Full suite 3034/3036 passed (2 pre-existing unrelated failures in
`test_bundle_consistency_ci_gate.py`, confirmed reproducing on clean
`origin/main`).
NEXT: none — the shadow observer's state model now correctly reflects only
genuinely-allowed intents.
