# GOAL-3 Architecture Audit — Cluster D: renquant-orchestrator + renquant-strategy-104

Date: 2026-07-01. READ-ONLY audit. Contracts: `RenQuant/doc/arch/subrepo-operating-model.md`,
orchestrator `CLAUDE.md` hard boundaries, strategy-104 `CLAUDE.md`/`README.md`.
Strategy repos in scope per `RENQUANT_REPOS.md`: only `renquant-strategy-104` (no other strategy repo exists).
Method: 4 parallel deep-explore passes + direct verification of the sharpest claims. Tags: [VERIFIED] = code read at cited lines.

## Bottom line

No live-today hard violation of the orchestrator's three "do not implement" boundaries — training
delegates to renquant-model pins, order submission goes through `renquant_execution` ports, and no
ML library is imported in `src/` [VERIFIED]. The real findings are: (1) a cluster of **latent,
shadow-gated kernel-logic modules** growing inside the orchestrator (sizing, entry-timing policy,
execution control loop, duplicated pipeline gates); (2) **`parking_sleeve` implemented 3× across 3
repos** with divergent formulas — the strategy-104 copy is orphaned kernel code in a config-only
repo; (3) the **live/daily bridge is fail-open by default on subrepo pin drift** and its run bundle
is flag-gated, and the **native-live path has no fingerprint gate at all** — both against the
CLAUDE.md "never silently continue without fingerprints / persist a run bundle per full run"; (4)
the umbrella at `/Users/renhao/git/github/RenQuant` is load-bearing in 4 distinct ways (pin
manifest, test venv, launchd job paths, one umbrella-code import in the retrain path); (5)
active==golden IS mechanically tested (CI) — but unknown config keys are silently ignored
everywhere, 5 top-level keys are dead, and the big silent-default surface (100+ keys) lives in the
pipeline kernel; (6) the progress-doc gate is the ONLY mechanically-enforced discipline item —
memory-tier updates are pure honor-system (Codex LLM review).

---

## 1. Orchestrator `src/renquant_orchestrator/` — kernel-logic inventory [VERIFIED]

Structural hygiene: zero `xgboost`/`lightgbm`/`torch`/`sklearn` imports in `src/`;
`renquant_common` Task/Job/Pipeline used in 36 places (genuinely, not decoratively);
subrepo kernels are imported/subprocessed, never re-implemented
(`renquant_execution` ×11, `renquant_pipeline` ×8, `renquant_artifacts` ×6, `renquant_model_gbdt` ×3,
PatchTST/alpha158 via subprocess).

### Training modules — CLEAN (delegate to renquant-model pins)
| Module | Verdict | Evidence |
|---|---|---|
| `train_gbdt.py` | OK | Pipeline of pinned `renquant_model_gbdt` tasks (`train_gbdt.py:99-105,236-241`); no local booster math. Exception: `SentimentGateTask` (`:119-142`) imports umbrella `scripts.train_production_model.apply_sentiment_training_gate` (`:126`) — umbrella CODE bridge, see §2. |
| `retrain_patchtst.py` | OK | subprocess into `renquant_model_patchtst.hf_trainer`/`fit_calibrator` (`:269,:298`). |
| `retrain_alpha158_fund.py` (1693 L) | OK | all `run()` → `run_subprocess`; calibrator delegates to `renquant_model_gbdt.fit_calibrator_alpha158_fund` (`:1352`). |
| `retrain_alpha158_linear.py` | OK | subprocess into `renquant_model_alpha158_linear.trainer` (`:103`) + `.calibrator` (`:127`). |
| `retrain_common.py` | OK | multi-pin PYTHONPATH + subprocess helper (`:63-73`). But default fail-open on missing subrepo src (see §6). |

### Latent violations (all currently shadow/dark-gated — none live)
| # | Module:line | Contract broken | Target owner | Size | Risk |
|---|---|---|---|---|---|
| V1 | `parking_sleeve.py:123-176` — `compute_sleeve_allocation` β-budget SPY/SGOV **sizing decision** (`spy_frac = min(1, beta_headroom/(w_sleeve*beta_spy))` `:146-152`, BEAR override `:139-144`) | "No signal/decision tree internals" + "never duplicate across repos" (3rd copy of this logic, see §3) | renquant-pipeline (canonical copy already exists there: `task_parking_sleeve.py`) | M | Low today (observe-only, `:14-16`); high drift risk — 3 divergent formulas |
| V2 | `entry_timing_policy.py:1,:12-33` — entry-timing decision-policy family (SUBMIT-NOW vs WAIT; `delay_fixed`, `gap_reversion_trigger`) | decision logic authored in orchestrator | renquant-pipeline `intraday_decisioning` when it goes Stage-2 (module self-declares "NO live wiring exists here" `:44-49`) | M | Low now; becomes a violation the day Stage-2 wires it live from here |
| V3 | `intraday_live_executor.py` (1954 L) — live order-submission control loop (`self.port.submit_order` `:1436`, cancel `:1493`, canary loss budget, entry cap, dead-man switch, restart reconciliation) | scope: execution-engine control logic belongs in renquant-execution. NOT a broker-adapter violation — port is injected, real impl = `renquant_execution.alpaca_broker_port.AlpacaBrokerPort` (`:89-115,:149-159`) [VERIFIED directly] | renquant-execution (the control loop) | L | Dark/unarmable today (needs `RENQUANT_INTRADAY_LIVE=1` + auth file + §9.4 gate that doesn't exist yet); largest single migration in this cluster |
| V4 | `tournament_shadow_admission.py:113-150` — `_tournament_would_admit` re-implements pipeline `ScoreBuyTask` + `ScoreThresholdTask` gate locally instead of importing | duplicated pipeline gate (drift-by-construction — same failure class as the triple-impl fingerprint bug) | renquant-pipeline (import the gate) | S | Med — a shadow readout that can silently diverge from the real gate |
| V5 | `sign_laundering_harness.py:36+` — re-implements calibrator neutral-raw zero-crossing rule; docstring admits it must "match `renquant_pipeline.kernel.panel_pipeline.global_calibrator` exactly" (`:37-41`) | duplicated kernel primitive | renquant-pipeline (export + import) | S | Med — same drift class as V4 |
| V6 | `intraday_session_inputs.py:462` — constructs `alpaca.trading.client.TradingClient` directly (`get_account`/`get_all_positions` `:475-478`) [VERIFIED directly] | "Do not implement broker adapters here" — read-only, documented never-submit (`:440-449`), but broker-SDK integration bypassing `renquant_execution.get_broker` | renquant-execution (read-only broker port) | S | Low (GET-only, no order path structurally) |
| V7 | `intraday_quote_logger.py:214,229-230` — direct `alpaca.data.historical.StockHistoricalDataClient` | market-data SDK in orchestrator; belongs behind a data port | renquant-base-data / execution data port | S/M | Low |
| V8 | `software_stop.py:118-182` + `gtc_catastrophe_planner.py:44-47+` — locally-authored stop-exit rule and GTC catastrophe-stop plan generation | execution risk overlays authored here (shadow-only, never talk to broker) | renquant-execution | S each | Low |
| V9 | `intraday_governors.py` turnover cap / post-loss cooldown | borderline risk-policy in orchestrator (self-declares pure control-plane `:39-41`) | keep or renquant-execution risk | S/M | Low |

### Scope creep (not a boundary breach, but undeclared role)
`agent_automation_poller.py` (2275 L — largest module in the repo), `agent_workflows.py`,
`roadmap_driver.py`, `repos.py` form an **agent/PR control-plane** that is nowhere in the declared
"Repo Role" (pinned-subrepo daily orchestration). Operator-established ("orchestrator is the
control panel") but the CLAUDE.md Repo Role should be amended to declare it, or it will look like
creep to every future audit. [VERIFIED — read docstrings; poller is deliberately merge-walled and
credential-free.]

### `scripts/` research-code placement — NO policy exists [VERIFIED]
~62 top-level scripts + `experiments/` (10) + `engineering/` (~25 prototypes). No stated rule
places research code; CLAUDE.md hard boundaries target `src/` only. 9 scripts fit/score models
locally with sklearn/xgboost/torch (`s9_track_a_conditional.py:206`, `m8_cluster_wave1.py:431`,
`m8_independent_verification.py:112`, `msig_c4_trendscan.py:178,500`, `d3_core_shrink_check.py:168`,
`diagnose_raw_jump_0626.py:252,272`, `experiments/2026-06-23-residual-audit.py:30`,
`experiments/2026-06-23-trendscan-label-shuffle.py:34`, `experiments/score_dead_window_pit.py:8`) —
exactly the research the repo map assigns to renquant-model (the MODEL FACTORY). Permissible under
current (absent) policy; recommend a written rule: research scripts → renquant-model or dated
`scripts/experiments/`, with a lifecycle (graduate-or-delete). Production-path writes: effectively
none — scripts write under `--out`/`--evidence` only; sole flag-worthy case
`generate_strategy_snapshot.py:92` writes repo `data/strategy_snapshot.json` behind an explicit
`--update` flag (diagnostic baseline, not an enumerated §2 path).

---

## 2. Orchestrator ↔ umbrella coupling — the umbrella IS load-bearing [VERIFIED]

Note the doc tension first: `subrepo-operating-model.md` declares the umbrella **permanent**
("integration harness + canonical data store"), while the offboard modules
(`live_offboard_status.py`, `live_offboard_rehearsal.py`) and `runtime_paths.default_data_root`
(RENQUANT_DATA_ROOT decoupling, `runtime_paths.py:53-71`) encode a migration OFF it. Both can't be
the end-state; the contract doc should say which.

Hardcoded `/Users/renhao/git/github/RenQuant` in `src/` (grepped whole tree):
| Location | Coupling | Severity |
|---|---|---|
| `repos.py:33` `DEFAULT_MANIFEST = /Users/renhao/git/github/RenQuant/subrepos.lock.json` | umbrella = pin-manifest source for the whole control plane | By-design (umbrella owns pins) but hardcoded absolute path — env-override missing |
| `scheduled_jobs.py:13` `CANONICAL_REPO_ROOT`; `:78-79,98-99,116-117,320-321` launchd stdout/stderr log paths under umbrella `logs/`; `:309,369` `backtesting/renquant_104`; `:311,371` `data/runs.alpaca.db` | production launchd job definitions pin umbrella dirs for logs, run DB, backtest root | HIGH — daily production jobs break if umbrella moves; this file is the single biggest umbrella anchor (13 occurrences) |
| `train_gbdt.py:126` imports umbrella `scripts.train_production_model.apply_sentiment_training_gate` | umbrella **code** on the retrain path (only umbrella-code import in src/) | MED — the one place umbrella source is executable-load-bearing; explicit "temporary bridge" |
| `cli.py:604` | help-text default umbrella root | trivial |
| `Makefile:1-5` `PYTHON ?= ../RenQuant/.venv/bin/python` | umbrella venv is the default interpreter for `make test`/`doctor` | MED — dev/CI-local only, but "make test" quietly depends on umbrella existing |
| `Makefile:6-18` PYTHONPATH = sibling working checkouts (`../renquant-*/src`), not pinned SHAs | test-time assembly ≠ pinned assembly ("merged is not deployed" root cause) | MED — known, documented in memory; note it is the sanctioned dev fallback |
| `runtime_paths.py:46-50` `default_repo_root() = github_root/"RenQuant"` fallback; `state_backup.py` `DEFAULT_REPO_ROOT = default_data_root()` | umbrella as data/state root fallback — but env-overridable (`RENQUANT_DATA_ROOT`, `RENQUANT_REPO_ROOT`) | LOW — this is the CORRECT migration pattern; adoption partial |
| ~40 `scripts/*` files (see grep counts: `d3_core_shrink_check.py` ×6, `m3_haircut_replay.py` ×4, poc_*/research_*/s*/m8* ×1-3 each) | research scripts read umbrella `data/` directly | LOW individually; collectively they make umbrella `data/` the de-facto research data lake |

Migration verdict: making the orchestrator umbrella-free = (a) move launchd log/DB/backtest paths
behind `runtime_paths` env resolution (S), (b) port `apply_sentiment_training_gate` into
renquant-model or pipeline (S), (c) own venv (S), (d) pins-not-siblings test assembly (M),
(e) research data root env (S). The pin manifest itself staying in the umbrella is consistent with
the operating model.

---

## 3. renquant-strategy-104 [VERIFIED]

Self-declared boundary (CLAUDE.md L14-22): "It is a config repo, not an implementation repo …
Do not add model training code, **runtime decision-tree implementation**, broker execution, QP
solver internals, raw data, or model checkpoints."

`src/renquant_strategy_104/` = 4 files, 525 lines total:
| File | Verdict |
|---|---|
| `config.py` (98 L) | POLICY-OK — schema validation/loader + fingerprint manifest, fail-closed `ValueError`s |
| `config_drift.py` (194 L) | POLICY-OK — golden-vs-active drift CLI (but unwired, see §4) |
| `__init__.py` | POLICY-OK — exports only `load_strategy_config, strategy_manifest` |
| `parking_sleeve.py` (227 L) | **KERNEL-VIOLATION + orphan** |

`parking_sleeve.py`: `compute_sleeve_allocation()` (L110-205) computes deployable cash after
reserve (L158-159), exposure-cap headroom (L161-163), SPY/SGOV split (L172-176), whole-share
counts/notional (L181-188), BEAR gate (L144-149) — runtime sizing, exactly what its own CLAUDE.md
forbids. **Zero importers anywhere** in `/Users/renhao/git/github/` outside its own test; not
exported by `__init__.py`; external repos import only `load_strategy_config, strategy_manifest`
(via orchestrator `contract_fixture.py:14`).

**Triple implementation** of the sleeve (breaks "never duplicate across repos"):
- A. strategy-104 `parking_sleeve.py` — fraction-based (`spy_fraction`/`max_sleeve_pct`) — orphan.
- B. orchestrator `parking_sleeve.py:123-176` — β-budget variant — shadow-only (V1 above).
- C. renquant-pipeline `kernel/pipeline/task_parking_sleeve.py:191` `ParkingSleeveShadowTask` —
  β-budget, **the actual live runtime consumer** (invoked from `pp_inference.py:584-585`), reads the
  strategy config `sleeve` block keys.
A's schema matches neither the config keys the runtime reads nor B/C's formula — a third drifting
variant. Remediation: **delete A + its 415-line test** (size S — nothing to port; C is canonical),
then fold B into C when the shadow graduates (M).

`configs/`: 4 files; active = `strategy_config.json` (1328 L), plus golden/shadow +
`xgb_prod_artifact_manifest.json`. No embedded executable logic (eval/lambda greps: only numeric
hyperparams + provenance prose). The `sleeve` config block (active L402-414, `enabled:false`,
`mode:"shadow"`) is lockstep across all three files and pinned by
`test_parking_sleeve_keys_are_explicit_inert_and_shadow_only` (`test_strategy_configs.py:381`) —
this is the CORRECT policy/kernel split. Training scripts: none exist (correct; no established
strategy-local training surface).

---

## 4. Config governance [VERIFIED]

**active==golden semantic match: MECHANICALLY TESTED, not convention.**
- Contract A (active==golden exact match): `renquant-strategy-104/tests/test_strategy_configs.py:40`
  `test_active_and_golden_semantic_config_match` — strips `_`-provenance keys (`:567`), pops
  `walkforward`, asserts full dict equality (`:58`). Runs on every push/PR via strategy-104
  `ci.yml` → `make test` (`Makefile:7-8`, whole tests dir). Reinforced by closed-set pin tests
  (slots `:61`, conviction `:101`, Kelly `:309`, max-hold `:346`, sleeve `:381`).
- Contract B (active config == model's training config): `renquant-common
  config_consistency.fingerprint_config` (`:104`) / `assert_consistent` (`:116`, raises
  `ConfigModelMismatch`; strict fails closed on missing stamp `:146-147`); enforced at RUNTIME in
  pipeline preflight (`kernel/preflight.py:812-820`,
  `preflight_pipeline/tasks/config_fingerprint.py:76-85`) and scoring
  (`job_panel_scoring.py:895-905`); enforced in CI by orchestrator `bundle-consistency.yml` →
  `scripts/check_model_bundle_consistency.py:88-90`.
- Gap: the tolerance-based `config_drift.py` CLI is wired into NO CI job or Makefile target; its
  test only runs on synthetic tmp configs. Manual-only.

**Declared-but-dead keys** (0 readers across all renquant-*/src + scripts; 26 top-level keys sampled of 70):
`train_split` (`strategy_config.json:177`), `volume_zscore_lookback` (`:178`), `volume_filter`
(`:179-182`), `training_years` (`:183`), `inference_frame_cache` (`:190-193`). (`model_name` looked
dead but is a required Pydantic field + read in backtesting `analyze_backtest.py:440`.)

**Silent-default readers** (key defaulted in code, absent from every config): the orchestrator's
load-bearing modules (daily/live_bridge/native_live_run/intraday_session_runner) barely do this —
they validate a typed subset and pass the config through. The 100+-key silent-default surface is in
the **pipeline kernel** (cluster-D-adjacent, flag for cluster owning pipeline): σ-adaptive stop
family entirely default-off (`kernel/exits.py:871,877,881,884,920`), fingerprint-gate strictness
itself a silent default (`job_panel_scoring.py:893` `strict_config_consistency, True`), IC sanity
floor (`:2128,2132`), wash-sale tax/discount rates (`task_candidates.py:48-49`), `seq_len`
(`model_registry.py:127`). Orchestrator-local: `gate_calibration_diagnostic.py:183-193` reads
top-level `conviction_gate`/`rotation_gate`/`veto` but the real gates live under
`ranking.panel_scoring` → this diagnostic silently extracts no gates from a real config (latent bug,
offline path).

**Unknown-key rejection: NONE — silently ignored everywhere.** strategy-104 loader checks only
required keys (`config.py:20-47`); orchestrator `config_schema.py:39` `extra="allow"` (docstring:
untyped keys "counted as telemetry"); `daily.py:71-89` warn-only, only present-but-invalid typed
values raise; pipeline `kernel/config_schema.py` `extra="allow"`, default `mode="warn"`. Tests
assert the OPPOSITE of rejection (`test_config_schema.py:41-45,87-91` — extras accepted/preserved).
Only two closed-set assertions exist, both in strategy-104 TESTS not the loader:
`test_strategy_configs.py:463-472` (intraday_decisioning) and `:517` (fingerprint block). A typo'd
gate key anywhere else silently does nothing — this plus the 5 dead keys is the config-rot vector.

---

## 5. doc/progress + memory-tier discipline: mostly honor-system [VERIFIED]

| Discipline item | Status | Mechanism |
|---|---|---|
| PR carries `doc/progress/<date>-<slug>.md` | **MECHANICAL** | `.github/workflows/require-progress-doc.yml:24` → `scripts/require_progress_doc.py` (filename regex `:17` only — content unchecked) on every PR event |
| Tests | MECHANICAL | `ci.yml` (full multirepo `make test` when token present, else 3-file subset `:80-93`) |
| Bundle/fingerprint consistency on PR | MECHANICAL (partial) | `bundle-consistency.yml`, path-filtered; sequence scorers (.pt/patchtst) short-circuit `deploy_ready=True, skipped=True` (`check_model_bundle_consistency.py:78-80`) |
| No self-merge / peer approval | MECHANICAL (config external) | `CODEOWNERS:11` `* @hallovorld @haorensjtu-dev`; branch-protection state itself not verifiable from repo [GUESS on live setting] |
| Memory-tier updates (LONG/MID/SHORT) | **HONOR-SYSTEM** | No linter/CI/hook anywhere; `doc/memory/README.md:22` says so explicitly ("Enforcement is external (Codex review per PR)"); SHORT tier is gitignored (`.gitignore:9`) so structurally uncheckable |
| No pre-commit / .claude hooks | — | no `.pre-commit-config.yaml`, no `.githooks`, `.claude/settings.local.json` has permissions only, no hooks |

The CLAUDE.md's own warning ("prompt, NOT enforcement") is accurate: exactly one of the four
"non-negotiable behaviours" (progress doc) has a mechanical backstop, and it's filename-presence only.

---

## 6. Fingerprint gates — "never silently continue without fingerprints" [VERIFIED]

Two fingerprint concepts: CONTENT (config/data/artifact sha) and PIN (subrepo git HEAD vs lock).

Fail-open list, ranked:
| # | Sev | Location | Behavior | Contract broken |
|---|---|---|---|---|
| F1 | HIGH | `runtime_paths.py:216-238` `enforce_or_warn`, invoked `live_bridge.py:254` | the scheduled LIVE/daily production bridge continues on missing/mismatched/dirty subrepo PIN with a stderr warning; fail-closed only with opt-in env (`RENQUANT_STRICT_SUBREPO_PINS`/`RENQUANT_OPS_FAIL_CLOSED`/`RENQUANT_STRICT_SUBREPO_CLEAN`) | "Do not silently continue without …artifact fingerprints" (pin = which code/artifact version runs). Fix: flip default to strict on the scheduled entrypoints (S; needs a soak to avoid breaking daily) |
| F2 | HIGH | `live_bridge.py:310-311,342-350` | bridge run bundle only written if `--bridge-bundle-output` passed — a full live.runner run can persist NO bundle | "Persist a run bundle for every full run". Fix: make it default-on (S) |
| F3 | MED | `native_live_run.py` (whole module; grep fingerprint/sha256 = 0 hits) | native live candidate path has no strategy/data/artifact fingerprint presence-or-match check; trusts upstream payload; bundle write unconditional (`:329`) | same contract; the native path is the offboard future — gate should be built before it takes over (M) |
| F4 | MED | `retrain_common.py:49-52`, `retrain_patchtst.py:143` | missing subrepo src paths only raise under `RENQUANT_STRICT_SUBREPO_PATHS==1`; else prepended to PYTHONPATH and retrain continues | silent-continue on assembly integrity (S) |
| F5 | LOW | `live_bridge.py:270-275` non-critical kernel alias `except: continue` (4 critical modules DO raise `:280-291`); `bridge_live_bundle.py:80-85` + `native_live_bundle.py:92-99` synthetic no-rows audit entries | benign softs | — |
| F6 | INFO | `daily.py:90-95` | fingerprint gate is presence-only (raises on missing, doesn't content-match — match is downstream in pipeline preflight + offline CI) | acceptable layering, worth documenting |
| F7 | INFO | `check_model_bundle_consistency.py:78-80` | sequence scorers skip JSON-artifact contracts by design | scoped |

Fail-closed (credit): `daily.py:90-95` + terminal `PersistDailyRunBundleTask` (`:223-265`, raises or
writes — bundle unconditional on success); `intraday_session_runner.py:208-241` §9.4 gate returns
fail-closed-to-shadow on missing file AND on any exception, `:432-471` refuses live without port /
raises on paper-mode misuse; `artifact_resolver.py:97-99`; `model_bundle.py:104-108,239-240`
(promote refuses unless deploy_ready); `check_model_bundle_consistency.py:156` exit 1.
Caveat: the only in-repo caller of `DailyRunPipeline` is the `daily-contract` smoke fixture with
hardcoded `"sha256:smoke-data"`/`"sha256:smoke-model"` (`contract_fixture.py:23,62`, `cli.py:768-784`)
— the repo's exemplary fail-closed pipeline is exercised in-repo only by a fixture; the real daily
goes through the bridge (F1/F2 path).

---

## 7. Correct patterns worth preserving (the good list)

- `daily.py:11-16` — canonical stitch: imports each subrepo's Pipeline/Context, composes with
  `renquant_common.Pipeline`; fail-closed validation; terminal bundle persist.
- `native_execution_payload.py:9,36-37` — delegates to `renquant_execution`, structurally refuses
  non-dry-run. `native_live_run.py:9` delegates commit to `renquant_execution.build_live_commit_plan`.
- `native_live_inference.py:58-64` — delegates to `renquant_pipeline.run_native_inference_snapshot`,
  no umbrella import, no order path.
- `shadow_realtime_serving.py:11-17,526,541` — observe-only collector, loads pinned artifact
  read-only via `renquant_common.load_scorer`.
- `m6_restamp.py:34-38` — hash logic imports ONLY `renquant_common.model_fingerprint` (the direct
  fix for the triple-impl fingerprint bug — V4/V5 above are the same bug-class waiting to recur).
- `runtime_paths.py:53-71` — `RENQUANT_DATA_ROOT` first-class decoupling with umbrella fallback:
  the right umbrella-offboard pattern; extend it to `scheduled_jobs.py`.
- `intraday_live_executor.py:89-115` — broker adapter properly injected from `renquant_execution`,
  fake port in every test.
- strategy-104 `sleeve` config block + pipeline `ParkingSleeveShadowTask` — the correct
  policy(config-repo)/kernel(pipeline) split, pinned by a closed-set test.
- `repos.py:249-255` — cross-repo merge blast-radius gate (`--allow-all` + bounded `--max-merges`).
- strategy-104 configs are purely declarative; active/golden/shadow lockstep CI-pinned.

## 8. Consolidated remediation queue (owner → items, sized)

1. **renquant-strategy-104 (S):** delete `src/renquant_strategy_104/parking_sleeve.py` + `tests/test_parking_sleeve.py` (orphan kernel dup; pipeline task is canonical).
2. **renquant-orchestrator hardening (S each):** F1 flip pin-drift to strict-by-default on scheduled entrypoints; F2 default-on bridge bundle; F4 strict retrain paths; V4/V5 import pipeline gate/calibrator primitives instead of re-implementing; V6/V7 move Alpaca SDK reads behind execution/base-data ports; port umbrella `apply_sentiment_training_gate` out of `train_gbdt.py:126`; env-resolve `scheduled_jobs.py` umbrella paths.
3. **Medium:** F3 fingerprint gate for the native-live path (build before offboard flips); V1 fold orchestrator sleeve variant into the pipeline task; V2 move entry-timing policy into pipeline at Stage-2; config unknown-key detection (extend `extra_key_count` telemetry into a ratcheted CI warn→strict, plus delete the 5 dead keys); wire `config_drift` CLI into CI or delete it; amend CLAUDE.md Repo Role to declare the agent/PR control plane; write the scripts/ research-placement policy.
4. **Large:** V3 migrate the intraday live execution control loop into renquant-execution before §9.4 arming ever happens; pins-not-siblings test assembly.
