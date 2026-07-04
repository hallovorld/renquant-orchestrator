# Progress: decision-ledger attribution engine (107 sprint D3)

Date: 2026-07-03 · Branch: `feat/attribution-engine`
Design note: `doc/design/2026-07-03-attribution-engine.md`.

## What landed

`src/renquant_orchestrator/attribution/` — ledger read model
(candidate_scores + trades + pipeline_runs + ticker_forward_returns, all
read-only), the SIGNAL/TIMING/SIZING/COST(+MARKET) decomposition identity
with enforced ~0 residual, and the report CLI
(`python -m renquant_orchestrator.attribution.report`) emitting markdown +
JSON rollups (per-leg totals, per-month/per-regime, leak ranking) plus a
first-class coverage/censoring report.

Extends #145's class-level forward-return attribution
(`decision_pnl_attribution`, untouched); adds the per-decision dollar
decomposition #145 explicitly deferred ("once orders carry a decision_id and
realized P&L is written back").

## First real read (live stream, 2026-07-03; details in design note)

99 decision records: 24 fully decomposable, 64 open mark-to-market, 15
unmatched exits, 30 censored by the #253 fill-confirmation gap (2026-06-09→).
On the decomposable era: SIZING is the largest measurable leak (−$1,182 /
25 records); TIMING nets +$180 (small n; per-entry slippage diagnostics in
the JSON). Numbers are era-bounded reads, not book-level claims — per-leg
populations differ under censoring.

## Verification

23 new tests in `tests/test_attribution_engine.py`: identity sum-check with
each leg isolated + 200-case fuzz, censoring representation (no imputation),
seeded live-schema fixtures (dedupe, cross-day re-record collapse,
shares-conflict censor, intervening-exit guard, open-position MTM), and a
read-only real-DB smoke (mtime asserted unchanged). Full suite green.

## Follow-ups (not this PR)

- Umbrella fill-confirmation writer (#253 precondition) to un-censor the
  June-era TIMING/SIZING/COST legs.
- `ticker_forward_returns` close gaps 2026-05-03→05-17 (19 records lose
  their reference price) — backfill candidate.
- S5 ledger wiring will make this continuous instead of backfilled.
