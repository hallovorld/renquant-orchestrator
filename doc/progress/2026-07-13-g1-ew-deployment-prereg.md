# 2026-07-13 G1: equal-weight deployment pre-registration design

## What

Filed `doc/design/2026-07-13-equal-weight-deployment-prereg.md` — a
pre-registration RFC for testing equal-weight top-k sizing against the
status-quo Kelly-based sizing path.

## Why

The D6 confirmatory replay (PR #466) rejected the deployment governor but
found `equal_weight_top_k` beat every governor arm by +9.3%. This is a
hypothesis, not a verdict — single regime block, no BEAR/CHOPPY coverage.
The prereg locks down the evaluation protocol BEFORE any data is examined.

## Key design decisions

- Two arms only (status quo vs equal-weight); NO adaptive components
- 6-gate frozen go/no-go rule (p-value + regime coverage + drawdown +
  turnover + concentration + OOS confirmation)
- Minimum 40 shadow trading days with regime coverage requirement
- Historical replay on held-out window (D6 data excluded)
- Newey-West HAC for dependent returns

## Next steps

1. Operator review of the RFC design
2. If approved: implement shadow telemetry (D2)
3. Shadow accumulation period (~40+ trading days)
4. Evaluation + result memo
