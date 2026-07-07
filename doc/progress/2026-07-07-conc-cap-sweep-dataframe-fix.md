# 2026-07-07 — Fix concentration cap sweep DataFrame truth-value crash

**PR**: orchestrator bugfix

## What

Fixed `ValueError: The truth value of a DataFrame is ambiguous` in
`run_concentration_cap_sweep.py:465`. The pattern `getattr(result,
"equity_df", []) or []` fails when `equity_df` is a non-empty DataFrame
because pandas doesn't support `bool(df)`.

## Why

The sweep crashes immediately after completing its first full backtest
run (sim date reaches 2026-03-28, then result extraction fails).
Without this fix, the 75-variant concentration cap sweep cannot execute.

## Fix

Replace `X or []` with explicit `None` checks:
- `eq_df = getattr(..., None); len(eq_df) if eq_df is not None else 0`
- Reuse already-extracted `trade_log` variable instead of repeating the
  unsafe pattern

## Scope

2 lines changed in `scripts/run_concentration_cap_sweep.py`. No behavior
change — same values computed, just without the crash.
