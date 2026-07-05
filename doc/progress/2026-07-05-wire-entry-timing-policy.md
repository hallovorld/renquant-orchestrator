# 2026-07-05 Wire entry_timing_policy into CLI

## What

Added `entry-timing` subcommand to the orchestrator CLI, delegating to
`entry_timing_policy.main(argv)` using the standard REMAINDER pass-through
pattern (same as `sign-laundering`, `gate-calibration`, etc.).

## Why

The `entry_timing_policy` module (1083 lines, sprint 105 D2) implements
shadow-evaluated entry-timing strategies with `report` and `replay` sub-
commands. It had a `main()` entry point and tests but was not wired into
the CLI, making it unreachable via `renquant-orchestrator entry-timing`.

## Changes

- `src/renquant_orchestrator/cli.py`: added `entry-timing` subcommand
  definition (REMAINDER delegation) and dispatch handler.
- `data/strategy_snapshot.json`: regenerated to include `entry-timing`
  (CI snapshot consistency gate).

## Verification

`make test` -- 2888 passed, 2 skipped.
