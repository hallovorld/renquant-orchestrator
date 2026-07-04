# Sprint checklist status audit — 2026-07-04T14:00

DATE: 2026-07-04

## Sprint checklist (operator 2026-07-03~07-06)

### 1. Experiment framework (expkit) — ✅ COMPLETE

Modules: `expkit/{prereg,evaluation,stats,evidence,__init__}.py` (1303 lines)
Tests: 52 passing (test_expkit_{stats,prereg,evaluation,evidence}.py)

All 6 required capabilities present:
- prereg freeze: `write_frozen_spec`, `check_spec_frozen_before_results`
- placebo diff: `shifted_label_placebo`, `paired_deltas`
- block bootstrap + small n exact: `block_bootstrap_diff`, `exact_sign_test`, `bootstrap_or_exact`
- dual control: `multi_seed_unanimity` + placebo diff
- evidence manifest: `build_manifest`, `write_evidence`, `verify_manifest`
- breadth replay: `solve_matched_admission` (M4-b matched-breadth protocol)

### 2. 105 intraday session — ✅ COMPLETE

9 modules, 8670 lines, 33+ tests:
- entry_timing_policy.py (1083L): 7 policies, tick-driven state machine
- entry_timing_shadow.py (1103L): Stage-1 observe-only evaluator
- intraday_live_executor.py (1941L): Stage-2 arming gate, canary envelope, order state book
- intraday_session_scheduler.py (1077L): market-hours scheduler
- intraday_session_inputs.py (501L): input assembly
- shadow_realtime_serving.py (667L): shadow real-time model serving
- intraday_pairing_logger.py (1138L): paired execution-observation logger
- intraday_quote_logger.py (828L): tick feed logger
- intraday_replay_audit.py (332L): replay/audit harness

Only deferred: `LiveSessionRunner` (the session-driving loop) — explicitly scoped out
pending §9.4 economic-authorization decision (per codex review).
Software stops: task_software_stops.py ✅ (task #5 this sprint)

### 3. 106 C1/PIT feature pipeline — ✅ COMPLETE

- C1 inventory: PR #303 (mirror_drift_inventory.py + CI freeze-line, 16 tests)
- PIT feature pipeline: ops/pit/ (3 launchd plists, wrapper scripts, liveness checker,
  concurrency-safe runner, 29 tests in test_pit_snapshotter_scheduling.py)
- Feature drift audit: feature_drift_audit.py (IC-based pruner)
- Status: built and flag-off (plists need `launchctl load` to activate)

### 4. 107 governance skeleton — ✅ COMPLETE

- Decision ledger: decision_ledger.py (96L) — append-only gate-verdict store
- Attribution engine: attribution/{decompose,ledger,report}.py (700+ lines)
  - 5-leg P&L decomposition (MARKET+SIGNAL+SIZING+TIMING+COST)
  - Sum-check identity enforcement
  - Coverage/censoring report
- Risk budget: risk_budget/{budget,report,attribution_bridge}.py
  - 4-budget statement (DD/β/concentration/sleeve)
  - Breach semantics (OK/WARN/CRITICAL)
- Transfer coefficient: transfer_coefficient.py + CLI (PR #305/#308/#310)
  - Per-run TC measurement + QP-status diagnostic
  - Root cause identified: 68% QP-infeasible (PR #308)
  - Design doc for fix (PR #309)

### 5. S-FRAC stages 1-3 — ⏳ MULTI-REPO (partially blocked)

Design merged (#254). Stage 0 in umbrella. Stages 1-3 need pipeline+execution
+strategy changes. Not orchestrator-only.

### 6. M6 fingerprint unification — ⏳ IN FLIGHT (B4+B7 agent)

B4+B7 agent running: score-sha + manifest writer unification.
scorer_identity_monitor.py (991L) is the orchestrator surface.

### 7. M4-b harness — ✅ COMPLETE (with gap)

Script: scripts/m4b_floor_replay.py (1537L) + tests (672L)
Full protocol: calibrator replay, matched-admission solve, block bootstrap,
5-criterion evaluation, placebo/noise controls, gate checks, evidence stamping.

Gap: standalone script, not yet factored into expkit as reusable library code.
Some functions duplicate expkit.stats. Sprint item = promote to expkit.

## Summary

| Item | Status | Lines | Tests |
|------|--------|-------|-------|
| Expkit | ✅ | 1303 | 52 |
| 105 | ✅ | 8670 | 33+ |
| 106 C1/PIT | ✅ | - | 45 |
| 107 skeleton | ✅ | 700+ | 57+ |
| S-FRAC 1-3 | ⏳ | multi-repo | - |
| M6 | ⏳ | in-flight | - |
| M4-b | ✅ (gap) | 2209 | - |

**Orchestrator-side sprint code: 5/7 items COMPLETE, 2 in-flight/multi-repo.**
