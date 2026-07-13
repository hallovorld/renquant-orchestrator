# 2026-07-12 — Crypto session scheduler (D-C11)

## Bottom line

24/7 crypto session scheduler module implementing crypto RFC §3.5. Sessions
span one UTC calendar day. Entry gating via triple gate (config + env +
kill-switch), quiet interval (first 15 min), and signal-snapshot-digest
verification. Exits always allowed.

## What this PR contains

- `src/renquant_orchestrator/crypto_session.py` — session scheduler core:
  `SessionWindow` (UTC day boundaries), `SignalSnapshot` (immutable digest),
  `CryptoSessionConfig` (from-dict), `evaluate_tick` (triple gate + quiet +
  snapshot verification), `build_session_bundle` (run-bundle factory),
  `watermark_for_session` (bar-close watermark).
- `tests/test_crypto_session.py` — 26 tests: session windows (incl. weekend),
  signal digest determinism, triple gate (3 failure modes + pass), tick
  evaluation (6 scenarios), serialization, bundle, watermark, config, session
  date boundary.

## Key design choices

1. Exits ALWAYS allowed (even kill-switched) per §5.4 precedence
2. Fail-closed: no signal snapshot → no entries (not degraded/stale)
3. Signal snapshot date must match current session (stale snapshot rejected)
4. Triple gate re-checked every tick (config + env + file)
5. 15-min quiet interval at UTC midnight for signal computation

## Verification

- 26/26 tests pass `[VERIFIED]`
- No existing tests regressed (7 pre-existing failures unchanged) `[VERIFIED]`
- Module has no external dependencies beyond stdlib `[VERIFIED]`
