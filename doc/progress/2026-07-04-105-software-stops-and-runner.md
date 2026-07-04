# 105 software stops + session runner — 2026-07-04

DATE: 2026-07-04

## What shipped

Two new modules that close the final 105 code gaps identified in the
sprint audit (doc/progress/2026-07-04-sprint-status-audit.md §2):

### 1. Per-position intraday software stops (`software_stop.py`)

Completes the 3-layer stop stack:
- Layer 1: GTC catastrophe planner (broker-resident at −20%) — existing
- Layer 2: Canary envelope (session-level cumulative loss budget) — existing
- Layer 3: **Per-position intraday stops** — NEW

Two stop types:
- **Hard stop**: exit if unrealized loss ≥ 5% of entry price (configurable)
- **Trailing stop**: exit if price drops ≥ 3% below session HWM (configurable)

Sticky (fires once per position per session). Shadow-only by default —
generates `StopSignal` records the runner logs or folds into live decisions.
21 tests.

### 2. Session runner (`intraday_session_runner.py`)

The integration layer that wires all 105 modules into a single session
lifecycle — the piece explicitly deferred in the Stage-2 codex review.

Lifecycle:
1. Evaluate `resolve_stage2_arming()` (quintuple gate)
2. If armed → drive `LiveTickExecutor` through the tick loop with
   software stops + entry timing policy
3. If ANY gate missing → delegate to unchanged Stage-1 `SessionScheduler`

Key design decisions:
- Never constructs a broker port unless all 5 gates arm
- Falls back to shadow even if armed but `port_factory` is None
- Software stop evaluator runs on every tick (shadow or live)
- Entry-timing policy wired as tick observer (unchanged)
- `SessionResult` carries mode_effective, armed status, manifest, stop summary

18 tests covering: shadow fallback, non-session day, kill switch, arming
record propagation, extract helpers, config resolution, live fallback
without port factory.

## Files

| File | Lines | Tests |
|------|-------|-------|
| `src/renquant_orchestrator/software_stop.py` | 228 | 21 |
| `src/renquant_orchestrator/intraday_session_runner.py` | 482 | 18 |
| `tests/test_software_stop.py` | 247 | 21 |
| `tests/test_intraday_session_runner.py` | 312 | 18 |

## Safety invariants preserved

- Shadow-only by default (quintuple gate controls live execution)
- No broker port constructed unless armed
- Stop config `enabled: false` by default
- All paths write to shadow logs, never canonical prod data
- Kill switch checked every tick in live path
- No branch protection bypass

## Test suite

`make test`: 2161 passed, 2 skipped, 0 failures.
