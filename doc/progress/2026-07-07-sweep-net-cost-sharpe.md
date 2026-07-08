# 2026-07-07 — concentration-cap sweep: make criterion 1 genuinely net-of-cost

**PR**: fix(sweep): evaluate BULL_CALM Sharpe net of modeled cost

## Problem

`scripts/run_concentration_cap_sweep.py` claimed to implement the approved
research contract from `doc/design/2026-07-06-concentration-cap-research.md`,
where criterion 1 is explicitly **BULL_CALM Sharpe net of transaction cost**.

But the runner was still comparing the gross regime Sharpe while only reporting
turnover and a modeled cost proxy on the side. That made the verdict wording
stronger than the actual implementation.

## Change

- derive a per-seed modeled total cost fraction from the existing turnover proxy
- spread that modeled drag across the seed's days as an explicit daily cost drag
- compute `sharpe_net_of_cost` for each regime, alongside the gross Sharpe
- stamp `sharpe_net_of_cost` at the full-period seed row too for auditability
- switch criterion 1 to compare the BULL_CALM `sharpe_net_of_cost` field
- add regression tests proving the verdict fails when gross Sharpe improves but
  net-of-cost BULL_CALM Sharpe regresses

## Why this is the right fix

This does **not** pretend the sim has a first-class commission/slippage model
it does not actually have. The runner remains honest: the cost term is a
modeled proxy derived from turnover, but the verdict now at least evaluates the
same modeled net-of-cost object the research design says it is evaluating.

That keeps Phase 2 from promoting a candidate on a gross-Sharpe win that
disappears once the study's own churn penalty is applied.

## Verification

- `python -m pytest tests/test_run_concentration_cap_sweep.py -q`
  - `23 passed`
