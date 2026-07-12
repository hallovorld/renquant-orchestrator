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
