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

## Round 2 (Codex review — 3 findings)

**1. Safety-narrative mismatch (blocking, CODE fix, not a docs relabel).**
Codex found that "shadow-only by default (quintuple gate controls live
execution)" — the claim in this doc and the module docstring — did NOT
match the code: `run_session()` dispatched to `_run_live()` (constructing a
real broker port and `LiveTickExecutor`) whenever the §9.3a quintuple gate
armed and a `port_factory` was supplied, with no representation anywhere of
the SEPARATE §9.4 economic-authorization decision that the earlier Stage-2
PR's own docstring said had not been made. Fixed by adding a genuinely
additional, closed-by-default gate
(`economic_authorization_9_4_confirmed()` /
`RENQUANT_STAGE2_ECONOMIC_AUTHORIZATION_9_4`) that `run_session()` checks
BEFORE ever considering `_run_live()`, independent of the quintuple gate's
own verdict — both gates must now hold. New tests
(`TestEconomicAuthorization94Gate`) prove: (a) quintuple-armed + port_factory
present + §9.4 unset still falls to shadow (confirmed to genuinely fail
against the pre-fix code, not a tautology), and (b) setting the env flag
does open the live path (proving the gate is real, not a permanent block).
Every session manifest now also stamps `economic_authorization_9_4` for
audit completeness, on every code path.

**2. S10 memo overclaiming (blocking, evidence fix).** The round-1 S10 memo
presented "No measurable execution leak" / "the §9.4 rationale is not
supported" as settled conclusions off a single cleaned cut (n=36,
1000bps outlier exclusion decided post-hoc, 30/67 trades silently dropped
as weekend-unmatched). Fixed by adding EX ANTE `--exclude-outlier-bps` and
`--weekend-remap` CLI parameters to `scripts/s10_open_auction_is.py` and
running a genuine 4-way sensitivity sweep — see
`doc/research/2026-07-04-open-auction-is-measurement.md` (round 2) for the
full table. The direction (no leak) holds across all four configurations;
the weekend remap also surfaced a SECOND HON split-artifact trade the
round-1 methodology had silently dropped rather than investigated. Both
as-built docs (104 and 105) updated to reflect the sensitivity-checked,
appropriately-hedged version of the finding rather than the single-cut
claim.

**3. `outcome_backfiller` provenance (non-blocking, documentation fix).**
Codex flagged that `decision_outcomes` rows written from
`candidate_scores.blocked_by` are RECONSTRUCTED/backfilled, not
authoritative live-ledger truth, and should be marked as such so downstream
consumers (e.g. the S5 attribution/coverage work, PR #320) don't mistake
one for the other. Fixed: every row `outcome_backfiller` writes now stamps
an explicit `provenance: "reconstructed_from_candidate_scores"` field
(distinct from a genuine live-ledger write), and the module docstring
states this plainly.
