# Progress: G2 Crypto Implementation — T-1/T-2/T-3

- Date: 2026-07-13
- Branch: `feat/crypto-scheduling` (orchestrator), `feat/crypto-trend-signal` (base-data), `feat/crypto-portfolio` (pipeline)
- Goal: G2 — Alpaca crypto trading sleeve

## What changed

Implemented the three core modules for the G2 crypto trend-following portfolio:

### T-1: Signal module (base-data PR #45)
- `crypto_trend_signal.py`: fixed SMA50 trend filter
- `compute_signals()` → `SignalSnapshot` with deterministic digest
- Integrates with crypto_session.py gate #7/#10
- 20 tests passing

### T-2: Portfolio module (pipeline PR #194)
- `crypto_portfolio.py`: equal-weight sizing + risk gates
- R1 drawdown circuit breaker (reuses existing `update_drawdown_circuit_breaker`)
- R2 per-pair stops with 14d cooldown
- R3 position cap at 40%
- Drift rebalancing at 15% threshold
- 21 tests passing

### T-3: Scheduling coordination (this PR)
- `crypto_scheduling.py`: S1-S4 + S9 DAG coordination
- File-based completion markers for step sequencing
- Universe rotation (weekly, 90d Sharpe ranking, excludes XRP/UNI/FIL/ARB)
- Signal computation wrapper (calls T-1)
- Portfolio sizing wrapper (calls T-2)
- `crypto_status()` for operational visibility
- 15 tests passing

## What's next

- T-4: launchd plist templates (deployment)
- T-5: Wire crypto_session.py to consume new SignalSnapshot
- T-8: CLI commands
- Run data ingestion (landing action — needs operator approval)
- Stage 1 shadow: 7 clean days

## Status

Operator GO + paper GO received. Core modules built and tested. Awaiting
codex review on all three PRs before merge.
