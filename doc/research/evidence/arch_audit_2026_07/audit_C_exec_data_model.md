# GOAL-3 Architecture Audit — Cluster C

Date: 2026-07-10 · Scope: `renquant-execution`, `renquant-base-data`, `renquant-model`,
`renquant-artifacts`, `renquant-backtesting` (exists as a repo — confirmed in
`RENQUANT_REPOS.md` line 21). READ-ONLY audit; all claims below tagged
[VERIFIED] were checked directly against files (diff/grep/read), not inferred.

Contracts audited against: `/Users/renhao/git/github/RenQuant/doc/arch/subrepo-operating-model.md`
plus each repo's `CLAUDE.md` / `README` / `docs/source-map.md`.

---

## 0. Bottom line

1. **Biggest structural violation: `renquant-artifacts` is bypassed.** Its registry
   contains exactly one fixture file; every real promotion record lives in the
   umbrella (lock pins, umbrella `artifacts/` dumps, promote scripts). [VERIFIED]
2. **Execution repo carries a full trading strategy** (IGV short plan state machine
   with hardcoded price levels) — direct breach of its own "do not decide alpha"
   contract. [VERIFIED]
3. **Six umbrella `live/` files have execution-repo twins; 4 of 6 have diverged**,
   with no mechanical drift guard, and the two stacks have split authority
   (umbrella = active daily live path, execution repo = orchestrator native/intraday).
   [VERIFIED]
4. **MIN_FRACTIONAL_NOTIONAL_USD has NO mechanical parity test** (comment-sync only);
   the QTY_INTEGRAL_EPS tripwire is one-sided. [VERIFIED]
5. **Promotion-gate thresholds are duplicated** (backtesting `wf_gate/runner.py` ↔
   model `oos_ic_export.py` mirror) and 10 files are byte-identical duplicates
   across/inside model + backtesting. [VERIFIED]
6. base-data is contract-clean on decision logic but is **yfinance-only on the daily
   OHLCV path** and **hardcodes the SPY-excess label benchmark** (asset-class coupling).
   [VERIFIED]

---

## 1. renquant-execution

### 1.1 Umbrella `live/` twin inventory (audit Q1) [VERIFIED via diff]

| Umbrella file (`RenQuant/live/`) | Execution twin (`src/renquant_execution/`) | State |
|---|---|---|
| `alerts.py` (237L) | `alerts.py` (237L) | **byte-identical** |
| `ibkr_broker.py` (43L) | `ibkr_broker.py` (43L) | **byte-identical** |
| `alpaca_broker.py` (497L) | `alpaca_broker.py` (521L) | **diverged — execution ahead** (lazy SDK import, fractional/S-FRAC statuses, `_FractionableLookupError`) |
| `broker.py` (126L) | `broker.py` (265L) | **diverged — execution ahead** (`NO_SUBMIT_STATUSES` vocab, fractional order rules, `QTY_INTEGRAL_EPS` helpers — none exist umbrella-side) |
| `paper_broker.py` (278L) | `paper_broker.py` (117L) | **diverged BOTH ways** — umbrella copy is the richer one (R2-audit cash/avg-cost/mark-to-market); execution copy is a leaner rewrite |
| `broker_readonly.py` (159L) | `readonly_broker.py` (196L) | **diverged — execution ahead** (D6-§2a broker-tag parameterization for multi-arm shadow); execution docstring self-declares "Owning implementation of the umbrella repo's `live/broker_readonly.py` port" |

Umbrella-only (no execution twin): `runner.py`, `agent_breaker.py`, `clock.py`,
`stream_watchdog.py`. Execution-only (native ports, no umbrella twin — cleanly
migrated): `order_state_machine.py`, `order_math.py`, `order_lifecycle.py`,
`live_commit.py`, `live_persistence.py`, `preopen_cancel_gate.py`,
`options_executor.py`, `igv_short_*`, `factory.py`, `execution.py`, `*_port.py`.
(`options_executor` / IGV have **no** umbrella copy left — good; the
`igv_short_monitor.py` docstring still says "live.options_executor" — stale doc.)

**Which is authoritative?** Split by path:
- The **active daily live path is the umbrella**: `RenQuant/live/runner.py:32-36`
  imports `.broker/.alpaca_broker/.paper_broker/.alerts` locally and `:178`
  imports `.broker_readonly` — it never imports `renquant_execution`. [VERIFIED]
- The **orchestrator native/intraday paths are execution-repo**:
  `renquant-orchestrator/src/renquant_orchestrator/execution_reconciler.py:69`,
  `intraday_live_executor.py:149`, `native_live_run.py`, `daily.py:14`,
  `intraday_session_runner.py:35` all import `renquant_execution`. [VERIFIED]

**Violation C1-a — un-guarded twin drift.** Contract broken: operating-model
"never duplicate across repos". There is **no parity test** anywhere that diffs
`live/*.py` against the execution repo (searched both test suites). `alerts.py`
/ `ibkr_broker.py` are identical today only by luck; `broker.py` semantics have
already forked (no-submit statuses recognized on one side only) and
`paper_broker.py` forked in the *opposite* direction. Target owner:
renquant-execution (per `docs/source-map.md` the port direction is
umbrella→execution); umbrella `live/` should shrink to a thin shim or be
deleted once the native cutover lands. Migration: **M** (per-file: S for
alerts/ibkr shimming; M for broker/alpaca/paper because the active live path
depends on the umbrella copies). Risk: HIGH-latent — a fix landed in one stack
silently missing from the stack that actually trades (this exact class caused
the 2026-06 `self._config` incident).

### 1.2 Strategy policy inside execution (audit Q2) [VERIFIED]

**Violation C1-b — IGV short plan = alpha/decision logic in execution.**
- `src/renquant_execution/igv_short_state.py:60-72` — `PlanConfig` hardcodes
  entry/exit price levels as code defaults: `reject_zone=(97.5, 99.0)`,
  `breakdown_level=94.8`, `tp_half_at=93.0`, `tp_most_at=90.0`,
  `sl_half_at=100.5`, `void_level=101.5`; `step()` is a full trade
  decision state machine (ENTER / CLOSE_HALF / CLOSE_MOST / CLOSE_ALL).
- `src/renquant_execution/igv_short_monitor.py` — cron entrypoint that fetches
  market data, *decides*, and places live option orders via `options_executor`.

Contract broken: execution `CLAUDE.md` "Consume explicit order intents from
`renquant-pipeline`… Do not decide alpha… tune strategy thresholds". Target
owner: decision machine → `renquant-pipeline`; the plan levels → strategy
config repo; execution keeps only the order-placement + audit surface.
Migration: **M**. Risk: MEDIUM — it is heavily gated (mode==live +
`IGV_LIVE_ARMED=1` + kill-switch file, fails closed on missing config), but it
is a second, parallel decision engine living where the contract says none may
exist.

Gray area (acceptable, noted): `preopen_cancel_gate.py:1-13` uses ES-futures/
SPY-sigma logic to cancel adverse queued orders. This is order-lifecycle
protection (execution-quality, not alpha) — defensible in execution, but it
bakes US-equity/NYSE/SPY assumptions into the repo (relevant to the crypto RFC).

### 1.3 Contract single-sourcing (audit Q3)

- **`MIN_FRACTIONAL_NOTIONAL_USD = 1.0` duplicated, NO mechanical parity test.**
  [VERIFIED] `renquant-execution/src/renquant_execution/broker.py:56` ↔
  `renquant-pipeline/src/renquant_pipeline/kernel/sizing.py:187` (comment
  `sizing.py:184-186`: "Keep the VALUE in sync with the execution repo").
  Each side's tests assert only against **its own import**
  (`renquant-pipeline/tests/test_sizing.py:268-283`,
  `renquant-execution/tests/test_order_math.py:113`) — if either side edits its
  literal, nothing fires. Fix: literal-pin test (`assert X == 1.0` + cross-ref
  comment) on both sides, or move the constant to `renquant-common`.
  Migration: **S**. Risk: LOW today (value stable), but it is the exact
  fingerprint-triple-impl failure shape.
- **`QTY_INTEGRAL_EPS` replication is the better pattern but one-sided.**
  [VERIFIED] `broker.py:8-21` documents the replication from umbrella
  `backtesting/renquant_104/adapters/commit_contract.py:60` and
  `tests/test_order_state_machine.py:711-723` pins the literal `1e-9`. But the
  umbrella has **no reciprocal pin test** (grep of `RenQuant/tests` empty) — an
  umbrella-side change drifts silently. Fix: add the mirror pin umbrella-side. **S**.
- **Order-status vocabulary: CORRECT, single-sourced.** [VERIFIED]
  `TERMINAL_STATUS_MAP` (`order_state_machine.py:150`) and
  `NO_SUBMIT_STATUSES` (`broker.py:27-43`) exist only in execution; the
  orchestrator imports them (`execution_reconciler.py:69`); renquant-pipeline
  never imports execution (verified zero direct imports) — the orchestrator
  *binds* the vocabulary in (`intraday_decisioning.py:313`). The umbrella
  runtime has no competing no-submit vocab (grep clean).
- **Fee constants: no exec↔pipeline duplication found.** Transaction costs are
  config-driven in pipeline kernel (`rotation.py`, `governor_sizing.py:76,414`);
  execution has none. The readonly wrapper also deliberately does NOT duplicate
  pipeline's `ALLOWED_BROKERS` allowlist (`readonly_broker.py` docstring:
  validates tag *shape* only, membership stays pipeline-owned) — **CORRECT**.
- Import-boundary test present: `tests/test_import_boundaries.py`. **CORRECT**.

---

## 2. renquant-base-data

- **Provider coupling: daily OHLCV path is yfinance-only.** [VERIFIED]
  `src/renquant_base_data/loaders/data.py:234` (`provider: str = "yfinance"`),
  `:252-272` (single provider branch + hang-timeout workaround), `:277`
  (`raise ValueError(f"Unknown provider… Supported: ['yfinance']")`). FMP /
  Finnhub / SEC / FRED / Alpaca exist as separate fetchers but are NOT wired as
  daily-price fallbacks. Not a boundary violation (provider logic belongs
  here per its CLAUDE.md), but a single-vendor SPOF on the price spine.
  Target: provider registry / fallback in this repo. Migration: **M**. Risk:
  MEDIUM (yfinance instability is already worked around by a fetch timeout —
  `:241-243` documents a 4-hour hang incident).
- **SPY-excess label + benchmark baked in.** [VERIFIED]
  `alpha158_qlib_panel.py:215-237` (`_compute_excess_label_frame`:
  `fwd_{n}d_excess = fwd_ticker − fwd_spy`), `:315-318` and `:416-418` hard
  `FileNotFoundError` without `ohlcv/SPY/1d.parquet`, `:60`
  (`MAX_SPY_LABEL_FFILL_DAYS = 5`); `rawlabel_sidecar.py:70`
  (`DEFAULT_BENCHMARK_TICKER = "SPY"` — at least parameterized);
  `track_b_features.py:85,111` (SPY-beta factor). Label construction living in
  base-data is BY DESIGN (it owns "the training-data INPUT to the factory"),
  but the benchmark is code-hardcoded rather than manifest-declared — blocks
  any non-US-equity reuse (crypto RFC). Fix: benchmark as a manifest field.
  Migration: **S/M**. Risk: LOW now.
- **Asset-class assumptions:** NYSE tz/session logic in `loaders/data.py:23-40`
  — but it delegates to canonical `renquant_common.market_calendar` (campaign
  B5) — **CORRECT** direction (single-sourced in common).
- **Decision-logic check: clean, one gray area.** No order/position/decision
  code found. `watchlist_screen.py` computes add/drop *suggestions* vs SPY
  (universe policy analytics) but is advisory-only — writes a markdown report +
  ntfy, mutates nothing [VERIFIED `:260-300`]. If it ever feeds automation it
  should move to a research/strategy home. **S** if moved.
- Broker-vendor check: `alpaca_common.py` is a data-refresh rate-limiter
  (TokenBucket) — data-plane only, no trading surface. **CORRECT**.
- Gap: **no import-boundary test** in base-data `tests/` (execution,
  backtesting, model all have one). **S**.

---

## 3. renquant-model

- **No live/broker leakage: clean.** [VERIFIED] grep for
  alpaca/broker/ib_insync/live across `src/` matches only `news_alpaca` data
  dir names. Per-family import-boundary tests exist
  (`tests/gbdt/test_import_boundaries.py`, `tests/patchtst/…`). **CORRECT**.
- **WF gate location (audit Q5):** the 3-tier gate lives in
  **renquant-backtesting** `wf_gate/runner.py` (`SHUF_IC_MAX = 0.005` :193,
  `PLACEBO_GENUINE_IC_MARGIN = 0.02` :203, `_placebo_ic_threshold` :207,
  verdict assembly :2964-3042). The weekly promote job imports it **from the
  pinned subrepo** (`RenQuant/scripts/weekly_wf_promote.sh:138,146`) — so the
  subrepo copy is authoritative for gating. [VERIFIED] This matches the
  operating model's assignment (backtesting owns "walk-forward validation"),
  but NOT the prompt's "model owns promotion gates" reading, and only half
  matches the D-C8 split (asset-specific gate decisions would move to model).
- **Violation C3-a — gate thresholds mirrored in model, comment-sync only.**
  [VERIFIED] `renquant-model/src/renquant_model_patchtst/oos_ic_export.py:62-67`
  (`SHUFFLED_IC_MAX_ABS = 0.005`, `PLACEBO_RATIO_MAX = 0.5`,
  `PLACEBO_FLOOR = 0.005`, "keep numerically identical to renquant-backtesting
  wf_gate/runner.py") and `:101` ("Mirror of wf_gate `_placebo_ic_threshold`").
  Model tests pin the mirror's own literals
  (`tests/patchtst/test_oos_ic_export.py:110`,
  `tests/patchtst/test_research_pipeline.py:140-142`) but nothing cross-checks
  backtesting. Contract broken: promotion semantics single-sourcing. Target:
  constants exported from one place (renquant-common contracts, or backtesting
  as the gate owner) and imported by model exporters. Migration: **M**
  (dependency direction: model must not import backtesting → the shared home
  has to be renquant-common). Risk: MEDIUM — a gate-threshold change that the
  model-side self-check doesn't see produces "exported IC passes locally,
  gate rejects" confusion (the chronic wf-promote tangle already has this shape).
- **Violation C3-b — byte-identical file duplicates across model ↔ backtesting.**
  [VERIFIED, `diff` = 0 lines each]
  - `renquant_model_common/acceptance_entry_ic.py` ≡ `renquant_backtesting/forensics/acceptance_entry_ic.py`
  - `renquant_model_common/challenger.py` ≡ `renquant_backtesting/forensics/challenger.py` (the de-facto "promote yes/no" challenger protocol — promotion logic duplicated across two repos)
  - `renquant_model_common/triple_barrier.py` ≡ `renquant_backtesting/labels/triple_barrier.py` ≡ `renquant_backtesting/meta_label/triple_barrier.py` (3 copies)
  Contract broken: "families/repos share code only through renquant-common".
  Target owner: `renquant-common` (they are exactly the "shared training/eval
  utilities" class the map assigns to common). Migration: **M** (mechanical
  move + re-export shims). Risk: MEDIUM — silent semantic fork of acceptance
  math between the factory and the validator.
- **Intra-backtesting duplication:** `metrics/{block_bootstrap,deflated_sharpe,
  hac_se,pbo,perf_summary}.py` ≡ `forensics/metrics/*` — 5 byte-identical
  pairs inside one repo [VERIFIED]. **S** (keep one, re-export).
- **D-C8 layout check:** renquant-common has **no** generic cost primitives
  today (grep: only incidental "cost" hits in `market_calendar`/`stats`);
  transaction-cost math is config-driven in pipeline kernel; model contains no
  cost code. So the D-C8 target (generic cost primitives → common) is
  **not yet built**, but nothing is in the *wrong* place — aspirational gap,
  not a violation.
- **Fingerprint single-sourcing: model side FIXED.** [VERIFIED]
  `renquant_model_gbdt/fit_calibrator_alpha158_fund.py:22` imports
  `renquant_common.model_fingerprint.model_content_sha256`
  (shared impl at `renquant-common/src/renquant_common/model_fingerprint.py:471`).
  Residual: the umbrella runtime still defines an independent copy
  (`RenQuant/backtesting/renquant_104/kernel/panel_pipeline/panel_scorer.py:108`)
  — outside cluster C, flag to the umbrella-cluster audit.
- **CORRECT:** model `artifacts/` working dir is `.gitignore`d (0 tracked files
  — [VERIFIED `git check-ignore` + `git ls-files`]); experiment dumps are not
  committed, consistent with "don't hide prod artifacts in a model repo".
- Cross-cluster note: umbrella `RenQuant/kernel/{hmm_regime_labels,walk_forward_splits}.py`
  **differ** from the renquant-common copies that officially own them
  [VERIFIED diff] — same drift class as §1.1, owned by cluster covering common/umbrella.

---

## 4. renquant-artifacts (audit Q6)

- **The package is genuinely used — as a contracts/validation library.**
  [VERIFIED] `validate_artifact_manifest` / `validate_panel_artifact_contract` /
  `validate_model_evidence_contract` / `validate_feature_contract` /
  `hash_jsonable` are imported by renquant-model (`gbdt/pipelines.py:16`,
  `patchtst/pipelines.py:10`), renquant-pipeline (`panel_scoring.py:15`,
  `model_admission.py:7`, `__init__.py:51`), and renquant-orchestrator
  (`daily.py:11` + 5 intraday modules). **CORRECT** pattern.
- **Violation C4-a — the registry (its actual mandate) is BYPASSED.** [VERIFIED]
  `registry/` contains exactly **one** file: `example-artifact.json`
  (`retention_class: "fixture"`, `promotion_status: "diagnostic"`). No real
  factory model has ever been published there. Real promotion state lives in
  the umbrella instead: `subrepos.lock.json` pins moved by
  `RenQuant/scripts/promote_pin.py` (4 `subrepos.lock.json.promote-bak.*`
  files sit at umbrella root), `RenQuant/scripts/weekly_wf_promote.sh` /
  `promote_shadow_patchtst.py` / `manual_promote.sh`, umbrella `artifacts/`
  experiment dirs (`patchtst_shadow`, `xgb_5cut_5seed_pt07`, …), and stamped
  `wf_gate_metadata` in live artifacts. Contract broken: operating-model
  "Artifact Storage And Discovery" (artifacts owns manifests + promotion
  status + searchable history; "The model comes from renquant-artifacts, not
  from a training repo working directory"; "Rejected/diagnostic artifacts must
  keep the verdict"). Target owner: renquant-artifacts. Migration: **L** —
  needs a publish step at the end of the factory/gate, a resolver in
  orchestrator/pipeline that reads the registry instead of umbrella paths, and
  a history backfill. Risk: MEDIUM-HIGH governance risk (no searchable
  promotion ledger; known-failure verdicts not preserved → re-running known
  failures blindly, which the contract explicitly exists to prevent), LOW
  runtime risk (current pin flow works).

---

## 5. renquant-backtesting

- Exists as a repo with full contract files. [VERIFIED]
- **CORRECT — sim/live parity via shared contracts:** `runtime_parity.py:1-25`
  runs `renquant_pipeline.RuntimeInferencePipeline`/`PanelScoringJob` for sim
  bars instead of re-implementing decision logic — exactly what its CLAUDE.md
  mandates.
- **CORRECT — no broker mutation:** grep for
  `place_order`/`ALPACA_API_KEY`/`AlpacaBroker`/`ib_insync` across `src/` is
  empty. [VERIFIED]
- **Hosts the WF gate** (see §3) and that is consistent with the operating
  model; the weekly promote imports the *pinned subrepo* runner — the subrepo
  is authoritative for gating. Promotion *records*, however, exit to the
  umbrella (see §4) — gate-owner ≠ record-owner today.
- **Twin drift:** `wf_gate/sim_driver.py` is a diverged copy of umbrella
  `RenQuant/scripts/run_sim_104.py` (same docstring/usage text; files differ)
  [VERIFIED]. Same class as §1.1 — no drift guard. **S**.
- Intra-repo `metrics/` ≡ `forensics/metrics/` duplication (see §3). **S**.
- Import-boundary test present. **CORRECT**.

---

## 6. Consolidated violation table

| ID | Repo | file:line | Contract broken | Target owner | Size | Risk |
|---|---|---|---|---|---|---|
| C1-a | execution ↔ umbrella | 6 twins, e.g. `live/broker.py` vs `renquant_execution/broker.py:23-56` | no duplication across repos / single authority | renquant-execution (umbrella shims out) | M | HIGH-latent (fix lands in wrong stack) |
| C1-b | execution | `igv_short_state.py:60-72`, `igv_short_monitor.py` | "do not decide alpha / consume intents from pipeline" | pipeline (machine) + strategy cfg (levels) | M | MEDIUM (heavily gated) |
| C1-c | execution ↔ pipeline | `broker.py:56` ↔ `kernel/sizing.py:187` | constant single-sourcing; **no parity test** | renquant-common, or literal-pin tests both sides | S | LOW |
| C1-d | execution ↔ umbrella | `broker.py:8-21` vs `adapters/commit_contract.py:60` | one-sided epsilon tripwire | reciprocal pin test umbrella-side | S | LOW |
| C2-a | base-data | `loaders/data.py:234,252,277` | (resilience) yfinance-only daily price spine | base-data provider fallback | M | MEDIUM |
| C2-b | base-data | `alpha158_qlib_panel.py:215-237,416-418`; `rawlabel_sidecar.py:70` | benchmark hardcoded, not manifest-declared | base-data manifest field | S/M | LOW |
| C3-a | model ↔ backtesting | `oos_ic_export.py:62-67,101` ↔ `wf_gate/runner.py:193-207` | promotion-gate threshold single-sourcing | renquant-common contracts | M | MEDIUM |
| C3-b | model ↔ backtesting | `acceptance_entry_ic.py`, `challenger.py`, `triple_barrier.py` ×3 (byte-identical) | share only via renquant-common | renquant-common | M | MEDIUM |
| C4-a | artifacts | `registry/` = 1 fixture; real records in umbrella (`promote_pin.py`, `weekly_wf_promote.sh`, lock-bak files) | artifacts owns promotion records/registry | renquant-artifacts | L | MED-HIGH governance |
| C5-a | backtesting ↔ umbrella | `wf_gate/sim_driver.py` vs `RenQuant/scripts/run_sim_104.py` | twin drift, no guard | renquant-backtesting | S | LOW |
| C5-b | backtesting (intra) | `metrics/*` ≡ `forensics/metrics/*` (5 pairs) | internal duplication | one module + re-export | S | LOW |
| C-gap | base-data, artifacts | no `test_import_boundaries.py` | boundary enforcement parity with other repos | each repo | S | LOW |

## 7. Correct patterns worth preserving (all [VERIFIED])

1. Order-status vocabulary single-sourced in execution
   (`order_state_machine.py:150`, `broker.py:27-43`); orchestrator imports it,
   pipeline consumes via orchestrator *binding* and never imports execution.
2. `readonly_broker.py` deliberately does NOT duplicate pipeline's
   `ALLOWED_BROKERS` contract — validates tag shape only, ownership documented
   in-code.
3. `QTY_INTEGRAL_EPS` replication done right on the execution side: documented
   provenance + literal-pin tripwire test (needs the umbrella mirror).
4. renquant_artifacts as an imported contracts library across model/pipeline/
   orchestrator (manifest + feature + evidence validation).
5. Model repo: per-family import-boundary tests (AST scan + fresh-subprocess
   runtime check), gitignored `artifacts/`, fingerprint now imported from
   `renquant_common.model_fingerprint`, scorers exposed only via
   `renquant_common.load_scorer` entry points.
6. Backtesting `runtime_parity.py` drives the shared `renquant_pipeline`
   decision contract for sim (no parallel hand-written logic); zero broker
   mutation surface in the repo.
7. base-data delegates session/calendar logic to canonical
   `renquant_common.market_calendar`; Alpaca usage is data-plane only;
   `watchlist_screen` is advisory-only (report + ntfy, mutates nothing).
8. Weekly WF-promote imports `renquant_backtesting.wf_gate.runner` from the
   **pinned subrepo** (`weekly_wf_promote.sh:138,146`), not a working copy.
