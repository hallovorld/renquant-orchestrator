# audit(arch): execution / common / model design-compliance findings

STATUS: findings memo for review — DOCS ONLY, no code change in this PR. Each finding
names a fix owner; fixes land as separate PRs in the owning repos.
DATE: 2026-07-04 (audit executed 2026-07-03).
SCOPE: deep design-compliance audit of `renquant-execution`, `renquant-common`,
`renquant-model` — the broker / primitives / factory boundaries (104 + 105 related) —
plus the cross-repo dimensions (version caps, import directions, hand-copied impls).
Placed in the orchestrator `doc/arch/` because the findings span repos.

## 0. Method and baseline

- Audited from **fresh clones at `origin/main`** in an isolated scratchpad (no git
  operation touched any primary checkout or the live tree). HEADs audited:
  execution `8fd788c` · common `74b728c` (0.9.2) · model `775804d` · pipeline `778983a`
  · backtesting `34fd4ed` · base-data `f3f17a1` · artifacts `c09d66f` · strategy-104
  `c5cd830` · orchestrator `6e0c972` · umbrella `79d47da`.
- Compliance baseline ("the charter"): umbrella `doc/arch/subrepo-operating-model.md`
  (repo roles + Universal Rules 1–6), each repo's `CLAUDE.md` + `renquant_repo.yml`,
  `RENQUANT_REPOS.md` cross-repo rules, the M6 fingerprint designs
  (`doc/design/2026-07-02-m6-fingerprint-unification.md` stage-1,
  `doc/design/2026-07-03-m6-stage2-fingerprint-migration.md` stage-2, step-0 executed
  2026-07-03), and the session rules (single-impl, flags default OFF, fail-loud
  fingerprints).
- Four audit lanes: execution repo, common repo, model factory, cross-repo
  (caps / import directions / duplicated impls). Every finding was verified against
  code at the cited file:line, not inferred from docs; load-bearing claims (both P0s,
  the factory stamping gap, the classification gap) were independently re-verified.

**Severity**: P0 = hard-rule violation with live/production-impact potential.
P1 = real design violation, currently contained. P2 = hygiene / doc drift /
contained duplication.

**Counts: 2 P0 · 13 P1 · 15 P2 (30 findings).**

## 1. Executive summary

1. **The execution repo contains a full discretionary trading strategy** (IGV short
   plan: entry signals, TP/SL thresholds, position management, launchd monitor) with
   live option-order capability that consumes no order intent from `renquant-pipeline`
   — a hard breach of the "broker execution + order audit ONLY" role (F1, P0).
2. **The walk-forward loader — fail-closed fingerprint verification on the
   `weekly_wf_promote` path — now exists as three divergent copies**: pipeline
   (migrated to M6 version dispatch), backtesting (266-line drift, retains 12-char
   prefix acceptance + venv-coupled recompute), and the umbrella copy, which is the
   one actually live via `run_wf_gate.py`. This is the exact triple-impl incident
   class M6 exists to kill, re-created around M6's own fix (F2, P0).
3. **The model factory is not yet the factory on the live path**: the umbrella script
   is still the production trainer, the two trainer lanes have already drifted in
   capability (#426 provenance stamping exists only umbrella-side), the factory
   publishes artifacts with no content fingerprint (Rule 5), and the
   `renquant-artifacts` registry is bypassed by the entire active path (F8–F11, P1).
4. **`renquant-common`'s v1 fingerprint API deviates from the reviewed stage-1 design**
   on exactly the properties designed to prevent the next incident: classification is
   top-level-only with one global table (no recursion, no family scoping), so nested
   predictive content is silently excluded from the hash (F5, P1).
5. Version caps are broadly sane post-0.9.x (no residual `<0.9` anywhere); the
   stragglers are execution (uncapped) and the orchestrator itself (floor too low for
   the shim surface its own M6 scripts import, all renquant deps uncapped) (F14, F17).

## 2. Findings — P0

| ID | Where | Finding | Rule violated | One-line fix | Fix owner |
|---|---|---|---|---|---|
| **F1** | renquant-execution `src/renquant_execution/igv_short_state.py` (whole module), `igv_short_monitor.py:94-262`, `configs/igv_short_plan.example.json`, `ops/launchd/com.renquant.igv-monitor.plist` | A complete discretionary strategy — price-structure entry signals (reject-zone / breakdown / failed-bounce), TP/SL thresholds, position management — lives in the execution repo and, when armed, places live option orders directly from market data with **no order intent from renquant-pipeline**, bypassing QP/gates/run-bundle | execution `CLAUDE.md` "do not decide alpha … or tune strategy thresholds"; `renquant_repo.yml` forbidden `alpha decision logic`; charter role "broker execution and order audit" | Move the plan state machine + monitor decision loop to renquant-pipeline (policy/config to strategy repo); execution keeps only `options_executor` broker mutations | execution → pipeline (+ strategy-104 for policy) |
| **F2** | renquant-backtesting `src/renquant_backtesting/walk_forward/loader.py` (266-line drift vs pipeline) + umbrella `backtesting/renquant_104/kernel/walk_forward/loader.py` (live via `scripts/run_wf_gate.py:2311`) | Three divergent copies of the fail-closed WF fingerprint verifier: pipeline's is M6-stage-2-migrated (schema-versioned dispatch, `accept_legacy_stamps`, no prefix matching); the backtesting fork retains legacy semantics — local `_normalize_fingerprint`/`_fingerprints_match` **with 12-char prefix acceptance**, bare `model_content_sha256` recompute lazy-imported from pipeline's `panel_scorer` (semantics-follows-venv, the pipeline#160 hazard), no version dispatch; the umbrella copy is the one the live gate imports, so the M6 migration is dark on `weekly_wf_promote` until re-point | single-impl session rule; M6 stage-2 §5 row 3 ("hash logic is imports only"); known M6 finding — status here: **DRIFTED, and a third copy is the live path** | Backtesting deletes its fork and re-exports pipeline's loader (dep already declared); umbrella re-points per the M6 stage-2 landing steps | backtesting (fork removal); umbrella re-point = M6 stage-2 landing (orchestrator-coordinated) |

Mitigations noted on F1 (why it is not an active incident): dry-run default,
`mode=paper`, `IGV_LIVE_ARMED=0`, kill-switch, plist is a do-NOT-auto-install
template. The placement is a hard-boundary breach with live-order capability
regardless — flags-OFF is a mitigation, not a compliance state.

## 3. Findings — P1

| ID | Where | Finding | Rule violated | One-line fix | Fix owner |
|---|---|---|---|---|---|
| **F3** | renquant-execution `alpaca_broker_port.py:14-22,94-141` | The slice-1 port's declared fractional seam was never closed: docstring still claims s-frac stage-1 (execution#22) is "not yet on main" (it merged, `8e2c61b`); `submit_order` passes `qty` through unvalidated while legacy `AlpacaBroker` preflights (`alpaca_broker.py:205,285`) — the newest live path (orchestrator Stage-2 executor → this port) bypasses the pinned Alpaca fractional rules, turning violations into broker HTTP 400s instead of classified no-submit results | S-FRAC design §4 fail-closed contract; single-impl | Wire `validate_fractional_order` + no-submit classification into `AlpacaBrokerPort.submit_order`; refresh the stale docstring | execution |
| **F4** | renquant-execution `preopen_cancel_gate.py:121-178` (yfinance ES→SPY fallback + sigma normalization), `igv_short_monitor.py:94-119` (direct Alpaca historical fetch) | Market-data acquisition + vendor-specific fallback logic inside the execution repo | charter Data Refresh: "API-specific fallback logic belongs in data materialization, not in model or execution repos" | Consume an orchestrator/base-data-provided snapshot; keep only cancel/submit actions in execution | execution + base-data |
| **F5** | renquant-common `src/renquant_common/model_fingerprint.py:25-31,165,223` | v1 ships **top-level-only classification, one global table, no artifact-family scoping** (`classify(payload, family=...)` from stage-1 §2a absent); `metadata` is OPERATIONAL as one atomic unit, so predictive content nested inside it is silently **excluded** from the hash — the false-MATCH class §2a explicitly warns against. Documented in-code as deferred scope, but a stage-4 cutover on this table would freeze the gap | M6 stage-1 §2a (recursive key-path tables + xgb/hf family split) | Land key-path recursion + family tables (with schema-version bump) BEFORE any stage-4 cutover | common (mechanism) + model (tables) |
| **F6** | renquant-common `src/renquant_common/calibrator_quality.py` ≡ renquant-model `src/renquant_model_common/calibrator_quality.py` | Byte-identical dual implementation, both docstrings claim "single source of truth", with live importers on BOTH sides (pipeline → common copy at `preflight.py:1663,1784`, `preflight_pipeline/tasks/calibrator.py:143,258`; model → own copy at `global_calibrator.py:22`, `fit_calibrator.py:22`, `fit_calibrator_alpha158_fund.py:23`) — acceptance-gate semantics drift silently on first divergence | single-impl; M6 stage-2 §5 row 3 (the hand-copy incident class) | renquant-model deletes its copy and imports `renquant_common.calibrator_quality` | model |
| **F7** | renquant-common `tests/api_snapshot/public_api.json` + `tests/test_api_snapshot.py:80` | Snapshot pins only top-level `__all__` (38 names); the `model_fingerprint` submodule surface — the fleet's most incident-hot contract, imported directly by pipeline/model — is NOT pinned. Empirically inadequate: 0.9.0 removed the 4 shim names pipeline imports, the snapshot test stayed green, the fleet broke → 0.9.1 restore | Universal Rule 6 ("main is the stable interface") | Extend the snapshot to enumerated submodule surfaces (at minimum `model_fingerprint`'s public names) | common |
| **F8** | umbrella `scripts/train_production_model.py:771,1134` + `scripts/train_walkforward_panel.py:63` (`TRAIN_PROD_SCRIPT`) | The umbrella is still the live production trainer: the WF-corpus/gate lane subprocess-trains the umbrella script, which builds and writes artifact JSON itself; the factory's `panel_trainer.py` exists only as a byte-parity mirror; **no cutover plan is recorded anywhere** (unified-107 master plan and `docs/source-map.md`: zero rows) | charter "renquant-model is THE factory"; RENQUANT_REPOS.md "never add code to the umbrella"; #210 §6 "umbrella scripts schedule and invoke, own no selection logic" | Record and execute cutover of the WF lane onto the factory engine (`renquant_orchestrator.train_gbdt` → factory `panel_trainer`); umbrella trainer becomes invoke-only | model + umbrella |
| **F9** | umbrella `scripts/train_production_model.py:55,967` vs renquant-model `panel_data.py` / `pipeline.py` | Trainer capability drift across the duplicated lanes: #426 (2026-07-02) added `stamp_provenance_schema` (recipe/schema stamped at training time; admission-relevant — `shadow_scoring._compute_admission` fail-closes on missing recipe stamps) to the UMBRELLA trainer only; factory `BuildArtifactTask`/`build_model_artifact` and orchestrator `train_gbdt.py` have none — factory-lane artifacts are not admission-equivalent | Rule 5; single-impl | Lift provenance stamping into the factory artifact builder; umbrella imports it | model |
| **F10** | renquant-model `src/renquant_model_gbdt/panel_data.py:228-245` (`StampFingerprintTask`) | The factory publishes artifacts with **no content fingerprint**: only `config_fingerprint` is stamped at build; `model_content_fingerprint` is absent → identity is recompute-on-read, the exact unstamped-artifact trap the M6 stage-2 census measured on every live artifact | Rule 5 (immutable fingerprints at promotion) | Stamp `model_content_fingerprint` (+ `fingerprint_schema_version` per stage-2) via renquant_common at artifact-write time; coordinate with M6 stage-2 steps 0/2 | model |
| **F11** | renquant-artifacts `registry/` (contains exactly one `example-artifact.json`); renquant-model `pipelines.py:10,16` (imports `validate_*` only, never publishes) | The registry is bypassed on the entire active path: live prod artifacts live in umbrella `data/` + `backtesting/renquant_104/artifacts/` (stage-2 census §1); the charter rows "produces models published to renquant-artifacts" / "consumed from renquant-artifacts" are unimplemented | charter repo roles; Rules 4/5 | Add a fingerprinted-manifest publish step to the promote chain; consumers resolve via the registry | model + artifacts + orchestrator |
| **F12** | renquant-backtesting `walk_forward/loader.py:352` + `analysis/smoke_test_model.py:193` | `from training_panel.global_calibrator import …` — the `training_panel` package exists only in umbrella `backtesting/renquant_104/`; a hidden umbrella-`sys.path` dependency | charter "LEAN must not silently import code from a developer-local random path"; Rule 3 | Import pipeline's `kernel/panel_pipeline/global_calibrator` instead | backtesting |
| **F13** | renquant-model `renquant_model_patchtst/training.py:59-60` (+ hand-rolled hashing `research_pipeline.py:666,1615-1646`) | Checkpoint-contract `fingerprint` computed locally via `json.dumps(..., default=str)` — the lossy 0.8.1 pattern v1 explicitly bans — instead of `renquant_common.model_fingerprint` | Rule 5; M6 stage-2 §5 row 3 (hash logic imports-only) | Stamp via common with an hf-family classification table (depends on F5) | model |
| **F14** | renquant-orchestrator `pyproject.toml:12-18` | `renquant-common>=0.8.0` floor too low — `scripts/prestamp_legacy_fingerprints.py` + `scripts/fingerprint_census.py` import the 0.9.1 shim surface — and all 8 renquant-* deps uncapped | Rule 6 / fleet cap discipline | `renquant-common>=0.9.1,<1.0`; cap the rest `<1.0` | orchestrator |
| **F15** | execution `broker.py:21` (`QTY_INTEGRAL_EPS=1e-9`, exported) vs execution `order_state_machine.py:76` (`_QTY_EPS=1e-9`, private copy) vs execution `live_persistence.py:173` (inline `1e-9`) vs orchestrator `execution_reconciler.py:92` (`_QTY_TOL=1e-6`) vs umbrella `adapters/runner.py:1209` (inline `1e-9`) | One quantity-epsilon concept, five sites, **one divergent value** (the orchestrator reconciler's `1e-6`) on the commit/reconcile path; partially mitigated by an equality tripwire (`test_order_state_machine.py:721-723`) | single-impl | Import `QTY_INTEGRAL_EPS` everywhere; if the reconciler's `1e-6` is deliberately looser, document it at the site | execution (+ orchestrator) |

## 4. Findings — P2

| ID | Where | Finding | Rule violated | One-line fix | Fix owner |
|---|---|---|---|---|---|
| **F16** | execution `order_state_machine.py:196-205` (`pi-<sha256:20>:<attempt_n>`) vs `options_executor.py:177,192` (`igv-open-…`/`igv-close-…`) vs `alpaca_broker.py:170-263` (`AlpacaBroker.place_order`: **no client_order_id at all**) | Three client-order-id conventions; the ACTIVE 104 daily path (umbrella `RunnerAdapter.commit` → `AlpacaBroker.place_order`) has no broker-side idempotency key | single-impl | Adopt the slice-1 `child_order_id` convention in `AlpacaBroker.place_order` (minimum: any deterministic client_order_id) | execution |
| **F17** | execution `pyproject.toml:11` + `renquant_repo.yml` | `renquant-common>=0.1.0` uncapped/stale floor; repo.yml declares a phantom `renquant-pipeline` dependency that exists in neither pyproject nor code | Rule 3; cap discipline | Pin `renquant-common>=0.9,<1.0`; drop the phantom dep or annotate it as data-contract-only | execution |
| **F18** | execution `ibkr_broker.py` (all methods `NotImplementedError`) exposed as mode `"ibkr"` in `factory.py:25` | An incomplete adapter in the audited broker-mode enum (contained: fail-loud on connect) | broker mode explicit + audited | Remove from the factory enum or mark experimental-only | execution |
| **F19** | execution `igv_short_monitor.py`, `preopen_cancel_gate.py` | Plain cron scripts, not Task/Job/Pipeline nor thin adapters, despite `renquant_repo.yml pipeline_required: true` (core order flow correctly uses `ExecutionJob`/`ExecutionPipeline`) | Universal Rule 1 | Wrap cron entrypoints as thin adapters over common primitives | execution |
| **F20** | common `model_fingerprint.py:240-253` + the two M6 design docs | 0.9.2 changed the classification table **without** a `FINGERPRINT_SCHEMA_VERSION` bump — contradicts stage-1 §2b's letter, while the stage-2 plan requires version stay 1 (hash-preserving, test-pinned); the docs conflict; §2b's independent table-vs-mechanism versioning is unimplemented (single constant) | M6 stage-1 §2b | Amend stage-1 design with the hash-preserving exception; split table/mechanism versions when family tables land (F5) | orchestrator docs + common |
| **F21** | common `src/renquant_common/registry/mlflow_registry.py` | MLflow registry wrapper with zero consumers fleet-wide, `mlflow` not declared even as optional dep (call-time ImportError), role overlap with renquant-artifacts | common CLAUDE.md (no artifact stores); charter (registry = renquant-artifacts) | Delete, or move to renquant-artifacts with an optional extra | common |
| **F22** | common `config_consistency.py:48`, `row_coverage.py:47`, `registry/mlflow_registry.py:30`, `metrics/__init__.py:1` | `logging.getLogger("kernel.*")` umbrella-lift remnants misattribute log records under name-based routing | hygiene (umbrella-lift residue) | Rename loggers to `renquant_common.*` | common |
| **F23** | model `panel_data.py:141-150` (`content_fingerprint()`, used at `:242`) | A hand-rolled ADDITIVE-allowlist hash survives as the config-fingerprint fallback; the name collides with the content-hash domain M6 just unified | M6 stage-2 §5 row 3 | Replace with the common API, or rename and explicitly scope to the config lane | model |
| **F24** | model `tests/gbdt/test_import_boundaries.py:10-17`; missing tests for `renquant_model_linear` + `renquant_model_alpha158_linear`; `renquant_repo.yml`/CLAUDE.md `owns` lists | GBDT boundary enforcement weaker than declared (forbidden set lacks `renquant_pipeline`/`renquant_backtesting`; no AST scan; no fresh-subprocess check — only the patchtst test has them); the two linear families have NO boundary tests; owns lists omit both new families | Rule 3; model CLAUDE.md porting contract | Extend the patchtst-style AST+subprocess check to all four families; refresh the owns lists | model |
| **F25** | model `tests/gbdt/test_model_content_sha256_cross_repo.py:28-52` + pyproject pythonpath + CI | Deliberate M6 is-identity fixture imports `renquant_pipeline` at test time while CLAUDE.md boundary 1 flatly forbids it — the test-only exception is unrecorded | Rule 3 (declared boundaries) | Document the test-only exception in CLAUDE.md (or move the fixture into pipeline) | model |
| **F26** | GitHub `renquant-model-gbdt` / `renquant-model-patchtst` | Both shells report `archived: false` — still pushable; nothing mechanically enforces "Do NOT work there" (contents verified untouched since the 2026-05-27 archival commits) | charter (ARCHIVED shells) | Mark both repos archived on GitHub | operator (repo admin) |
| **F27** | execution `alerts.py` (mature: retry+backoff+dedup) vs orchestrator `daily_trading_health.py:147` (bare urlopen, no retry) vs umbrella script-local `_ntfy` copies | ntfy notifier implemented ≥3 times | single-impl | Consumers adopt execution's `alerts` (execution owns notifications per its charter role) | execution |
| **F28** | model `oos_ic_export.py:214`, `sequence_training.py:436`, `research_pipeline.py:1615` | Whole-file sha256 re-implemented 3× while common exports `artifact_sha256` (`model_fingerprint.py:557`) | single-impl (mild: identical semantics) | Import `renquant_common`'s helper | model |
| **F29** | execution `preopen_cancel_gate.py:80,98`; 3 orchestrator modules; several umbrella scripts | NYSE-session/trading-calendar wrappers hand-rolled at ≥5 sites (same mcal pattern; no semantic divergence found) | single-impl (mild) | One `trading_session` helper in renquant-common | common |
| **F30** | pipeline `kernel/panel_pipeline/hf_patchtst_scorer.py:133` | Direct `renquant_model_patchtst.hf_trainer.HFPatchTSTRanker` import bypassing the `renquant_common.load_scorer` entry-point contract (openly declared in pipeline pyproject extras, so known but unsanctioned) | model CLAUDE.md boundary 3 ("consumers never import this package directly") | Route through the entry point, or record a sanctioned exception in model CLAUDE.md | pipeline (+ model CLAUDE.md) |

## 5. Cross-repo version-cap table (post-0.9.x fleet, at origin/main)

renquant-common at HEAD = **0.9.2**. No residual `<0.9` caps anywhere; no cap blocks
the planned 0.10 shim removal (`<1.0` admits 0.10).

| Repo | Version | renquant-* dep | Constraint | Verdict |
|---|---|---|---|---|
| renquant-execution | 0.1.0 | renquant-common | `>=0.1.0` | **MISSING-CAP + stale floor** (F17) |
| renquant-common | 0.9.2 | — | — | OK (no renquant deps) |
| renquant-model | 0.1.0 | renquant-common | `>=0.8.1,<1.0` | OK (#41) |
| renquant-model | | renquant-base-data / renquant-artifacts | `>=0.1.0` | uncapped (fleet-wide pattern; low risk pre-1.0) |
| renquant-pipeline | 0.4.0 | renquant-common | `>=0.8.1,<1.0` | OK |
| renquant-pipeline | | renquant-model[gbdt/patchtst] (extras) | `>=0.1,<0.2` | OK |
| renquant-backtesting | 0.1.0 | renquant-common / renquant-pipeline | `>=0.7,<1.0` / `>=0.4,<0.5` | OK |
| renquant-base-data | 0.3.0 | renquant-common | `>=0.6,<1.0` | OK |
| renquant-artifacts | 0.3.0 | renquant-common | `>=0.5,<1.0` | OK |
| renquant-strategy-104 | 0.3.0 | renquant-common | `>=0.7,<1.0` | OK |
| renquant-orchestrator | 0.1.0 | renquant-common `>=0.8.0` + 7 renquant deps `>=0.1.0` | all uncapped | **FLOOR-TOO-LOW + MISSING-CAP ×8** (F14) |

## 6. Import-direction matrix (grep-verified at src/ level)

| Direction | Status |
|---|---|
| execution → pipeline / model / backtesting / kernel.* | **CLEAN** (enforced by `tests/test_import_boundaries.py`) |
| common → any downstream renquant_* / broker / torch / xgboost | **CLEAN** (deps: numpy/pandas/pydantic/scipy/statsmodels/arch only) |
| model → pipeline / execution / backtesting / kernel / alpaca / live | **CLEAN in src/** (test-time exception F25; enforcement gaps F24) |
| model families cross-importing each other | **CLEAN** |
| pipeline / backtesting → execution internals | **CLEAN** |
| backtesting → umbrella-only `training_panel` via sys.path | **VIOLATION** (F12) |
| pipeline → factory package directly (bypassing `load_scorer`) | **VIOLATION** at one site (F30); orchestrator's `daily.py`/`train_gbdt.py` DI-shell imports are the sanctioned training-driver surface |
| execution repo.yml declared deps vs reality | **DRIFT** (phantom renquant-pipeline dep, F17) |

## 7. Known-finding status: the backtesting forked WF loader

Already flagged by M6; current measured status is WORSE than the M6 docs record:
not "identical in pipeline and backtesting" anymore (that was true at the step-0
verification on 2026-07-03) but **266 lines drifted** after pipeline's stage-2 step-1
migration landed, and a **third copy in the umbrella is the live path**
(`run_wf_gate.py:2311` imports `kernel.walk_forward.loader`). See F2 (P0).
Owner: pipeline owns the loader; backtesting deletes its fork and re-exports;
umbrella re-point is an M6 stage-2 landing step (orchestrator-coordinated, operator
grant for the live tree). Related out-of-scope observation for M6's owner: the
umbrella's bare `kernel.*` namespace import implies the whole umbrella kernel tree is
still a live fork of pipeline's kernel beyond just the loader — needs its own
inventory (not audited here).

## 8. Verified clean (checked, no violation found)

- **Order state machine inertness is real** (execution): inside execution only
  `__init__` re-exports, a constant import in `alpaca_broker_port`, and its own tests
  reference it; umbrella has zero imports; the only live wiring is the orchestrator
  Stage-2 `intraday_live_executor` behind its arming gate — the intended integration
  per execution#21 / orchestrator#291.
- **No live-call leaks in execution tests**: AlpacaBrokerPort tests inject a fake
  TradingClient; IGV monitor tests monkeypatch market/execute; the preopen-gate test
  asserts fail-loud on missing ALPACA keys; no real endpoints or credentials anywhere.
- **Eps VALUE parity** on the umbrella commit contract: `commit_contract.py:60` =
  execution `broker.py:21` = `1e-9`, with a literal tripwire test (F15 is copy-count
  plus the one divergent reconciler value, not commit-path drift).
- **BrokerPort completeness**: AlpacaBrokerPort implements the full slice-1 protocol
  (submit/cancel/open_orders/order_status) fail-closed; legacy AlpacaBroker implements
  the full BaseBroker surface incl. fractional + stops (IBKR stub is F18).
- **Broker mode explicit + flags OFF** (execution): factory requires an audited mode
  string; live Alpaca only via explicit `"alpaca"`; readonly wrapper for shadow; all
  IGV/live-armed defaults OFF; `build_live_commit_plan` is readonly-only.
- **0.9.1 shims are verbatim 0.8.1** (common): diffed against `b96d190` — denylist,
  `default=str`, silent file-hash fallbacks all logic-identical; removal-contract
  `DeprecationWarning` present; bare `model_content_sha256` = v1 — exactly what the
  stage-2 design assumes.
- **v1 API complete per stage-1 §2b** (common): `stamp()`/`verify()`;
  `UnclassifiedKeyError` hard at stamp AND verify; `NonFiniteValueError`; exact
  `repr(float)` canonicalization (no rounding, `allow_nan=False`); sorted-key compact
  JSON; `fingerprint_schema_version` stamped; `VersionGapError` distinct from
  `MismatchError`. The deviation is classification structure (F5), not hashing.
- **Common's API snapshot is current** at 0.9.2 for the surface it pins (38/38
  top-level names; 3-way version enforcement); the gap is pinned SCOPE (F7).
- **PR #40 landed as claimed** (model): `fit_calibrator_alpha158_fund.py:22` imports
  `model_content_sha256` from `renquant_common.model_fingerprint`; the old
  additive-allowlist copy at that site is gone; is-identity test pins model == common
  == pipeline.
- **Archived shells untouched in content**: last commit on each is the 2026-05-27
  archival commit; zero commits after (F26 is about the GitHub archived flag only).
- **Scorer entry points correct** (model): all five scorers registered under
  `renquant_common.scorers`; orchestrator retrain lane invokes factory code
  (`train_gbdt` → `panel_trainer`; PatchTST WF manifests subprocess `hf_trainer`);
  no training math in orchestrator `agent_workflows`.
- **0.9.2 review discipline held**: common #21/#22 both approved by the counterpart
  reviewer pre-merge; hash-preservation and shims-untouched are test-pinned.

## 9. Suggested remediation order

1. **F2** (loader triple-fork) — fold into the already-sequenced M6 stage-2 landing;
   it blocks trusting `weekly_wf_promote` and is drifting NOW.
2. **F1** (IGV relocation) — flags are OFF, so this is a planned move, not a hotfix;
   do it before any IGV re-arm.
3. **F3** (fractional seam) — small, closes a fail-closed gap on the newest live path.
4. **F10 + F9 + F8** (factory stamping → provenance parity → trainer cutover) — in
   that order; F10 rides the M6 stage-2 re-stamp window.
5. **F5** hard-gates any M6 stage-4 cutover; **F7/F14/F17** are one-PR-each hygiene.
6. F11 (registry) is the largest structural item — schedule as its own design PR.
