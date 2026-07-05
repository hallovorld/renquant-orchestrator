# S5: Decision-ledger pipeline integration specification

DATE: 2026-07-04
STATUS: SPEC (not yet implemented — pipeline-side PR required)
BLOCKS: S8 (Track A substrate), M-SIG (signal measurement), M3 (shrinkage review),
        107 attribution engine validation

## Purpose

The decision-ledger modules exist in renquant-orchestrator (`decision_ledger.py`,
`gate_registry.py`, `ledger_attribution.py`, `outcome_backfiller.py`,
`decision_outcome_validator.py`) but the pipeline does NOT yet call them during
live runs. This document specifies exactly what the pipeline must wire up to
satisfy S5's acceptance criterion: **every live run writes gate verdicts; forward-
outcome join ≥95% for aged decisions.**

## Current state

| Component | Exists? | Where | Status |
|-----------|---------|-------|--------|
| `GateRegistry` | Yes | orchestrator `gate_registry.py` | Module ready, no callers in pipeline |
| `write_verdicts()` | Yes | orchestrator `decision_ledger.py` | Module ready, no callers in pipeline |
| `decision_outcomes` table | Yes | orchestrator `ledger_attribution.py` DDL | Table exists, no live population |
| `outcome_backfiller.py` | Yes | orchestrator (PR #335) | Reconstructed bootstrap, not live |
| `decision_outcome_validator.py` | Yes | orchestrator (PR #335) | Ready to consume live data |
| Readiness check | Yes | orchestrator `readiness_monitor.py` | `S5_decision_ledger` check active |

## What the pipeline must do

### Step 1: Instrument gate verdicts (per live run)

At the end of the buy-funnel in `kernel/pipeline/task_buy_quality_gates.py` (or
wherever the per-ticker gate decisions are finalized), the pipeline should:

```python
from renquant_orchestrator.gate_registry import GateRegistry, GateVerdict
from renquant_orchestrator.decision_ledger import connect, write_verdicts

registry = GateRegistry()

# For each gate that runs:
registry.submit(GateVerdict(
    gate="VetoWeakBuys",
    scope=ticker,           # or "book" for book-level gates
    verdict="block",        # "allow" | "halve" | "block"
    reason="rank below floor (rank=45, floor=30)",
    inputs={"rank": 45, "rank_floor": 30, "mu": 0.012},
))

# After all gates for this run:
conn = connect()  # opens ~/renquant-data/decision_ledger.db
write_verdicts(conn, run_id=run_id, as_of=run_date, verdicts=[
    {"scope": v.scope, "gate": v.gate, "verdict": v.verdict,
     "reason": v.reason, "inputs": v.inputs}
    for v in registry._verdicts
])
conn.close()
```

### Step 2: Gate names to instrument

These are the gates in the 104 buy funnel that produce per-ticker verdicts:

| Gate name (ledger key) | What it does | Scope |
|------------------------|-------------|-------|
| `WashSaleGate` | 30-day wash-sale window on sold names | per-ticker |
| `RealizedVolGate` | Blocks new buys above 60% annualized vol | per-ticker |
| `VetoWeakBuys` | Rank floor veto | per-ticker |
| `ConvictionGate` | mu_floor + optional demean | per-ticker |
| `CorrelationCap` | Max correlation between held names | per-ticker |
| `SectorCap` | Per-regime max_positions_per_sector / max_sector_weight_pct | per-ticker |
| `RotationTree` | Initiate threshold + min_hold + tax-aware rotation | per-ticker |
| `QpNotSelected` | Passed all gates but not selected by QP solver | per-ticker |
| `WfSanityGate` | Walk-forward sanity (leakage, correlation, lean) | book |
| `PanelExitRule` | Bottom-20% + mu≤0 panel-exit | per-ticker |

The `inputs` dict should contain the numerical values the gate used to decide
(thresholds, scores, ranks) — this is what makes the ledger queryable for
forensics ("why was GRMN blocked?").

### Step 3: Forward-return population

After gate verdicts are recorded, forward returns must be joined. Two paths:

**Path A (bootstrap)**: Run `outcome_backfiller.py` (PR #335) against
`runs.alpaca.db:candidate_scores` to populate decision_outcomes from historical
pipeline annotations. This is RECONSTRUCTED substrate (see provenance warning in
the module docstring).

**Path B (live, target)**: At verdict-write time, also record the candidate's
current scores. Then, after forward periods elapse (5d, 20d, 60d), a scheduled
job updates the outcome row with realized forward returns from ticker price data.

The readiness monitor's `S5_decision_ledger` check gates on ≥95% of aged
decisions (≥60d old) having `fwd_60d_ret IS NOT NULL`.

### Step 4: Canonical fixture — OXY 2026-07-01

The S5 AC names OXY 07-01 as the canonical test fixture. The pipeline PR
should include a test that:
1. Replays the OXY 07-01 decision (known: 6th-ranked candidate, admitted
   through gates, selected by QP, 1-share buy)
2. Writes verdicts to an in-memory ledger
3. Verifies all expected gates recorded with correct verdicts
4. Runs `decision_outcome_validator` on the fixture and asserts
   `overall_verdict == "INSUFFICIENT_DATA"`

**Note on (4):** a single fixture is n=1, below `decision_outcome_validator`'s
`MIN_SAMPLE_SIZE = 5` default — per-gate verdicts below that threshold are
`INSUFFICIENT_DATA` by design (not a bug to work around), so a real `PASS`
verdict is not an achievable or meaningful target for a one-decision replay.
This step is a **write-side plumbing check**: it verifies the ledger rows the
fixture produces are structurally correct and that the validator consumes them
without erroring, not that the validator's statistical assessment reaches
significance. Do not lower `min_sample` to force a `PASS` here — that would
defeat the purpose of the threshold rather than validate anything. A real
`PASS` requires ≥5 decisions per gate and belongs to the live-data readiness
path (Step 3 / `S5_decision_ledger` in the readiness monitor), not this
fixture.

## Integration checklist

- [ ] Pipeline PR: instrument `task_buy_quality_gates.py` with GateRegistry
- [ ] Pipeline PR: call `write_verdicts()` at end of each live run
- [ ] Pipeline PR: record per-ticker `inputs` dict with numerical gate values
- [ ] Pipeline PR: OXY 07-01 fixture test
- [ ] Orchestrator: outcome_backfiller bootstrap run (one-time, after #335 merges)
- [ ] Orchestrator: forward-return scheduled job (S5 Path B, post-bootstrap)
- [ ] Readiness: monitor `S5_decision_ledger` transitions to READY

## Data contract

The `decision_ledger` table schema (from `decision_ledger.py`):

```sql
CREATE TABLE IF NOT EXISTS decision_ledger (
  run_id TEXT NOT NULL,
  as_of DATE NOT NULL,
  scope TEXT NOT NULL,         -- "book" | ticker symbol
  gate TEXT NOT NULL,          -- gate name from table above
  verdict TEXT NOT NULL CHECK(verdict IN ('allow','halve','block')),
  reason TEXT NOT NULL,        -- human-readable reason string
  inputs_json TEXT NOT NULL DEFAULT '{}',  -- JSON dict of gate inputs
  PRIMARY KEY (run_id, scope, gate)
) WITHOUT ROWID;
```

The `decision_outcomes` table schema (from `ledger_attribution.py`):

```sql
CREATE TABLE IF NOT EXISTS decision_outcomes (
  as_of DATE NOT NULL,
  scope TEXT NOT NULL,
  ticker TEXT NOT NULL,
  gate TEXT NOT NULL,
  verdict TEXT NOT NULL,
  fwd_5d_ret REAL,
  fwd_20d_ret REAL,
  fwd_60d_ret REAL,
  entry_price REAL,
  exit_price REAL,
  exit_date DATE,
  exit_reason TEXT,
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (as_of, scope, ticker, gate)
) WITHOUT ROWID;
```

## Safety

- `write_verdicts` is append-only (INSERT OR IGNORE on PK)
- The DB uses WAL mode + busy timeout for concurrent-agent safety
- The pipeline should NEVER delete from or UPDATE the ledger
- **Explicit operational tradeoff — fail-open on ledger-write import/version
  skew:** if the orchestrator modules are not importable (version skew), the
  pipeline logs a warning and continues the run rather than blocking it. This
  is a deliberate choice, not a quiet default: S5 is a critical measurement
  substrate for several downstream programs (S8, M-SIG, M3, the 107
  attribution engine), and choosing fail-open means a version-skew or import
  failure silently produces a gap in ledger coverage for that run — reducing
  the ≥95% forward-outcome-join coverage the S5 AC requires — rather than
  surfacing as a pipeline failure. The tradeoff is made deliberately in favor
  of run availability over ledger completeness, on the reasoning that a
  missing day of ledger coverage is recoverable via `outcome_backfiller.py`
  (bootstrap/reconstruction path), while a blocked daily run is not
  recoverable after the fact. Any pipeline PR implementing this contract
  should log fail-open events at a level that is monitored (not silently
  swallowed), since repeated fail-opens would erode the coverage this
  substrate depends on without any other visible signal.
