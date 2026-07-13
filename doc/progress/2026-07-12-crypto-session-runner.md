# 2026-07-12 feat(crypto): session runner + launchd plist

## What

Minimal CLI runner for the crypto session scheduler (D-C11) and a launchd
plist template for 24/7 paper-mode operation.

## Components

- `scripts/crypto_session_runner.py` — thin CLI wrapping `evaluate_tick`:
  - `--once` (default): single tick, exits
  - `--loop --interval N`: daemon mode
  - `--config`: JSON config file, defaults to `CryptoSessionConfig(enabled=True, mode="paper")`
  - Logs each tick as JSON to stdout and `data/crypto/session_logs/session_YYYY-MM-DD.jsonl`
- `deploy/com.renquant.crypto-session.plist` — launchd template, 900s interval,
  `RunAtLoad=false`. Template only; arming is a separate operator landing step.
- `tests/test_crypto_session_runner.py` — 7 tests covering config loading,
  single tick, log file writing, loop mode

## Deployment note

Entries are currently structurally blocked by
`ENTRY_AUTHORIZATION_TRUST_ANCHOR_READY=False` in `crypto_session.py`.
The scheduler will run, evaluate gates, and log results, but will not
authorize any entries until the trust anchor is wired. This is by design.

## Evidence

- 7 new tests pass
- 3901 total pass (twin parity expected fail; one battery test has a
  pre-existing ordering sensitivity in the full suite)

## PR

- orchestrator (on branch pr-148)
