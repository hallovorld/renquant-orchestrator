# 2026-07-07 — 105 cash-drag shadow scorecard

STATUS: implemented in orchestrator as a read-only observability surface. No
live behavior, sizing logic, or broker path changes.

## What ships

- `src/renquant_orchestrator/intraday_cash_drag_scorecard.py`
- `tests/test_intraday_cash_drag_scorecard.py`

The scorecard reads `logs/renquant105_pilot/intraday_decisions_shadow.jsonl`
and summarizes only the cash-drag signals the current 105 contract exposes
honestly:

- close idle-cash fraction (`cash / equity` on the latest tick),
- final envelope counters (`entries_count`, `deployed_notional`,
  `turnover_notional`),
- recorded skip counts for:
  - `zero_quantity_after_whole_share_floor`
  - `insufficient_available_cash`

## Why this belongs here

This is orchestrator-owned evidence plumbing over existing shadow-run artifacts.
It does not change scoring, sizing, gating, or execution internals.

## What it does NOT claim

Current 105 intraday logs do **not** expose pre-quantization sizing intent
(`target_notional`). Therefore this scorecard explicitly records the following as
unavailable contract fields instead of fabricating them:

- `target_notional`
- `true_zero_drop_pre_quantization`

That keeps the repo boundary clean:

- `renquant-pipeline` must expose 105 pre-quantization sizing intent if we want
  a true zero-drop / target-vs-realized diagnostic.
- `renquant-orchestrator` can then persist and score that contract.
