# RenQuant-104 As-Built Architecture

> Production daily batch decisioning system. This documents **what is deployed**
> as of 2026-07-04, not what was designed — read the code, not the plans.

## Purpose

104 is the daily post-close decisioning loop: ingest market data, score the panel,
gate-check candidates, size positions, and submit orders to the broker. It runs
once per trading day after market close.

## Architecture

```
data refresh (base-data)
  → alpha158 feature matrix (panel_pipeline)
  → panel scoring (PatchTST shadow / XGB primary)
  → walk-forward sanity gate
  → global calibration (raw → μ/σ)
  → conviction gate (μ floor + optional demean)
  → vol gate / wash-sale / correlation / sector caps
  → rotation tree (held vs candidate comparison)
  → Kelly sizing → portfolio QP
  → execution (Alpaca via renquant-execution)
  → run bundle persistence
```

## Key Modules by Repo

### renquant-pipeline (AUTHORITY for kernel/ per C1 governance)

| Path | Role |
|---|---|
| `kernel/pipeline/pp_inference.py` | Daily inference pipeline — orchestrates all tasks |
| `kernel/pipeline/pp_training.py` | Walk-forward training pipeline |
| `kernel/pipeline/pp_execution.py` | Post-decision execution hand-off |
| `kernel/pipeline/task_candidates.py` | Universe filtering + candidate generation |
| `kernel/pipeline/task_regime.py` | Regime detection (BULL_CALM / BULL_VOLATILE / CHOPPY / BEAR) |
| `kernel/pipeline/task_sell.py` | Exit logic: panel-exit, stop-loss, drawdown |
| `kernel/pipeline/task_buy_quality_gates.py` | Buy funnel: vol gate, veto, conviction, correlation, sector |
| `kernel/pipeline/task_rotation.py` | Rotation tree: initiate threshold + min_hold + tax |
| `kernel/pipeline/task_selection.py` | Final candidate selection |
| `kernel/pipeline/task_execution.py` | Order construction + sizing |
| `kernel/panel_pipeline/panel_scorer.py` | Panel scoring dispatcher |
| `kernel/panel_pipeline/hf_patchtst_scorer.py` | PatchTST scorer (HuggingFace) |
| `kernel/panel_pipeline/global_calibrator.py` | Raw score → calibrated μ/σ |
| `kernel/panel_pipeline/shadow_scoring.py` | Shadow lane scoring |
| `kernel/walk_forward/` | WF sanity gate (leakage, correlation, lean guards) |
| `kernel/portfolio_qp/` | Convex portfolio optimization (cvxportfolio backend) |
| `kernel/execution/` | Execution backend (fees, slippage, T+2) |

### RenQuant umbrella (`backtesting/renquant_104/`)

| Path | Role |
|---|---|
| `main.py` | CLI entry point |
| `adapters/runner.py` | `RunnerAdapter` — the live daily-run orchestrator |
| `adapters/commit_contract.py` | Order commit contract (S-FRAC stage 0: `normalize_fill_qty`) |
| `adapters/runner_prep.py` | Pre-run data preparation |
| `adapters/runner_artifacts.py` | Run bundle persistence |
| `adapters/panel_runtime.py` | Panel scorer runtime wiring |
| `adapters/state_store.py` | Persistent state management |
| `adapters/z9_stops.py` | Software stop registry |
| `kernel/` | **Frozen compatibility mirror** — pipeline is the authority; this copy drifts and is being governed under C1 |
| `kernel/tournament_acceptance.py` | Tournament-shaped acceptance gate (T1–T5) |

### renquant-execution

| Path | Role |
|---|---|
| `order_state_machine.py` | Order lifecycle FSM (slice 1 of 105 build) |
| `alpaca_broker_port.py` | Live Alpaca TradingClient broker port |

### renquant-base-data

| Path | Role |
|---|---|
| `transformer_corpus.py` | TRUE panel recipe (B1 fix: unified train/serve corpus) |
| `rawlabel_sidecar.py` | Raw label recipe with NaN-extension |
| `alpha158_ops.py` | Unified train/serve alpha158 operators (B8 fix) |

### renquant-common

| Path | Role |
|---|---|
| `market_calendar.py` | Canonical NYSE session calendar (B5, v0.10.0) |
| `notify.py` | Canonical ntfy sender with `RENQUANT_NO_NOTIFY` (B6, v0.10.0) |

### renquant-orchestrator

| Path | Role |
|---|---|
| `agent_workflows.py` | Multi-repo orchestration (pin management, promote) |
| `build_patchtst_wf_manifest.py` | PatchTST walk-forward manifest builder |
| `scorer_identity_monitor.py` | Run-over-run scorer identity diff alarm |

## Models

- **Primary**: XGB panel scorer (re-promoted 2026-06-23, trained 2026-06-21)
- **Shadow**: PatchTST (HuggingFace Transformer, panel-trained)
- **Calibrator**: Global calibrator paired to the primary scorer (re-fit after 06-21 restore)
- **Regime**: HMM-based regime detector (BULL_CALM / BULL_VOLATILE / CHOPPY / BEAR)

## Gates and Contracts

| Gate | What it does | Where |
|---|---|---|
| WF sanity | Leakage guard, correlation guard, lean guard on walk-forward results | `kernel/walk_forward/` |
| Conviction | `mu_floor` (0.03) + optional `demean_cross_sectional` (enabled, monitored) | `task_buy_quality_gates.py` |
| Vol gate | Realized vol > 60% annualized blocks new buys (grandfathers held positions) | `task_buy_quality_gates.py` |
| Wash-sale | 30-day wash-sale window on sold names | `kernel/intraday_wash.py` |
| Correlation cap | Max correlation between held names | `task_buy_quality_gates.py` |
| Sector cap | Per-regime `max_positions_per_sector` / `max_sector_weight_pct` | `task_buy_quality_gates.py` |
| Rotation tree | Initiate threshold + min_hold + tax-aware rotation | `task_rotation.py` |
| Tournament acceptance | T1–T5 gate for Sunday tournament model writes | `kernel/tournament_acceptance.py` |
| Fingerprint governance | M6 version-dispatched verification + census (47/47 green) | `panel_pipeline/fingerprint_dispatch.py` |

## Known Issues

- **Kernel dual-home drift**: 78/169 kernel files materially drifted between pipeline
  and umbrella copies; C1 governance program in progress (pipeline = authority,
  umbrella = frozen mirror, CI drift detection planned)
- **RANK5-60 train/serve skew (B8)**: pandas average-rank (train) vs max-rank (serve)
  on the XGB path — biting the entire XGB service life; behavior change requires
  separate operator-visible design PR per fix-wave protection contract
- **Sign laundering**: calibrator neutral at raw −0.2902; 44–45/90 candidates get
  sign-laundered to μ=0 post-recentering; M4-b matched-breadth protocol pending
- **Whole-share sizing artifact**: `int()` floor truncation in `commit_contract.py`
  (S-FRAC stage 0 `normalize_fill_qty` delivered, capability-gated behind
  `fractional_shares_enabled`)

## Cross-references

- [105 as-built](renquant-105-as-built.md) — 105's intraday tick consumes 104's daily signals as frozen class-A inputs
- [106 as-built](renquant-106-as-built.md) — signal evolution experiments target the 104 scoring pipeline
- [107 as-built](renquant-107-as-built.md) — attribution engine decomposes 104's realized P&L; risk budgets observe 104's book
