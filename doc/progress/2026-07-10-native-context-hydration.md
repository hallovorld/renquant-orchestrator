# Native pipeline-context hydration + shadow-ab launchd wrapper (GOAL-1 final blocker)

**Date**: 2026-07-10
**Status**: BUILT + real-replay VERIFIED (see Evidence)
**Related**: #451 (P-2 two-arm runner), #456 (paired-world CLI verification), #443 (D6 §2a)
**Repro**: `/Users/renhao/renquant-shadow-ab/2026-07-10/shadow_ab_session_bundle.json` —
arm step 2 (`native-live-inference`) died with
`AttributeError: 'types.SimpleNamespace' object has no attribute 'today'`
(pp_inference.py:307). Step 1 (sealed dual-snapshot verification) was already green.

## Bottom line

`native-live-inference` handed the pinned pipeline a `SimpleNamespace` of the context
JSON; `InferencePipeline.run(ctx)` needs the REAL
`renquant_pipeline.context.InferenceContext` (today / config / ohlcv / holdings /
prices / regime_state / ...). The native offboard path was only ever fixture-tested
(audit D), so this skew was invisible until the first real session. This PR adds the
hydration layer, makes the full arm chain work end-to-end on the real session inputs,
and ships the (uninstalled) launchd wrapper + plist template for the daily cadence.

## Seam choice (justified)

Hydration lives in a new `native_context_hydration.py`, invoked by
`native_live_inference` immediately before `InferencePipeline.run` — NOT inside
`native-live-context`. The context JSON stays a serializable, digest-verified audit
artifact (#456's sealed-snapshot verification is untouched); runtime objects (OHLCV
DataFrames, loaded scorers, HoldingState instances) cannot live in JSON and must be
materialized in the process that runs the pipeline. Legacy invocations (no
`--hydrate-pipeline-context`) keep the namespace behavior byte-identical.

## What hydration builds (all pinned-repo imports; NO umbrella module anywhere)

- `today` ← `--session-date` (the runner's frozen session identity).
- `config` ← the resolved strategy config inside the (verified) context payload;
  `config["_strategy_dir"]` set so the kernel scorer resolves relative artifact refs
  with the same anchor the runner used (#456 anchors).
- OHLCV ← the pinned pipeline's own `kernel.data.LocalStore` in READONLY mode (no
  network fetch, no writes) for watchlist + benchmark + `sector_etf_map` values +
  held tickers — exactly `DataFreshnessGateTask`'s expected set (the first replay
  attempt failed closed on the sector/bond ETFs; fixed).
- `spy_returns` ← benchmark frame closes (last 100 pct-changes).
- holdings / cash / portfolio value ← the SEALED account snapshot, normalized through
  the pipeline's own `account_snapshot_from_live_state`, mapped to real
  `HoldingState` instances (entry-date sentinel = today − 31d, the umbrella's own
  documented fallback).
- prices ← broker marks (market_value/quantity) from the sealed account snapshot,
  local close fallback.
- model + calibrator ← loaded downstream by the pipeline's OWN
  `LoadScorerTask`/`ApplyGlobalCalibrationTask` (kernel panel pipeline) — the module
  routings production's bridge forces (`renquant_pipeline.panel_scoring` → kernel
  job; `renquant_pipeline.kernel.meta_label` → pinned `renquant_backtesting.meta_label`)
  are installed natively by `install_native_pipeline_aliases()`; every target is a
  pinned-subrepo module.
- `regime_state=RegimeState()` (REQUIRED — the dataclass default `None` crashes
  CUSUMTask); regime computed by the pipeline's own RegimeJob (gmm/corr/earnings
  artifacts best-effort, None-guarded).
- Deliberate v1 simplifications (arm-symmetric, cancel in the §2a paired design):
  per-ticker legacy `ctx.models` empty (panel scorer is the decision authority);
  entry-date sentinel; optional artifacts may be None.

## CLI surface (kept in lockstep with build_arm_plan — the #456 meta-test extends)

`native-live-inference` gains `--hydrate-pipeline-context --session-date
--broker-name --strategy-dir --repo-root --ohlcv-dir` (all optional; absent = legacy
identical). `build_arm_plan` now emits the hydration flags on the inference step; the
runner-emissions CLI contract test asserts they thread through.

## launchd wrapper (NOT installed by this PR)

`scripts/shadow_ab_daily.sh` — env recipe copied from the working
`check_readonly_e2e.sh` pattern (+ the verified 2026-07-10 manual session): umbrella
`.env` + `subrepo_env.sh` full pinned PYTHONPATH; builds the session market snapshot
from the PINNED shadow_a watchlist; runs one `shadow-ab` paired session against the
pinned configs + `xgb_prod_artifact_manifest.json`, dedicated ntfy topic
`renquant-shadow-ab`. `deploy/com.renquant.shadow-ab-daily.plist` — 14:35 PT daily
template; installation is the operator-granted landing step.

## Evidence (real replay, failed-session inputs)

The exact arm-A step-2 command from the repro bundle, re-run with the hydration flags
against the REAL inputs (145-ticker pinned shadow_a config, sealed snapshots, real
`RenQuant/data/ohlcv` store, pinned pipeline 8775fec): hydration loads the full
universe; the pipeline's own `LoadScorerTask` loads the real PatchTST checkpoint with
config-consistency fingerprint OK; the run completes and produces a decision payload
(see PR body for the exit code, order-intent/score counts, and the follow-on
`native-live-run` step-3 result). Readonly throughout: no orders, no prod state.

## Tests

`tests/test_native_context_hydration.py` (7): a REAL-pipeline e2e (no fixture
pipeline, no mocked stages — the exact gap audit D flagged), dataclass hydration
correctness (today/regime_state/holdings/prices/pending tickers/_strategy_dir),
fail-closed on missing market data / empty config / empty watchlist / bad date /
missing session-date, alias idempotence + pinned-repo-only targets, legacy-path
byte-identical pin. `tests/test_shadow_ab_runner.py` meta-test extended for the new
inference flags. Full `make test` green.

## r2 review round (Codex CHANGES_REQUESTED): explicit runtime, pinned manifest, bar validity

1. **No umbrella runtime defaults in the wrapper** — `scripts/shadow_ab_daily.sh`
   rewritten: `RENQUANT_SHADOW_AB_PYTHON` / `_RUN_MANIFEST` / `_REPO_ROOT` /
   `_STRATEGY_DIR` are REQUIRED env inputs (`:?` fail-closed, zero literal umbrella
   paths in the script); the data root defaults only off the explicit repo-root
   input; credentials come from an explicit `_ENV_FILE`; PYTHONPATH is built from
   the run manifest's repo paths + this orchestrator checkout (no
   `subrepo_env.sh`, no sibling lookup); arm configs + the frozen data manifest
   resolve from the manifest's pinned strategy-104 checkout. The plist carries the
   operator's explicit values as reviewed configuration.
2. **Immutable run manifest** — new `load_run_manifest` / `verify_run_manifest` /
   `build_run_manifest_payload` in `shadow_ab_runner`: each required repo is
   resolved from the manifest (path + commit) and verified — commit match AND
   clean working tree — BEFORE either arm (any failure = precheck abort, neither
   arm invoked); resolved commits + `data_revision` are recorded in the session
   bundle AND the sealed `decision_snapshot.json`; the §2a pins now come from the
   verified manifest, and the manifest's `data_revision` is threaded to each
   arm's hydration report. `--run-manifest` is REQUIRED on the shadow-ab CLI.
   A directory that merely exists is rejected (`test_e2e_unpinned_sibling_rejected`
   covers both wrong-commit and dirty-tree).
3. **Market-bar validity** — `validate_market_bars` in the hydration layer: every
   consumed symbol's last bar is sealed (per-symbol bar timestamps + session-close
   watermark + window bounds recorded in the run bundle) and must land inside
   `[required_closed_session, decision_cutoff]`, where the required session comes
   from the pinned pipeline's own NYSE calendar helper (weekday fallback).
   A future bar (rerun lookahead) or a stale bar rejects the hydration →
   the arm exits nonzero → paired invalidation of BOTH arms.
   `test_e2e_stale_bar_rejected` / `test_e2e_future_bar_rejected` added.

Tests: hydration file 10, shadow-ab runner file 52 (manifest e2e + CLI updates).
