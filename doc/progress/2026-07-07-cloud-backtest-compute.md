# 2026-07-07 — cloud backtest compute design

**PR**: design(infra): Modal-first cloud backtest compute for parallel sweeps

## Problem

Concentration cap sweep (75 variants × 3 seeds × 575 days) takes ~38h on 12
local cores. This blocks the machine and delays data-driven decisions.

## Design

Local controller + Modal cloud workers. The sweep script dispatches independent
variant backtests to N Modal containers via `.map()`, collects results locally,
and runs verdicts. Same `execute_variant` function, same result schema — cloud
is a transparent backend swap.

Data (OHLCV 250MB + model artifacts 2.7GB) lives on a Modal Volume, synced
before each sweep. No API keys or live state leave local.

Estimated: 74 workers × ~30 min = **$4.40** vs 38h local.

## Scope

Design RFC only. No code, no infra, no spend.
