# Design: cloud compute platform for RenQuant research & backtesting

STATUS: design / RFC for cross-agent review. No infra, no spend, no live behavior change.

DATE: 2026-07-07

---

## 0. This document's job

Define the compute infrastructure that RenQuant needs NOW and will grow into
over the next 12 months, then select a platform and design the system.

The previous draft started from "Modal is cool" and worked backward.
This version starts from our workloads and works forward.

---

## 1. Workload taxonomy — what we actually compute

### 1.1 Current workloads

| ID | Workload | Hardware | Parallelism | Duration (local) | Frequency |
|----|----------|----------|-------------|------------------|-----------|
| W1 | Parameter sweep (conc cap, Kelly, etc.) | CPU | embarrassingly parallel (75-225 variants) | 38h | ad hoc (~2/month) |
| W2 | Walk-forward retrain | GPU (PatchTST) + CPU (XGB/NGBoost) | sequential per cutoff, parallelizable across cutoffs | PatchTST ~50s/cut × 20 cuts; XGB ~154s/cut × 20 cuts | weekly |
| W3 | Daily-full pipeline | CPU | sequential | ~5 min | daily |
| W4 | Placebo/shuffle significance | CPU | embarrassingly parallel (100+ shuffles) | ~20h | per gate change |

### 1.2 Planned workloads (H2 2026 roadmap)

| ID | Workload | Hardware | Parallelism | Estimated duration | Frequency |
|----|----------|----------|-------------|-------------------|-----------|
| W5 | Panel-admission shadow replay | CPU | 20 sessions, parallelizable | ~10h local | once |
| W6 | Signal stack validation (M-SIG) | CPU | per-signal × per-regime × placebo | ~15h local | per signal PR |
| W7 | Down-cap universe screen (RS-5) | CPU | parallel across tickers | ~8h local | once |
| W8 | Book-scaling simulation | CPU | parallel across $ levels | ~5h local | ad hoc |
| W9 | Attribution engine | CPU | per-trade, parallelizable | ~2h local | daily |

### 1.3 Future workloads (12-month horizon)

| ID | Workload | Hardware | Key change |
|----|----------|----------|-----------|
| W10 | 500+ ticker universe | CPU | 3.5× current pipeline days per variant |
| W11 | Multi-strategy concurrent | CPU | 2-3× total workload |
| W12 | Scheduled model retraining | GPU (CUDA) | needs GPU cloud, not just CPU |

### 1.4 What does NOT go to cloud

| Workload | Why |
|----------|-----|
| W3 (daily-full pipeline) | Latency-sensitive, touches live DB + broker state, <5 min local |
| rq105 session scheduler | Real-time, needs local broker connection |
| Quote logger | Real-time streaming, latency-sensitive |
| Any live-state operation | Security: API keys, positions, orders stay local |

---

## 2. Requirements derived from workloads

### 2.1 Functional

| Req | Source | Description |
|-----|--------|-------------|
| F1 | W1,W4-W8 | Execute a Python backtest function with a config JSON, return structured results |
| F2 | W1 | Support 20-200+ concurrent workers |
| F3 | W1,W4 | Stream results back as each worker completes (not batch at end) |
| F4 | W2,W12 | Support GPU workers (CUDA) for model training |
| F5 | all | Shared read-only data volume (OHLCV 250MB + model artifacts 2.7GB) |
| F6 | W1 | Resume interrupted sweeps from checkpoint |
| F7 | all | Identical results on cloud vs local (backend-transparent) |

### 2.2 Non-functional

| Req | Target | Rationale |
|-----|--------|-----------|
| NF1 Performance | 75-variant sweep ≤45 min e2e | Current: 38h. 50× improvement is the floor. |
| NF2 Cold start | ≤90s per worker | >90s on a 30-min job = >5% overhead, noticeable |
| NF3 Cost | ≤$10/sweep (75 variants) | Must be sustainable for 2-4 sweeps/month on free/starter tier |
| NF4 Reliability | Zero silent data loss | Every result persisted on receipt; crash recovery via resume |
| NF5 Security | No API keys / live state / prod DB leave local | Backtests use only historical data |
| NF6 Portability | Switch platform in ≤1 week of engineering | No deep vendor lock-in in the abstraction layer |
| NF7 Observability | Progress visible during sweep; completion notification | ntfy + terminal progress |
| NF8 Reproducibility | Same data + code + config = same result (±FP) | Volume commit ID + image hash + config fingerprint |

### 2.3 Growth vectors

| Vector | Impact on platform choice |
|--------|--------------------------|
| GPU training (W12) | Platform MUST support GPU instances, not just CPU |
| 500+ ticker universe (W10) | Workers need more memory (4GB → 8GB); data volume grows to ~1GB OHLCV |
| Higher sweep frequency | Cost efficiency matters more; warm pools / reserved capacity useful |
| Multi-strategy | Same infra, different configs; no architectural change |

---

## 3. Platform evaluation

### 3.1 Candidates

| Platform | Type | Strengths | Weaknesses |
|----------|------|-----------|------------|
| **Modal** | Python-native serverless | Best DX; Volume snapshots; GPU support; cold start ~10-30s | Vendor lock-in (Python decorator API); US-only regions |
| **Beam** | Python-native serverless | Similar to Modal; persistent volumes; GPU | Smaller community; less mature docs |
| **Anyscale (Ray)** | Distributed framework + managed cloud | Ray is OSS (portable); scales to 1000s of workers; GPU native | Heavier setup; min cluster size; overkill for burst | 
| **Fal.ai** | AI/ML-focused serverless | Good for inference/training; GPU-first | Not designed for general CPU backtests; limited Volume support |
| **AWS Batch + Spot** | Traditional IaaS | Cheapest (spot ~$0.01/vCPU·h); full control; GPU via EC2 | Heavy setup (ECR/IAM/VPC/job-def); cold start 2-5 min; no streaming results |

### 3.2 Scoring against our requirements

| Requirement | Modal | Beam | Anyscale | Fal.ai | AWS Batch |
|-------------|-------|------|----------|--------|-----------|
| F1 Python function dispatch | ★★★ | ★★★ | ★★☆ | ★★☆ | ★☆☆ |
| F2 20-200 concurrent | ★★★ | ★★★ | ★★★ | ★★☆ | ★★★ |
| F3 Streaming results | ★★★ (.map generator) | ★★☆ | ★★★ (Ray futures) | ★☆☆ | ★☆☆ (poll SQS) |
| F4 GPU support | ★★★ (T4/A10G/A100) | ★★★ | ★★★ | ★★★ | ★★★ |
| F5 Shared volume | ★★★ (Volume + commit) | ★★☆ | ★★☆ (S3/NFS) | ★☆☆ | ★★☆ (EFS/S3) |
| F6 Resume | ★★☆ (app-level) | ★★☆ | ★★★ (Ray checkpoints) | ★☆☆ | ★★☆ (app-level) |
| F7 Backend-transparent | ★★★ | ★★★ | ★★☆ (Ray API leaks) | ★★☆ | ★★★ |
| NF2 Cold start | ★★★ (~10-30s) | ★★☆ (~30-60s) | ★★☆ (~60s cluster) | ★★☆ (~30s) | ★☆☆ (2-5 min) |
| NF3 Cost (75-var sweep) | ★★☆ (~$4-5) | ★★☆ (~$4-5) | ★★☆ (~$5-8) | ★★☆ (~$5) | ★★★ (~$1-2 spot) |
| NF6 Portability | ★★☆ (decorator lock-in) | ★★☆ (same) | ★★★ (Ray is OSS) | ★☆☆ | ★★★ (containers) |

### 3.3 Selection

**Primary: Modal.** Best fit for our current scale (10-200 workers, burst,
mixed CPU/GPU). Fastest time-to-value. Volume commit snapshots solve the data
consistency problem natively. GPU support covers W12 when we get there.

**Escape hatch: Anyscale/Ray.** If we outgrow Modal (>500 workers, need
multi-region, or pricing becomes unfavorable), Ray's OSS core means we can
self-host or move to Anyscale with the same application code. The abstraction
layer (§4.1) is designed so this migration is a backend swap, not a rewrite.

**Why not AWS Batch:** 2-5 min cold start is 8-15% overhead on 30-min jobs.
No streaming results (must poll SQS or wait for all). Heavy IAM/VPC/ECR
setup for a 1-person team. Cheapest on $/vCPU·h but most expensive on
$/engineering-hour.

**Why not Fal.ai:** AI-inference-focused; CPU backtest support is second-class.
Limited volume/storage primitives.

---

## 4. Architecture

### 4.1 Abstraction layer — platform-agnostic interface

The system is designed around a **BacktestExecutor** interface that hides the
platform. Switching from Modal to Ray (or local ProcessPoolExecutor) is a
one-line config change.

```python
class BacktestExecutor(Protocol):
    """Platform-agnostic interface for dispatching backtest workloads."""

    def execute_batch(
        self,
        requests: list[BacktestRequest],
        *,
        on_result: Callable[[BacktestResult], None],
        on_error: Callable[[str, Exception], None],
        max_concurrent: int = 100,
    ) -> BatchSummary:
        """Dispatch requests, call on_result/on_error as each completes.

        on_result is called with each successful result as it arrives
        (streaming — not batched at end). on_error is called for failed
        variants with the variant name and exception.

        Returns BatchSummary with total timing + cost estimate.
        """
        ...

    def preflight(self, data_manifest: DataManifest) -> PreflightReport:
        """Verify platform readiness: data sync, image freshness, cost
        projection. Returns pass/fail with details."""
        ...

    def sync_data(self, local_paths: DataPaths) -> DataManifest:
        """Upload/refresh data to the platform's storage. Returns a
        manifest with commit IDs and checksums for verification."""
        ...


# Implementations
class LocalExecutor(BacktestExecutor):
    """ProcessPoolExecutor backend (today's behavior)."""
    ...

class ModalExecutor(BacktestExecutor):
    """Modal cloud backend."""
    ...

# Future:
# class RayExecutor(BacktestExecutor): ...
# class AWSBatchExecutor(BacktestExecutor): ...
```

### 4.2 Data flow — the full lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA FLOW                                    │
│                                                                     │
│  ┌──────────┐                                                       │
│  │ LOCAL    │                                                       │
│  │ DATA     │  1. SYNC                                              │
│  │          │  ─────────▶  ┌──────────────────┐                     │
│  │ ohlcv/   │  SHA-256     │ CLOUD VOLUME     │                     │
│  │ artifacts/│  checksums  │ (immutable commit)│                     │
│  │ manifest │  incremental │ commit_id=abc123 │                     │
│  └──────────┘              └────────┬─────────┘                     │
│                                     │                               │
│  ┌──────────┐   2. DISPATCH         │ 3. READ (RO)                  │
│  │CONTROLLER│──────────────▶  ┌─────▼────────┐                     │
│  │          │  BacktestReq[]  │  WORKERS     │                     │
│  │ grid gen │                 │  (stateless) │                     │
│  │ A/A ctrl │  4. RESULTS     │  execute_    │                     │
│  │ dispatch │◀──────────────  │  variant()   │                     │
│  │ ingest   │  BacktestResult │              │                     │
│  │ verdict  │  (JSON, ~200KB) └──────────────┘                     │
│  └────┬─────┘                                                       │
│       │                                                             │
│       │ 5. PERSIST                                                  │
│       ▼                                                             │
│  ┌──────────────────────────────────────────┐                       │
│  │ LOCAL RESULT STORE                       │                       │
│  │                                          │                       │
│  │ sweep_db/{sweep_id}/                     │                       │
│  │   results.db          ← SQLite           │                       │
│  │     sweep_runs        (crash-safe,       │                       │
│  │     variant_results    per-variant        │                       │
│  │     seed_metrics       INSERT)            │                       │
│  │   verdicts.json       ← computed after all│                       │
│  │   sweep_meta.json     ← provenance       │                       │
│  │   configs/            ← variant configs   │                       │
│  │   equity/             ← decompressed      │                       │
│  │     {variant}/{seed}.csv                  │                       │
│  │   trades/             ← decompressed      │                       │
│  │     {variant}/{seed}.jsonl                │                       │
│  │   checkpoints/        ← resume state      │                       │
│  │     completed.json                        │                       │
│  └──────────────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.3 Step 1 — Data sync (local → cloud)

**What syncs:**

| Asset | Path | Size | Sync method |
|-------|------|------|-------------|
| OHLCV bars | `data/ohlcv/*.parquet` | 250 MB | Incremental (SHA-256 diff) |
| WF model artifacts | `artifacts/walkforward_v2_*/` | 2.7 GB | Incremental |
| WF manifest | `walkforward_manifest_*.json` | <1 MB | Always |

**What NEVER syncs (hardcoded exclusion list):**

```python
SYNC_EXCLUSIONS = [
    ".env", "*.key", "*.pem", "*.secret",  # secrets
    "runs.alpaca.db",                       # production run DB
    "live_state*.json",                     # live portfolio state
    "strategy_config.json",                 # live config (has mode/keys sections)
    "data/rawlabel.parquet",                # canonical production input
    "logs/",                                # operational logs
]
```

**Sync protocol:**

```python
def sync_data(local_paths: DataPaths) -> DataManifest:
    # 1. Inventory local files, compute SHA-256 for each
    local_manifest = build_local_manifest(local_paths, exclude=SYNC_EXCLUSIONS)

    # 2. Load previous sync manifest (if any)
    prev = load_previous_manifest()

    # 3. Diff: new + changed files
    to_upload = diff_manifests(local_manifest, prev)
    if not to_upload:
        return prev  # no changes, reuse existing commit

    # 4. Upload changed files
    for path, checksum in to_upload:
        volume.write_file(remote_path(path), read_file(path))
        log.info(f"uploaded {path} ({checksum[:8]})")

    # 5. Commit volume → immutable snapshot
    commit_id = volume.commit()

    # 6. Save sync manifest locally
    manifest = DataManifest(
        commit_id=commit_id,
        timestamp=utcnow(),
        files={path: checksum for path, checksum in local_manifest},
        total_bytes=sum(file_size(p) for p, _ in local_manifest),
    )
    save_manifest(manifest)
    return manifest
```

### 4.4 Step 2 — Dispatch + streaming ingestion

```python
def run_sweep(
    variants: list[VariantSpec],
    executor: BacktestExecutor,
    sweep_id: str,
    data_manifest: DataManifest,
    ...
) -> SweepResult:
    # Init local result store
    store = ResultStore(sweep_id)

    # Pre-flight
    report = executor.preflight(data_manifest)
    if not report.passed:
        raise PreflightError(report)

    # Load checkpoint (for resume)
    completed = store.completed_variants()
    remaining = [v for v in variants if v.name not in completed]

    # Build requests
    requests = [
        BacktestRequest(
            variant_name=v.name,
            config_json=v.config_path.read_text(),
            volume_commit_id=data_manifest.commit_id,
            seeds=list(v.seeds),
            start=start, end=end,
            initial_cash=initial_cash,
            incumbent_turnover=inc_turnover,
        )
        for v in remaining
    ]

    # Dispatch with streaming ingestion
    def on_result(result: BacktestResult):
        # Verify integrity
        verify_checksum(result)
        verify_volume_commit(result, data_manifest.commit_id)

        # Persist IMMEDIATELY (crash-safe)
        store.insert_variant(result)
        store.save_artifacts(result)  # decompress equity + trades
        store.checkpoint(result.variant_name)

        # Compute verdict
        verdict = unanimity_verdict(result, incumbent_result, ...)
        store.insert_verdict(result.variant_name, verdict)

        # Progress
        n = len(completed) + store.count_completed()
        print(f"[{n}/{len(variants)}] {result.variant_name} "
              f"tier3={verdict['tier3_ready']} "
              f"({result.elapsed_seconds:.0f}s)")

    def on_error(variant_name: str, exc: Exception):
        store.insert_error(variant_name, str(exc))
        print(f"[!] {variant_name} FAILED: {exc}")

    summary = executor.execute_batch(
        requests,
        on_result=on_result,
        on_error=on_error,
        max_concurrent=100,
    )

    # Finalize
    store.finalize(summary)
    notify(sweep_id, store.summary())
    return store.to_sweep_result()
```

### 4.5 Step 3 — Result persistence (local SQLite)

**Why SQLite (not flat JSON):**
- Current `sweep_results.json` writes atomically at END — crash at 73/74 loses all
- SQLite: each variant INSERT'd on receipt; crash at 73/74 preserves 72 results
- Queryable: compare sweeps, filter by regime, rank by Sharpe
- Resume: checkpoint = set of completed variant_names in the DB

**Schema:**

```sql
-- One row per sweep run
CREATE TABLE sweep_runs (
    sweep_id        TEXT PRIMARY KEY,
    created_at      TIMESTAMP NOT NULL,
    backend         TEXT NOT NULL,            -- 'local' | 'modal' | 'ray'
    volume_commit   TEXT,                     -- NULL for local backend
    image_id        TEXT,                     -- container image hash
    code_commit     TEXT,                     -- git SHA of orchestrator
    backtest_start  TEXT NOT NULL,            -- ISO date
    backtest_end    TEXT NOT NULL,
    initial_cash    REAL NOT NULL,
    grid_spec_json  TEXT NOT NULL,
    n_variants      INTEGER NOT NULL,
    n_completed     INTEGER DEFAULT 0,
    n_failed        INTEGER DEFAULT 0,
    aa_sharpe_lift  REAL,
    aa_passed       INTEGER,
    status          TEXT DEFAULT 'running',   -- running|completed|partial|failed
    total_seconds   REAL,
    cost_usd        REAL
);

-- One row per variant (inserted on receipt, not batched)
CREATE TABLE variant_results (
    sweep_id            TEXT NOT NULL,
    variant_name        TEXT NOT NULL,
    role                TEXT NOT NULL,        -- candidate|incumbent|aa_resplit
    entry_cap           REAL,
    drift_buffer        REAL,
    topup_threshold     REAL,
    config_fingerprint  TEXT NOT NULL,
    worker_id           TEXT,
    elapsed_seconds     REAL,
    peak_memory_mb      REAL,
    tier3_ready         INTEGER,
    verdict_json        TEXT,
    error               TEXT,                -- NULL if succeeded
    received_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (sweep_id, variant_name),
    FOREIGN KEY (sweep_id) REFERENCES sweep_runs(sweep_id)
);

-- One row per variant × seed (queryable metrics)
CREATE TABLE seed_metrics (
    sweep_id        TEXT NOT NULL,
    variant_name    TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    apy             REAL,
    sharpe          REAL,
    max_dd          REAL,
    calmar          REAL,
    turnover_ann    REAL,
    cost_bps        REAL,
    winner_cont_pct REAL,
    equity_path     TEXT,                    -- relative path to CSV
    trade_log_path  TEXT,                    -- relative path to JSONL
    PRIMARY KEY (sweep_id, variant_name, seed),
    FOREIGN KEY (sweep_id, variant_name)
        REFERENCES variant_results(sweep_id, variant_name)
);

-- Per-variant per-seed per-regime breakdown
CREATE TABLE regime_metrics (
    sweep_id        TEXT NOT NULL,
    variant_name    TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    regime          TEXT NOT NULL,
    apy             REAL,
    sharpe          REAL,
    max_dd          REAL,
    n_days          INTEGER,
    PRIMARY KEY (sweep_id, variant_name, seed, regime),
    FOREIGN KEY (sweep_id, variant_name, seed)
        REFERENCES seed_metrics(sweep_id, variant_name, seed)
);
```

**Artifact storage (equity curves + trade logs):**

Workers return equity curves and trade logs as gzip+base64 JSON strings
(~150KB per variant). The controller decompresses and writes to:

```
sweep_db/{sweep_id}/equity/{variant_name}/seed_{N}.csv
sweep_db/{sweep_id}/trades/{variant_name}/seed_{N}.jsonl
```

These are plain files, not in SQLite — they can be large and are consumed by
analysis scripts (pandas, plotting) that expect file paths.

### 4.6 Result data objects

```python
@dataclass(frozen=True)
class BacktestRequest:
    variant_name: str
    role: str
    config_json: str         # full strategy config JSON
    volume_commit_id: str    # expected data snapshot
    seeds: list[int]
    start: str               # ISO date
    end: str
    initial_cash: float
    incumbent_turnover: float | None

@dataclass(frozen=True)
class BacktestResult:
    # Identity + provenance
    variant_name: str
    role: str
    config_fingerprint: str  # SHA-256 of config_json
    worker_id: str
    volume_commit_id: str
    code_image_id: str
    started_at: str          # ISO 8601 UTC
    finished_at: str
    elapsed_seconds: float
    peak_memory_mb: float

    # Results (same schema as local execute_variant)
    seeds: list[int]
    per_seed: list[dict]     # {seed, apy, sharpe, max_dd, calmar, per_regime, turnover, winner_cont}

    # Serialized artifacts
    equity_curves: dict[int, bytes] | None  # seed → gzipped CSV
    trade_logs: dict[int, bytes] | None     # seed → gzipped JSONL

    # Integrity
    result_checksum: str     # SHA-256 of canonical JSON (excl. this field)
```

---

## 5. Failure modes and recovery

| Category | Failure | Detection | Recovery |
|----------|---------|-----------|----------|
| **Worker** | OOM | Container killed; `MemoryError` at caller | Retry once with 2× memory; if still fails, record error |
| | Timeout (>60 min) | Container killed; `TimeoutError` at caller | Record error, no retry (likely stuck) |
| | Python exception | Exception propagated via `.map()` | Retry once; record error + traceback |
| | Data checksum mismatch | Worker verifies on read → `DataIntegrityError` | Retry once; if persists, abort sweep |
| | Wrong result schema | Controller validates on receipt | Record as error, skip verdict |
| **Controller** | Crash mid-sweep | `sweep_runs.status = 'running'` stays in DB | `--resume {sweep_id}` re-dispatches missing variants |
| | Network partition | `.map()` hangs or `ConnectionError` | Checkpoint preserved; operator re-runs with `--resume` |
| | Disk full | `OSError` on SQLite write | Fail loudly; operator frees space; `--resume` |
| **Data** | Stale Volume | Pre-flight: local manifest hash ≠ Volume content | Abort + prompt sync |
| | Upload interrupted | `sync_manifest.json` not updated | Re-run sync (idempotent) |
| | Volume corruption | Worker checksum fail | Re-sync from local (Volume is disposable) |
| **Platform** | Modal outage | Connection timeout | `--backend local` (always works) |
| | Pricing change | n/a | Abstraction layer: swap to Ray/Batch |

**Resume protocol:**

```bash
python scripts/run_concentration_cap_sweep.py \
    --execute --backend modal --resume 20260707_091306
```

1. Open `sweep_db/20260707_091306/results.db`
2. Read completed variant names from `variant_results`
3. Verify Volume `commit_id` matches sweep_runs record
4. Dispatch remaining variants only
5. Merge results into existing DB

---

## 6. Non-functional requirements

### 6.1 Performance targets

| Metric | Target | How measured |
|--------|--------|-------------|
| 75-variant sweep e2e | ≤45 min | sweep_meta.json `total_seconds` |
| Cold start per worker | ≤90s | worker `started_at - dispatched_at` |
| Data sync (incremental, <10 files) | ≤30s | sync log |
| Data sync (full, 3 GB) | ≤5 min | sync log |
| Result ingestion | ≥5 variants/s | controller log |
| Local CPU during sweep | ≤5% | measured by operator |

### 6.2 Reliability

| Metric | Target | Mechanism |
|--------|--------|-----------|
| Silent data loss | zero | Checksum + schema validation on every result |
| Crash recovery | resume from last checkpoint | SQLite WAL + `--resume` |
| Automatic retry (transient) | 1 retry per worker | Modal `retries=1` |
| Partial result preservation | always | per-variant INSERT, not batch |
| Backend equivalence | ±0.01 Sharpe | A/A cross-backend test |

### 6.3 Security

| Boundary | Rule |
|----------|------|
| API keys | NEVER leave local. Hardcoded exclusion list in sync. |
| Live state | NEVER leave local. No positions/orders/cash snapshots uploaded. |
| Production DB | NEVER leave local. `runs.alpaca.db` excluded from sync. |
| Model weights | Private Modal account + private container images. |
| Strategy code | Private container images. No public repos. |
| Result data | Returns to local only. Not stored on cloud post-execution. |

### 6.4 Cost controls

| Control | Mechanism |
|---------|-----------|
| Per-sweep ceiling | `--max-cost 10.00` flag; abort if projection exceeds |
| Per-worker timeout | 3600s (1h) hard kill |
| Concurrency limit | 100 max containers (configurable) |
| Cost tracking | Per-variant cost estimated from elapsed_seconds; total in sweep_meta |
| Monthly alert | Modal dashboard alert at 80% of budget |
| Fallback | `--backend local` always functional; cloud is acceleration |

### 6.5 Observability

| Signal | Channel | Format |
|--------|---------|--------|
| Per-variant completion | terminal | `[37/74] variant_name tier3=True (182s) est=$3.40` |
| Sweep completion | ntfy push | `sweep 20260707: 74/74, 3 winners, 42min, $3.80` |
| Errors | terminal + DB | traceback stored in variant_results.error |
| Cost projection | terminal | after first 3 results, print projected total |
| Data sync status | terminal | `synced 12 files (450MB), commit=abc123` |
| Sweep history | CLI query | `SELECT * FROM sweep_runs ORDER BY created_at DESC` |

### 6.6 Reproducibility

Every result is stamped with full provenance:

```json
{
  "provenance": {
    "sweep_id": "20260707_091306",
    "backend": "modal",
    "volume_commit_id": "vol_abc123",
    "code_image_id": "im_def456",
    "code_commit": "e914f31a",
    "backtest_range": ["2024-06-01", "2026-07-01"],
    "initial_cash": 10000,
    "grid_spec_hash": "sha256:...",
    "ohlcv_file_count": 146,
    "ohlcv_total_sha256": "sha256:...",
    "wf_manifest_sha256": "sha256:..."
  }
}
```

To reproduce: same Volume commit + same image + same config → identical result
(modulo FP non-associativity, bounded by A/A cross-backend test ≤0.01 Sharpe).

---

## 7. Container image management

### 7.1 Image build

The image bundles all Python code. It is rebuilt when code changes.

```
_bundle/                          ← created by bundle.py
  subrepos/
    renquant-pipeline/src/...
    renquant-common/src/...
    renquant-model/src/...
    renquant-artifacts/src/...
    renquant-execution/src/...
    renquant-strategy-104/src/...
    renquant-base-data/src/...
    renquant-backtesting/src/...
  kernel/                         ← backtesting/renquant_104/kernel/
  sim/                            ← backtesting/renquant_104/sim/
  bundle_manifest.json            ← SHA-256 of every bundled file
```

**Bundle script** strips: `.git/`, `__pycache__/`, `tests/`, `*.pyc`,
`*.pyo`, `data/`, `artifacts/` (data is on the Volume, not in the image).

**Image is rebuilt only when `bundle_manifest.json` changes** (content-addressed).

### 7.2 GPU image variant

For W12 (model retraining), a separate image with CUDA:

```python
gpu_image = (
    modal.Image.from_registry("nvidia/cuda:12.1-runtime-ubuntu22.04")
    .pip_install("torch", ...)
    .copy_local_dir("_bundle/", "/app/")
)

@app.function(image=gpu_image, gpu="T4", ...)
def train_model_remote(request_json: str) -> str: ...
```

Same `BacktestExecutor` interface; different `@app.function` under the hood.

---

## 8. Pre-flight checks

Before any cloud dispatch, the controller runs:

| Check | Pass condition | Fail action |
|-------|---------------|-------------|
| Volume freshness | OHLCV latest date ≥ yesterday | Abort + prompt sync |
| Volume integrity | 3 random symbols: local SHA ≟ remote SHA | Abort + re-sync |
| Manifest match | local WF manifest SHA ≟ Volume manifest SHA | Abort + re-sync |
| Image recency | image build ≤30 days old | Warn (7-30d) or abort (>30d) |
| Cost projection | projected_cost ≤ max_cost | Abort |
| Platform health | Modal API responds in <5s | Abort; suggest `--backend local` |
| Backend equivalence | (first run only) 1 variant local≟modal ±0.01 Sharpe | Abort; investigate |

---

## 9. Implementation phases

### Phase 1: abstraction layer + local executor refactor

1. `cloud/__init__.py` — BacktestExecutor protocol + data objects
2. `cloud/local_executor.py` — wrap existing ProcessPoolExecutor
3. `cloud/result_store.py` — SQLite persistence (replaces flat JSON)
4. Refactor `run_concentration_cap_sweep.py` to use BacktestExecutor
5. Tests: result store (insert, resume, query), executor protocol compliance

**This phase ships value without Modal** — the SQLite store + crash recovery
+ resume improves even the local path.

### Phase 2: Modal executor + data sync

1. `cloud/modal_app.py` — Modal function definition
2. `cloud/modal_executor.py` — ModalExecutor implementing BacktestExecutor
3. `cloud/sync_data.py` — Volume sync with checksums
4. `cloud/bundle.py` — code packaging for container image
5. `cloud/preflight.py` — pre-dispatch validation
6. `--backend modal` flag on sweep script
7. Tests: mocked Modal, data sync, preflight, schema validation
8. Integration test: 2 variants on real Modal

### Phase 3: operational tooling

1. `make sweep-cloud` convenience target
2. ntfy notification on completion
3. `--max-cost` enforcement
4. `--resume` CLI
5. Sweep comparison: `scripts/compare_sweeps.py {id1} {id2}`

### Phase 4: GPU training (when W12 is needed)

1. GPU image variant
2. `train_model_remote` function
3. Walk-forward retrain integration

---

## 10. Cost model

Modal pricing (~$0.000033/vCPU·s, $2.78/GPU·h for T4):

| Workload | Workers | Time/worker | CPU/GPU | Est. cost |
|----------|---------|-------------|---------|-----------|
| W1: 75-variant sweep | 74 | ~30 min | CPU×2 | ~$4.40 |
| W4: 100 placebo shuffles | 100 | ~30 min | CPU×2 | ~$6.00 |
| W6: signal validation (10 combos) | 10 | ~30 min | CPU×2 | ~$0.60 |
| W12: PatchTST retrain (20 cutoffs) | 20 | ~5 min | T4 GPU | ~$4.60 |
| Backend equivalence test | 1 | ~30 min | CPU×2 | ~$0.06 |

Free tier ($30/month) covers: ~6 full sweeps + ~3 placebo runs + ~4 retrains.

---

## 11. Non-goals

- Does NOT move live trading / daily pipeline to cloud
- Does NOT upload secrets, live state, or production DB
- Does NOT require cloud for the system to function (`--backend local` is default)
- Does NOT implement multi-cloud (Modal primary; swap via abstraction layer if needed)
- Does NOT implement persistent cloud workers (burst-only; containers die after task)
- Does NOT change any backtest logic (same `execute_variant` everywhere)
