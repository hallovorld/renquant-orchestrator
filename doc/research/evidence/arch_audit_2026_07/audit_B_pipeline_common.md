# GOAL-3 Architecture Audit — Cluster B: renquant-pipeline + renquant-common

Date: 2026-07-10. READ-ONLY audit. All file:line refs checked against working trees at
`/Users/renhao/git/github/renquant-pipeline` and `/Users/renhao/git/github/renquant-common`.
Contracts read: `RenQuant/doc/arch/subrepo-operating-model.md`, both repos' CLAUDE.md/README,
pipeline `docs/source-map.md`, `kernel/__init__.py` lift manifest.

Verdict in one line: **the fingerprint unification worked (1 impl survives); the dominant
architectural debt is now the unfinished copy-not-move kernel lift (two divergent full kernel
copies, live runner on the umbrella one) plus a training pipeline and ~4.5k lines of replay
harness living inside the runtime repo.**

---

## B-1. Two divergent full kernel copies across the repo boundary — [VERIFIED] — SEVERITY: HIGHEST

- Pipeline kernel is a "copy-not-move" lift of `RenQuant/backtesting/renquant_104/kernel/`
  (`renquant_pipeline/kernel/__init__.py:3-6` says so explicitly; `docs/source-map.md` lists the port plan).
- The umbrella copy still exists in full AND the live path uses it:
  `RenQuant/live/runner.py:210,239,328,348,419,460` import `from kernel.X ...` (umbrella copy),
  not `renquant_pipeline.kernel`. Umbrella runtime imports only
  `renquant_pipeline.software_stops` (1 hit).
- Measured drift (umbrella vs pipeline): `rotation.py` 0 diff-lines; `exits.py` 138 (873→938);
  `sizing.py` 342 (187→468); `preflight.py` 308 (1865→2058). The subrepo copy is AHEAD —
  features merged in renquant-pipeline are not in the code the live runner executes.
- Contract broken: operating-model §Open-Migration item 3 ("Runtime 104 tasks into
  renquant-pipeline") left half-done; "merged is not deployed" incident family.
- Target owner: renquant-pipeline is canonical; umbrella kernel modules should become
  re-export shims (the proven `kernel/net_safety.py` pattern) or be deleted at cutover.
- Migration: **L** (per-module cutover with parity tests; the repo already has 15+
  `test_lift_*`/`test_c2*` parity tests to lean on). Risk: HIGH while open — silent behavior
  fork between live and pinned code; this is the exact class behind prior no-trade incidents.

## B-2. Duplicated module layer INSIDE renquant-pipeline (top-level vs kernel/) — [VERIFIED]

Three names exist at both `src/renquant_pipeline/X.py` and `src/renquant_pipeline/kernel/X.py`:

1. `state_paths.py` — **byte-identical copies** (cmp clean), incl. `ALLOWED_BROKERS` at
   `src/renquant_pipeline/state_paths.py:29` and `kernel/state_paths.py:29`. Why two: top-level
   came from Phase-1 "runtime contract helpers" (commit 74ad8aa); kernel copy arrived via
   functional-lift slice 12 (f162a41). Instead of deleting one, a parity test pins them equal
   (`tests/test_shadow_arm_broker_tags.py:37`). Consumers split: top-level used by
   `software_stops.py:111`, `live_state_contract.py:16`, package `__init__`; kernel copy used by
   `kernel/preflight.py:1236`, `kernel/pipeline/job_universe.py:402,552`,
   `kernel/preflight_pipeline/tasks/{state.py:31,broker_fill_freshness.py:32}`.
   Fix: make `kernel/state_paths.py` a pure re-export shim of the top-level module
   (net_safety pattern). Size **S**, risk LOW. Note: `ALLOWED_BROKERS` is a broker-tag
   enumeration shared conceptually with execution/orchestrator — candidate for a
   renquant-common contract constant later (S).
2. `decision_trace.py` — **two different implementations of overlapping audit surface**
   (272 vs 401 lines; top-level = "trace contract, plain dicts", kernel = "shared helpers for
   sim/live/LEAN" centralizing `candidate_scores`/`ticker_daily_state`). Reconcile into one
   module + shim. Size **M**, risk MEDIUM (audit-surface drift = forensics ambiguity).
3. `selection.py` — different purposes under one name (top-level 93-line SelectionJob
   contract "must not promote"; kernel 497-line homegrown scoring/tier loop, docstring boasts
   "No common/ imports"). Name collision invites wrong-import bugs. Rename kernel module
   (e.g. `selection_loop.py`) or fold. Size **S/M**.

Also: `kernel/__init__.py:24` claims `config_consistency` was lifted into kernel — no such file
exists; consumers correctly use `renquant_common.config_consistency` (`kernel/preflight.py:812`,
`kernel/panel_pipeline/job_panel_scoring.py:895`). Stale manifest docstring (doc fix, S).

## B-3. Fingerprint implementations — CONSOLIDATED, one sibling remains — [VERIFIED]

- Surviving `model_content_sha256` implementations: **exactly one** —
  `renquant_common/model_fingerprint.py:471` (+ intentional in-module legacy shims
  `:684,:700` for pre-v2 artifacts). No other `def model_content_sha256` in pipeline, model,
  or umbrella src (grep-verified).
- Pipeline consumes via `kernel/panel_pipeline/fingerprint_dispatch.py:72-73,342,350` and the
  `panel_scorer.py:58-59` re-export; `pyproject.toml` pins `renquant-common>=0.8.1` with a
  structural comment naming the 05-27/06-22/07-01 incident. Identity pinned by
  `tests/test_model_content_sha256_shared.py`. The triple-impl bug family is closed here.
- **Remaining duplicate of the same class**: `compute_parent_intent_id` exists byte-lockstep in
  `renquant_pipeline/intraday_decisioning.py:103` AND
  `renquant_execution/order_state_machine.py:177`, pinned only by golden vectors; the docstring
  itself (intraday_decisioning.py:34-40) says the renquant-common lift is the follow-up.
  Target owner: renquant-common. Size **S**. Risk: same silent-drift class as the fingerprint bug.

## B-4. Tax/cost conventions — THREE divergent families in one repo — [VERIFIED]

- Canonical `tax_drag()` lives at `kernel/rotation.py:51`; its default rate pair
  `short_term_rate=0.50 / long_term_rate=0.32` is **hand-repeated at 8+ call sites**:
  `kernel/rotation.py:134,299,478`, `kernel/pipeline/governor_sizing.py:410`,
  `kernel/pipeline/task_joint_actions.py:140`, `kernel/pipeline/soft_exit_guards.py:218`,
  `kernel/pipeline/task_rotation.py:135`, `kernel/trade_events.py:330`, plus frozen replay
  constants `kernel/portfolio_qp/allocator_replay.py:70-71`.
- The QP leg uses a DIFFERENT default AND model: `qp_tax_rate_st=0.30 / qp_tax_rate_lt=0.15`
  (`kernel/portfolio_qp/tasks.py:590`) with Brown-Smith bridge interpolation
  (`tasks.py:3628`, `_per_asset_tax`) vs rotation's ST/LT cliff.
- Third family: flat `tax_rate=0.30` in `kernel/selection.py:66,105` and
  `wash_sale_tax_rate` 0.30 in `kernel/pipeline/task_candidates.py:48`.
- Consequence: the same sell can be costed at 0.50 ST by rotation and 0.30 ST by QP within one
  run. Contract broken: strategy repo is policy-only + single-source-of-truth.
- Fix: one tax-model function (rotation.tax_drag or a common module) + ONE default table
  sourced from strategy-104 config; call sites read `tax_cfg` with fail-closed missing-key
  behavior. Size **M**. Risk: MEDIUM (economics inconsistency, not a crash).

## B-5. Strategy policy embedded as code defaults — pattern-level leak

The idiom `cfg.get(key, HARDCODED_POLICY)` is pervasive; the fallback default IS policy and can
silently diverge from `strategy_config.golden.json` on a typo'd key (violates pipeline
CLAUDE.md "do not silently fallback"). Representative:
- `kernel/kelly.py:63-64` `max_concentration=0.35`, `fractional=0.25`
- `kernel/market_gates.py:15-16` `lookback_days=3`, `halt_pct=0.03`
- QP band knobs `(0.02, 0.05, 1.0)` documented as "hand-tuned" in
  `kernel/portfolio_qp/davis_norman.py:4-9`
- all B-4 tax defaults
Fix direction: schema-required policy keys (fail-closed) via `kernel/config_schema.py` for
gates/sizing/tax; keep code defaults only for non-economic tuning (timeouts, log cadence).
Size **M** (mechanical but wide). Risk if untouched: MEDIUM — key-rename drift class.

## B-6. Broker/vendor leakage + committed market data — [VERIFIED]

- `kernel/data.py:534-537` lazily imports the **alpaca SDK** (intraday fetch, IEX feed at
  `:578`) and wraps yfinance for OHLCV (`fetch_ohlcv:270`, `_yf_translate:70`). The lift
  manifest `kernel/__init__.py:69-71` explicitly states data.py "is NOT lifted here — belongs
  in renquant-base-data" — **but the file exists and is consumed** by
  `kernel/pipeline/pp_training.py:376` / `pp_training_full.py:143`. The boundary test knows:
  `tests/test_import_boundaries.py` `_PHASE1_EXCLUSIONS` whitelists exactly
  `kernel/data.py`, `kernel/panel_pipeline/{panel_scorer,patchtst_scorer,hf_patchtst_scorer}.py`
  as "Phase 5+" debt. Target owner: renquant-base-data (fetch), renquant-model (scorer libs).
  Size **M**. Risk MEDIUM (vendor fallback logic in the decision repo; contradicts operating
  model "API-specific fallback belongs in data materialization").
- Committed OHLCV parquet store `data/ohlcv/<TICKER>/1d.parquet` (~2.5MB, dozens of tickers)
  inside the code repo, refreshed by commit c083244 ("refresh default OHLCV store") — violates
  operating-model Universal Rule 4 (data by manifest/fingerprint, not git). Move to a
  manifest-referenced fixture or renquant-base-data. Size **S/M**. Risk: stale prices silently
  used as the "default store".
- Otherwise broker isolation is good: no eager broker imports anywhere;
  `kernel/broker_reconciliation.py` is a **pure** state machine (no I/O — correct pattern).
- Gray zone: `kernel/execution/backend_lean.py` — a LEAN `QCAlgorithm` order proxy inside
  pipeline; operating model puts LEAN assembly in backtesting. It is thin, no LEAN import at
  module load. Acceptable as an ExecutionBackend port surface; flag for the C-cluster
  (backtesting) audit rather than moving now. Size (if moved) **M**.

## B-7. Model-training pipeline inside renquant-pipeline — [VERIFIED] — SEVERITY: HIGH

- `kernel/pipeline/pp_training.py` (873 lines) + `pp_training_full.py` (436) implement full
  retrain flows (DataFetch→RegimeFit→per-ticker tournament→model EXPORT→calibration fit).
  They lazily import a bare `training.*` package (`pp_training.py:407,434,618,636,728,747,775,806`)
  and `scripts.recalibrate_scores` (`pp_training_full.py:340`) — **neither exists in this repo
  or any subrepo**; `training/` lives only in the umbrella at
  `RenQuant/backtesting/renquant_104/training/`. These modules import-succeed only under
  umbrella PYTHONPATH — the "aliased dark" hazard class.
- Contracts broken: pipeline CLAUDE.md "Do not train models... from this repo";
  `docs/source-map.md:16-17` "Do not port model training loops"; operating model (training =
  renquant-model factory).
- In-repo consumers: only the lift test `tests/test_c212_pipeline_drivers_lift.py:51-52`.
- Target owner: renquant-model (or delete from pipeline and leave the umbrella driver until
  the factory owns retrain). Size **M**. Risk: HIGH ambiguity in retrain flows (this is the
  per-ticker-tournament-staleness incident surface).

## B-8. Task/Job/Pipeline discipline — mostly GOOD, two parallel systems noted

- **Good**: `kernel/pipeline/pipeline.py:1-53` re-exports canonical
  `Task/Job/run_parallel/ParallelTimeoutError/resolve_workers` from `renquant_common` and adds
  only `TickerJob` + a config-defaults `run_parallel` wrapper — it explicitly collapsed the
  bootstrap's duplicate executor. Top-level jobs (`inference.py`, `selection.py`,
  `intraday_decisioning.py`, `panel_scoring.py`) all build on `renquant_common` Task/Job.
- `preflight_pipeline/base.py:18` subclasses common `Task`, but `PreflightJob:76` /
  `PreflightPipeline:91` are homegrown mini-classes (not common Job/Pipeline). Thin and
  deliberate (run-all-gates semantics), acceptable — but TWO preflight systems coexist:
  the 2058-line legacy monolith `kernel/preflight.py` AND `kernel/preflight_pipeline/`.
  Finish the migration, then shrink the monolith. Size **M**.
- `pp_training.py:40` builds its own ABC/thread-pool phase machinery — moot if B-7 lands.
- God-modules on top of the primitives: `kernel/panel_pipeline/job_panel_scoring.py` (>3500
  lines), `kernel/portfolio_qp/tasks.py` (3934), `kernel/preflight.py` (2058) — discipline is
  per-file size, not pattern; flag for decomposition, size **L**, low urgency.

## B-9. NYSE-calendar / asset-class hardwiring — [VERIFIED, seed confirmed + extended]

`renquant_common/market_calendar.py` (378 lines) exists precisely to be "the ONE shared
implementation" (its own docstring: hand-copied previous/last-completed-session impls had
accumulated), exports `last_completed_session`, `sessions_between`, `SessionCalendar` Protocol,
fail-closed `CalendarUnavailableError`. **The pipeline kernel never imports it** (grep: zero
`renquant_common.market_calendar` hits in pipeline src). Parallel implementations survive at:
- `kernel/data.py:34-57` `_last_completed_nyse_session` (seed confirmed) + `:21-31` NY-tz stamp
- `kernel/exits.py:52-106` `_is_nyse_trading_day` + `nyse_trading_days_between`
  (weekday-only fallback `:65` silently assumes trading day on pmc failure — fail-open)
- `kernel/pipeline/task_data_freshness.py:183,199,213`
- `kernel/typed_past/typed_data_freshness.py:83`
- `kernel/intraday_wash.py:133-139` (NY-time session features)
- `kernel/execution/t2_settlement.py:29,48` — settlement rolls by `weekday() < 5` only,
  **no holiday calendar** → T+1/T+2 dates wrong across market holidays (also a correctness bug,
  not just a duplication).
Asset-class: calendar name "NYSE"/"XNYS" and `America/New_York` are hardcoded at every site —
crypto/24x7 (RFC §2) requires swapping each; common's `SessionCalendar` Protocol is the ready
seam. Migration: mechanical per-site swap to `renquant_common.market_calendar` — **S per site,
M total**, risk LOW-MEDIUM (freshness/streak/settlement semantics must be parity-tested).

## B-10. portfolio_qp (12,113 lines) — runtime vs research split — [VERIFIED]

Production status: `strategy_config.json` `rotation.joint_actions.solver="greedy"` (QP path OFF
live since the 2026-06-09 <2% sizing bug, renquant-pipeline #59); `strategy_config.shadow.json`
sets `solver="qp"` → the QP runtime path is **shadow-live, NOT dead — retain**.
Wiring is clean: `kernel/pipeline/job_joint_actions.py:41` lazily mounts `JointPortfolioQPTask`,
no-op unless config says qp.

Belongs in pipeline (runtime kernel):
- `qp_solver.py` (642 — textbook soft-penalty formulation, well-documented),
  `signal_combiner.py`, `task_joint_qp.py`, `job_qp.py`, `constraint_snapshot.py`,
  `live_shadow_telemetry.py`, `cvxportfolio_backend.py`, `proportional_trade.py`,
  `davis_norman.py` (canonical band, 3 refs), and the runtime Task parts of `tasks.py`.

Belongs in renquant-backtesting (replay/eval harness, ~4,300 lines):
- Experiment drivers with argparse CLIs: `e1_tc_decomposition.py` (482),
  `e2_horizon_sweep.py` (219), `e3_e4_breadth_shortsleeve.py` (286, 1 ref),
  `stage_a_significance.py` (271, 1 ref)
- Replay harness: `run_ab_replay.py` (955), `allocator_replay.py` (928),
  `replay_significance.py`, `wf_replay_loader.py` (573), `patchtst_replay_loader.py` (366),
  `placebo_replay_loader.py` (69, 1 ref), `baseline_allocators.py` (713 — E-series baselines,
  refs are tests/replay only).
These are backtesting/forensics by the operating-model table ("Sim/LEAN/WF validation and
forensics" → renquant-backtesting). They correctly import stats from
`renquant_common.metrics` (DSR/PBO/HAC) — the move is mostly `git mv` + import path.
Migration **M-L** (tests move with them). Risk LOW (shadow/research only). Sequencing: move
the four e*/stage_a drivers + placebo loader first (near-zero refs, **S**).

`tasks.py` (3934) is a god-module mixing runtime QP tasks, wash/churn/saturation masks, and TWO
tax models — split when the B-4 tax unification happens.

## B-11. Dead / retire-retain ledger

| Item | Evidence | Guidance |
|---|---|---|
| `renquant_common/registry/mlflow_registry.py` (229) | zero importers in pipeline/model/orchestrator src (grep) | RETIRE from common or move to renquant-model when MLflow is actually adopted; it drags a lazy mlflow surface into the "boring" contracts repo. **S** |
| `kernel/net_safety.py` shim | self-documented "can be deleted once consumers switch" | RETAIN until kernel importers rewired; then delete. **S** |
| `kernel/models.py` legacy scorers (`predict_qlearning/manual/classification`) | LIVE — `task_sell.py:128`, `task_candidates.py:170`, `job_universe.py:73`; legacy per-ticker tournament is still the buy-admission gate | RETAIN. Do not retire until panel path replaces per-ticker admission. |
| `fetch_intraday_bars` (`kernel/data.py:495`) | no in-repo callers; umbrella may call via lift | VERIFY umbrella usage, then move with B-6 to base-data. |
| `pp_training(.full)` | only lift-test consumers in-repo | see B-7 — move/delete. |
| QP disabled (greedy) production path | config-verified greedy since 06-09; QP shadow-only | RETAIN both; the greedy path is production, QP is the shadow candidate. Don't delete either. |
| `kernel/meta_label/triple_barrier.py` | AFML labeling (training-side) but feeds the config-gated meta-label ENTRY filter + preflight artifact contract (`preflight.py:1355`) | RETAIN in place short-term; long-term the LABELING belongs in renquant-model, the runtime FILTER stays here. **M** |
| pipeline `data/ohlcv/*` parquet | committed market data | move per B-6. |

## B-12. CORRECT patterns worth codifying (positive findings)

1. **Re-export shim with deletion note** — `kernel/net_safety.py`: canonical impl in common,
   local name kept as a pure shim. The template for retiring every B-2/B-9 duplicate.
2. **Structural dependency pinning** — pipeline `pyproject.toml` comments WHY
   `renquant-common>=0.8.1` (the fingerprint unification) — version floors carry incident
   provenance.
3. **Single-source consumption + identity test** — `fingerprint_dispatch.py` imports
   fingerprints only from common; `tests/test_model_content_sha256_shared.py` pins is-identity.
4. **Compose-don't-copy orchestration** — `kernel/pipeline/pipeline.py` re-exports common
   Task/Job/run_parallel and adds only the domain extension (TickerJob); explicitly deleted the
   duplicated executor loop.
5. **Enum single source** — `context.py:12` imports `RegimeLabel` from renquant_common as the
   regime taxonomy.
6. **Canonical-path re-export (§3.5)** — `__init__.py:48-58`: `renquant_artifacts.contracts`
   re-exported for API convenience but resolving straight to the canonical source, no shim.
7. **One train/serve transform** — `kernel/panel_pipeline/alpha158_features.py` imports
   `renquant_base_data.alpha158_ops` shared by training and serving (the anti-skew pattern).
8. **Boundary enforcement as tests** — `tests/test_import_boundaries.py`: runtime import check
   + AST scan that catches lazy imports, with an explicit, dated exclusion list
   (`_PHASE1_EXCLUSIONS`) instead of silent tolerance. Mirrar in every repo.
9. **Pure policy state machines** — `kernel/broker_reconciliation.py`: no broker calls, no I/O,
   deterministic idempotency ids; broker mutation stays in execution.
10. **Golden-vector lockstep for unavoidable temporary duplicates** —
    `intraday_decisioning.compute_parent_intent_id` pinned by vectors generated from the
    execution impl, with the common-lift follow-up named in the docstring.
11. **Fail-closed shared calendar** — common `market_calendar.py` SessionCalendar Protocol +
    `CalendarUnavailableError` (pipeline should actually USE it — B-9).

## B-13. renquant-common health

- Import boundary CLEAN [VERIFIED]: no broker/torch/xgboost/LEAN imports; deps are
  numpy/pandas/pandas_market_calendars/pyarrow/pydantic/scipy/arch; mlflow only lazy inside the
  (unused) registry.
- Doc drift: common CLAUDE.md still says "small and boring: Task/Job/Pipeline, schemas,
  contract helpers", but the package legitimately carries the operating-model-sanctioned
  training/eval utils (risk_metrics 491, stats, metrics/DSR-PBO-HAC, market_calendar, hurst,
  hmm_regime_labels, purged_cv, walk_forward_splits). Update common CLAUDE.md to match the
  ledger role so the boundary is enforceable as written. **S**
- `notify.py` performs network I/O (ntfy.sh POST, `notify.py:127-133`) from the contracts
  package — env-suppressible (`RENQUANT_NO_NOTIFY`), but side-effectful code in the
  "domain-neutral contracts" repo is a mild smell; fine to retain, document as the one
  sanctioned side effect.
- `tests/test_import_boundaries.py` + `tests/test_api_snapshot.py` in common are good
  enforcement patterns.

---

## Priority ordering (cluster B remediation)

1. **B-7** training pipeline out of renquant-pipeline (M) — removes a boundary violation AND an
   environment-dependent dark-alias hazard.
2. **B-1** finish the kernel cutover repo-by-repo or freeze the umbrella copy behind shims (L) —
   everything else (B-2, drift risk) is a symptom of this.
3. **B-4** one tax model + config-sourced rates (M) — direct economics consistency.
4. **B-9** swap calendar call sites to common market_calendar (M, mechanical) — includes the
   t2_settlement holiday bug.
5. **B-3 residue** lift `compute_parent_intent_id` to common (S).
6. **B-2** state_paths shim + decision_trace/selection reconciliation (S/M).
7. **B-10** move e*/stage_a/placebo replay drivers to backtesting (S first tranche, M-L full).
8. **B-6** fetchers → base-data; drop committed OHLCV (M).
9. **B-11** retire mlflow_registry from common (S); **B-13** doc refresh (S).
