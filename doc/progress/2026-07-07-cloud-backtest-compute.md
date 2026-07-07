# 2026-07-07 — cloud backtest compute design

**PR**: design(infra): cloud backtest compute — controller/worker burst execution

## Problem

Concentration cap sweep (75 variants × 3 seeds × 575 days) takes ~38h on 12
local cores. Blocks the machine including live trading ops.

## Design

v2 rewrite: starts from workload taxonomy → requirements → platform evaluation
→ architecture, replacing the previous Modal-first sketch.

**Platform evaluation**: compared Modal, Beam, Fal.ai, Anyscale (Ray), AWS
Batch Spot across 10 requirements (F1-F7, NF2/NF3/NF6). Selected Modal as
primary (best DX for our scale, Volume snapshots, GPU path for W12). Fal.ai
eliminated (GenAI-focused, not CPU batch). Anyscale eliminated (over-engineered
for embarrassingly parallel). AWS Batch Spot = escape hatch if cost matters
more at scale. Abstraction layer (`BacktestExecutor` protocol) ensures platform
swap is a one-file change.

**Architecture**: local controller / remote worker with `BacktestExecutor`
interface. Three implementations: `LocalExecutor` (today), `ModalExecutor`
(primary), future `RayExecutor`/`AWSBatchExecutor`.

**Key mechanisms**:
- Data sync: SHA-256 checksums + Volume commit snapshots; hardcoded exclusion list
- Results: per-variant INSERT to local SQLite on receipt (crash-safe); equity curves
  + trade logs via gzip+base64 (~200KB/variant)
- Resume: `--resume {sweep_id}` re-dispatches only missing variants
- Pre-flight: volume freshness, integrity spot-check, cost projection, cross-backend A/A
- Security: no API keys, live state, or production DB leave local

NFRs: 75-variant sweep ≤45min, ≤$10/sweep, zero silent data loss, backend
equivalence ±0.01 Sharpe, platform switch ≤1 week engineering.

## Scope

Design RFC only. No code, no infra, no spend.
