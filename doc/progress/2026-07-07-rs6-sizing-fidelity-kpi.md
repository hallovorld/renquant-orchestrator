# 2026-07-07 — RS-6 sizing-fidelity KPI baseline

**PR**: follow-up orchestrator KPI work for 104/105 cash-drag program

## What

Added a new `sizing_fidelity` metric to `scripts/kpi_scorecard.py`, owned by
orchestrator because it is a standing read-only measurement surface rather
than strategy logic, pipeline sizing logic, or broker execution behavior.

The metric reports, on the latest canonical FULL live run:

- `median_gap` and `p90_gap` for accepted buy entries
- raw `n_size_insufficient_cash` baseline from `candidate_scores.blocked_by`
- explicit blockers for still-unstamped active-path fields:
  - one-share-floor roundup counts / overshoot notional
  - fractional-book percentage
  - fractionable-subset-only zero-drop count

## Why

The cash-drag design RFC merged the execution order, but orchestrator still
needed the standing scoreboard promised for fractional-shares Phase 1.

Today the active path does **not** yet stamp `target_notional`, `sizing_mode`,
or `size_floor_reason` directly into the live runs DB, so the scorecard now:

1. computes what is already provable from the current schema, and
2. labels the rest `unavailable` instead of inferring or faking it.

That gives us a truthful daily baseline now, while preserving the future
acceptance contract the fractional stage will need.

## Notes

- `target_notional` is currently a **schema proxy**:
  `kelly_target_pct * portfolio_value`
- this is intentionally called out in the metric method text
- once active-path stamping lands in the owning repos, the scorecard can
  tighten from proxy to direct contract without changing ownership

## Current baseline (real run, as_of 2026-07-07)

Generated scorecard: `doc/research/evidence/kpi_scorecards/kpi_2026-07-07.json`

- latest canonical full run: `2026-07-02-live-85496d1c`
- `sizing_fidelity.value` / `median_gap`: **0.6957**
- `p90_gap`: **0.6957**
- `n_entries`: **1**
- raw `n_size_insufficient_cash`: **2**
- current measured buy gap came from `GRMN`:
  - target notional proxy: `787.8884`
  - realized notional: `239.76`
  - gap: `0.6957`

That is exactly the kind of standing evidence the cash-drag plan needed:
the deployment problem is still materially a sizing-fidelity problem on the
latest canonical baseline, not just a vague “high cash” symptom.
