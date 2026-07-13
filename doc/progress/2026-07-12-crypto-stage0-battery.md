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
