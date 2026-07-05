# Attribution + risk-budget test coverage (2026-07-04)

## What

Added 149 unit tests across the attribution and risk-budget packages:

- `tests/test_attribution_report.py` (49 tests, new) — coverage_report,
  rollup, render_markdown, _check_out_dir, write_report
- `tests/test_attribution_bridge.py` (29 tests, new) — _in_window,
  _aggregate, leg_dd_consumption (mocked)
- `tests/test_risk_budget.py` (+65 tests, added to existing 34) —
  build_budgets, resolve_strategy_config, load_strategy_risk_controls,
  read_sleeve_shadow edge cases, running_drawdown recovery, burn_rate
  arithmetic, concentration sector weights, realized_beta zero-variance,
  per_name_betas, beta_composition, _fmt, _check_out_dir, write_statement,
  render_markdown sections

## Why

The attribution/ and risk_budget/ packages (107 sprint D3 deliverables)
had ~946 lines of code with only 34 tests, all in the risk_budget integration
test. Pure-function coverage was thin — censoring edge cases, boundary
conditions, and the report rendering paths were untested.

## Test count

2278 → 2427 (+149). All passing.

## Modules covered

| Module | Lines | Tests before | Tests after |
|---|---|---|---|
| attribution/report.py | 255 | 0 | 49 |
| risk_budget/attribution_bridge.py | 112 | 0 | 29 |
| risk_budget/budget.py | 655 | 34 | 67 |
| risk_budget/report.py | 549 | (shared above) | (shared above) |
