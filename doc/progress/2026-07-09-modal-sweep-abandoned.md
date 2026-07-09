# Modal cloud sweep — abandoned

**Date**: 2026-07-09
**Decision**: operator directive to abandon Modal cloud sweep execution
**Code preserved**: branches `feat/modal-per-seed-fanout-v2` (code) +
`doc/modal-sweep-retrospective` (retrospective)

## What was built

The Modal cloud backtest infrastructure for running the 75-variant
concentration cap sweep remotely:

- `src/renquant_orchestrator/cloud/` — full cloud execution stack:
  - `executor.py` — BacktestExecutor protocol + data types
  - `modal_executor.py` — Modal backend with preflight cost gate
  - `modal_app.py` — remote worker (container-side backtest runner)
  - `bundle.py` — multi-repo source bundler (8 subrepos)
  - `sync_data.py` — data staging + Volume sync
  - `data_contract.py` — deterministic preflight verification (237 checks)
- `scripts/run_sweep_modal.py` — sweep orchestration with resume logic
- `tests/test_cloud_modal.py` — 40+ unit tests

## What worked

- Data contract (enumerate → verify → sync → verify remote → execute) — PASS
- Code bundling (8 subrepos + strategy kernel into one container) — PASS
- Round-7 smoke test: 2 variants × 3 seeds completed on Modal ($0.30)
- Per-seed fan-out architecture (1 pod per seed for max parallelism) — PASS

## What failed (10 rounds)

| Round | Failure | Root cause |
|-------|---------|------------|
| 1-3 | Missing files on container | No enumeration — used execute as debugger |
| 4-6 | Wrong paths / broken symlinks | Multi-repo path resolution (3 independent impls) |
| 7 | PASS | Built data_contract.py; should have been round 1 |
| 8 | 225 pods hung | `order_outputs=True` default + no container limit |
| 9 | Timeout killed all pods | 1h timeout < I/O contention at 30 concurrent readers |
| 10 | 13h unacceptable | `max_containers=10` too low |
| 11 | ImportError | PYTHONPATH not set before executing |

Total Modal spend: ~$3.50. Total agent time: ~12 hours across 2 days.

## Why abandoned

The Modal infrastructure works in isolation (round-7 smoke test proved
end-to-end) but integrating it into a reliable full-sweep execution has
proven unreliable. Each fix introduces a new failure mode because the
agent lacks the ability to enumerate all constraints before executing.
The operator decided to cut losses.

## What to preserve

1. **Code**: `feat/modal-per-seed-fanout-v2` branch — complete, tested,
   PR #438 open. The `order_outputs=False` + `return_exceptions=True` +
   timeout/concurrency fixes are correct and tested.
2. **Retrospective**: `doc/modal-sweep-retrospective` branch — PR #437
   open, documents all 10 rounds.
3. **Data contract pattern**: `data_contract.py` is genuinely reusable
   for any future remote execution surface.
4. **Multi-repo bundling**: the bundler handles 8 subrepos correctly
   and is tested.

## What to do instead for cash drag

The concentration cap sweep can still run LOCALLY (serial, ~50h). The
Modal parallelization was an optimization, not a prerequisite. The
design RFC (#421) and the sweep research design (#403) are both merged
and valid regardless of where the sweep executes.

Alternatively, the sweep grid could be reduced (fewer variants, shorter
OOS window) to make local execution practical within ~6-8 hours.

## Lessons (beyond the retrospective)

The retrospective (PR #437) already documents the pipeline-thinking and
multi-repo architecture lessons. The meta-lesson from abandonment:

**Know when to stop.** 10 rounds of the same pattern (fix one thing,
discover another) with diminishing returns is a signal that the approach
has too many moving parts for the agent's current capability. The correct
response is to simplify (run locally) or reduce scope, not to keep
iterating on the complex path.
