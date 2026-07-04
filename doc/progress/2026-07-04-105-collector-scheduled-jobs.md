# 105 collectors + monitors — scheduled job wiring

**Date**: 2026-07-04
**PR**: (this PR)
**Master plan ref**: N1 (105 collectors live + liveness), S11-adjacent (scorer identity)

## What

Wires 8 existing modules into the job runner + scheduled job inventory so they are
dispatchable via `renquant-orchestrator run-job <job_id>`:

### 105 Stage-1 intraday collectors (N1)
| Job ID | Module | Kind | Cadence |
|--------|--------|------|---------|
| `intraday_quote_logger` | tick feed poller | ops | intraday_session |
| `intraday_pairing_logger` | paired execution observer | ops | intraday_session |
| `entry_timing_shadow` | entry-timing shadow evaluator | ops | intraday_session |
| `intraday_session_scheduler` | session control plane | control | intraday_session |
| `realtime_data_plane` | real-time market snapshot | ops | intraday_session |
| `shadow_realtime_serving` | shadow model serving | inference | intraday_session |

### Monitors
| Job ID | Module | Kind | Cadence |
|--------|--------|------|---------|
| `scorer_identity_monitor` | run-over-run scorer diff alarm | ops | daily |
| `fallback_shadow_logger` | best-of-recent shadow logger (#210) | ops | daily |

All 8 are `production_safe=True` and `native_multirepo`. The 6 intraday collectors
use a new `intraday_session` cadence (they run during exchange sessions, not on a
fixed daily/weekly schedule). The 2 monitors (scorer_identity, fallback_shadow) have
`umbrella_state_dependency` since they inspect model artifacts.

## Why

N1 AC: "3 sessions of complete output + lapse-alert test-fire." These modules exist
and have tests, but without job dispatcher entries they can only be invoked via
`python -m` — invisible to the scheduling inventory, health checks, and audit trail.

## Tests

All 1912 tests pass. Scheduled job counts updated (21→29 total, 19→27 native,
15→17 umbrella_state_dep).
