# RenQuant-107 As-Built Architecture

> Governance and risk infrastructure. This documents **what is implemented**
> as of 2026-07-04. All modules are observe-only; no enforcement wiring exists.

## Purpose

107 is the governance layer: decision-ledger attribution (decomposing realized P&L
into its sources), risk budgets (measuring consumption against limits), experiment
reliability (S-REL — governing evidence quality), scorer identity monitoring, and
the model freshness governance policy. It observes and measures; it does not gate
or trade.

## Architecture

```
Run bundles (104 persists after each daily run)
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
S-REL experiment reliability
  → D-gate verdicts provisional until adversarial re-verification UPHELD
  → positive controls mandatory
  → standing verdict ledger (VERDICTS.md)
  ↓
Scorer identity monitor
  → run-over-run identity diff on prod/calibrator/shadow lanes
  → unexplained boundary → CRITICAL alert
  → freshness check (28-day directive)
```

## Key Modules (all in renquant-orchestrator)

### Attribution Engine (`attribution/`)

| Module | Role |
|---|---|
| `attribution/decompose.py` | Per-decision P&L decomposition into 5 legs |
| `attribution/ledger.py` | Decision ledger: round-trip records with entry/exit/reference prices |
| `attribution/report.py` | Aggregate attribution report generator |

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

### Scorer Identity Monitor

| Module | Role |
|---|---|
| `scorer_identity_monitor.py` | Run-over-run scorer identity diff alarm |

Reads run bundles (read-only DB), extracts scorer identity tuples per lane
(prod_panel, calibrator, shadow_models), diffs consecutive runs. Unexplained
boundary → CRITICAL ntfy alert. Also checks trained-date freshness against
28-day operator directive.

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

- Attribution engine: DELIVERED, observe-only (23 tests)
- Risk budget ledger: DELIVERED, observe-only (34 tests)
- Scorer identity monitor: DELIVERED, installed as launchd job (35 tests)
- S-REL: ACTIVE — 6 verifications dispatched, 1 UPHELD, verdict ledger maintained
- Model freshness governance: RFC merged, enforced by scorer identity monitor's
  trained-date freshness check
- Fix-wave protection contract: ACTIVE, governing the compliance fix campaign

## Open Items

- Attribution engine blocked by missing decision ledger persistence (#133) —
  validation of demean (#145) and momentum guard (#187) impossible without
  per-name raw+mu+fwd history
- Risk budgets observe-only — no enforcement wiring (existing enforcement stays
  where it lives in the strategy config's regime caps / per-name caps / vol gate)
- S-REL verification queue: V1–V4 still IN FLIGHT or PROVISIONAL
- β overshoot handling (MU β=4.29) — no automated response implemented

## Cross-references

- [104 as-built](renquant-104-as-built.md) — attribution decomposes 104's P&L; risk budgets observe 104's book
- [105 as-built](renquant-105-as-built.md) — 105 fills feed the TIMING leg; canary envelope is a 107-class risk budget
- [106 as-built](renquant-106-as-built.md) — S-REL governs 106's evidence; VERDICTS.md is shared governance
