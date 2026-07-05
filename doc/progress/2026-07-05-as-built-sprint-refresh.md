# As-built documentation refresh (post-sprint)

DATE: 2026-07-05

## What changed

Updated 104 and 107 as-built docs to reflect all sprint deliveries:

### 107 as-built (major update)
- Added Decision Ledger section (S5 substrate: 5 modules)
- Added Readiness Monitor section (12 checks with detailed table)
- Added Gate Diagnostics section (calibration, sign-laundering, software stops)
- Updated Open Items: removed stale "#133 blocked" (now delivered), added
  "pipeline wiring pending" as the current state
- Updated status: all modules DELIVERED

### 104 as-built (minor update)
- Added readiness_monitor, sign_laundering_harness, check_model_bundle_consistency
  to orchestrator module table

## Round 2 (Codex review — factual drift in test counts)

Codex found several per-module test counts in the 107 doc didn't match the
checked-in suite (citing `gate_registry.py`, `decision_outcome_validator.py`,
`outcome_backfiller.py` as examples, and noting the gate-diagnostics/freshness
sections had the same problem). Re-verified every numeric test-count claim in
the diff by counting `^\s*def test_` occurrences in each module's test file
(`grep -cE "^\s*def test_" tests/test_<module>.py`), cross-checked against
class-based test files by listing test methods directly to confirm no
miscounting from indentation/parametrize style. Corrected:

| Module | Claimed | Real (verified) |
|---|---|---|
| `gate_registry.py` | 16 | 8 |
| `decision_outcome_validator.py` | 11 | 18 |
| `outcome_backfiller.py` | 12 | 19 |
| `readiness_monitor.py` | 50+ | 61 |
| `gate_calibration_diagnostic.py` | 14 | 20 |
| `sign_laundering_harness.py` | 10 | 29 |
| `software_stop.py` | 10 | 21 |
| `config_experiment_store.py` | 8 | 11 |
| `model_freshness_monitor.py` | 30+ | 57 |
| Risk budget ledger (`test_risk_budget.py`) | 34 | 28 |

Confirmed matching (no change needed): `decision_ledger.py` (6),
`scorer_identity_monitor.py` (35), Attribution engine (`test_attribution_engine.py`, 23).
