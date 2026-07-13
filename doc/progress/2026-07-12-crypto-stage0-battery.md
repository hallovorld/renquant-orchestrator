# 2026-07-12 — Crypto Stage-0 paper battery runner (D-C12)

## Bottom line

CLI script that runs the Stage-0 paper battery for crypto trading capability
verification. Checks account crypto status, snapshots pair list + increments,
tests GTC/IOC and stop-limit order acceptance, captures fee data from fills,
verifies buying power, and runs two-source data parity. Outputs structured
JSON report with PASS/FAIL/SKIP per step.

## UPDATE (same day, before Codex review): step-check logic moved to renquant-execution#32

The original version of this PR imported `alpaca.trading.*`/`alpaca.data.*`
SDK types directly inside the 7 step functions. That was found and fixed
proactively (before Codex's review) for two reasons:

1. **CI was genuinely red.** This repo's CI job
   (`.github/workflows/ci.yml`) never installs `alpaca-py` — the pip
   install line lists `pytest numpy pandas scipy xgboost pyarrow pydantic
   cvxpy scikit-learn pandas_market_calendars` only. The step functions'
   deferred `from alpaca...` imports raised `ModuleNotFoundError` even
   with a `MagicMock()` client, because the SDK enum/request TYPES
   themselves (not just the client) were unavailable — surfacing as
   `ERROR` instead of `PASS`/`FAIL` in CI's actual run.
2. **Architecture violation.** This repo's own `CLAUDE.md` states a hard
   boundary: "Do not implement broker adapters here." Building Alpaca
   order requests/enums and driving the trading/data clients directly is
   broker-adapter work — it belongs in `renquant-execution`, which
   already owns all Alpaca SDK interaction elsewhere (`alpaca_broker.py`)
   and already declares `alpaca-py` as a real dependency installed in its
   own CI. Same anti-pattern Codex flagged repeatedly this cycle (e.g.
   orchestrator#481's umbrella-script issue).

Fix: the 7 step functions, the `StepResult` dataclass, and the two
Alpaca client factories moved to
`renquant_execution.crypto_stage0_checks` (renquant-execution#32),
mirroring the `software_stops_liveness` precedent
(renquant-execution#29/#30) — a broker-facing checker moves out of
orchestrator, orchestrator becomes a thin consumer. This PR now owns
**only**: CLI argument parsing (`--paper`/`--dry-run`/`--output`),
aggregating the 7 imported `StepResult`s into a `BatteryReport`, JSON
report writing, and exit-code handling.
`scripts/crypto_stage0_battery.py` and `tests/test_crypto_stage0_battery.py`
no longer reference `alpaca` anywhere (grepped to confirm) and no longer
require `alpaca-py` to be installed in this repo's own environment.

## What this PR contains

- `scripts/crypto_stage0_battery.py` — thin CLI/orchestration wrapper:
  `--paper` (required) and `--dry-run` modes, imports the 7 step
  functions from `renquant_execution.crypto_stage0_checks`, aggregates
  into a `BatteryReport`, writes the JSON report.
- `tests/test_crypto_stage0_battery.py` — 4 tests covering CLI/orchestration
  only (live-blocking, dry-run report aggregation, JSON serialization,
  `BatteryReport` counts); every imported step function is monkeypatched
  with a fake `StepResult`, so this suite needs no `alpaca-py` install at
  all. The 12 step-level tests that used to live here (per-step
  PASS/FAIL/ERROR classification) moved to
  `renquant-execution`'s `tests/test_crypto_stage0_checks.py`
  (renquant-execution#32).

## Key design choices

1. --paper is required; live account is hard-blocked at the entry point
   (unchanged — this safety property lives entirely in this repo's
   `run_battery`/`main`, never in the moved step functions)
2. --dry-run mode skips order-placement steps (safe for CI / pre-agreement)
3. Each step is independent and produces a structured StepResult
4. Fee data captured from actual fill receipts, not assumed
5. `renquant_execution.crypto_stage0_checks` is consumed via a direct
   submodule import (`from renquant_execution.crypto_stage0_checks import
   ...`), not re-exported from `renquant_execution/__init__.py` — see
   that module's docstring / renquant-execution's progress doc for the
   judgment call and why it's an easy reversal if a reviewer disagrees.

## Verification

- All tests pass with a mocked Alpaca client (execution side) / faked
  step functions (orchestrator side) `[VERIFIED]`
- Live blocking works (paper=False → immediate FAIL) `[VERIFIED]`
- JSON output is serializable and structured `[VERIFIED]`
- `grep -in "alpaca" scripts/crypto_stage0_battery.py
  tests/test_crypto_stage0_battery.py` shows only prose docstring
  mentions, no `import`/`from` statements `[VERIFIED]`
- `data/strategy_snapshot.json` regenerated via
  `python scripts/generate_strategy_snapshot.py --update`: no diff
  (this script lives under `scripts/`, outside the snapshot's tracked
  surface) `[VERIFIED]`

## Revision note (2026-07-12, after execution#34 landed its 6-point Codex fix)

execution#34 went through a full Codex CHANGES_REQUESTED round after this
PR was first opened, restructuring its public API materially: the two
order-placing checks (`_check_gtc_order_acceptance`/
`_check_stop_limit_acceptance`) became **private** — Codex's finding 4
required a single sanctioned entry point for anything that can place a
transactional probe order — and `run_full_battery(broker, *, dry_run=...)`
is now that one entry point, owning the full 6-step aggregation, the
fail-closed paper/environment verification, and the required/optional
step policy (`StepResult.required`, `BatteryReport.all_passed`) itself.

This PR's script and tests are rewritten accordingly:

1. **No more per-step imports.** The script no longer imports the
   individual `step_*` functions (which don't exist as a public surface
   anymore) — it imports `AlpacaBroker`, `BatteryReport`, `StepResult`,
   `StepStatus`, and `run_full_battery` only, and delegates the entire
   battery run to `run_full_battery`. This repo's `run_battery()` now does
   exactly two things before delegating: refuse `--paper`-less invocations
   before any broker object is created, and report a clear FAIL if the
   execution-repo dependency isn't installed yet (expected during the
   dependency-ordering window before execution#34 merges).
2. **Real `AlpacaBroker` construction.** `AlpacaBroker(paper=True)` +
   `.connect()` replaces the old standalone `get_trading_client(paper=True)`
   factory (which no longer exists in execution#34's API).
3. **`StepStatus` enum serialization.** `run_full_battery`'s `StepResult`
   now types `status` as `StepStatus` (a `str` Enum), not a plain string.
   `_step_to_jsonable`/`_report_to_jsonable` normalize via
   `getattr(status, "value", status)` so the JSON report always contains
   the plain string value regardless of whether the real enum or the
   fallback plain-string stub is in play.
4. **Fallback `BatteryReport.all_passed` now computes for real.** The
   fallback dataclass (used only when `renquant_execution` isn't
   importable) originally had `all_passed` hardcoded to `False` — caught
   by my own test suite while verifying this rewrite: since `_HAS_CHECKS`
   is resolved once at import time, patching it in a test does not
   retroactively swap the fallback classes back to the real ones, so a
   test exercising the "dependency present" path with mocked
   `run_full_battery`/`AlpacaBroker` still constructs `BatteryReport`
   through the fallback class in this repo's own dev/CI environment
   (`renquant_execution` isn't installed here). Fixed the fallback to
   mirror the real `all_passed` logic (`required=True` steps must all be
   `"PASS"`) so tests behave sensibly in both states, not just whichever
   one happens to be importable locally.
5. Test suite rewritten to match: 8 tests covering --paper live-blocking
   before broker construction, missing-dependency FAIL, broker
   construction+connection+delegation to `run_full_battery`, enum-status
   JSON serialization, and `main()`'s exit codes (argparse's own
   `required=True` on `--paper` makes a `--paper`-less CLI invocation a
   parse-time `SystemExit`, not a `run_battery`-level FAIL — verified this
   is pre-existing behavior, not something this rewrite changed, and
   adjusted the test to assert `SystemExit` rather than a return code).
- Full orchestrator suite: 3736 passed, 4 pre-existing unrelated failures
  (Python 3.9 vs `list | tuple | set` PEP-604 syntax in a sibling
  `renquant-pipeline` module, confirmed via `git stash` to pre-date this
  change), 5 skipped `[VERIFIED]`.

## Revision note (2026-07-12, after execution#34 merged — addressing Codex blockers)

execution#34 is now merged into renquant-execution main. This revision
addresses the remaining Codex blockers from the two CHANGES_REQUESTED
reviews on PR #500:

1. **Single-entrypoint API consumed** (Codex finding 2): the CLI now
   imports only `run_full_battery` (plus types) from the execution repo
   and delegates the entire battery run to it. No individual step
   functions are imported or called. This was already done in commit
   `b1fd2e5e` but is now the stable contract.

2. **Orchestration run bundle persisted** (Codex finding 4): new
   `--bundle-dir` CLI argument. When provided, the CLI writes a
   timestamped JSON bundle file containing the full `BatteryReport`,
   orchestrator commit SHA, bundle timestamp, overall verdict, and a
   SHA-256 content hash of the canonical report serialization. Written
   atomically (temp + rename) following `shadow_ab_runner` pattern.
   `build_run_bundle()` is the public function; `BUNDLE_CONTRACT_VERSION`
   is `"1.0.0"`.

3. **Versioned execution report contract** (Codex finding 3): the
   `BatteryReport` from `run_full_battery` IS the execution report
   contract. The bundle includes `report_sha256` (SHA-256 of the
   deterministic canonical JSON serialization) for tamper-evidence /
   auditability.

4. **ERROR status fails closed** (Codex finding 1, first review):
   `all_passed` only returns True when every required step has status
   PASS — an ERROR step exits nonzero. Added explicit test for this.

5. **Test coverage**: 15 tests total (up from 8). New tests cover bundle
   envelope structure, verdict logic (required vs optional failures),
   SHA-256 determinism and sensitivity, bundle-dir file persistence, and
   ERROR-only battery exit code.

### Verification

- `pytest tests/test_crypto_stage0_battery.py -v`: 15/15 pass `[VERIFIED]`
- No `alpaca.*` imports anywhere in script or tests `[VERIFIED]`

## Revision note (2026-07-12, Codex round 3 — canonical bundle + hash scope + mandatory persistence)

Addresses Codex's "ad hoc bundle format" finding. Changes:

1. **Canonical bundle documented as TODO** (Codex item 1): `build_run_bundle()`
   docstring now explicitly states this is a temporary ad-hoc format, not the
   canonical `PersistDailyRunBundleTask` / `DailyRunContext.run_bundle` schema.
   The battery lacks the required context fields (`strategy_manifest`,
   `artifact_manifest`, `decision_trace`, etc.) because it is not a daily
   training-to-trading run. Added a `.. todo::` referencing the canonical
   pattern in `daily.py` for when a multi-workflow bundle schema is introduced.

2. **Bundle mandatory for non-dry runs** (Codex item 2): `--bundle-dir` is now
   required when `--dry-run` is not set. A real battery run that completes with
   no persisted bundle is an audit gap — `parser.error()` exits before the
   battery even runs. Two new tests cover this: the failure path (missing
   `--bundle-dir` without `--dry-run` exits nonzero) and the success path
   (non-dry-run with `--bundle-dir` runs and persists).

3. **Hashes documented as corruption detection only** (Codex item 3):
   `report_sha256` docstring now says "corruption detection only — NOT
   authentication or provenance." Removed "tamper-evidence" language. The hash
   detects truncation/garbling on disk, not adversarial tampering (no signing
   key, no chain of custody).

4. **CLI marked as paper/shadow readiness work** (Codex item 3): module
   docstring now opens with "Paper/shadow readiness work only. This CLI is
   structurally unable to authorize live trading entries."

5. **Rebased onto origin/main** (Codex item 4): includes merged #501.

### Verification

- `pytest tests/test_crypto_stage0_battery.py -v`: 17/17 pass `[VERIFIED]`
- Full suite: `make test` pass `[VERIFIED]`

## Revision note (2026-07-12, Codex round 4 — first-class workflow using renquant-common primitives)

Addresses Codex's blocking architectural requirement: the battery was a
standalone CLI script bypassing `renquant-common` Task/Job/Pipeline
primitives. Now refactored into a proper first-class workflow.

### Changes

1. **New workflow module** `src/renquant_orchestrator/crypto_stage0_workflow.py`:
   - `CryptoStage0Context` dataclass: mutable context with `run_id` (UUID),
     `output_dir`, `paper`, `dry_run`, `report`, `readiness_record`, and
     `stage_trace` — follows the same pattern as `DailyRunContext` in `daily.py`.
   - `ValidateStage0InputsTask(Task)`: validates run_id, paper flag, dependency
     availability. Blocks live before any broker object is created.
   - `RunBatteryTask(Task)`: constructs paper broker, delegates to execution's
     `run_full_battery`, records elapsed time and step count in stage trace.
   - `PersistStage0ReadinessTask(Task)`: writes a scoped
     `crypto_stage0_readiness` record (named so daily/session bundles can
     compose it). Record includes: `record_type`, `schema_version`, `run_id`,
     `run_type`, `paper`, `dry_run`, `orchestrator_commit`, `timestamp`,
     `verdict`, `report_sha256`, `report`, and `stage_trace`.
   - `CryptoStage0Job(Job)` + `CryptoStage0Pipeline(Pipeline)`: chains the
     three tasks via renquant-common's sequential execution model.
   - `run_stage0_workflow()`: public entry point — creates context with
     UUID run_id, runs the pipeline, returns the populated context.

2. **CLI refactored** `scripts/crypto_stage0_battery.py`:
   - Now a thin wrapper: argument parsing, invoking `run_stage0_workflow()`,
     optional report output (stdout/file), exit-code handling. All
     orchestration logic (Task/Job/Pipeline, stage trace, persistence) lives
     in the workflow module.
   - Removed: `build_run_bundle()`, `run_battery()`, `_orchestrator_commit()`,
     `_content_sha256()`, `_write_json_atomic()`, `_step_to_jsonable()`,
     `_report_to_jsonable()`, `BUNDLE_CONTRACT_VERSION` — all moved to or
     replaced by the workflow module's primitives.

3. **Tests rewritten** `tests/test_crypto_stage0_battery.py`:
   - 29 tests (up from 17) covering:
     - `run_id` generation (UUID4 validity, uniqueness)
     - `ValidateStage0InputsTask`: missing run_id raises, live-blocked before
       broker, missing dependency FAIL, valid inputs pass
     - `RunBatteryTask`: broker construction + connection + delegation
     - `PersistStage0ReadinessTask`: readiness record schema, file persistence,
       verdict logic, SHA-256 determinism, missing report raises
     - Pipeline integration: full pipeline produces readiness record,
       short-circuits on live-blocked and missing dependency, run_id propagation
     - `run_stage0_workflow()`: auto-generates run_id, uses explicit run_id
     - CLI: argparse enforcement, exit codes (pass/fail/error), readiness
       record persistence via CLI, enum status serialization, non-dry-run
       with bundle-dir

### What the readiness record looks like

```json
{
  "record_type": "crypto_stage0_readiness",
  "schema_version": 1,
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "run_type": "crypto_stage0_battery",
  "paper": true,
  "dry_run": false,
  "orchestrator_commit": "f981cbf4...",
  "timestamp": "2026-07-12T22:00:00+00:00",
  "verdict": "PASS",
  "report_sha256": "a1b2c3...",
  "report": { "...BatteryReport fields..." },
  "stage_trace": [ "...per-stage audit records..." ]
}
```

### Verification

- `pytest tests/test_crypto_stage0_battery.py -v`: 29/29 pass `[VERIFIED]`
- Full suite: `make test`: 3881 passed, 2 skipped, 1 pre-existing unrelated
  failure (twin parity: alpaca_broker hash drift, confirmed pre-existing via
  `git stash` test) `[VERIFIED]`
