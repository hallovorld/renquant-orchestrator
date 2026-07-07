# Design: cloud backtest compute — controller/worker burst execution

STATUS: design / RFC for cross-agent review. No infra, no spend, no live behavior change.

DATE: 2026-07-07

SCOPE: move embarrassingly-parallel backtest workloads from local CPU to cloud
burst compute with a local controller / remote worker architecture. This
document covers the full system: data lifecycle (upload, versioning, protection,
result ingestion), failure modes and recovery, non-functional requirements,
security model, cost controls, and observability.

---

## 0. Executive summary

75-variant concentration cap sweep: **38h local → ~30min cloud at ~$4**.

The system is a LOCAL CONTROLLER + REMOTE WORKERS architecture:

```
                        ┌─────────────────────────────────────────┐
                        │            MODAL CLOUD                  │
                        │                                         │
┌──────────────┐  dispatch   ┌─────────┐ ┌─────────┐             │
│  LOCAL       │────────────▶│Worker 1 │ │Worker N │  ...        │
│  CONTROLLER  │             │(variant)│ │(variant)│             │
│              │◀────────────│         │ │         │             │
│  • grid gen  │   results   └────┬────┘ └────┬────┘             │
│  • A/A ctrl  │                  │           │                   │
│  • dispatch  │            ┌─────▼───────────▼─────┐            │
│  • ingest    │            │   Modal Volume (RO)   │            │
│  • verdict   │            │   OHLCV + artifacts   │            │
│  • persist   │            │   commit_id=abc123    │            │
└──────┬───────┘            └───────────────────────┘            │
       │                                                          │
       ▼                    └─────────────────────────────────────┘
┌──────────────┐
│ LOCAL STORE  │
│ sweep_db/    │
│  results.db  │
│  equity/     │
│  trades/     │
│  configs/    │
└──────────────┘
```

Key design principles:
1. **Cloud is stateless** — workers read from immutable Volume snapshot, return
   results, leave no state behind
2. **Local is the source of truth** — all results persist locally; cloud is
   disposable compute
3. **Backend-transparent** — `--backend local|modal`; identical results
   regardless of backend
4. **Fail-safe** — partial failures produce partial results, never corrupt state;
   any incomplete sweep is resumable

---

## 1. Problem statement

### 1.1 Quantitative

| | Local (12 cores) | Cloud (74 workers) |
|---|---|---|
| Wall-clock | ~38h | ~30 min |
| Local CPU blocked | 100% all cores | 0% |
| Machine usable | No | Yes |
| Marginal cost | ~$1.50 electricity | ~$4 |
| Opportunity cost | 38h of blocked dev/trading ops | negligible |

### 1.2 Qualitative

The local sweep blocks ALL other compute on the machine — including the live
trading pipeline (daily-full, rq105 session scheduler, quote logger). This
creates an operational conflict: we can't run experiments and production
simultaneously. Cloud compute eliminates this conflict entirely.

---

## 2. Data lifecycle

### 2.1 Upload: local → cloud

| Asset | Size | Mutability | Upload trigger | Sensitivity |
|-------|------|------------|----------------|-------------|
| OHLCV daily bars | 250 MB | daily append | pre-sweep sync | PUBLIC market data |
| WF model artifacts | 2.7 GB | weekly (retrain) | post-retrain sync | PRIVATE (trained weights) |
| WF manifest | <1 MB | weekly | with artifacts | PRIVATE (model selection) |
| Strategy kernel + sim | 4.4 MB | per-PR | image rebuild | PRIVATE (proprietary logic) |
| Subrepo Python code | 93 MB | per-PR | image rebuild | PRIVATE (proprietary logic) |
| Variant configs | 44 KB each | per-sweep | inline (function args) | non-sensitive |

**Upload protocol:**
1. `sync_data` checksums every local file (SHA-256)
2. Compares against a local manifest of previously uploaded checksums
3. Uploads only changed/new files (incremental)
4. After upload: `volume.commit()` → immutable snapshot ID
5. Stores `{commit_id, timestamp, file_count, total_bytes, checksums}` in
   local `sync_manifest.json`
6. Returns the `commit_id` — the controller passes this to every worker for
   consistency verification

**Upload integrity:**
- Every file uploaded is SHA-256 checksummed locally before upload
- After upload, the worker reads the file and re-checksums on first access
  (lazy verification — only files actually used are verified)
- Mismatch → worker aborts with `DataIntegrityError`, controller marks that
  variant as failed + retries once

### 2.2 Result return: cloud → local

Each worker returns a structured result object (not raw files). The result is
serialized as JSON (not pickle — deterministic, inspectable, no code execution
on deserialization).

**Per-variant result payload (~200 KB):**

```python
@dataclass
class RemoteVariantResult:
    # Identity
    variant_name: str
    role: str  # "candidate" | "incumbent" | "aa_resplit"
    config_fingerprint: str  # SHA-256 of the variant config JSON

    # Execution metadata
    worker_id: str  # Modal container ID
    volume_commit_id: str  # data snapshot used
    code_image_id: str  # container image hash
    started_at: str  # ISO 8601 UTC
    finished_at: str  # ISO 8601 UTC
    elapsed_seconds: float
    peak_memory_mb: float

    # Results (identical schema to local execute_variant)
    seeds: list[int]
    per_seed: list[dict]  # {seed, apy, sharpe, max_dd, calmar, per_regime, turnover, winner_continuation}

    # Artifacts (compressed, base64-encoded)
    equity_curves: dict[int, str] | None  # seed → gzipped CSV, base64
    trade_logs: dict[int, str] | None  # seed → gzipped JSONL, base64

    # Integrity
    result_checksum: str  # SHA-256 of the canonical JSON (excluding this field)
```

**Why include equity curves and trade logs?**
- Metrics alone (Sharpe, max_dd) are not auditable — you can't verify HOW a
  Sharpe was computed without the underlying equity curve
- Trade logs enable post-hoc analysis (turnover decomposition, winner
  continuation, regime-conditional behavior) without re-running
- Compressed size: ~50 KB per seed → ~150 KB per variant → ~11 MB for 75
  variants. Negligible network cost.

### 2.3 Result ingestion: persist locally

The controller receives results as they complete (streaming via `.map()`)
and persists them **immediately** — not batched at the end.

**Local result store** (`sweep_db/{sweep_id}/`):

```
sweep_db/
  20260707_091306/
    sweep_meta.json          # grid spec, volume_commit_id, image_id, timing
    results.db               # SQLite: per-variant metrics, per-seed metrics
    verdicts.json            # unanimity verdicts (computed after all results)
    configs/                 # variant config JSONs (reproducibility)
      cap08_drift00_topup02.json
      ...
    equity/                  # decompressed equity curves (per-variant/seed)
      cap08_drift00_topup02/
        seed_42.csv
        seed_43.csv
        seed_44.csv
      ...
    trades/                  # decompressed trade logs
      cap08_drift00_topup02/
        seed_42.jsonl
        ...
    checkpoints/             # partial progress (for resume)
      completed_variants.json
```

**SQLite schema (`results.db`):**

```sql
CREATE TABLE sweep_runs (
    sweep_id        TEXT PRIMARY KEY,
    created_at      TIMESTAMP,
    backend         TEXT,  -- 'local' | 'modal'
    volume_commit   TEXT,
    image_id        TEXT,
    grid_spec_json  TEXT,
    incumbent_json  TEXT,
    aa_result_json  TEXT,
    aa_sharpe_lift  REAL,
    aa_passed       INTEGER,
    status          TEXT,  -- 'running' | 'completed' | 'partial' | 'failed'
    n_variants      INTEGER,
    n_completed     INTEGER,
    n_failed        INTEGER,
    total_seconds   REAL
);

CREATE TABLE variant_results (
    sweep_id            TEXT,
    variant_name        TEXT,
    role                TEXT,
    entry_cap           REAL,
    drift_buffer        REAL,
    topup_threshold     REAL,
    config_fingerprint  TEXT,
    worker_id           TEXT,
    elapsed_seconds     REAL,
    peak_memory_mb      REAL,
    result_json         TEXT,  -- full per_seed array
    tier3_ready         INTEGER,
    verdict_json        TEXT,
    error               TEXT,  -- NULL if succeeded
    received_at         TIMESTAMP,
    PRIMARY KEY (sweep_id, variant_name)
);

CREATE TABLE seed_metrics (
    sweep_id        TEXT,
    variant_name    TEXT,
    seed            INTEGER,
    apy             REAL,
    sharpe          REAL,
    max_dd          REAL,
    calmar          REAL,
    turnover_ann    REAL,
    cost_bps        REAL,
    equity_path     TEXT,  -- relative path to CSV
    trade_log_path  TEXT,  -- relative path to JSONL
    PRIMARY KEY (sweep_id, variant_name, seed)
);
```

**Why SQLite, not flat JSON?**
- Current `sweep_results.json` is a single 10+ MB file written atomically at
  the END — a crash at variant 73/74 loses everything
- SQLite: each variant is INSERT'd on receipt; crash at 73/74 preserves 72
  completed results
- Queryable: `SELECT * FROM seed_metrics WHERE sharpe > 0.5 ORDER BY calmar DESC`
- Sweep comparison: join two sweep_runs to compare parameter sensitivity

### 2.4 Data protection

| Layer | Mechanism |
|-------|-----------|
| In transit (upload) | Modal SDK uses HTTPS/TLS 1.3 |
| In transit (results) | Modal SDK uses HTTPS/TLS 1.3 |
| At rest (Modal Volume) | Modal's default encryption (AES-256) |
| At rest (local) | local filesystem (operator's responsibility) |
| Access control | Modal account-level (private, single-user) |
| Secret isolation | API keys NEVER uploaded; backtests use only historical data |
| Code protection | Proprietary code bundled in private container image |
| Data residency | Modal runs on AWS us-east-1 by default; configurable |

**What NEVER leaves local:**
- Alpaca/FMP/broker API keys
- Live portfolio state (positions, cash, orders)
- `runs.alpaca.db` (production run history)
- Strategy config with live-mode sections
- Any file under `data/` canonical paths

### 2.5 Data versioning and reproducibility

Every sweep result is stamped with:

```json
{
  "provenance": {
    "sweep_id": "20260707_091306",
    "volume_commit_id": "vol_abc123",
    "image_id": "im_def456",
    "code_commit": "e914f31a",
    "backtest_range": ["2024-06-01", "2026-07-01"],
    "initial_cash": 10000,
    "grid_spec_hash": "sha256:...",
    "ohlcv_manifest_hash": "sha256:...",
    "wf_manifest_hash": "sha256:..."
  }
}
```

To reproduce: same `volume_commit_id` + same `image_id` + same config →
deterministic result (modulo floating-point non-associativity across
architectures, which is bounded and monitored via A/A control).

---

## 3. Failure modes and recovery

### 3.1 Worker failures

| Failure | Detection | Response |
|---------|-----------|----------|
| Worker OOM | Modal kills container; raises `MemoryError` at caller | Retry once with 2× memory; if still OOM, mark failed |
| Worker timeout (>60 min) | Modal kills container; raises `TimeoutError` | Mark failed; no retry (likely stuck, not slow) |
| Worker crash (Python exception) | Exception propagated to `.map()` caller | Retry once; if still fails, record error + stack trace |
| Worker data integrity error | Worker checksums mismatch → `DataIntegrityError` | Retry once (transient Volume read issue); if persists, abort sweep |
| Worker returns malformed result | Controller schema validation fails | Mark failed; record raw response for debugging |

### 3.2 Controller failures

| Failure | Detection | Response |
|---------|-----------|----------|
| Controller crash mid-sweep | Process dies; `sweep_runs.status = 'running'` in DB | Resume: re-read `completed_variants.json`, re-dispatch only missing variants |
| Network partition (controller ↔ Modal) | `.map()` hangs or raises `ConnectionError` | Controller writes checkpoint; operator re-runs with `--resume sweep_id` |
| Local disk full | `OSError` on SQLite write | Fail loudly; operator frees space; resume |

### 3.3 Data sync failures

| Failure | Detection | Response |
|---------|-----------|----------|
| Upload interrupted | `sync_manifest.json` not updated | Re-run sync (idempotent — checksums skip already-uploaded files) |
| Volume corrupted | Worker checksum verification fails | Re-sync from local (local is source of truth); Volume is disposable |
| Stale Volume (forgot to sync) | `volume_commit_id` doesn't match expected | Controller pre-flight check: compare local manifest hash vs Volume content hash; abort if mismatch |

### 3.4 Resume protocol

```bash
# Resume a crashed/interrupted sweep
python scripts/run_concentration_cap_sweep.py \
    --execute --backend modal --resume 20260707_091306
```

1. Read `sweep_db/20260707_091306/checkpoints/completed_variants.json`
2. Compute `remaining = all_variants - completed_variants`
3. Verify Volume `commit_id` matches the original sweep's `commit_id`
4. Dispatch only remaining variants
5. Merge new results into existing `results.db`

---

## 4. Non-functional requirements

### 4.1 Performance

| Requirement | Target | Measurement |
|-------------|--------|-------------|
| Sweep wall-clock (75 variants) | ≤45 min end-to-end | sweep_meta.json total_seconds |
| Cold start overhead per worker | ≤60s | worker started_at - dispatch_at |
| Data sync (incremental, <10 files changed) | ≤30s | sync log |
| Data sync (full, 3 GB) | ≤5 min | sync log |
| Result ingestion throughput | ≥5 variants/s | controller log |
| Local controller CPU during sweep | ≤5% | top/Activity Monitor |

### 4.2 Reliability

| Requirement | Target | Mechanism |
|-------------|--------|-----------|
| Zero silent data loss | 100% | Checksum + schema validation on every result; checkpoint on every receipt |
| Crash recovery | resume from last checkpoint | `--resume` flag; SQLite WAL mode |
| Automatic retry (transient) | 1 retry per worker | Modal `retries=1` |
| Partial result preservation | always | per-variant SQLite INSERT, not batch write |
| Backend equivalence | results identical ±FP noise | A/A cross-backend test (see §6) |

### 4.3 Observability

| Signal | Where | How |
|--------|-------|-----|
| Sweep progress | terminal | `[37/74] cap12_drift08_topup03 tier3_ready=True (182s)` |
| Sweep completion | ntfy push | `sweep 20260707: 74/74 done, 3 tier3_ready, 42min, $3.80` |
| Per-worker timing | results.db | `SELECT variant_name, elapsed_seconds FROM variant_results ORDER BY elapsed_seconds DESC` |
| Cost tracking | Modal dashboard + local log | `sweep_meta.json: {cost_estimate_usd}` |
| Error details | results.db | `SELECT variant_name, error FROM variant_results WHERE error IS NOT NULL` |
| Data version audit | sweep_meta.json | `provenance.volume_commit_id` + all checksums |

### 4.4 Cost controls

| Control | Mechanism |
|---------|-----------|
| Per-sweep ceiling | `--max-cost 10.00` flag; controller tracks cumulative cost estimate; aborts dispatch if ceiling approached |
| Per-worker timeout | Modal `timeout=3600` (1h); prevents runaway containers |
| Concurrency limit | `concurrency_limit=100` on Modal function; prevents accidental 1000-worker spike |
| Monthly budget alert | Modal dashboard alert at $25 (free tier = $30) |
| Cost-per-variant estimate | logged after first 3 completions; projected total printed |
| Fallback | `--backend local` always works; cloud is acceleration, not dependency |

### 4.5 Security

| Threat | Mitigation |
|--------|------------|
| API key leakage | Keys NEVER uploaded. Backtests need zero external API access. Env vars explicitly filtered in bundle step. |
| Model IP exposure | Private Modal account. Container images are private. Volume is account-scoped. |
| Code IP exposure | Same as model: private account, private images. |
| Supply chain (malicious Modal SDK) | Pin `modal` version in requirements. Verify PyPI checksums. |
| Result tampering (MITM) | TLS in transit. `result_checksum` field verified by controller. |
| Rogue container (escape) | Modal's container isolation (gVisor/Firecracker). Not our threat model. |
| Stale data leading to wrong decisions | Volume commit_id stamped on every result; controller rejects mismatched commits |

---

## 5. Architecture details

### 5.1 Container image build

The image bundles ALL Python code needed to run a backtest. It is built locally
and pushed to Modal's registry.

```python
image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install_from_pyproject("/path/to/renquant-orchestrator/pyproject.toml")
    .pip_install(
        "pandas", "numpy", "scipy", "scikit-learn",
        "torch",  # PatchTST model inference
        "xgboost",
        # ... exact versions from requirements.txt
    )
    .copy_local_dir("_bundle/subrepos/", "/app/subrepos/")
    .copy_local_dir("_bundle/kernel/", "/app/kernel/")
    .copy_local_dir("_bundle/sim/", "/app/sim/")
    .env({
        "PYTHONPATH": "/app/subrepos/renquant-pipeline/src:"
                      "/app/subrepos/renquant-common/src:"
                      "/app/subrepos/renquant-base-data/src:"
                      "/app/subrepos/renquant-model/src:"
                      "/app/subrepos/renquant-artifacts/src:"
                      "/app/subrepos/renquant-execution/src:"
                      "/app/subrepos/renquant-strategy-104/src:"
                      "/app/subrepos/renquant-backtesting/src:"
                      "/app/kernel:/app/sim",
    })
)
```

**Bundle script** (`cloud/bundle.py`):
1. Copies subrepo source trees (src/ only, no .git, no tests, no data)
2. Copies kernel/ and sim/ from backtesting/renquant_104/
3. Strips `__pycache__`, `.pyc`, `.pyo`
4. Writes a `bundle_manifest.json` with SHA-256 of every file
5. Image is rebuilt only when `bundle_manifest.json` changes

### 5.2 Worker function

```python
@app.function(
    image=image,
    volumes={"/data": data_volume},
    cpu=2,
    memory=4096,
    timeout=3600,
    retries=1,
)
def run_variant_remote(request_json: str) -> str:
    """Execute one variant backtest. Input and output are JSON strings
    (not pickle — deterministic, inspectable, no code execution risk).
    """
    import json, time, hashlib, os, gzip, base64, io
    import resource
    import pandas as pd

    request = json.loads(request_json)
    t0 = time.time()

    # Verify data integrity
    expected_commit = request["volume_commit_id"]
    # (Modal mounts the committed snapshot — commit_id is structural)

    # Load OHLCV from Volume
    ohlcv_dir = Path("/data/ohlcv")
    ohlcv = {}
    for f in ohlcv_dir.glob("*.parquet"):
        ohlcv[f.stem] = pd.read_parquet(f)

    # Load manifest
    manifest_path = "/data/manifest.json"

    # Deserialize variant config
    config = json.loads(request["config_json"])
    config["_strategy_dir"] = "/app/kernel"
    # ... (same setup as local execute_variant)

    # Run backtest
    from sim.runner import run_backtest_multi_seed
    result = run_backtest_multi_seed(...)

    # Collect per-seed results + artifacts
    per_seed = []
    equity_curves = {}
    trade_logs = {}
    for seed, seed_result in zip(seeds, result.per_seed_results):
        # ... metrics extraction (same as local)

        # Serialize equity curve
        eq_df = getattr(seed_result, "equity_df", None)
        if eq_df is not None:
            buf = io.BytesIO()
            eq_df.to_csv(buf, index=True)
            equity_curves[seed] = base64.b64encode(
                gzip.compress(buf.getvalue())
            ).decode()

        # Serialize trade log
        tl = getattr(seed_result, "trade_log", None)
        if tl:
            tl_json = "\n".join(json.dumps(t, default=str) for t in tl)
            trade_logs[seed] = base64.b64encode(
                gzip.compress(tl_json.encode())
            ).decode()

    # Build result
    peak_mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # MB
    result_obj = {
        "variant_name": request["variant_name"],
        "role": request["role"],
        "config_fingerprint": hashlib.sha256(
            request["config_json"].encode()
        ).hexdigest(),
        "worker_id": os.environ.get("MODAL_TASK_ID", "unknown"),
        "volume_commit_id": expected_commit,
        "code_image_id": os.environ.get("MODAL_IMAGE_ID", "unknown"),
        "started_at": request.get("dispatched_at"),
        "finished_at": datetime.utcnow().isoformat(),
        "elapsed_seconds": time.time() - t0,
        "peak_memory_mb": peak_mem,
        "seeds": seeds,
        "per_seed": per_seed,
        "equity_curves": equity_curves or None,
        "trade_logs": trade_logs or None,
    }

    # Compute checksum over result (excluding checksum field itself)
    canonical = json.dumps(result_obj, sort_keys=True, default=str)
    result_obj["result_checksum"] = hashlib.sha256(canonical.encode()).hexdigest()

    return json.dumps(result_obj, default=str)
```

### 5.3 Controller dispatch and ingestion

```python
def run_sweep_modal(candidates, incumbent_result, sweep_id, volume_commit_id, ...):
    """Dispatch variants to Modal workers, ingest results as they arrive."""

    db = init_sweep_db(sweep_id)
    checkpoint = load_checkpoint(sweep_id)  # for resume
    remaining = [v for v in candidates if v.name not in checkpoint.completed]

    # Build requests
    requests = []
    for variant in remaining:
        requests.append(json.dumps({
            "variant_name": variant.name,
            "role": variant.role,
            "config_json": variant.config_path.read_text(),
            "volume_commit_id": volume_commit_id,
            "dispatched_at": datetime.utcnow().isoformat(),
            "start": start, "end": end,
            "initial_cash": initial_cash,
            "seeds": list(variant.seeds),
            "incumbent_turnover": inc_turnover,
        }))

    # Stream results as they complete
    completed = len(checkpoint.completed)
    total = len(candidates)
    cost_estimate = 0.0

    for result_json in run_variant_remote.map(requests):
        completed += 1
        result = json.loads(result_json)

        # Verify integrity
        verify_result_checksum(result)
        verify_volume_commit(result, volume_commit_id)
        verify_schema(result)

        # Persist immediately
        ingest_variant_result(db, sweep_id, result)
        decompress_and_save_artifacts(sweep_id, result)
        update_checkpoint(sweep_id, result["variant_name"])

        # Compute verdict
        verdict = unanimity_verdict(result, incumbent_result, ...)
        update_verdict(db, sweep_id, result["variant_name"], verdict)

        # Progress + cost tracking
        cost_estimate += estimate_cost(result["elapsed_seconds"])
        print(f"[{completed}/{total}] {result['variant_name']} "
              f"tier3_ready={verdict['tier3_ready']} "
              f"({result['elapsed_seconds']:.0f}s) "
              f"est_cost=${cost_estimate:.2f}")

    # Final
    finalize_sweep(db, sweep_id)
    notify_completion(sweep_id, completed, total, cost_estimate)
```

### 5.4 Pre-flight checks

Before dispatching to cloud, the controller runs a checklist:

```python
def preflight_checks(volume_commit_id, grid_variants, ...):
    """Abort-or-proceed gate. Every check must pass."""
    checks = []

    # 1. Volume freshness
    local_ohlcv_latest = max_date_in_ohlcv_dir(local_ohlcv_path)
    checks.append(("ohlcv_fresh", local_ohlcv_latest >= yesterday()))

    # 2. Volume integrity (spot-check 3 random symbols)
    for sym in random.sample(all_symbols, 3):
        local_hash = sha256_file(local_ohlcv_path / f"{sym}.parquet")
        remote_hash = volume_file_hash(volume_commit_id, f"ohlcv/{sym}.parquet")
        checks.append((f"ohlcv_{sym}_match", local_hash == remote_hash))

    # 3. Manifest integrity
    checks.append(("manifest_match",
        sha256_file(local_manifest) == volume_file_hash(volume_commit_id, "manifest.json")))

    # 4. Image recency (warn if >7 days old, fail if >30)
    checks.append(("image_fresh", image_age_days() <= 30))

    # 5. Cost projection
    projected = len(grid_variants) * COST_PER_VARIANT_ESTIMATE
    checks.append(("cost_within_budget", projected <= max_cost))

    # 6. Backend equivalence (run 1 variant locally + remotely, compare)
    # Only on first use or after image rebuild
    if not backend_equivalence_verified(volume_commit_id):
        local_r = execute_variant(grid_variants[0], backend="local", ...)
        remote_r = execute_variant(grid_variants[0], backend="modal", ...)
        sharpe_diff = abs(local_r.sharpe - remote_r.sharpe)
        checks.append(("backend_equivalence", sharpe_diff < 0.01))

    failed = [(name, ok) for name, ok in checks if not ok]
    if failed:
        raise PreflightError(f"Pre-flight checks failed: {failed}")
```

---

## 6. Testing and validation

### 6.1 Backend equivalence test

Run the SAME variant on both backends; verify results match within FP tolerance.

```python
def test_backend_equivalence():
    """Local and Modal backends produce identical results (±FP noise)."""
    variant = build_test_variant(entry_cap=0.12, drift_buffer=0.0, topup=0.05)
    local_result = execute_variant(variant, backend="local")
    modal_result = execute_variant(variant, backend="modal")

    for seed in variant.seeds:
        local_seed = get_seed_result(local_result, seed)
        modal_seed = get_seed_result(modal_result, seed)
        assert abs(local_seed["sharpe"] - modal_seed["sharpe"]) < 0.01
        assert abs(local_seed["max_dd"] - modal_seed["max_dd"]) < 0.005
        assert abs(local_seed["apy"] - modal_seed["apy"]) < 0.02
```

This test is run:
- Once per image rebuild (CI or pre-flight)
- A/A cross-backend control in sweep_meta.json

### 6.2 Unit tests (mocked Modal)

```python
def test_result_ingestion_persists_immediately(tmp_path):
    """Each result is persisted to SQLite on receipt, not batched."""
    db = init_sweep_db("test_sweep", tmp_path)
    fake_result = make_fake_result("variant_1")
    ingest_variant_result(db, "test_sweep", fake_result)
    # Simulate crash
    # Re-open DB — variant_1 should be there
    rows = query_db(db, "SELECT * FROM variant_results")
    assert len(rows) == 1
    assert rows[0]["variant_name"] == "variant_1"

def test_resume_skips_completed(tmp_path):
    """Resume dispatches only remaining variants."""
    ...

def test_malformed_result_rejected():
    """Result with missing fields or bad checksum is rejected, not persisted."""
    ...

def test_volume_commit_mismatch_rejected():
    """Worker result with wrong volume_commit_id is rejected."""
    ...
```

### 6.3 Integration tests (real Modal, small scale)

```python
def test_end_to_end_2_variants():
    """Dispatch 2 variants to real Modal, verify results in local DB."""
    # Uses test data (small OHLCV subset, 30 days)
    # Verifies: dispatch, execution, return, ingestion, verdict
    ...
```

---

## 7. Implementation phases

### Phase 1: core infrastructure

1. `renquant_orchestrator/cloud/__init__.py`
2. `renquant_orchestrator/cloud/bundle.py` — package subrepo + kernel code
3. `renquant_orchestrator/cloud/sync_data.py` — OHLCV + artifact upload with checksums
4. `renquant_orchestrator/cloud/modal_app.py` — Modal function definition
5. `renquant_orchestrator/cloud/result_store.py` — SQLite result persistence
6. `renquant_orchestrator/cloud/preflight.py` — pre-dispatch validation
7. Tests: mocked Modal + result store + resume + integrity checks

### Phase 2: sweep integration

1. `--backend modal` flag on `run_concentration_cap_sweep.py`
2. `--resume <sweep_id>` flag
3. Backend equivalence test
4. End-to-end integration test (2 variants, real Modal)

### Phase 3: operational tooling

1. `make sweep-cloud` convenience target
2. ntfy notification on completion
3. `--max-cost` ceiling enforcement
4. Sweep comparison CLI (`compare-sweeps <id1> <id2>`)

---

## 8. Cost model

Modal pricing (2026-07): ~$0.000033/vCPU·s.

| Scenario | Workers | Time/worker | vCPU·h | Est. cost |
|----------|---------|-------------|--------|-----------|
| 75-variant sweep | 74 | ~30 min | 74 | ~$4.40 |
| 225-variant expanded grid | 224 | ~30 min | 224 | ~$13.40 |
| Single A/B test | 2 | ~30 min | 2 | ~$0.12 |
| Backend equivalence test | 1 | ~30 min | 1 | ~$0.06 |

Free tier: $30/month → ~7 full sweeps/month.

---

## 9. Non-goals

- Does NOT move live trading / daily-full pipeline to cloud
- Does NOT upload API keys, live state, or account data
- Does NOT replace local development workflow
- Does NOT require Modal for the system to function (cloud = opt-in)
- Does NOT change any backtest logic
- Does NOT implement multi-cloud (Modal only; revisit if pricing changes)
- Does NOT implement persistent cloud workers (burst only; containers die after task)
