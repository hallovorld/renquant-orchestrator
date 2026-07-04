# Design-Compliance Audit: orchestrator / base-data / backtesting

Date: 2026-07-04
Scope: `renquant-orchestrator` @ 6e0c972, `renquant-base-data` @ f3f17a1,
`renquant-backtesting` @ 34fd4ed (all `origin/main`, audited in fresh clones).
Type: docs-only findings memo. No code changes in this PR.

## 0. Executive summary

**41 findings: 0 P0, 16 P1, 25 P2.** No active boundary violation on a live
path was found — the charter's hard boundaries (no broker adapters, no
training internals, no production training in backtesting, no credentials)
hold where it counts today. The dominant risk pattern, across all three
repos, is the SAME one that produced the calibrator-fingerprint incidents:
hand-copied implementations of shared semantics that are self-consistent
today and diverge silently tomorrow. Second pattern: safety/provenance
machinery that exists as parsed config, docstring promises, or stamped-only
metadata — but is not enforced or persisted (canary allowlist, live-session
manifests, base-data Required Evidence fields).

Top 5 by risk:

1. **BT-1** — the forked WF loader in backtesting is a third copy that the
   M6 fingerprint-migration inventory does NOT list and whose bare import
   the step-5 sweep grep will never flag; its manifest-sanity leg feeds the
   live promote gate, and it has already accumulated three divergences
   (URI resolution, dropped `artifact_sha256` digest, calibrator class).
2. **OR-3** — the Stage-2 canary allowlist is parsed and stamped but never
   enforced, and the §9.3a loss budget / 20-session counter are
   unimplemented: dark today, but the day it arms, "canary" degenerates to
   watchlist-wide live trading under only a notional cap.
3. **OR-1/OR-2** — `execution_reconciler` re-implements the §7
   parent-intent identity DIVERGENT by construction from renquant-execution
   (prefix, hash length, case, separator) plus a parallel order-lifecycle
   state machine already drifted in-repo (`done_for_day`).
4. **XC-1** — two incompatible canonical-JSON hashers both stamp
   `score_content_sha256` in the orchestrator (artifacts `hash_jsonable`
   vs ops `canonical_hash`) — the exact pre-incident shape of the
   model_content_sha256 bug.
5. **BD-1/BD-4** — base-data has no shared manifest writer (3 divergent
   hand-rolled shapes, none passing the repo's own validator) and the
   validator itself under-enforces the charter: owner, retention class,
   freshness rule, and validation command are stamped by ZERO manifests
   in the repo.

## 1. Charter audited against

- Umbrella `doc/arch/subrepo-operating-model.md` — repository roles and
  Universal Rules 1-6 (R1 pipeline primitives, R3 owner boundaries, R4
  manifest+fingerprint+URI references, R5 immutable promotion fingerprints,
  R6 stable `main`).
- Each repo's `CLAUDE.md` hard boundaries (orchestrator: no broker adapters /
  training internals / signal internals, no silent continue without
  fingerprints, run bundle for every full run; base-data: manifests not blobs,
  Required Evidence fields; backtesting: parity via shared contracts, no
  silent local paths, no production training).
- RFC #208 §8 per-repo ownership (execution = order lifecycle; pipeline =
  runtime decision logic + sizing; orchestrator = scheduling, provenance,
  flags/canary/kill-switch, ledger, replay harness).

## 2. Method

Five dimensions, audited in parallel over fresh scratchpad clones (never the
live tree or primary checkouts): (1) orchestrator boundary sweep,
(2) base-data manifest/PIT discipline, (3) backtesting WF/gate/parity,
(4) cross-cutting duplicated implementations, (5) doc/progress convention
spot-check. Each finding cites repo+file:line, the rule violated, severity,
a one-line fix, and a fix owner.

Severity: **P0** = active boundary violation or safety/correctness risk on a
live path. **P1** = charter violation likely to cause drift or bugs
(duplicated semantics, untested gate, missing fingerprint/bundle). **P2** =
hygiene/convention.

## 3. Findings

### 3.1 renquant-orchestrator (0 P0 / 4 P1 / 6 P2)

| # | Sev | Location | Rule | Finding | One-line fix | Fix owner |
|---|---|---|---|---|---|---|
| OR-1 | P1 | `execution_reconciler.py:265-293` vs renquant-execution `order_state_machine.py:177` | R3; RFC #208 §8 row 1 (execution owns the §7 identity) | Orchestrator re-implements the §7 dedup identity DIVERGENT by construction: `make_parent_intent_id` → `pi_{sha256[:16]}`, side `.lower()`, `\|` separator vs execution's `compute_parent_intent_id` → `pi-{sha256[:20]}`, side `.upper()`, `\x1f` separator — same decision, different id in the two repos; no lockstep test (`tests/test_execution_reconciler.py` never imports `renquant_execution`). The calibrator-fingerprint triple-impl failure mode reborn. | Delete the local derivation; import execution's functions (or at minimum add a byte-lockstep parity test). | orchestrator (consume renquant-execution) |
| OR-2 | P1 | `execution_reconciler.py:98-263` (`ALPACA_STATUS_TO_STATE:202`) | RFC #208 §8 row 1; no-broker-adapters adjacency | A full parallel order-lifecycle state machine + Alpaca status vocabulary instead of consuming `renquant_execution.order_state_machine` — already drifted IN-REPO: `:211` maps `done_for_day→ACCEPTED` while `intraday_live_executor.py:179` treats it as canceled. Observe-only and unwired today (hence P1 not P0). | Hoist status maps + lifecycle validation into renquant-execution; keep only diff/report/alert here. | renquant-execution (canonical) + orchestrator |
| OR-3 | P1 | `intraday_live_executor.py:929-1074`, `intraday_session_scheduler.py:210-225` | RFC #208 §8 row 3 ("canary allowlist enforced") + §9.3a envelope | Stage-2 live path enforces the notional cap + 31-day window, but (a) the canary allowlist is parsed and stamped yet NEVER enforced — `process_tick` submits any BUY subject only to the cap, `Stage2Authorization` has no symbol allowlist field, no test asserts allowlist blocking; (b) the §9.3a cumulative loss budget (1.5% equity) and 20-live-session counter are unimplemented (calendar expiry is the only clock). Dark today; the day it arms, "canary" = watchlist-wide live trading under a $500/day cap. | Allowlist filter + loss/duration stop conditions + tests must land before/with the session runner. | orchestrator |
| OR-4 | P1 | `entry_timing_policy.py:364-487` (config docstring `:153-156`) | CLAUDE.md no signal/decision internals; RFC #208 §8 row 2 | `decide()` implements live entry-timing decision rules on microstructure (gap-retrace trigger `mid <= open − retrace_frac×gap`, fixed-delay elapse, deadline degradation), and the config docstring designates `policy` as "the value a future Stage-2 live consumer would read" — built as the live WHEN-decider. Today wired shadow-only via the scheduler observer seam (the shadow-harness half IS §8-row-3 orchestrator turf); the violation is prospective placement (P1 dark). | Keep evaluator/report here; the live-consumed `decide()` moves to renquant-pipeline before Stage-2 wiring. | renquant-pipeline (future home) |
| OR-5 | P2 | `intraday_live_executor.py:174-179,748-895,984-1000` | RFC #208 §8 boundary note | The dark live executor correctly consumes `OrderStateBook` + an injected `BrokerPort`, but still embeds broker semantics: own ack/cancel vocabularies incl. Alpaca `accepted_for_bidding`, order-type/TIF shaping, SELL remainder-chase policy — a 4th place broker statuses are interpreted. | Execution repo exports status classification + a submit/cancel driver; orchestrator keeps WAL/cap/arming/provenance. | renquant-execution + orchestrator |
| OR-6 | P2 | `retrain_alpha158_fund.py:755-806` | No-training-internals gray zone; R3 | `_default_rawlabel_build_fn` inlines fwd-60d excess-return label math as a hand-copied port of umbrella `scripts/build_raw_fwd60d_label.py` — a second implementation of a training-data builder in the orchestration repo (well-guarded: staging + validation + atomic swap). | Lift into renquant-base-data and consume pinned. | renquant-base-data |
| OR-7 | P2 | the new 105/107 family (scheduler, executors, loggers, replay, census, `risk_budget/`, `attribution/`, `expkit/`) | R1 | None of the new family imports renquant-common Task/Job/Pipeline — ad-hoc dataclass + argparse CLIs (contrast `daily.py`, `anomaly_triggers.py`, `retrain_*`: Pipeline-based). A session loop is arguably not a batch workflow; the one-shot jobs (replay, reports, census) have no such excuse. | Wrap one-shot entrypoints in Task/Job adapters incrementally. | orchestrator |
| OR-8 | P2 | `intraday_live_executor.py:37-39,1112-1146` | Run-bundle rule; §8 row 3 "provenance per tick" | Docstring promises the arming downgrade is counted in the session manifest and `ArmDecision.to_manifest_record()` exists — but no code persists it: the session runner was deferred, `LiveTickWriter` has zero callers. Live-path run-bundle discipline is a promise, not code (acceptable only while dark). | Ship the manifest writer with the session runner. | orchestrator |
| OR-9 | P2 | `entry_timing_shadow.py:145` | No machine-pinned paths | `DEFAULT_TICK_SOURCE` hard-codes `~/git/github/RenQuant/logs/renquant105_pilot/...` (the live umbrella tree) while the rest of the family resolves `default_data_root()`. | Default to `default_data_root()/logs/...`. | orchestrator |
| OR-10 | P2 | `gate_registry.py:1-78` (wired only at `daily_trading_health.py:490`) | No-signal-internals adjacency | The verdict algebra includes sizing semantics (`halve` ⇒ ×0.5, block dominance). Today it records (ledger rows) rather than decides — but an admission/sizing algebra is pipeline-territory semantics parked in orchestrator. | Keep ledger-only, or move the algebra to pipeline before any enforcement wiring. | orchestrator / renquant-pipeline |

### 3.2 renquant-base-data (0 P0 / 4 P1 / 6 P2)

| # | Sev | Location | Rule | Finding | One-line fix | Fix owner |
|---|---|---|---|---|---|---|
| BD-1 | P1 | `validation.py:43` vs `pit_revision_features.py:763-782`, `fmp_estimate_revisions.py:338-359`, `fmp_fundamentals_5y.py:322-346,593-625` | CLAUDE.md Required Evidence; "consumers resolve through manifests" | No shared manifest writer: 3 divergent hand-rolled manifest shapes; `validate_data_manifest` is called by NO output-producing module, and every hand-rolled manifest would fail it (missing `dataset_id`/`uri`/`asset_class`). Same triple-independent-impl anti-pattern as the calibrator-fingerprint bug. | One `write_dataset_manifest()` helper that stamps all 8 Required Evidence fields and self-validates; migrate the 3 writers. | base-data `validation.py` + the 3 modules |
| BD-2 | P1 | `transformer_corpus.py:270`, `rawlabel_sidecar.py:326` | R4/R5 | The PatchTST shadow-training corpus and the calibrator-fit rawlabel sidecar are written as loose parquet with NO content fingerprint and NO manifest (neither module imports `hashlib`). These are exactly the promotion-relevant artifacts R5 exists for. | sha256 the output + sidecar manifest via the BD-1 writer (input-panel sha + code sha per the `pit_revision_features` pattern). | base-data |
| BD-3 | P1 | `sec_fundamentals.py:736,765` (also `alpha158_fund_panel.py:106`, `alpha158_qlib_panel.py:659`, `alpaca_news_refresh.py:194`, `options_iv_refresh.py:191`) | R4/R5; repo role "owns freshness contracts" | The LIVE serving feeds gated by P-FUND-FRESHNESS are materialized as bare parquet; no manifest, fingerprint, or declared freshness rule — the freshness SLA lives only in the consumer (pipeline promote gate). | Emit a sidecar manifest (fingerprint + freshness_rule + axis frontier) at each materialization. | base-data `sec_fundamentals.py`; legacy refreshers follow-up |
| BD-4 | P1 | `validation.py:18`, `manifests/example-dataset.json` | CLAUDE.md Required Evidence | The shared validator requires only 5 fields — omits source, freshness rule, owner, retention class, validation command — so even a compliant writer cannot be charter-compliant today; the repo's own reference manifest carries 6/8 fields. | Extend the required tuple to the 8-field set (staged warn→fail); fix the example. | base-data `validation.py` |
| BD-5 | P2 | `watchlist_screen.py:144-174` | Role boundary (universe selection = strategy, not data) | Ticker ranking/screening by Sharpe + `median_sharpe + 0.5σ` add-threshold — signal logic in the data repo. Advisory-only (markdown report + ntfy, mutates no config), hence P2. | Relocate the screen to the strategy repo; keep only perf-stat computation here. | renquant-strategy-104 (dest) / base-data (removal) |
| BD-6 | P2 | `fmp_estimate_revisions.py:107-110` (inherited by `fmp_fundamentals_5y.py:128`) | Manifest resolution; the validator itself rejects `/Users/` URIs | Hardcoded developer-local absolute defaults (`/Users/renhao/git/github/RenQuant/.env`, golden strategy config path). Overridable and read-only, but machine-pinned. | Default to env vars / required CLI args; universe via the orchestrator-passed pinned config. | base-data |
| BD-7 | P2 | `fmp_estimate_revisions.py:491-499`, `fmp_fundamentals_5y.py:210`, `pit_revision_features.py:158-164` | No-duplication | Three hand-copied `_FORBIDDEN_LEAVES` write-guard sets that have already drifted (the third omits `fmp_harvest_finnhub`/`fmp_harvest_5y`). Mitigated by per-module leaf-name allowlists — no writable hole today. | One shared `FORBIDDEN_CANONICAL_LEAVES` constant + guard function. | base-data shared path-guard module |
| BD-8 | P2 | `fmp_estimate_revisions.py`, `fmp_fundamentals_5y.py`, `transformer_corpus.py`, `rawlabel_sidecar.py`, `pit_revision_features.py` (mains) | R1 | R1 regression trend: everything added since 06-27 is an ad-hoc argparse main, skipping renquant-common Task/Job/Pipeline (older `registry.py`/`sec_fundamentals.py` are compliant) — run-record/step-audit is absent exactly where the newest recipes live. | Wrap fetch/validate/publish stages as Tasks in a Job. | base-data, the 5 new modules |
| BD-9 | P2 | `fmp_estimate_revisions.py:166-207`, `pit_revision_features.py:171-174,568`, `sec_fundamentals.py:458-519,675-702`, `rawlabel_sidecar.py:235-255,121-124` | PIT convention single-sourcing | ~4 independent PIT machineries (as-of resolution, busday offsets, future-date guards, no-lookahead validators) — each individually correct, fail-closed, and tested; NO semantic inconsistency found, hence P2 not P1. | Extract a shared `pit.py` helper and converge. | base-data |
| BD-10 | P2 | `manifests/track-b-bull-calm-feature-readiness.json` | Registry contract | A readiness checklist (keyed `manifest_id`, no fingerprint/uri) sits in the dataset-registry glob path; inert but pollutes the namespace — and is ironically the ONLY manifest declaring a validation entrypoint. | Move to a subdir excluded from the registry glob. | base-data `manifests/` |

Required-Evidence field coverage measured across the repo: owner, retention
class, freshness rule, and validation command are stamped by ZERO manifests.

| Module (output) | schema | URI | fingerprint | source | freshness | owner | retention | validation cmd |
|---|---|---|---|---|---|---|---|---|
| transformer_corpus (corpus parquet) | — | — | NONE | — | — | — | — | — |
| rawlabel_sidecar (sidecar parquet) | — | — | NONE | — | — | — | — | — |
| sec_fundamentals (daily+extended feeds) | — (in-band provenance cols only) | — | NONE | — | — (SLA in consumer) | — | — | — |
| pit_revision_features (`c1_revision_drift.manifest.json`) | partial | no | YES (sha256+input+code) | yes | no | no | no | no |
| fmp_estimate_revisions (per-endpoint) | no | partial | YES (sha256) | yes | partial | no | no | no |
| fmp_fundamentals_5y (bundle manifest) | yes | partial | YES (sha256+bundle+universe) | yes | no | no | no | no (verifier exists, undeclared) |
| `manifests/example-dataset.json` (reference) | yes | yes | yes | no | no | no | yes | no |

### 3.3 renquant-backtesting (0 P0 / 2 P1 / 5 P2)

| # | Sev | Location | Rule | Finding | One-line fix | Fix owner |
|---|---|---|---|---|---|---|
| BT-1 | P1 | `walk_forward/loader.py:152-425` | Cross-repo no-duplication; boundary (a) | The forked WF loader (lifted byte-equivalent 97a5e5e, switched-to 77493b5) is a full THIRD copy alongside renquant-pipeline `kernel/walk_forward/loader.py` and the umbrella copy — and it is **absent from the M6 migration inventory** (stage-1 §3a / stage-2 §2a list the pipeline/umbrella loaders only) while the step-5 zero-legacy-callers grep does not match its bare `model_content_sha256` import — the sweep will never flag it. Already-accumulated divergences: (a) three different `_resolve_uri` fixes of the same resolution bug across the three copies (`:358-388` heuristic vs pipeline ancestor-walk vs umbrella PR #421 digest-bound resolver); (b) the fork's `_parse_entry` (`:103-129`) silently DROPS the umbrella's per-entry `artifact_sha256` digest, losing stale/wrong-artifact protection; (c) different calibrator classes loaded. Its fail-closed fingerprint path (`calibrator_as_of:330`/`_assert_calibrator_matches_entry:403`) is dormant (zero callers) — hence P1 not P0 — but its `entry_as_of` manifest-sanity leg feeds the LIVE promote gate (`weekly_wf_promote.sh:116` → `python -m renquant_backtesting.wf_gate` → `wf_gate_metadata` required by `model_acceptance.promote()`). | Delete the fork and import the pipeline-owned loader; at minimum add this copy to the M6 stage-2 §2a inventory + step-5 grep. | renquant-pipeline (loader owner per M6 §4); deletion PR in backtesting; inventory amendment in orchestrator design doc |
| BT-2 | P1 | `wf_gate/train_walkforward_panel.py:61`, `train_walkforward_patchtst.py:26`, `fit_walkforward_calibrators.py:23`, `merge_walkforward_manifests.py:34` | Boundary (b); repo's own `repo_root.py` convention | Broken package-relative repo root: `REPO = Path(__file__).resolve().parent.parent` resolves to `src/renquant_backtesting/` inside the installed package, so `STRATEGY_DIR = REPO/"backtesting"/"renquant_104"` is nonexistent; none consult `RENQUANT_REPO_ROOT` (unlike the already-fixed `runner.py:79-89`, `stamp_walkforward_fingerprints.py:20`, `sim_driver.py:38`, each with a repo-root test). Fails loudly (FileNotFoundError), not silently — hence P1. | Switch all to `renquant_backtesting.repo_root.resolve_repo_root` + repo-root tests. | backtesting wf_gate |
| BT-3 | P2 | `wf_gate/runner.py:2154-2172` (comment `:2177`) | R1 / no-duplication | `_manifest_uri_to_path` is a further hand-copied URI resolver with an admitted manual-sync comment ("Keep this in lockstep with WalkForwardModelLoader") — a 4th resolution semantics on the promote path's manifest-sanity leg. | Delegate to the loader's `_resolve_uri`. | backtesting wf_gate |
| BT-4 | P2 | `wf_gate/runner.py:217` vs `:2823,2866-2869,2886,2913` | Single-sourcing (intra-module) | The ENFORCED v2 placebo ceiling exists as `_placebo_ic_threshold()` AND re-implemented inline in the per-regime leg, with the criterion string duplicated as two literals. Same semantics today; drift-able in one edit. | Per-regime leg calls the pooled helpers; criterion string becomes a constant. | backtesting wf_gate |
| BT-5 | P2 | `wf_gate/dump_walkforward_sim_metrics.py:120-160`, `write_walkforward_report.py` | CLAUDE.md Required Evidence | The standard backtest report has benchmark comparison, gross/tax/net, attribution — but NO config/data/model fingerprints: only the config NAME (`"strategy_config": args.strategy_config_name`). Fingerprints exist in the gate-verdict lane and dashboard, not the report. | Stamp manifest path + scorer `model_content_fingerprint` + `config_fingerprint` into `out_data` and render. | backtesting wf_gate |
| BT-6 | P2 | `reconciliation/live_sim_reconcile.py:1-7,140-153` | Boundary (a): parity claims must be tested | Docstring claims the §5.13.1 SimAdapter end-to-end walk; the behavioral test remained in the umbrella (`RenQuant/tests/test_reconciliation.py`) — this repo has only an import-lift test. | Lift the end-to-end test alongside the module. | backtesting reconciliation |
| BT-7 | P2 | `wf_gate/stamp_walkforward_fingerprints.py:114-119` | M6 inventory completeness | The M6 stage-2 §2a inventory names the umbrella WRAPPER (`scripts/stamp_walkforward_fingerprints.py:214`) but this subrepo module is the ACTUAL implementation it delegates to (imports bare `model_content_sha256` from pipeline `panel_scorer`); a migration executed strictly per-inventory patches the wrapper and misses the module. | Amend M6 §2a/§3a to name `renquant_backtesting.wf_gate.stamp_walkforward_fingerprints`. | orchestrator (design doc); pipeline+common (migration) |

Blast-radius map for the forked loader:

| Caller | Uses | Feeds promote gate? |
|---|---|---|
| `wf_gate/runner.py:2197-2209` manifest-sanity leg | `entry_as_of` only (manifest parse, leakage/lookahead guards) — not the fingerprint functions | **YES — live** (`weekly_wf_promote.sh` → `wf_gate_metadata` → `model_acceptance.promote()`) |
| `train_walkforward_panel.py:145`, `train_walkforward_patchtst.py:132` | `RetrainEntry` dataclass only | Indirect — their manifests are consumed in the sim leg by the UMBRELLA loader |
| `walk_forward/__init__.py:26-28` re-export | public import surface | Latent — orchestrator imports only meta_label + BacktestContext/Pipeline |
| `calibrator_as_of` / `_assert_calibrator_matches_entry` / `_scorer_fingerprints_from_payload` | — | **NO callers — dormant** (the fail-closed fingerprint contract runs in the umbrella loader, which IS M6-scheduled) |

### 3.4 Cross-cutting (0 P0 / 6 P1 / 6 P2)

| # | Sev | Location | Rule | Finding | One-line fix | Fix owner |
|---|---|---|---|---|---|---|
| XC-1 | P1 | orch `ops/renquant105/batch_scores_bundle.py:25-27` vs `intraday_session_inputs.py:236-243` | No-duplication / owning repo | Two incompatible canonical-JSON hashers both stamp a field named `score_content_sha256` over the same semantic (a score vector): `canonical_hash` (default separators, no volatile-strip) vs `renquant_artifacts.hash_jsonable` (compact separators + `_strip_volatile`) — identical payloads hash differently by construction. Each loop is self-consistent today; any future join of bundle-meta ↔ frozen-signal fingerprints mismatches 100%. The exact pre-incident shape of the model_content_sha256 bug. | `batch_scores_bundle` imports `renquant_artifacts.hash_jsonable`; delete `canonical_hash`. | orchestrator |
| XC-2 | P1 | orch `retrain_alpha158_fund.py:499-573` vs base-data `loaders/data.py:34-57` | Cross-repo no-duplication | Self-declared "mirror" of `_last_completed_nyse_session`, already diverged: 16d vs 14d lookback; fail-closed raise vs swallow-to-None + 2-day fallback. | Lift one `last_completed_session()` to renquant-common with an explicit fail-mode parameter. | renquant-common (+ both consumers) |
| XC-3 | P1 | orch `scripts/kpi_scorecard.py:308-338` vs backtesting `analysis/session_resolution.py:78-101` | Cross-repo no-duplication | `_ledger_session_keys` re-implements backtesting's `session_key` semantics (docstring admits it), own weekday fallback included; a holiday-handling change in backtesting will not propagate. | Lift `session_resolution` to renquant-common; both import. | renquant-common |
| XC-4 | P1 | ~10 Python + 8 shell ntfy senders across 3 repos (table §4.2) | Cross-repo no-duplication | Divergences are semantic, not cosmetic: priority none/3/4, timeout 5/10, and `RENQUANT_NO_NOTIFY` suppression honored ONLY in base-data + backtesting — no orchestrator sender checks it (ops-mute of orchestrator monitors via the documented env is impossible). | `renquant_common.notify.post_ntfy(...)` honoring `RENQUANT_NO_NOTIFY` + one `ops/notify.sh`; migrate. | renquant-common, then per-repo |
| XC-5 | P1 | base-data `alpha158_fund_panel.py:230-240` vs backtesting `wf_gate/wf_pead_sue.py:80-92` | Cross-repo no-duplication | Verbatim copy of the production SUE/surprise-momentum/streak feature block (eps 1e-6, clip ±5, shift(1) PIT rule). Agrees today; any production-panel tweak silently de-syncs the WF harness that validates it. | Export `compute_sue_features()` from base-data; import in wf_pead_sue. | base-data |
| XC-6 | P1 | orch `ops/renquant104/` (no liveness checker) | Ops pattern gap | rq105 and pit each have an output-freshness liveness checker + plist; rq104 has NONE — a silent launchd lapse of `rq104-risk-budget`/`rq104-scorer-identity` is undetectable (wrappers only alert on non-zero exit of runs that start). Both jobs observe-only, so P1 not P0. | Add rq104 outputs to a shared liveness core (see XC-8). | orchestrator |
| XC-7 | P2 | backtesting `metrics/` + `forensics/metrics/` + `forensics/risk_metrics.py` | Owning-repo rule | Byte-identical stale vendored copies of renquant-common's metrics package (double-vendored within backtesting), kept alive only by import-surface tests post lift-to-common; product code already imports common. | Delete copies (or one-line re-export shims); repoint the two tests. | backtesting |
| XC-8 | P2 | orch `ops/pit/pit_liveness_check.py:54-89` vs `ops/renquant105/rq105_liveness_check.py:93-167` | Intra-repo duplication | `_session_calendar` / `_is_session_day` / `_alert` trio copy-pasted between the two checkers. | Shared `ops/liveness_common.py` used by both (and XC-6's rq104 checker). | orchestrator |
| XC-9 | P2 | orch `intraday_session_inputs.py:120-128` vs `ops/renquant105/export_batch_scores.py:130-139` | Intra-repo duplication | `_fingerprint_gaps` duplicated verbatim; the run-selection SQL contract is also mirrored ("matches export_batch_scores.py" docstring). | Move both into one module the ops script imports. | orchestrator |
| XC-10 | P2 | orch `daily_trading_health.py:147` | Doc/code mismatch | Docstring claims "reusing the established post_ntfy path" while defining a divergent copy (priority 4 + tags). | Fixed by XC-4; until then fix the docstring. | orchestrator |
| XC-11 | P2 | orch `scripts/minute_rth.py:16`, `scripts/minute_feature_scan.py:15` | Calendar-source split | Research scripts session-filter with `exchange_calendars` XNYS while production uses `pandas_market_calendars` NYSE — two independent holiday/half-day datasets in one repo (acceptable for research; noted so production reuse doesn't inherit it). | Note-only / converge on production reuse. | orchestrator |
| XC-12 | P2 | orch `ops/renquant105/rq105_liveness_check.py:474` | Provenance convention | Bare-hex sha256 while the rest of the stack uses the `sha256:`-prefixed convention — third JSON-canonicalization variant. | Adopt the prefixed convention. | orchestrator |

## 4. Duplicated-implementation tables

### 4.1 Session calendars — NO canonical impl exists (renquant-common has none)

Six independent implementations of "previous / last-completed NYSE session"
plus two research-only variants; all `pandas_market_calendars`-based paths
agree on holidays/half-days today (same underlying dataset), the weekday
fallback paths are holiday-blind by documented design. No hardcoded holiday
lists anywhere (good).

| # | Impl | Location | Divergence | Suggested home |
|---|---|---|---|---|
| 1 | `NyseSessionCalendar` + `default_session_calendar()` | orch `intraday_quote_logger.py:285-339` | De-facto repo canonical; reused by scheduler, entry-timing, both liveness checkers | renquant-common |
| 2 | `_expected_last_completed_session` | orch `retrain_alpha158_fund.py:499-573` | Docstring admits it mirrors base-data; 16d lookback vs 14; fail-closed raise vs swallow→None | renquant-common |
| 3 | `_last_completed_nyse_session` | base-data `loaders/data.py:34-57` | The original #2 mirrors; `except Exception: return None` + 2-calendar-day cap | renquant-common |
| 4 | `nyse_sessions`/`session_key`/`classify_date` | backtesting `analysis/session_resolution.py:46-117` | Weekday fallback (Sat/Sun→Fri), holidays flagged `session_resolved=False`; properly reused within backtesting | renquant-common |
| 5 | `_ledger_session_keys` | orch `scripts/kpi_scorecard.py:308-338` | Cross-repo hand-copy of #4's semantics (docstring admits it) | renquant-common |
| 6 | `expected_previous_session` | orch `ops/renquant105/batch_scores_bundle.py:30-52` | Own impl, 14-day window, fail-closed ValueError | merge into #1 |
| 7 | `previous_session` (day-walk) | orch `intraday_session_inputs.py:92-113` | Third "previous session" impl in the same repo as #6 | merge into #6/#1 |
| 8 | `exchange_calendars` XNYS | orch `scripts/minute_rth.py:16-29`, `minute_feature_scan.py:15` | Different holiday dataset package; research-only | note-only |
| 9 | Documented weekday/BDay approximations | orch `model_freshness_monitor.py:319`, `patchtst_weekly_cutoff.py:105-106`; base-data `pit_revision_features.py:62-63` | Holiday-blind by documented design, skew absorbed in slack | acceptable |

### 4.2 ntfy senders — ~10 Python + 8 shell copies

| Impl | Location | Divergence |
|---|---|---|
| `post_ntfy` | orch `weekly_apy_monitor.py:127-138` | Title only, timeout 5; partial de-facto canonical (imported by `model_freshness_monitor.py:98`, `scorer_identity_monitor.py:102`, `retrain_alpha158_fund.py:31`) |
| `post_ntfy` | orch `weekly_promote_monitor.py:320-333` | Byte-near copy of the above |
| `post_ntfy` | orch `daily_trading_health.py:147-160` | Priority 4, tags `warning,chart`; docstring claims reuse, defines a copy |
| `post_ntfy` | orch `state_backup.py:60-71` | Priority 3, tags `warning` |
| `post_ntfy` | orch `execution_reconciler.py:1357-1371` | Priority 4, returns bool |
| `_post_live_persistence_alert` | orch `native_live_run.py:101-109` | Delegates to a renquant-execution impl (another copy, another repo) |
| `_alert` (curl + .env parse) | orch `ops/pit/pit_liveness_check.py:78-89` | Near-verbatim copy of the next row |
| `_alert` (curl + .env parse) | orch `ops/renquant105/rq105_liveness_check.py:155-167` | ditto |
| inline `curl` blocks ×8 | orch ops wrappers (`run_quote_logger.sh:22`, `run_session_scheduler.sh:37`, `run_postclose_loggers.sh:24`, `run_shadow_serving.sh:19,33,52`, `run_c1_feature_builder.sh:43`, `run_estimate_snapshotter.sh:42`, `run_risk_budget_statement.sh:30`, `run_scorer_identity_monitor.sh:34`) | Each hand-rolls `source .env` + curl |
| `notify` | base-data `watchlist_screen.py:93-107` | Honors `RENQUANT_NO_NOTIFY=1` |
| `notify_ntfy` | backtesting `analysis/backtest_and_analyze.py:120-136` | Honors `RENQUANT_NO_NOTIFY=1`; timeout 10 (everyone else 5) |

Topic default `renquant` consistent everywhere. Semantic divergences:
priority (none/3/4), timeout (5/10), and `RENQUANT_NO_NOTIFY` honored only
outside the orchestrator (XC-4).

### 4.3 Eps / tolerance constants — no cross-repo conflict on a shared quantity

| Quantity | Locations | Verdict |
|---|---|---|
| SUE `(s/(rolling_std+1e-6)).clip(-5,5)` + momentum/streak | base-data `alpha158_fund_panel.py:230-240` (prod) vs backtesting `wf_gate/wf_pead_sue.py:80-92` (research) | Verbatim cross-repo copy of a production feature definition (XC-5) — agrees today, drift breaks comparability |
| `_STD_ZERO_EPSILON = 1e-12` + risk stats | common `risk_metrics.py` vs backtesting `forensics/risk_metrics.py:41-45` | Byte-identical vendored copy (XC-7) |
| z-score denominators | backtesting harnesses `std+1e-9` vs orch research `std+1e-12` | Disjoint harnesses, never cross-compared — no conflict |
| Cash/notional `_EPS = 1e-9` | orch `intraday_live_executor.py:175` | repo-local, single definition |
| PnL identity `SUM_CHECK_ABS_TOL = 1e-6` USD | orch `attribution/decompose.py:59` | repo-local |
| Share-lot residual `1e-9` | backtesting `wf_gate/sim_ledger.py:389-966` + attribution analyzer | consistent within backtesting |

### 4.4 Fingerprint impls

- `model_content_sha256`: **genuinely unified** — one engine in
  `renquant_common/model_fingerprint.py`, re-exported via pipeline
  `panel_scorer`, consumed through that single chain by orchestrator
  (`model_bundle.py:73-78`, census/prestamp tools) and backtesting
  (`walk_forward/loader.py:154`, `wf_gate/stamp_walkforward_fingerprints.py:115`).
  No hand-rolled model-payload hasher remains in the three repos.
- `score_content_sha256`: **two incompatible canonicalizations in one repo**
  (XC-1) — `renquant_artifacts.hash_jsonable` vs
  `ops/renquant105/batch_scores_bundle.canonical_hash`.
- Minor: `rq105_liveness_check.py:474` bare-hex row hash (XC-12); local
  provenance hashes in `retrain_alpha158_fund.py:334-337`,
  `kpi_scorecard.py:660,685`, `entry_timing_policy.py:194` are self-contained.

### 4.5 Ops/liveness patterns (orchestrator)

- Plists (11 jobs across renquant104/renquant105/pit): ONE uniform
  convention — `com.renquant.<ns>-<job>` labels, umbrella-logs out/err paths,
  all `StartCalendarInterval`, zero KeepAlive/ThrottleInterval. Clean.
- Wrappers: one skeleton (`set -u`, pinned `*-run` checkout on PYTHONPATH,
  dated log, on-failure ntfy) with three divergences: bash (rq104/pit) vs
  zsh (rq105) shebangs; 8 hand-rolled curl+.env ntfy blocks (§4.2); flock
  only where the module contract demands it (justified).
- Liveness model = output-freshness checking by a separate checker job; NO
  wrapper stamps a heartbeat. rq105 and pit have checkers; **rq104 has none**
  (XC-6). No `RENQUANT_OPS_FAIL_CLOSED`-style flag exists anywhere in ops/.
- Monitor cores: ~8 hand-rolled variants of the same 30-line
  check/stamp/alert pattern (`scheduled_health`, `daily_trading_health`,
  two weekly monitors, two identity/freshness monitors, reconciler, two
  liveness checkers); record shape shared by convention only.

## 5. Dimension 5 — doc/progress convention spot-check (2 P2)

| # | Sev | Repo | Finding | Fix | Owner |
|---|---|---|---|---|---|
| D5-1 | P2 | renquant-base-data | Only ONE progress doc exists (`doc/progress/2026-07-03-fund-feed-provenance.md`, PR #34) against ~7 merged PRs this week (#27-#33 have none). The convention was adopted mid-week; earlier merges carry no durable per-PR record. | Adopt the orchestrator's pre-PR progress-doc gate repo-wide; backfill is optional, forward compliance is not. | base-data |
| D5-2 | P2 | renquant-backtesting | Uses `docs/progress/` (plural `docs/`) vs the house `doc/progress/` (orchestrator + base-data), and coverage is partial: the wf-gate lane is documented (3 docs), but PRs #59 (`--dump-predictions`), #60 (as-of forward returns), #62 (deps) have no progress docs. | Converge on one directory convention and per-PR coverage. | backtesting |

Orchestrator itself is dense and compliant: every merged PR of the week has
a `doc/progress/` record (spot-checked #283-#294 inclusive, including the
one-line test fix in #293).

## 6. Clean checks (verified compliant)

Reported so coverage is honest — these were audited, not assumed:

- **Broker-adapter relocation is real** (orchestrator): zero
  `AlpacaBrokerPort`/order-submission imports anywhere in src/ops/scripts;
  the direct alpaca imports that remain are GET-only
  (`intraday_session_inputs.py:402-441` account/positions,
  `intraday_quote_logger.py:214-230` market data). Commit 69f36e4's
  boundary holds.
- **Stage-1/Stage-2 gate + kill-switch test coverage is strong**:
  default-OFF proven (`test_absent_section_means_disabled`,
  `test_env_flag_default_off`, ...), quadruple gate exhaustively tested
  (`test_quadruple_gate_all_16_combinations`), kill switches pre-session and
  mid-session, dead-man, entry-cap (blocks entries never exits), WAL-before-
  broker-call, and the parent-intent lockstep halt for the pipeline↔execution
  pair. The gap is OR-3's allowlist/loss-budget, not the gates that exist.
- **Training boundary holds in both repos that touch training**:
  orchestrator `retrain_*`/`train_gbdt` drive the pinned factory via
  renquant-common Pipelines/subprocess (no `.fit` anywhere; sole caveat
  OR-6 label-building); backtesting WF fold training subprocess-invokes the
  single-source production training script into isolated
  `artifacts/walkforward_v2/<cutoff>/` paths, and `model_acceptance.promote()`
  refuses anything without passing `wf_gate_metadata` — nothing silently
  mints a production model from the WF harness.
- **Gate v2/v3 machinery is single-sourced** in backtesting
  `wf_gate/runner.py` (v2 enforcing, v3 stamped shadow-only); no thresholds
  or pass/fail predicates re-derived in sim_driver, reports, or the
  orchestrator's promote monitors (they read stamped verdicts/logs only).
- **Sim/live parity is contract-based where claimed**: `runtime_parity.py`
  runs the shared `renquant_pipeline` RuntimeInferencePipeline (tested);
  `simulation.py` is renquant-common Job/Pipeline and fail-closes on any
  manifest missing a fingerprint (tested both ways). Exception: BT-6's
  un-lifted end-to-end reconciliation test.
- **`model_content_sha256` is genuinely unified post-M6-stage-1**: one
  engine in `renquant_common/model_fingerprint.py` re-exported via pipeline
  `panel_scorer`, consumed through that single chain by orchestrator and
  backtesting. No hand-rolled model-payload hasher remains (the residual
  risks are the inventory gaps BT-1/BT-7, and the non-model-payload XC-1).
- **Import boundaries are structurally enforced in backtesting**
  (`tests/test_import_boundaries.py` bans alpaca/ib_insync/renquant_execution/
  model-family imports); broker DB access is read-only (`mode=ro`); no
  credentials anywhere.
- **base-data blob discipline is clean** (largest tracked file 42 KB,
  CI-enforced no-large-files) and **PIT correctness is clean** — no
  lookahead found in any of the four PIT machineries; the serving-axis-clip
  lesson is properly implemented and regression-tested
  (`resolve_serving_daily_index` + `tests/test_serving_axis_decoupled.py`);
  `transformer_corpus`/`rawlabel_sidecar` keep the training/serving axis
  distinction correct.
- **base-data signal boundary is clean except BD-5**: track_b_features is
  pure causal feature computation, track_b_readiness is schema validation
  with an explicit `no_long_training_in_base_data` checklist item,
  pit_revision_features never ranks/selects by predictive power.
- **Orchestrator daily path is charter-exemplary**: `daily.py`
  Task/Job/Pipeline throughout, hard-fails on missing manifest fingerprints,
  persists `run_bundle.json` with content hashes;
  `intraday_session_scheduler` fail-closes config, refuses to run without
  the pinned pipeline contract, stamps per-tick fingerprints, atomic
  session manifests.
- **launchd plist conventions are uniform** across all 11 ops jobs; ops
  wrappers consistently run from pinned `*-run` checkouts; no hardcoded
  holiday lists anywhere in the three repos.
- **Observe-only claims verified as observe-only**: entry_timing_shadow,
  intraday_pairing_logger, realtime_data_plane, shadow_realtime_serving,
  risk_budget/, attribution/, expkit/ — no decision or submit path; expkit
  evidence manifests stamp input sha256 + git SHA + dirty flag.

## 7. Recommended fix order

1. **Before any Stage-2 arming** (blocking, not calendar-urgent while dark):
   OR-3 (allowlist + loss budget + session counter + tests), OR-8 (session
   manifest writer), OR-4 (move `decide()` to pipeline), OR-1/OR-2 (delete
   the reconciler's parallel identity/state machine in favor of
   renquant-execution imports).
2. **M6 completeness now** (cheap doc+grep changes that de-risk the live
   promote gate): BT-1 inventory amendment + step-5 grep widening, BT-7
   naming the real implementation; then the fork deletion PR.
3. **One shared writer/validator in base-data** (BD-1 + BD-4), then stamp
   the missing fingerprints/manifests mechanically (BD-2, BD-3).
4. **renquant-common lifts**: session calendar (XC-2/XC-3, table 4.1),
   `post_ntfy` (XC-4), SUE feature export (XC-5); XC-1 one-line hasher fix.
5. **The P2 tail** opportunistically, preferring deletions (XC-7 vendored
   metrics, BT-3 resolver) over new abstractions.

## 8. Method note on what was NOT audited

renquant-pipeline, renquant-execution, renquant-model, renquant-artifacts,
and the umbrella were consulted read-only as canonical references but were
not themselves audited. Severity of dark-path findings assumes the
documented default-OFF states are real (verified in tests where cited).
