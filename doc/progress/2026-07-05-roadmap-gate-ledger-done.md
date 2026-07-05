# Roadmap: mark s2-wire-gate-ledger done

Date: 2026-07-05
Task: s2-wire-gate-ledger (roadmap-backlog.json)

## What shipped

- Verified umbrella runner.py:2141 calls `record_gate_verdicts()` on every
  live run (best-effort, never blocks the bar)
- Umbrella sim.py:1362 also calls `record_gate_verdicts()` for sim runs
- `kernel/persistence.py` defines the `gate_verdicts` table + `record_gate_verdicts()`
  function (mirrored from pipeline per the task spec)
- `kernel/pipeline/task_gates.py` submits verdicts to `GateRegistry` for
  flatten_cooldown, drawdown_circuit, transition_window, bull_vol_offensive,
  regime_alpha gates
- Orchestrator-side `decision_ledger.py` and `gate_registry.py` modules
  already merged (#133)
- Pipeline-side decision-ledger formatter merged (#176)
- Blocker `s2-god-file-decomp-next` already done — cleared `blocked_by`

## Evidence

The task spec said "Mirror the verdict algebra into the umbrella kernel if a
cross-import is not allowed" — this mirroring IS what was built. The umbrella
kernel has its own `record_gate_verdicts()` that persists to the runs DB
`gate_verdicts` table, matching the orchestrator's `decision_ledger` concept.
