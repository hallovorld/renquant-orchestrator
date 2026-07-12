# Architecture Violation Registry

Date: 2026-07-12
Scope: ALL RenQuant repos audited against the canonical subrepo operating model
(`RenQuant/doc/arch/subrepo-operating-model.md`) and pipeline architecture
(`renquant-common` Task/Job/Pipeline primitives).

Methodology: automated grep + manual inspection of every repo under
`/Users/renhao/git/github/`. Evidence cited as `repo:file:line`.

---

## Summary

| Severity | Count | Description |
|---|---|---|
| P0 | 5 | Active production paths with wrong ownership or unsafe coupling |
| P1 | 8 | Architectural debt that blocks asset-class extension or causes drift |
| P2 | 6 | Cleanup / hygiene that doesn't block production but violates the model |

---

## P0 — Active production paths, wrong ownership

### V-001: Umbrella live/runner.py is the active decisioning core (1,200 LOC)

- **Evidence**: `RenQuant:live/runner.py` (1,200 lines)
- **Violation**: The umbrella's `live/runner.py` is the ACTIVE production
  execution path — it orchestrates inference, commit, reconciliation, and
  alerting. This should be owned by `renquant-orchestrator` (scheduling/wiring)
  and `renquant-execution` (broker commit). Instead, the umbrella owns the
  entire vertical.
- **Impact**: Any orchestrator or execution change must be mirrored here or is
  deployed-but-dark. The umbrella cannot be deprecated while this file is the
  live path.
- **Owner**: renquant-orchestrator (scheduling) + renquant-execution (commit)
- **Remediation**: Migrate to `renquant-orchestrator.native_live_run` (partially
  built) as the orchestration entry point, calling `renquant-execution` for
  broker commit. The umbrella runner becomes a thin shim that imports and calls
  the orchestrator. Sequence: (1) prove feature parity via shadow comparison,
  (2) swap the launchd entry point, (3) deprecate the umbrella runner.

### V-002: daily_104.sh monolith (647 LOC) owns cross-repo orchestration

- **Evidence**: `RenQuant:scripts/daily_104.sh` (647 lines)
- **Violation**: This shell script is the production daily-full entry point. It
  hardcodes paths to every subrepo, manages PYTHONPATH construction, runs
  inference, handles retries, and sends notifications — all responsibilities
  that belong to `renquant-orchestrator`.
- **Impact**: Adding a new repo, changing a path, or extending to crypto requires
  editing a 647-line bash monolith in the deprecated umbrella.
- **Owner**: renquant-orchestrator
- **Remediation**: Replace with `renquant-orchestrator` CLI entry points (the
  `native_live_run` + `native_context_hydration` modules are partially built).
  The shell script becomes a 5-line wrapper that calls `python -m
  renquant_orchestrator.cli daily-full`.

### V-003: Pipeline imports from orchestrator (reverse dependency)

- **Evidence**: `renquant-pipeline:kernel/pipeline/task_decision_ledger.py:77`
  ```python
  from renquant_orchestrator.decision_ledger import connect, write_verdicts
  ```
- **Violation**: Pipeline (downstream producer) imports from orchestrator
  (upstream consumer). This creates a circular dependency: orchestrator depends
  on pipeline for inference, pipeline depends on orchestrator for ledger writes.
- **Impact**: Cannot test or deploy pipeline independently; orchestrator changes
  can break pipeline at import time.
- **Owner**: The decision ledger write contract should live in `renquant-common`
  or `renquant-pipeline` itself (pipeline produces decisions, it should own the
  write path). Orchestrator should be a consumer, not a provider.
- **Remediation**: Move `decision_ledger.connect` and `write_verdicts` to
  `renquant-common` or a `renquant-pipeline.persistence` module. Orchestrator
  imports from there instead of owning the definition.

### V-004: Orchestrator hardcodes 13 umbrella paths

- **Evidence**: `renquant-orchestrator:src/renquant_orchestrator/scheduled_jobs.py`
  — 13 occurrences of `/Users/renhao/git/github/RenQuant`
  ```python
  CANONICAL_REPO_ROOT = "/Users/renhao/git/github/RenQuant"  # :13
  launchd_stdout_path="/Users/renhao/git/github/RenQuant/logs/..."  # :78,79,98,99,...
  ```
- **Violation**: The orchestrator — which exists to REPLACE umbrella coupling —
  hardcodes absolute paths to the umbrella. These should resolve through R-PIN
  runtime inventory (`deployment_manifest.load_runtime_inventory`).
- **Impact**: Cannot run on any machine with a different checkout layout.
  Contradicts the R-PIN neutral-path design that already landed (#477/#483).
- **Owner**: renquant-orchestrator
- **Remediation**: Replace `CANONICAL_REPO_ROOT` and all hardcoded paths with
  `deployment_manifest.load_runtime_inventory()` lookups (the API already exists
  and is used by the stops-liveness pager).

### V-005: Orchestrator imports pipeline kernel internals

- **Evidence**: `renquant-orchestrator:src/renquant_orchestrator/native_context_hydration.py`
  ```python
  from renquant_pipeline.kernel.data import LocalStore  # :140
  from renquant_pipeline.kernel.exits import HoldingState  # :421
  from renquant_pipeline.kernel.regime import RegimeState  # :422
  from renquant_pipeline.kernel.pipeline.job_universe import ...  # :563
  ```
  Also: `train_gbdt.py:271` imports `renquant_pipeline.kernel.persistence`.
- **Violation**: `kernel` is pipeline's internal implementation. Orchestrator
  should import from `renquant_pipeline`'s public API (top-level exports), not
  reach into kernel internals. Any kernel refactor breaks the orchestrator.
- **Impact**: Tight coupling; kernel refactors require orchestrator changes.
- **Owner**: renquant-pipeline (expose public API) + renquant-orchestrator
  (consume public API only)
- **Remediation**: Pipeline exposes the needed types (`LocalStore`,
  `HoldingState`, `RegimeState`, etc.) in its public `__init__.py` or a
  `renquant_pipeline.types` module. Orchestrator imports only from the public
  surface. Add a CI lint that rejects `from renquant_pipeline.kernel` in
  orchestrator.

---

## P1 — Blocks asset-class extension or causes drift

### V-006: ALLOWED_BROKERS duplicated in pipeline (2 copies)

- **Evidence**:
  - `renquant-pipeline:src/renquant_pipeline/state_paths.py:29`
  - `renquant-pipeline:src/renquant_pipeline/kernel/state_paths.py:29`
  Both define `ALLOWED_BROKERS: frozenset[str] = frozenset({...})`.
- **Violation**: Two independent copies of the same allowlist. Adding a broker
  tag (e.g. `alpaca_crypto` for GOAL-2) requires editing both or one drifts.
  A parity pin test exists but the duplication is the root cause.
- **Owner**: renquant-common (broker tags are a cross-repo concept)
- **Remediation**: Define `ALLOWED_BROKERS` once in `renquant-common`. Pipeline
  imports from common. Execution already references it in docs only.

### V-007: NYSE calendar hardcoded in pipeline exits

- **Evidence**: `renquant-pipeline:kernel/exits.py:54-72`
  ```python
  def _is_nyse_trading_day(d: datetime.date) -> bool:
      nyse = mcal.get_calendar("XNYS")
  ```
  Also: `kernel/typed_past/typed_data_freshness.py:32-83` (hard-fail vs last
  NYSE session).
- **Violation**: Hold/streak clocks and data freshness are NYSE-only. Crypto
  positions don't age over weekends, freshness rejects weekend bars as stale.
  The `asset_class.py` module exists with an `is_trading_day` function (`:82-89`)
  but `exits.py` and freshness still use the hardcoded NYSE path.
- **Impact**: Crypto RFC §2.2 P1/P2 — blocks 24/7 asset-class operation.
- **Owner**: renquant-pipeline (already has `kernel/asset_class.py`)
- **Remediation**: Wire `exits.py` and freshness checks through
  `asset_class.is_trading_day(d, asset_class)` instead of `_is_nyse_trading_day`.
  The abstraction already exists; it just isn't called from all sites.

### V-008: WF gate has no transaction-cost model

- **Evidence**: `renquant-pipeline:kernel/preflight.py` and
  `kernel/preflight_pipeline/tasks/gate.py` — the WF gate checks IC, regime IC,
  monotonicity, sanity, and placebo. No check involves transaction costs.
  `rotation.py:129` has `transaction_cost_pct` but it's a decision-time rotation
  cost, not a gate validation cost.
- **Violation**: The WF gate promotes models based on gross IC/return without
  deducting realistic transaction costs. The D6 Governor replay (PR #466)
  showed frictions eat 86-100% of gross — the gate can't catch this because
  it doesn't model costs.
- **Impact**: Models that look good gross but are negative net-of-cost can pass
  the gate. The crypto RFC (§4.4) requires a net-of-fees BTC baseline, making
  this worse for crypto (25 bps taker fees).
- **Owner**: renquant-pipeline (gate definition) + renquant-common (cost model)
- **Remediation**: Add a cost-aware return metric to the WF gate: net-of-cost
  walk-forward return using configurable fee/slippage parameters. Start with
  a simple `gross_return - 2 * (fee_pct + slippage_pct) * turnover` deduction
  per period.

### V-009: Execution TIF hardcoded to DAY for equities

- **Evidence**: `renquant-execution:alpaca_broker.py:304-306`
  ```python
  if time_in_force is not None and str(time_in_force).strip().lower() != "day":
      raise ValueError(f"equity place_order is TIF=DAY only, got {time_in_force!r}")
  ```
  Also `alpaca_broker_port.py:129`: `"time_in_force": TimeInForce.DAY`
- **Violation**: The equity path hard-rejects any non-DAY TIF. This is correct
  for equities but means the equity and crypto code paths share no TIF
  abstraction — adding a new TIF rule requires touching broker internals.
- **Impact**: Crypto RFC §2.1 E1/E2 identified this. Crypto uses GTC/IOC.
  Partially addressed: `alpaca_broker.py:398` has a `_crypto_tif_enum` helper.
  But the equity path still hard-rejects, so any future equity GTC need
  (e.g. protective stops) requires rework.
- **Owner**: renquant-execution
- **Remediation**: Already partially done for crypto. The equity GTC stop path
  (`place_stop_order` at `:382`) does use GTC. Remaining: unify TIF resolution
  into an asset-class-aware method.

### V-010: Wash-sale engine is equity-only

- **Evidence**: `renquant-pipeline:kernel/pipeline/task_candidates.py:24-58`
  — wash-sale gate with no asset-class check.
  `kernel/config_schema.py:55` — no `asset_class` field in wash-sale config.
- **Violation**: IRC §1091 wash-sale rules apply to securities, not property.
  Crypto is property — wash-sale must be bypassed per asset class. The gate
  currently applies to everything uniformly.
- **Impact**: Crypto RFC §2.2 P5 — would incorrectly block crypto re-entry
  after a loss.
- **Owner**: renquant-pipeline
- **Remediation**: `task_candidates.py` checks `ctx.asset_class` and bypasses
  wash-sale for `"crypto"`. The `asset_class.py` module already exists.

### V-011: Vol clips pin at equity levels

- **Evidence**: `renquant-pipeline:kernel/panel_pipeline/job_panel_scoring.py:3556-3582`
  — σ clip `[0.05, 1.50]` annualized.
  `kernel/vol_target.py:24-47` — target 0.15, SPY-proxied.
- **Violation**: Crypto realized vol is 60-150%+ annualized. The 1.50 ceiling
  clips most crypto names to the same value, so Kelly can't discriminate vol
  across crypto pairs. SPY proxy is meaningless for crypto.
- **Impact**: Crypto RFC §2.2 P7 — sizing is broken for crypto without
  asset-class-aware vol parameters.
- **Owner**: renquant-pipeline + renquant-strategy-crypto (config)
- **Remediation**: Make vol clip bounds configurable per asset class in strategy
  config. The `vol_target` already accepts `annualization_days` parameter.

### V-012: Fundamentals hard-block has no asset-class bypass

- **Evidence**: `renquant-pipeline:kernel/preflight_pipeline/tasks/fundamentals_freshness.py`
  — `P-FUND-FRESHNESS` gate, enabled by default.
  `kernel/panel_pipeline/job_panel_scoring.py:229-250` — panel fails closed
  without fundamentals.
- **Violation**: No 10-Q/fiscal calendar exists for crypto. Every crypto buy
  would be hard-blocked by fundamentals freshness.
- **Impact**: Crypto RFC §2.2 P8 — "every buy hard-blocked; scorer fail-closes."
- **Owner**: renquant-pipeline
- **Remediation**: Fundamentals freshness gate checks `ctx.asset_class` and
  skips for `"crypto"` (crypto model uses price/volume features only, no
  fundamentals). Panel scorer must not fail-close on missing fundamentals when
  the model doesn't use them.

### V-013: Execution reconciliation filters US_EQUITY only

- **Evidence**: `renquant-execution:alpaca_broker.py:145` (`get_filled_orders`),
  `:161` (`get_open_orders`) — filter `asset_class=US_EQUITY`.
- **Violation**: Crypto fills and open orders are silently invisible to
  reconcile-before-emit.
- **Impact**: Crypto RFC §2.1 E3 — a correctness hazard; crypto order state
  would be invisible to the reconciler.
- **Owner**: renquant-execution
- **Remediation**: Pass `asset_class` parameter (or remove the filter and
  let the caller filter). The broker tag isolation (`alpaca_crypto` vs
  `alpaca`) handles separation.

---

## P2 — Hygiene / model violations

### V-014: 274 Python scripts in umbrella

- **Evidence**: `RenQuant/scripts/*.py` — 274 files, including 30 training/fit
  scripts that belong in `renquant-model`.
- **Violation**: The umbrella is supposed to be a thin integration harness.
  274 scripts is a shadow monorepo.
- **Owner**: Various — training scripts → renquant-model; data scripts →
  renquant-base-data; evaluation scripts → renquant-backtesting; ops scripts →
  renquant-orchestrator.
- **Remediation**: Triage scripts into 4 buckets (active-production,
  research-archival, migrated-duplicate, dead-code). Migrate active scripts
  to owning repos. Archive the rest. Do NOT delete — the umbrella is "never
  deleted or emptied" per the operating model.

### V-015: Stale strategy_config.json copies in umbrella

- **Evidence**: 10+ `strategy_config*.json` files under
  `RenQuant/backtesting/renquant_104/` and `RenQuant/scripts/`.
- **Violation**: These are snapshot copies that drift from the pinned
  `renquant-strategy-104` config. The `merged-is-not-deployed` lesson
  specifically flags this.
- **Owner**: renquant-strategy-104 (canonical) / renquant-backtesting (sim)
- **Remediation**: Backtesting configs should reference the pinned strategy
  config via manifest, not carry copies. For sim variant configs, move to
  `renquant-backtesting` with explicit `_sim_` naming.

### V-016: base-data has verbatim-copied pipeline feature code

- **Evidence**: `renquant-base-data:src/renquant_base_data/alpha158_ops.py:204,306`
  ```python
  # Moved verbatim from alpha158_qlib_panel.py (the builder the prod model's...
  # Moved verbatim from renquant_pipeline .../alpha158_features.py (the live...
  ```
- **Violation**: Feature computation code was copied from pipeline to base-data
  instead of sharing through `renquant-common`.
- **Impact**: Two implementations of the same feature logic can drift.
- **Owner**: renquant-common (shared feature computation)
- **Remediation**: Extract the shared feature computation into
  `renquant-common` and import from both base-data and pipeline.

### V-017: Execution software_stops_liveness imports pipeline private API

- **Evidence**: `renquant-execution:software_stops_liveness.py:148`
  ```python
  from renquant_pipeline.software_stops import (  # noqa: PLC0415
  ```
- **Violation**: Execution imports from pipeline's internal API. Codex already
  flagged this on orchestrator PR #481 — the same pattern exists here.
- **Impact**: Pipeline refactoring `software_stops` breaks execution at import
  time.
- **Owner**: renquant-pipeline (expose public validation API)
- **Remediation**: Pipeline exposes a public `validate_snapshot` function.
  Execution imports the public name. (This is part of the #481 dependency chain
  — pipeline public API → execution#30 → orchestrator installer.)

### V-018: No CI lint for cross-repo import boundaries

- **Evidence**: No repo has a test or CI check that enforces import boundaries
  (e.g. "orchestrator must not import from `renquant_pipeline.kernel`").
- **Violation**: The operating model says "Every repo defines inputs, outputs,
  owner boundaries, and forbidden imports" but no mechanical enforcement exists.
- **Impact**: Boundary violations accumulate silently (V-003, V-005, V-017).
- **Owner**: All repos
- **Remediation**: Add a per-repo `test_import_boundaries.py` that greps the
  source tree for forbidden import patterns and fails CI. Start with the
  highest-value boundaries: orchestrator must not import `kernel.*`, pipeline
  must not import `renquant_orchestrator`, execution must not import pipeline
  private names.

### V-019: Annualization factor 252 hardcoded (partially addressed)

- **Evidence**: `renquant-pipeline:kernel/vol_target.py:48` — default 252.
  `kernel/portfolio_qp/tasks.py:477` — `TRADING_DAYS_PER_YEAR = 252.0`
- **Violation**: Equity annualization factor hardcoded. However, both sites
  already have comments saying "crypto resolves 365 via asset_class" and
  `vol_target` accepts `annualization_days` parameter.
- **Impact**: Low — the abstraction seam exists, it's just the DEFAULT that's
  equity-centric. Crypto config will pass 365.
- **Owner**: renquant-pipeline (already partially done)
- **Remediation**: Wire `asset_class.annualization_days_for(asset_class)` into
  the default parameter resolution so callers don't need to pass it explicitly.

---

## Resolved violations (previously known, now fixed)

| ID | Violation | Resolution |
|---|---|---|
| R-001 | Triple-implementation fingerprint | Unified into `renquant-common.model_fingerprint` (PR #M6) |
| R-002 | asset_class concept missing | `renquant-pipeline:kernel/asset_class.py` exists + `renquant-common:market_calendar.py` + `renquant-execution:crypto.py` — abstraction landed, not yet wired everywhere |
| R-003 | Umbrella dependency in stops-liveness pager | Fixed in orchestrator #481 — neutral runtime-state root, R-PIN resolution |

---

## Migration sequencing (recommended priority)

### Phase 1 — Unblock crypto (G2) and close circular deps
1. **V-003** (pipeline→orchestrator import): move decision ledger write to common
2. **V-006** (ALLOWED_BROKERS): unify in common, add `alpaca_crypto`
3. **V-010** (wash-sale): asset-class bypass
4. **V-012** (fundamentals hard-block): asset-class bypass
5. **V-013** (reconciliation filter): asset-class parameter

### Phase 2 — Strengthen boundaries
6. **V-018** (import boundary CI): add lints
7. **V-005** (orchestrator→pipeline kernel): expose public API
8. **V-017** (execution→pipeline private): public validation API
9. **V-004** (hardcoded paths): migrate to R-PIN

### Phase 3 — Migrate production path
10. **V-001** (live/runner.py): prove parity, swap entry point
11. **V-002** (daily_104.sh): replace with orchestrator CLI
12. **V-014** (274 scripts): triage and migrate

### Phase 4 — Cleanup
13. **V-015** (stale configs): manifest references
14. **V-016** (copied features): extract to common
15. **V-007, V-008, V-009, V-011, V-019**: wire existing abstractions
