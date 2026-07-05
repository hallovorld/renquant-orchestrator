# RenQuant-107 As-Built Architecture

> Governance and risk infrastructure. This documents **what is implemented**
> as of 2026-07-05. All modules are observe-only; no enforcement wiring exists.

## Purpose

107 is the governance layer: decision-ledger attribution (decomposing realized P&L
into its sources), risk budgets (measuring consumption against limits), experiment
reliability (S-REL — governing evidence quality), scorer identity monitoring,
model freshness governance, readiness monitoring, and gate diagnostics. It
observes and measures; it does not gate or trade.

## Architecture

```
Run bundles (104 persists after each daily run)
  ↓
Decision ledger (S5 substrate)
  → gate verdicts: append-only per (run_id, scope, gate)
  → gate registry: verdict algebra (max-join lattice)
  → outcome validator: forward-return coverage check
  → outcome backfiller: bootstraps from candidate_scores (RECONSTRUCTED)
  ↓
Attribution engine
  → per-round-trip decomposition: TOTAL = MARKET + SIGNAL + SIZING + TIMING + COST
  → identity sum-check enforced per record (RESIDUAL ≡ 0)
  → censoring when inputs missing (never imputes)
  ↓
Risk budget ledger
  → max_drawdown (15% HARD), book_beta (0.6 planning), concentration, sleeve DD
  → consumption measured from read-only sources
  → attribution bridge (connects attribution legs to budget consumption)
  ↓
Readiness monitor (12 programmatic checks)
  → N1/N2/N3 data accumulation
  → S5/S6/S8/S-TC evidence substrate
  → D1 gate verdicts, baseline trading days
  → state transitions logged for automation
  ↓
Scorer identity monitor + model freshness enforcer
  → run-over-run identity diff on prod/calibrator/shadow lanes
  → freshness check (28-day directive) + recommendation engine
  ↓
Gate diagnostics
  → calibration diagnostic: sign-laundering zone, mu distribution
  → sign-laundering harness: matched-breadth protocol
  → software stops: trailing + dollar-max + session P&L limits
  ↓
S-REL experiment reliability
  → D-gate verdicts provisional until adversarial re-verification UPHELD
  → positive controls mandatory
  → standing verdict ledger (VERDICTS.md)
```

## Key Modules (all in renquant-orchestrator)

### Decision Ledger (S5 substrate)

| Module | Role |
|---|---|
| `decision_ledger.py` | Append-only gate-verdict event store (WAL mode, busy timeout) |
| `gate_registry.py` | GateRegistry + verdict algebra (lattice: allow < halve < block) |
| `decision_outcome_validator.py` | Forward-return coverage check (≥95% for aged decisions) |
| `outcome_backfiller.py` | Reconstructs decision_outcomes from candidate_scores (RECONSTRUCTED provenance) |
| `ledger_attribution.py` | Decision-outcomes DDL + attribution join |

### Attribution Engine (`attribution/`)

| Module | Role |
|---|---|
| `attribution/decompose.py` | Per-decision P&L decomposition into 5 legs |
| `attribution/ledger.py` | Decision ledger: round-trip records with entry/exit/reference prices |
| `attribution/report.py` | Aggregate attribution report generator |
| `decision_pnl_attribution.py` | Per-name P&L attribution (flat-module, legacy) |

The identity decomposition:
```
TOTAL  = N_r × r_real − cost
       = MARKET + SIGNAL + SIZING + TIMING + COST

MARKET = N_i × r_spy          (benchmark/beta)
SIGNAL = N_i × (r_ref − r_spy) (pick vs benchmark at intended sizing)
SIZING = (N_r − N_i) × r_ref   (realized vs intended — shrinkage + whole-share)
TIMING = N_r × (r_real − r_ref) (fill prices vs reference — entry leak)
COST   = −(fees + spread_proxy)
```

Sum is exact by construction. Censoring (HARD honesty rule): missing inputs →
affected legs reported as `None` with machine-readable reason; nothing imputed.

### Risk Budget Ledger (`risk_budget/`)

| Module | Role |
|---|---|
| `risk_budget/budget.py` | Budget definitions + current consumption from read-only sources |
| `risk_budget/report.py` | Budget report generator |
| `risk_budget/attribution_bridge.py` | Connects attribution legs to budget consumption |

Budgets (each cites its source — nothing invented):

| Budget | Limit | Source | Status |
|---|---|---|---|
| Max drawdown | 15% HARD | G* bar (#230 §4) | Observe-only |
| Book beta | 0.6 planning | RS-1 §2 heuristic (β_max = DD/stress) | Observe-only; CURRENT β CRITICAL at 0.745 (MU β=4.29) |
| Per-name concentration | Per-regime max_position_pct | Pinned strategy config | Observe-only |
| Sleeve DD sub-budget | `sleeve.dd_budget_pct` | Pipeline #157 ParkingSleeveShadowTask | Observe-only (sleeve default-OFF) |

### Readiness Monitor

| Module | Role |
|---|---|
| `readiness_monitor.py` | 12 programmatic data-accumulation checks with state transition logging |

12 checks (authoritative unless noted):

| Check | What | Authoritative |
|---|---|---|
| N1_collector_liveness | 105 collector output freshness | No (informational) |
| N2_pit_snapshots | PIT revision snapshot count (≥90d, 4-endpoint contract) | Yes |
| N2_pit_features | C1 revision-drift features built from PIT | Yes |
| N3_fmp_coverage | FMP harvest coverage (≥95%, latest file, 14d freshness) | Yes (when watchlist available) |
| S10_intraday_symbols_present | Tick-feed day/symbol accrual | No (informational) |
| M1_session_logs_observed | 105 Stage-1 session logs present | No (informational) |
| S5_decision_ledger | Decision-ledger forward-return coverage (≥95% aged) | Yes |
| S8_oos_pick_table | Track A OOS pick table exists and non-empty | Yes |
| S_TC_baseline | Transfer coefficient measurements (≥10 sessions) | Yes |
| D1_gate_verdict | WF-gate verdict freshness (≤14d) | Yes |
| S6_lambda_sweep | λ sweep config experiments (≥45) | Yes |
| baseline_trading_days | Total live trading days (≥60) | Yes |

### Gate Diagnostics

| Module | Role |
|---|---|
| `gate_calibration_diagnostic.py` | Calibrator sign-laundering zone analysis, mu distribution diagnostics |
| `sign_laundering_harness.py` | Matched-breadth protocol for measuring sign-laundering impact (M4-b) |
| `software_stop.py` | Trailing stop, dollar-max stop, session P&L limit — observe-only (105 Stage-2) |
| `config_experiment_store.py` | Persistent config-experiment DB for λ sweeps (S6) |

### Scorer Identity Monitor + Model Freshness

| Module | Role |
|---|---|
| `scorer_identity_monitor.py` | Run-over-run scorer identity diff alarm |
| `model_freshness_monitor.py` | Tournament + panel + shadow freshness tracking |
| `model_freshness_enforcer.py` | Recommendation engine (28-day directive) |

### S-REL Experiment Reliability

S-REL is a governance program (design: `doc/design/2026-07-03-s-rel-experiment-reliability.md`),
not a single module. Its mechanical enforcement surfaces through:

- **expkit** (106's experiment framework) — prereg freeze-first, placebo evaluation,
  evidence manifests
- **VERDICTS.md** (`doc/research/VERDICTS.md`) — standing verdict ledger, 14 rows,
  each with verification status and reopening conditions
- **Verification queue**: V1–V6 adversarial re-verifications dispatched; V6 UPHELD
  (Phase −1 recompute + positive control)

Key S-REL rules:
1. D-gate verdicts PROVISIONAL until adversarial re-verification UPHELD
2. Positive controls mandatory (known-good signal must fire correctly)
3. Retrospective audit queue for all pre-S-REL verdicts
4. Evidence-boundary blocks: a verdict's evidence boundary defines what data/conditions
   it covers; claims outside that boundary are not covered

### Model Freshness Governance

Operator directive (2026-06-30): NO model >28 days. If a fresh retrain fails its
gate, use the BEST model from the last 10 days (freshness > strict gate). RFC PR #210.

### Fix-Wave Protection Contract

Six rules governing all production fixes (operator directive 2026-07-03):

1. Production path is sacred — no behavior changes in fix PRs
2. Behavior-invariance proof required for every fix
3. Behavior changes = separate operator-visible design PRs
4. Production artifacts read-only
5. Sequencing: flag-off → bump → align → verify → enable
6. Live bugs: notify + propose, not hot-fix

## Current Status

- Decision ledger: DELIVERED — modules ready, pipeline integration spec written;
  pipeline-side wiring pending (S5)
- Attribution engine: DELIVERED, observe-only
- Risk budget ledger: DELIVERED, observe-only
- Readiness monitor: DELIVERED, 12 checks
- Gate diagnostics: DELIVERED (gate calibration, sign-laundering harness, software stops)
- Scorer identity monitor: DELIVERED, installed as launchd job
- Model freshness: DELIVERED (monitor + enforcer recommendation engine)
- S-REL: ACTIVE — 6 verifications dispatched, 1 UPHELD, verdict ledger maintained
- Fix-wave protection contract: ACTIVE, governing the compliance fix campaign

## Open Items

- Decision ledger pipeline wiring (S5): orchestrator modules ready, pipeline needs
  to call `write_verdicts()` at gate-verdict time — spec in #339
- Attribution validation blocked until S5 pipeline wiring lands (need per-name
  raw+mu+fwd history for demean #145 and momentum guard #187 analysis)
- Risk budgets observe-only — no enforcement wiring (existing enforcement stays
  where it lives in the strategy config's regime caps / per-name caps / vol gate)
- S-REL verification queue: V1–V4 still IN FLIGHT or PROVISIONAL
- β overshoot handling (MU β=4.29) — no automated response implemented

## Cross-references

- [104 as-built](renquant-104-as-built.md) — attribution decomposes 104's P&L; risk budgets observe 104's book
- [105 as-built](renquant-105-as-built.md) — 105 fills feed the TIMING leg; canary envelope is a 107-class risk budget
- [106 as-built](renquant-106-as-built.md) — S-REL governs 106's evidence; VERDICTS.md is shared governance
