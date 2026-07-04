# M4-b: Sign-Laundering Measurement Harness

**Date:** 2026-07-04
**Sprint:** 2026-07-03 ~ 07-06 (105/106/107 engineering)
**Branch:** feat/m4b-sign-laundering-harness

## What

Measurement harness for sign laundering: names whose raw scores lie between
the calibrator's neutral point (~-0.29) and 0 receive calibrated mu of the
OPPOSITE sign. On 2026-07-01, 44/90 names (49%) were sign-laundered.

## Deliverables

- `sign_laundering_harness.py` — `measure_sign_laundering()` (single artifact)
  and `audit_laundering_history()` (DB time-series), CLI with `measure` and
  `history` subcommands, exit code 1 if laundering rate > 10%
- 25 tests covering calibrator neutral detection, score estimation, laundering
  measurement, DB history audit, and CLI
- CLI wiring: `renquant-orchestrator sign-laundering measure|history`

## Key decisions

- Read-only: never modifies scorer, calibrator, or DB artifacts
- Neutral-raw auto-detection from calibrator breakpoints, intercept/slope, or
  cross-ticker score interpolation (3-level fallback)
- DB pattern matches `transfer_coefficient.py` (read-only URI connection)
- Exit code 1 threshold at 10% laundering rate (current rate ~49%)

## References

- Master plan: M4 (sign-laundering measurement) in sprint plan
- Root cause: calibrator neutral at ~-0.29, not 0; scores in (-0.29, 0) get
  sign-flipped mu through piecewise-linear calibration
