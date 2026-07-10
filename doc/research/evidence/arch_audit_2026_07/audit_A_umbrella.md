# GOAL-3 Architecture Audit — Cluster A: RenQuant UMBRELLA repo

Date: 2026-07-10 · Auditor: Claude (read-only; no git commands run) · Scope: `/Users/renhao/git/github/RenQuant` working tree vs the multi-repo operating model.

Contracts audited against:
- `/Users/renhao/git/github/RenQuant/doc/arch/subrepo-operating-model.md` (roles table + Universal Rules 1–6; umbrella = "Permanent umbrella/integration harness + canonical data store", primary output = "Pinned assembly in subrepos.lock.json")
- `/Users/renhao/git/github/RenQuant/RENQUANT_REPOS.md` ("never add code to the umbrella `RenQuant` (integration/rollback only)")
- Umbrella `CLAUDE.md` §3.5 (umbrella never canonical source; Phase-1 byte-equivalent mirror; "Phase 5 will retire that bridge") + `AGENTS.md` (mirror of CLAUDE.md)
- On-record deprecation decision: `renquant-orchestrator/doc/design/2026-07-04-compliance-fix-campaign.md` — "pipeline = single authority for kernel/; **umbrella kernel becomes a frozen compatibility mirror — no new features land there**"

Prior art this audit builds on (do NOT re-litigate; deltas noted):
- **RQ PR #444** (merged 2026-07-04): `doc/arch/2026-07-04-umbrella-compliance-audit.md` — 30 findings (6 P0/19 P1/5 P2) [VERIFIED — read in full]
- **C1 mirror-drift inventory**: `renquant-orchestrator/doc/design/2026-07-04-c1-mirror-drift-inventory.md` — 217 umbrella kernel files, 73 material-drift, 49 umbrella-only (42 LIFT / 7 RETIRE), 21 pipeline-native [VERIFIED]

---

## 0. Executive summary

The umbrella is still, in practice, the **production runtime** for everything except the aliased kernel stems — not a deprecated pin consumer. Three unpinned umbrella layers sit directly on the live money path every day: `live/*` (broker classes + runner CLI), `backtesting/renquant_104/adapters/*` (RunnerAdapter order dispatch, 9,098 lines), and the scheduled shell layer (`scripts/daily_104.sh` + launchd). The kernel is a bidirectionally-drifted dual-home (113 files differ vs the pinned pipeline as of today — up from 73 material-drift at the 07-04 baseline), ~15.4k lines of training code and ~7.9 GB of model binaries/artifacts still live in the tree, and the umbrella `strategy_config.json` working copy has diverged stale (47.9 KB vs the pinned 57.8 KB policy) while sim/eval/rollback legs still read it. What IS correctly umbrella-owned (pins, assemble/doctor, promote-pin, rollback baks, dagster dependency-guard) is healthy — the audit lists it explicitly in §3 so migration doesn't overshoot.

### Summary table (violations)

| # | Component | Sharp location | Contract broken | Target owner | Size | Live-path risk | Exception/PR on record |
|---|---|---|---|---|---|---|---|
| A1 | RunnerAdapter live order dispatch | `backtesting/renquant_104/adapters/runner.py:1039` (`commit`), `:1177` (SELL `broker.place_order`), `:1499` (BUY) | broker mutation outside renquant-execution; adapters NOT covered by kernel alias → unpinned live code | renquant-execution | L | **HIGHEST** (places every real order) | #444 F-20; #454 execmath slice merged 07-10 |
| A2 | Order math `runner_execmath.py` | `adapters/runner_execmath.py:19` (`cap_buy_order_to_cash`) | order-sizing math outside execution repo | renquant-execution | S (mostly done) | Medium | **PR #454 (merged 2026-07-10)** — time-bounded call-site exception; math delegated to `renquant_execution.order_math.cap_affordable_qty` (execution#25); sunset = adapter-migration cutover |
| A3 | `live/broker_readonly.py` notional forward | `live/broker_readonly.py:154` (`__getattr__`), no `place_notional_order` override | readonly wrapper duplicates execution port; fail-open on notional writes | renquant-execution (`readonly_broker.py:148` already fixed there) | S | Medium (latent — no caller today) | **Issue #456 (open, 2026-07-10)**; execution PR #26 = migration target |
| A4 | Umbrella broker stack `live/*.py` | `live/alpaca_broker.py` (497L), `broker.py`, `paper_broker.py`, `runner.py:420` | duplicates renquant-execution (which declares itself owner); bidirectional drift | renquant-execution | L | **HIGHEST** (real Alpaca submission class) | Operating-model "Open Migration Work" item 4; partial ports exist |
| A5 | Training code resident in umbrella | `backtesting/renquant_104/training/` (2,380 LOC) + `training_panel/` (13,042 LOC) | "Do not implement model training internals here"; renquant-model owns factory | renquant-model | L | High (Sunday tournament writes prod models — #444 F-17 P0) | #444 F-17/F-19; renquant-model has a DIVERGED parallel impl, not a migration |
| A6 | Dual-home kernel (57k LOC) | `backtesting/renquant_104/kernel/` — 217 files; 113 differ vs pinned pipeline today | §3.5 mirror invariant dead; sim/WF-gate/promote run umbrella kernel while live runs pinned pipeline stems | renquant-pipeline (authority) | XL | High (promote evidence from code live won't run — #444 F-3) | C1 inventory + freeze decision 2026-07-04; `scripts/check_mirror_drift.py` report-only |
| A7 | Root `kernel/{hmm_regime_labels,regime_labels,walk_forward_splits}.py` | full impls, md5-diverged from renquant-common twins | shared training/eval utils belong to renquant-common; split-brain importers | renquant-common | S | Low (research/eval only) | #444 F-13; common's copy self-documents "lifted from umbrella" |
| A8 | Strategy-config working-copy drift | `backtesting/renquant_104/strategy_config.json` (47,880 B, STALE) vs pinned strategy-104 `configs/strategy_config.json` (57,835 B) + 72 side-config sprawl | strategy policy owned by renquant-strategy-104 | renquant-strategy-104 (canonical); umbrella copy demote to experiment-only | M | Medium (sim/analysis/rollback-mode read the stale copy) | #444 F-7 — still diverged as of 07-10 |
| A9 | Model binaries + artifacts in tree | `backtesting/renquant_104/models/` (1.1 GB q-tables etc.) + `artifacts/` (6.8 GB incl. full subrepo copies under `artifacts/diagnostics/modal_sweep_*/bundle/subrepos/`) | Universal Rule 4 (manifest+URI, not git) | renquant-artifacts (manifests) + object store | L (mechanical) | Low-Med (backup jobs couple) | #444 F-28/29/30 — still present |
| A10 | `scripts/daily_104.sh` monolith + sibling shell chains | `scripts/daily_104.sh` (647L; bridge default `:380-383`); `weekly_wf_promote.sh`; `weekly_tournament_retrain.sh` | daily orchestration is renquant-orchestrator's declared role | renquant-orchestrator (policy/sequencing); host keeps env glue | M | High (it IS the daily run) | daily-bridge default already delegates the runner leg |
| A11 | Broker mutation in scripts/ | `scripts/preopen_cancel_gate.py:367` (direct `cancel_order_by_id`, fail-OPEN fallback); `scripts/execute_shadow_orders.py` (own Alpaca SDK path) | broker semantics outside live/ and outside execution repo | renquant-execution | S | Medium (order-cancelling path) | #444 F-18/F-22c |
| A12 | Run-bundle writer in umbrella kernel | `kernel/artifact_contract.py:318` (`build_run_bundle`) ← `adapters/runner.py:1991,2054` | run bundle = orchestrator's declared primary output | renquant-orchestrator (or common contract lib) | M | Medium | C1 inventory: `artifact_contract.py` = LIFT |
| A13 | Rust scorer workspace | `rust/transformer_scorer*` + `kernel/panel_pipeline/panel_scorer.py:289,300` import hooks | model inference code in umbrella; parallel-track | renquant-model (or pipeline once runtime) | M | None today (scaffold, no prod dependency per `rust/README.md`) | none |
| A14 | Live state + stray root DBs | `backtesting/renquant_104/live_state.alpaca.json` (v1 writers umbrella-side); root `runs.alpaca.db`+`score_db.sqlite` 0-byte strays (`score_db.sqlite` NOT gitignored) | state schema owned by orchestrator (`live_state_v2.py`); path-resolution hygiene | renquant-orchestrator/pipeline (writers); umbrella keeps the anchor | S | Low | live_state_v2 self-documents as the replacement |

---

## 1. Per-violation detail

### A1 — RunnerAdapter: the live order path lives in the umbrella, unpinned [VERIFIED]
- `live/runner.py:420` `from adapters.runner import RunnerAdapter`; `:526-535` constructs it, runs `InferencePipeline`/`SellOnlyPipeline`, then `adapter.commit(ctx)`.
- `adapters/runner.py` is **2,311 lines** (grew from 2,189 at the 07-04 audit — still under active development post-freeze-decision, e.g. `runner.py.bak_configfix_20260626_095913` sits beside it). `commit()` at `:1039`; real submissions at `:1177` (SELL) and `:1499` (BUY) via `broker.place_order`. State save `save_live_state_atomic(state_file, self._state, self._config)` at `:1980`.
- The whole `adapters/` package (9,098 lines across 31 files: broker_sync, commit_contract, runner_ext_sell, runner_tax_lots, z9_stops, state_store, sim.py 2,475L, lean*.py …) is resolved from the **working tree** via `sys.path` — the kernel-alias bridge does not cover `adapters.*`, so this is unpinned production code on every live cycle (#444 F-20 note re-verified).
- Contract broken: renquant-execution owns "broker adapters … order submission/cancel/reconcile" (`renquant-execution/README.md:16-18`); operating-model Open Migration item 4.
- Migration size **L**; risk **highest** — this is the money path; operator memory pins "fix-wave protects production" (behavior-invariance proof + A/B required). #454 shows the sanctioned pattern: move math to execution, keep a delegating call-site, sunset later.

### A2 — runner_execmath.py: order math, #454 exception on record [VERIFIED]
- `adapters/runner_execmath.py` (183L): `cap_buy_order_to_cash` (`:19`), `broker_order_execution` (`:73`), `effective_live_holdings_after_orders` (`:126`). Docstring declares "No broker calls of their own".
- **PR #454 merged 2026-07-10**: sizing math (whole-share + fractional) now owned by `renquant_execution.order_math.cap_affordable_qty` (execution#25); the umbrella keeps only a TIME-BOUNDED delegating call-site with a fail-closed ImportError fallback; deletion planned under the adapter-migration program, "renquant-execution owns the cutover". Auditor: `scripts/check_commit_path_no_int_truncation.py`.
- Residual: `broker_order_execution` status-classification and holdings-projection remain umbrella-resident (small, migrate with A1).

### A3 — broker_readonly.py: duplicated port + notional-forward defect (issue #456) [VERIFIED]
- Umbrella `live/broker_readonly.py` (159L) `ReadOnlyBrokerWrapper` overrides `place_order`/`place_stop_order`/`cancel_order` but has **no `place_notional_order` override**; `__getattr__` at `:154-159` forwards unknown attrs to the wrapped REAL broker. A future shadow-path notional order would really submit. Latent today: no `place_notional` symbol anywhere in umbrella `live/` (grep-verified); the capability exists in renquant-execution (`alpaca_broker.py:265`, `broker.py:205`).
- The owning implementation already exists and is FIXED: `renquant-execution/src/renquant_execution/readonly_broker.py:148-163` swallows notional orders (`shadow_ack`), parameterizes `broker_name` (umbrella hardcodes `alpaca_shadow` at `:47`), and its docstring (`:2-4`) declares itself "the owning implementation of the umbrella repo's live/broker_readonly.py port".
- On record: **issue #456 (open, filed 2026-07-10)** — fix direction per issue: defensive override only in umbrella (no new capability), migration target = the execution port (execution PR #26).

### A4 — the umbrella broker stack duplicates renquant-execution, bidirectionally drifted [VERIFIED]
Per-file (umbrella `live/` vs `renquant-execution/src/renquant_execution/`):

| live/ file | L | counterpart | status |
|---|---|---|---|
| runner.py | 1,200 | none | umbrella-only CLI/orchestration glue; imports ONLY umbrella-local broker modules (`runner.py:32-36,178`), never `renquant_execution` |
| alpaca_broker.py | 497 | alpaca_broker.py (521) | DIVERGED both directions — live-only: G2 AgentBreaker in `place_order` (`:200-212`), whole-share `int(quantity)` (`:242`), paginated fills; execution-only: fractional support (`place_notional_order:265`, `validate_fractional_order`, fractional qty submit) |
| broker.py | 126 | broker.py (265) | diverged — execution richer (order-math helpers, notional, status constants) |
| broker_readonly.py | 159 | readonly_broker.py (196) | diverged — execution fixed + parameterized (A3) |
| paper_broker.py | 278 | paper_broker.py (117) | diverged — **umbrella richer** (Z9 stop simulation, NaN guards) — reverse-drift: features landing on the deprecated side |
| ibkr_broker.py | 43 | ibkr_broker.py (43) | byte-identical |
| alerts.py | 237 | alerts.py (237) | byte-identical |
| clock.py / agent_breaker.py / stream_watchdog.py | 30/79/225 | none | umbrella-only; agent_breaker is order-admission gating (execution-shaped, G2 caps + kill-file); clock is declared sole TZ authority (#444 F-16); watchdog is read-only observability |
| __main__.py | 4 | none | shim |

- Execution also has a newer `BrokerPort` Protocol seam (`order_state_machine.py:958`, `alpaca_broker_port.py:42`, `paper_broker_port.py:30`, `factory.py:42-50`) with NO umbrella equivalent — the target architecture already exists; the umbrella stack simply isn't wired to it.
- Contract: execution repo README/CLAUDE declare ownership; umbrella runs its own copies live daily. Migration **L**, highest live sensitivity (cutover must be behavior-invariant; paper_broker Z9-sim and agent_breaker features must be lifted first or they're lost).

### A5 — ~15.4k lines of training code resident + production-writing [VERIFIED]
- `backtesting/renquant_104/training/` — 2,380 LOC: per-ticker tournament (`tournament.py` 459L), model factory (`models.py` 702L), exports that WRITE production per-ticker models (`export.py` 299L), learners (q_table/random_tree/bag).
- `backtesting/renquant_104/training_panel/` — 13,042 LOC: `pp_panel_training.py` **3,827 LOC**, `transformer_model.py` 1,389, `global_calibrator.py` 768, `lgbm_ltr.py`, `ngboost_head.py`, `purged_cv.py`, `labels.py`, etc.
- **No filename-level migration into renquant-model has happened**: renquant-model carries a diverged parallel implementation under different names (`renquant_model_gbdt/panel_trainer.py`, `renquant_model_patchtst/*`, `renquant_model_linear/trainer.py`); only `global_calibrator.py` has a same-name twin (in renquant-model-common AND renquant-common). Two factories, drifting.
- ACTIVE schedule wiring (launchd-verified): `com.renquant.weekly-tournament-retrain.plist` → `train_104.py --skip-panel --force` → umbrella `kernel.pipeline.pp_training_full` → `training.*` — **no delegation, acceptance gate auto-disabled, writes straight to `models/<TICKER>/`** (#444 F-17 P0, still live; per-ticker q-tables updated 2026-07-09). `retrain-alpha158-linear` → `training_panel.linear_ltr` behind a delegate flag. `retrain_panel.sh` is a compatibility no-op → weekly_wf_promote.
- Contract: umbrella CLAUDE.md "Do not implement model training internals here" is violated by residence AND by active scheduling. Owner renquant-model. Size **L**; risk high specifically on the tournament chain (admission models = live buy gating).

### A6 — dual-home kernel: 57k LOC, drift growing despite the freeze decision [VERIFIED]
- `backtesting/renquant_104/kernel/`: 217 .py files / 57,040 LOC. Fresh diff today vs the sibling renquant-pipeline checkout (proxy for the pin; may run slightly ahead of it): **113 files differ, 43 umbrella-only, 29 pipeline-only** (C1 baseline 2026-07-04 vs pinned: 73 material-drift/49/21 — drift has GROWN in 6 days post-freeze-decision on either measure).
- What actually executes (reconciles agent-B's finding with the bridge): scheduled live runs go through `daily_104.sh:380-383` default → `renquant_orchestrator daily-bridge` → `live_bridge.bootstrap_multirepo` (`live_bridge.py:207-292`) which force-aliases `kernel.preflight`/`kernel.panel_pipeline` (+ per-stem aliases) to the **pinned pipeline**, silently falling back to umbrella per-module on import failure (#444 F-8). Sim, WF-gate sims, research entrypoints (`main.py`, `sim/runner.py`, `run_sim_104.py`, `production_runner.py`) `sys.path.insert` the strategy dir and run the **umbrella kernel wholesale**. Promotion evidence is generated by code live will not run (#444 F-3, P0, unresolved).
- Dispositions already decided in the C1 inventory (LIFT 42 / RETIRE 7 / DESIGN-PR 73); enforcement `scripts/check_mirror_drift.py` exists but is report-only (strict mode not enabled). The audit's delta finding: **the freeze is not holding** — e.g. `shadow_scoring.py` umbrella-ahead (+924/−128), `adapters/runner.py` still growing.

### A7 — umbrella-root `kernel/` trio: drifted twins of renquant-common [VERIFIED]
- `/Users/renhao/git/github/RenQuant/kernel/{hmm_regime_labels.py(172L), regime_labels.py(124L), walk_forward_splits.py(133L)}` are FULL implementations (not shims), md5-diverged from `renquant_common` counterparts (301/154/135L). renquant-common's copy self-documents the lift ("Lifted from umbrella kernel.regime_labels…").
- Split-brain importers: `scripts/patchtst_doe_hf.py`, `xgb_baseline_cut.py`, `eval_xgb_5cut_5seed.py` etc. import the umbrella copy; `scripts/run_wf_gate.py`, `patchtst_doe_sweep.py` import `renquant_common.*`. Same eval names, two drifted impls → non-comparable research numbers (#444 F-13 class). No production runtime importers.
- Fix: delete umbrella trio, repoint the 7 research scripts at renquant-common. Size **S**, risk low.

### A8 — strategy-config drift + side-config sprawl [VERIFIED by diff, 2026-07-10]
- **DIVERGED and stale**: umbrella `backtesting/renquant_104/strategy_config.json` = 47,880 B vs pinned `renquant-strategy-104/configs/strategy_config.json` = 57,835 B. Keys only in pinned: `live, intraday_decisioning, decision_ledger, sleeve, sizing, bear_defensive_sleeve, sdl_skip_if_trailing_armed(+reason)`; only in umbrella: `tournament_shadow`; shared-but-differing: `ranking, regime, regime_params, risk, rotation, sector_map, watchlist`. (#444 F-7 additionally documented a primary-model flip — umbrella `hf_patchtst` vs pinned `xgb` — as of 07-04; `ranking` still differs today.)
- **Runtime is safe on the default path**: `daily-bridge` → `live_bridge._with_pinned_strategy_config` (live_bridge.py:86-106) rewrites argv to the PINNED config; `daily_104.sh:113-120` also resolves `PROD_STRATEGY_CONFIG` pinned-first with `RENQUANT_STRICT_SUBREPO_PATHS` fail-closed. The stale umbrella copy is loaded only by `RQ_DAILY_RUNNER=umbrella` rollback mode (`live/runner.py:1077,1100`), `run_sim_104.py`, and analysis scripts — i.e. the sim/eval and rollback legs read different policy than live.
- Sprawl: **72** `strategy_config*.json` files in the strategy dir (golden, shadow + ~68 sim/codex/whatif experiment snapshots), plus 7 `strategy_config.json.preview_backup_*` and `.pre-meta-label-deploy` baks [VERIFIED by ls]. Experiment side-configs belong in worktrees per the LONG ledger; policy belongs in renquant-strategy-104.
- Fix: sim/analysis entrypoints resolve the pinned config by default; delete or clearly demote the umbrella working copy; archive the sprawl. Size **M**, medium risk (silent wrong-policy evaluation, rollback-mode landmine).

### A9 — model store + artifacts inside the tree [VERIFIED sizes]
- `models/` 1.1 GB (per-ticker q-tables ~11 MB each, RF trees, policy metadata — the F-17 tournament output surface); `artifacts/` 6.8 GB including `artifacts/diagnostics/modal_sweep_*/bundle/subrepos/` = **full copies of renquant-model/common/pipeline/backtesting inside the umbrella tree**. `.gitignore` covers only narrow slices (staging/bak patterns).
- Universal Rule 4 violated at scale (#444 F-28/29/30 quantified ~1.46 GB tracked >1MB; the modal_sweep subrepo bundles are a NEW post-audit accretion). Owner: renquant-artifacts (manifests) + object store. Mechanical but must coordinate with backup jobs and the tournament writer.

### A10 — scheduled shell layer: orchestration policy in umbrella scripts [VERIFIED]
- `scripts/daily_104.sh` (647L) full breakdown: host glue — venv/log/notify `:29-102`, /tmp lock `:125-156`; pinned-runtime + strict-path resolution `:104-120`; NYSE holiday gate `:158-170`; live-checkout guard `:172-205`; pin-align preflight `:207-220`; config-drift guard `:222-252`; system-doctor `:254-266`; model smoke + stale-age alert `:268-328` (no inline retrain — moved to weekly 2026-05-09); LEAN export + backfill/metrics `:330-345`; live runner leg `:355-426` with bridge default `:380-384` (`--broker alpaca --once` at `:388`) and an inline WF-gate/preflight→sell-only FALLBACK DECISION parser `:396-419`; buy-blocked ntfy `:428-460`; audit jsonl + dashboard `:462-545`; news sentiment `:547-560`; shadow e2e (readonly-alpaca, shadow config) `:562-647`.
- Split: only ~120 lines are true host glue (env, lock, ntfy, launchd anchoring). The stage sequencing, gate/fallback policy (`:396-419`), drift/doctor/model-age gating and shadow-arm policy duplicate what `renquant_orchestrator` already implements (`daily.py` Validate/Train/RunRuntime/Execute/Backtest/PersistDailyRunBundle tasks; `live_bridge.main`; `cli.py daily-bridge/live-bridge`).
- **Migration path is already on record orchestrator-side**: `scheduled_jobs.py` registers `daily_live_runner_bridge` (`:274-292`) and `live_runner_bridge` (`:334-353`) with `migration_state="umbrella_bridge"` and `native_replacement_job_id="native_live_run_candidate"` + a `native_cutover_command`, while sibling jobs (weekly alpha158/patchtst retrains, apy/promote monitors) are already `migration_state="native_multirepo"` running `renquant-orchestrator run-job`. The daily/live legs are the not-yet-cut-over remainder.
- launchd layer: 18 plists in `scripts/launchd/`, ALL invoking umbrella `scripts/*.sh` (e.g. `com.renquant.daily104.plist` → `scripts/daily_104.sh` directly), none invoking native `renquant-orchestrator run-job` yet.
- Sibling chains with inline policy: `weekly_wf_promote.sh` (promote sequencing + fallbacks), `weekly_tournament_retrain.sh` (NO delegate branch — A5), `monthly_meta_label_retrain.sh:154-194` (inline acceptance thresholds + prod `mv` — #444 F-19), `monthly_calibrator_refresh.sh`.
- Size **M**, high sensitivity (it IS the daily run — cut over leg-by-leg to the native jobs already registered, behind the existing flags).

### A11 — direct broker mutation from scripts/ [VERIFIED per #444; spot-checked]
- `scripts/preopen_cancel_gate.py:367` cancels live orders via `TradingClient.cancel_order_by_id` with a fail-OPEN fallback default (`preopen_cancel_gate.sh:72-79`, strict only if `RQ_PREOPEN_GATE_STRICT=1`) — opposite of the fail-closed convention; execution-repo port exists (`renquant_execution/preopen_cancel_gate.py`).
- `scripts/execute_shadow_orders.py` — ad-hoc ManualExecutionPipeline submitting real Alpaca orders via SDK, bypassing `live/` brokers (dry-run default). Owner renquant-execution; size **S**; medium risk (order-cancelling path).

### A12 — run-bundle persistence implemented umbrella-side on the live leg [VERIFIED]
- `kernel/artifact_contract.py:318 build_run_bundle` called from `adapters/runner.py:1991,2054` — run bundle is the orchestrator's declared primary output (operating-model roles table + lock's own role string "daily orchestration + run bundles") yet the LIVE-path implementation is an umbrella-only kernel module (C1 disposition: LIFT).
- The orchestrator-side machinery already exists (`daily.py::PersistDailyRunBundleTask` at `:223`, `native_live_bundle.py`, `bridge_live_bundle.py`, `model_bundle.py`) — the live trading leg simply doesn't route through it yet; it persists via the umbrella impl inside `RunnerAdapter.commit`. Migrates together with A1/A10 native cutover. Size **M**.

### A14 — live mutable state + stray root DBs in the umbrella tree [VERIFIED; producer of strays = GUESS]
- `backtesting/renquant_104/live_state.alpaca.json` (mtime today) is the live portfolio/HWM/regime state, written via pipeline `state_paths.live_state_path`; orchestrator's `live_state_v2.py:3` self-describes as "Replaces the flat, untyped live_state.alpaca.json" — the schema owner is orchestrator/pipeline while the file and its v1 writers sit in the umbrella tree. Anchor location (umbrella state root) is by design (`RENQUANT_STRICT_SUBREPO_PATHS` keeps state umbrella-anchored); the WRITERS should move with A1/A4.
- Stray root-level empties: `/Users/renhao/git/github/RenQuant/runs.alpaca.db` (0 B) and `score_db.sqlite` (0 B, 07-07) — canonical stores live under `data/` (`data/runs.alpaca.db` 106 MB etc.); the strays look like a CWD-relative path-resolution bug in some invocation [GUESS on producer]. Hygiene sharp edge: **`score_db.sqlite` is NOT gitignored** (`.gitignore` has `*.db`/`*.db-journal` but no `*.sqlite`), so the stray is add-eligible at the repo root. Size **S**.

### A13 — rust/ scorer workspace [VERIFIED]
- `rust/transformer_scorer*`: scaffolded Rust port of the panel transformer scorer; README declares "no Python pipeline depends on this Rust workspace yet"; import hooks exist at umbrella `kernel/panel_pipeline/panel_scorer.py:289,300` (`TransformerPanelScorer`). Model-inference code parked in the umbrella; if it graduates it should land in renquant-model/pipeline, not here. Size **M** if activated, none today.

---

## 2. Duplication census (single-source-of-truth breaks tied to the umbrella)

Carried from #444 §2 (re-confirmed unresolved unless noted):
- `model_content_sha256` ×4 (umbrella `kernel/panel_pipeline/panel_scorer.py:43,88,108` = stale local copy feeding the PRODUCTION calibrator fit + WF stamping) — F-10, P0.
- `fingerprint_config` fork: umbrella `kernel/config_consistency.py` hand-rolled vs pipeline's `renquant_common` import — F-11, P0.
- `WalkForwardModelLoader` ×3 (backtesting stamp leg / umbrella sim leg 12-char fuzzy / pipeline M6 dispatch) — F-2, P0; campaign B1 in flight.
- `kernel/execution/*` fill/eps semantics forked (`int(intent.shares)` umbrella vs `resolve_fill_quantity` pipeline) — F-12.
- NYSE calendar ×6 → planned `renquant_common.market_calendar` (campaign B5).
- Triple-barrier ×2, `artifact_resolver` hand-mirror, `ZoneInfo` re-derivations ×3 — F-15/F-14/F-16.
- NEW (this audit): umbrella `live/paper_broker.py` reverse-drift (Z9 stop-sim only umbrella-side) and `live/agent_breaker.py` (G2 order-admission caps) exist ONLY umbrella-side — protective features that will be LOST on naive cutover to the execution stack; must be lifted first.

## 3. Correctly umbrella-owned (do NOT migrate) [all VERIFIED]

- **`subrepos.lock.json`** (104L): pins all 9 subrepos with `name/role/local_path/remote/branch/commit/test_command/status` + `source_repo` marked `never_delete: true`. The 4 root `subrepos.lock.json.promote-bak.*` files are pre-bump rollback snapshots written by `promote_pin.backup_lock` — the rollback history working as designed.
- **`scripts/promote_pin.py`** (241L): atomic pin bump/revert — backs up lock (`:120-123`), atomic `os.replace` (`:113-117`), re-materializes runtime root (`:131-134`), runs a "still-buys" verify guard (`check_conviction_admits.py`, `:214-218`), AUTO-REVERTS on sync/verify failure (`:199-204`). Exemplary umbrella glue.
- **`scripts/subrepo_assemble.py`** (202L): deterministic assembly (`manifest.json`/`pythonpath.txt`/`env.sh`), `--runtime-root --sync` clones pinned repos into `.subrepo_runtime/repos` and emits `RENQUANT_STRICT_SUBREPO_PATHS=1` + `RENQUANT_OPS_FAIL_CLOSED=1` (`:145-150`). `.subrepo_assembly/` (~60 timestamped dirs + current.env) and `.subrepo_runtime/repos/` (9 pinned clones) both live on disk as designed.
- **`scripts/subrepo_doctor.py`** (105L) + **`sync_subrepo_docs.py`** (123L, lock → RENQUANT_REPOS.md single-source generator with `--check` drift gate); Makefile targets `subrepo-{doctor,test,assemble,smoke,runtime-root,daily-contract,ops-contract}`.
- **`scripts/daily_multirepo.py` / `live_multirepo.py`** (72L each): pure thin shims delegating to `renquant_orchestrator.live_bridge.main(mode=…)` — the compliant delegation pattern the rest of the shell layer should converge to.
- **`dagster_renquant/`** — NOT a competing orchestrator: validate-only asset graph ("Side-by-side with launchd (NOT a replacement)"); encodes cron-tier dependencies so the `RQ_ALLOW_NO_WF=1` promote bypass is structurally un-runnable. Keep.
- **`data/`** as the canonical gitignored data store (`/data/*` in .gitignore) — explicitly the umbrella's role per the operating-model roles table; the real runs DBs live under `data/` (`data/runs.alpaca.db` 106 MB etc.). Live mutable state anchored in the umbrella (`RENQUANT_STRICT_SUBREPO_PATHS` keeps state/artifact paths umbrella-anchored) — the ANCHOR stays; only the writers move (A14).
- `doc/arch/*` cross-repo canon (single documentation home per RENQUANT_REPOS.md); launchd plist wiring + `.env` (machine-local); `tests/` integration harness; ~120 lines of true host glue inside `daily_104.sh` (env, lock, ntfy, holiday short-circuit, live-checkout guard).
- `live/stream_watchdog.py` (read-only observability, hard no-TradingClient invariant) and `live/clock.py` — low-priority; clock is a candidate for renquant-common eventually but is glue, not business logic.

## 4. Migration sequencing recommendation (aligned with the on-record campaign)

1. **Defensive `place_notional_order` override in umbrella wrapper** (issue #456, S, no new capability) — closes the latent shadow foot-gun while migration proceeds.
2. Finish the campaign in-flight legs: fingerprint unification (B1/B2), sim/WF-gate onto pinned pipeline (F-3) — these de-risk everything else.
3. Enable `check_mirror_drift.py --strict` — the freeze decision is currently unenforced and drift GREW since 07-04.
4. Adapter-migration program (A1/A2/A4): lift umbrella-only protective features (paper Z9-sim, agent_breaker G2) into execution FIRST, then cut RunnerAdapter dispatch over to the execution `BrokerPort` seam, leg-by-leg with behavior-invariance pins (the #454 pattern).
5. Tournament chain (A5/F-17): delegate + gate before any model-code relocation.
6. Cut the daily/live launchd legs over to the natively-registered orchestrator jobs (`scheduled_jobs.py` already carries `native_replacement_job_id="native_live_run_candidate"` + cutover commands) — this collapses most of A10 and A12 without new design.
7. Mechanical hygiene: A8 config default + sprawl archive, A7 root-kernel trio, A9 data-in-git untrack, A11 script mutations, A14 stray DBs + `*.sqlite` gitignore.

## 5. Verification legend

Every [VERIFIED] above = file read / grep / ls / md5 or GitHub API record fetched during this audit (2026-07-10). Items citing #444 findings were re-confirmed current unless explicitly marked as historical. [GUESS] items: none load-bearing; agent-B's "tracked-in-git" inference for A9 relies on .gitignore inspection only (no git commands run, per audit constraints) — #444's D6 scan independently confirmed ~1.46 GB tracked as of 07-04.
