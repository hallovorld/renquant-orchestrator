# Design: cloud backtest compute — Modal-first burst execution

STATUS: design / RFC for cross-agent review. No infra, no spend, no live behavior change.

DATE: 2026-07-07

SCOPE: move embarrassingly-parallel backtest workloads (concentration cap sweeps,
A/B parameter searches, walk-forward retrains) from local CPU to cloud burst
compute. Local machine keeps the controller role; cloud workers execute the
per-variant backtests.

---

## 0. Executive summary

The concentration cap sweep (75 variants × 3 seeds × 575 days = 129k pipeline
runs) takes **~38h on 12 local cores**. The same work on 74 Modal containers
finishes in **~30 minutes** at ~$3-5. The architecture is a thin wrapper:

```
LOCAL CONTROLLER                    MODAL CLOUD
┌─────────────────┐                ┌─────────────────────┐
│ sweep script     │── .map() ────▶│ N containers         │
│ (grid gen,       │               │ (each runs 1 variant │
│  verdict agg,    │◀── results ──│  × 3 seeds backtest) │
│  report)         │               └─────────────────────┘
└─────────────────┘                        │
        │                           ┌──────┴──────┐
        │                           │ Modal Volume │
        │                           │ (OHLCV, model│
        │                           │  artifacts)  │
        │                           └─────────────┘
        ▼
  sweep_results.json
  sweep_verdicts.json
```

---

## 1. Problem

| Metric | Local (12 cores) | Cloud (74 workers) |
|--------|------------------|--------------------|
| Wall-clock | ~38h | ~30min |
| CPU blocked | 100% all cores | 0% local |
| Cost | electricity + opportunity | ~$3-5 |
| Machine usable during? | No | Yes |

Current sweep uses `ProcessPoolExecutor(max_workers=12)`. Each variant is
independent — no cross-variant state, no shared mutable data. This is textbook
embarrassingly parallel.

---

## 2. Data dependencies (what goes to cloud)

| Asset | Size | Changes | Upload strategy |
|-------|------|---------|-----------------|
| OHLCV daily bars | 250 MB | daily | Modal Volume, refresh nightly |
| Model artifacts (walkforward) | 2.7 GB | weekly (retrain) | Modal Volume, refresh on retrain |
| Strategy kernel + sim | 4.4 MB | per-PR | Bundle in container image |
| Subrepo Python code | 93 MB | per-PR | Bundle in container image |
| Variant configs | 44 KB each | per-sweep | Passed as function args (serialized JSON) |
| Walk-forward manifest | <1 MB | weekly | Passed as function arg |

**Security constraints:**
- NO API keys (Alpaca, FMP) go to cloud — backtests use only historical data
- NO live state (positions, orders) leaves local
- OHLCV data is non-proprietary (public market data)
- Model artifacts contain trained weights — acceptable for private Modal account

---

## 3. Architecture

### 3.1 Modal app definition

```python
# renquant_orchestrator/cloud/modal_app.py

import modal

app = modal.App("renquant-backtest")

# Persistent storage for large assets (OHLCV + model artifacts)
data_volume = modal.Volume.from_name("renquant-backtest-data", create_if_missing=True)

# Container image: Python 3.10 + all subrepo dependencies
image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install_from_pyproject("pyproject.toml")
    .copy_local_dir("subrepo_bundle/", "/app/subrepos/")
    .copy_local_dir("kernel_bundle/", "/app/kernel/")
    .env({"PYTHONPATH": "/app/subrepos:/app/kernel"})
)

@app.function(
    image=image,
    volumes={"/data": data_volume},
    cpu=2,
    memory=4096,
    timeout=3600,
    retries=1,
)
def run_variant_remote(
    variant_json: str,
    ohlcv_path: str = "/data/ohlcv",
    manifest_path: str = "/data/manifest.json",
    start: str = "2024-06-01",
    end: str = "2026-07-01",
    initial_cash: float = 10_000.0,
    incumbent_turnover: float | None = None,
) -> str:
    """Execute one variant backtest (all seeds) in the cloud.
    Returns JSON string with per-seed results."""
    ...  # deserialize variant, run backtest, return JSON
```

### 3.2 Local controller changes

The sweep script gains a `--backend` flag:

```
python scripts/run_concentration_cap_sweep.py \
    --execute --backend modal    # cloud
    --execute --backend local    # today's ProcessPoolExecutor (default)
```

Controller responsibilities (always local):
1. Generate variant grid + configs
2. Run incumbent + A/A control locally (fast, 2 variants)
3. Dispatch N candidates to Modal via `.map()`
4. Collect results, compute unanimity verdicts
5. Write `sweep_results.json` + `sweep_verdicts.json`

### 3.3 Data sync workflow

```bash
# One-time setup (or after retrain / data refresh)
python -m renquant_orchestrator.cloud.sync_data \
    --ohlcv /path/to/ohlcv/ \
    --artifacts /path/to/walkforward_artifacts/ \
    --manifest /path/to/manifest.json
# Uploads to Modal Volume. Incremental — only changed files.
```

The sync script:
- Checksums local files, skips unchanged
- Uploads OHLCV as parquet files (one per symbol)
- Uploads walkforward model artifacts
- Uploads the manifest JSON
- Prints a summary: N files uploaded, total size, Volume name

### 3.4 Result integrity

Each remote worker returns a JSON result with:
- `variant_name`, `seeds`, `per_seed` metrics (same schema as local)
- `worker_id` (Modal container ID)
- `elapsed_seconds`
- `data_volume_commit_id` (ensures all workers used the same data snapshot)

The local controller verifies:
- All N variants returned results (no silent drops)
- `data_volume_commit_id` matches across all workers (consistent data)
- Result schema matches expected fields
- No NaN/Inf in critical metrics (Sharpe, max_dd, calmar)

---

## 4. Cost model

Modal pricing (as of 2026-07): $0.12/vCPU·h.

| Scenario | Workers | Time/worker | Cost |
|----------|---------|-------------|------|
| 75-variant sweep (current) | 74 | ~30 min | ~$4.40 |
| 225-variant expanded grid | 224 | ~30 min | ~$13.40 |
| Single A/B test (2 variants) | 2 | ~30 min | ~$0.12 |

Free tier: $30/month credit covers ~7 full sweeps.

Compare: 38h of local compute at $0.15/kWh ≈ $1.50 electricity, but
**opportunity cost of blocking the machine for 38h** is the real expense.

---

## 5. Generalization: not just sweeps

The same Modal function can serve ANY embarrassingly-parallel backtest:

| Use case | Variants | Estimated time |
|----------|----------|----------------|
| Concentration cap sweep | 75 × 3 seeds | ~30 min |
| Kelly fraction search | 20 × 3 seeds | ~10 min |
| Walk-forward retrain validation | 10 cutoffs × 3 seeds | ~10 min |
| Regime-conditional parameter search | 50 × 3 seeds | ~20 min |
| Placebo/shuffle significance test | 100 shuffles | ~40 min |

The `run_variant_remote` function takes a generic config JSON — any backtest
expressible as a strategy config variant can run on it.

---

## 6. Implementation phases

### Phase 1: Modal app + sweep integration (this PR series)

1. `renquant_orchestrator/cloud/modal_app.py` — Modal function definition
2. `renquant_orchestrator/cloud/sync_data.py` — OHLCV + artifact upload
3. `renquant_orchestrator/cloud/bundle.py` — package subrepo + kernel code
4. Modify `run_concentration_cap_sweep.py` to accept `--backend modal`
5. Tests: mock Modal, verify result schema, verify data integrity checks

### Phase 2: CLI convenience (after Phase 1 proven)

```bash
# One command to sweep in cloud
make sweep-cloud GRID=concentration_cap
```

### Phase 3: Monitoring + cost guard (after Phase 2)

- ntfy notification on sweep completion
- Cost ceiling per sweep (Modal supports `max_cost` per function)
- Dashboard: sweep history, cost per sweep, time saved

---

## 7. What this does NOT do

- Does NOT move live trading / daily-full pipeline to cloud
- Does NOT upload API keys, live state, or account data
- Does NOT replace local development workflow — `--backend local` stays default
- Does NOT require Modal for the system to function — cloud is opt-in acceleration
- Does NOT change any backtest logic — the same `execute_variant` runs locally or
  remotely with identical inputs and outputs

---

## 8. Pre-requisites

1. Modal account + API token (`modal setup`)
2. `pip install modal` in the orchestrator venv
3. First data sync (~3 min for 250 MB OHLCV + 2.7 GB artifacts)

---

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Modal outage | Sweep blocked | Fall back to `--backend local` |
| Data drift (stale Volume) | Wrong results | `data_volume_commit_id` check; sync before sweep |
| Cost runaway | $ | Modal `max_cost` per function; free tier covers normal use |
| Code/data mismatch | Wrong results | Bundle code in image; version-stamp results |
| Model artifacts = IP | Leakage | Private Modal account; artifacts are trained weights not source |
