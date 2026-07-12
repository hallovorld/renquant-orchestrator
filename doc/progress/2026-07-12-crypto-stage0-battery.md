# 2026-07-12 — Crypto Stage-0 paper battery runner (D-C12)

## Bottom line

CLI script that runs the Stage-0 paper battery for crypto trading capability
verification. Checks account crypto status, snapshots pair list + increments,
tests GTC/IOC and stop-limit order acceptance, captures fee data from fills,
verifies buying power, and runs two-source data parity. Outputs structured
JSON report with PASS/FAIL/SKIP per step.

## What this PR contains

- `scripts/crypto_stage0_battery.py` — 7-step battery runner with --paper
  (required) and --dry-run modes
- `tests/test_crypto_stage0_battery.py` — 14 tests covering all steps,
  dry-run skipping, live blocking, JSON serialization

## Key design choices

1. --paper is required; live account is hard-blocked at the entry point
2. --dry-run mode skips order-placement steps (safe for CI / pre-agreement)
3. Each step is independent and produces a structured StepResult
4. Fee data captured from actual fill receipts, not assumed

## Verification

- All tests pass with mocked Alpaca client `[VERIFIED]`
- Live blocking works (paper=False → immediate FAIL) `[VERIFIED]`
- JSON output is serializable and structured `[VERIFIED]`
