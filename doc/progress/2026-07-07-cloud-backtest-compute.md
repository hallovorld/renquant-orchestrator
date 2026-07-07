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

## r1→r2 changes (addresses Codex review)

Codex blocked r1 on three points; all three fixed:

1. **Cost model bug.** r1's cost tables (both docs) applied Modal's A10 GPU
   per-second rate ($0.000306/sec) to a CPU-only workload, and every
   platform's cost estimate omitted memory cost entirely. Verified Modal's
   real CPU pricing (`$0.0000131`/physical-core-sec + `$0.00000222`/GiB-sec,
   modal.com/pricing) and AWS Fargate's (`$0.000011244`/vCPU-sec +
   `$0.000001235`/GB-sec, aws.amazon.com/fargate/pricing), both checked
   2026-07-07. Recomputed the 75-variant sweep cost: Modal **$2.93** (was
   wrongly $81.56), AWS Fargate on-demand **$3.66** (was $3.00, missing
   memory), AWS Fargate Spot **$1.10** (was $0.89, missing memory). This
   reverses the platform recommendation: Modal is now cheaper than on-demand
   Fargate and only ~2.7× Spot (not ~27×), so **Modal is now recommended as
   primary AND production**, not just a prototyping tier ahead of a migration
   to AWS Batch Spot.

2. **Scope too broad for orchestrator.** Narrowed this RFC's actual Phase 1-3
   implementation to W1 (parameter sweeps) and W4 (placebo/shuffle
   significance) — the two workloads that already run via orchestrator-owned
   scripts today. W2/W12 (GPU model training/retraining) are now explicitly
   out of scope, marked as `renquant-model`'s decision to make. W5-W9
   (planned workloads) are kept as forward-looking context but explicitly
   not implemented by this RFC; if pursued at a scope beyond this repo's own
   sweep scripts, the right owner is `renquant-backtesting`. Removed Phase 4
   (GPU training) and the GPU container-image section entirely.

3. **Provenance contract too weak.** The `sweep_runs` schema (§4.5) recorded
   only one `code_commit` (this repo's own SHA) + a volume commit. Replaced
   with the full pinned-multirepo assembly: `subrepo_pins_json` (the complete
   `{repo: commit}` map actually imported by the worker) + a sha256 digest of
   it, plus `strategy_config_fingerprint`, `data_manifest_fingerprint`, and
   `artifact_manifest_fingerprint` — all validated present-and-non-empty
   before a sweep is allowed to write results, matching this repo's existing
   fail-closed provenance pattern (`RunProvenance` in
   `shadow_realtime_serving.py`) and the CLAUDE.md hard rule against silently
   continuing without strategy/data/artifact fingerprints.

Still docs-only — no code, no infra, no spend in this revision either.
