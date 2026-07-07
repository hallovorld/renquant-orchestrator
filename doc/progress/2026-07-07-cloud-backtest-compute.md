# 2026-07-07 — cloud backtest compute design

**PR**: design(infra): cloud backtest compute — controller/worker burst execution

## Problem

Concentration cap sweep (75 variants × 3 seeds × 575 days) takes ~38h on 12
local cores. Blocks the machine including live trading ops.

## Design

Local controller / remote worker architecture with Modal:
- **Upload**: OHLCV (250MB) + model artifacts (2.7GB) to Modal Volume with
  SHA-256 checksums and immutable commit snapshots
- **Dispatch**: controller sends variant configs as JSON; workers are stateless
- **Return**: structured JSON results (~200KB/variant) with equity curves and
  trade logs (gzip+base64); integrity verified via result_checksum
- **Ingest**: each result INSERT'd to local SQLite immediately on receipt (not
  batched); crash at variant 73/74 preserves 72 results; `--resume` flag for
  interrupted sweeps
- **Security**: no API keys, no live state, no production DB leaves local;
  code/model in private Modal images; public OHLCV only sensitive-by-volume

NFRs covered: performance targets, reliability (retry/resume/checkpoint),
observability (progress/ntfy/cost tracking), cost controls (per-sweep ceiling),
security (threat model), testing (backend equivalence, mocked + integration).

## Scope

Design RFC only. No code, no infra, no spend.
