# Wire risk_budget.report into CLI

**Date:** 2026-07-05
**Status:** Ready for review

## Summary

Adds `risk-budget-report` subcommand to the orchestrator CLI, delegating
to `risk_budget.report.main()` via the standard REMAINDER pass-through
pattern. The module was previously unreachable from the CLI despite having
a complete `main()` entry point and test coverage.

## Changes

- `src/renquant_orchestrator/cli.py`: Added parser + dispatch for
  `risk-budget-report` (REMAINDER delegation).
- `data/strategy_snapshot.json`: Updated baseline to include new subcommand.

## Test results

2888 passed, 2 skipped, 0 failures.
