# Decision-ledger attribution engine (107 skeleton, S5)

**Date**: 2026-07-04
**PR**: (this PR)
**Master plan ref**: S5 (fwd-outcome join >=95%), 107 skeleton

## What

Adds `ledger_attribution.py` — the forward-outcome tracking and per-gate
value-add analysis engine that extends the S2 decision ledger:

### Schema
- `decision_outcomes` table: one row per (as_of, scope, ticker, gate) recording
  realized forward returns at 5d/20d/60d horizons, entry/exit prices, metadata

### API
- `write_outcomes()` — append realized outcomes (append-only, idempotent)
- `gate_value_report()` — per-gate per-verdict report: n, avg_fwd_ret, hit_rate
- `gate_information_value()` — single-gate VOI: allow_avg_ret − block_avg_ret
- `outcome_coverage()` — per-date join ratio (S5 AC: >=95% for aged decisions)

### CLI
- `renquant-orchestrator gate-value [--gate G --horizon 20 --start-date --end-date]`
  — full report or single-gate VOI

## Why

The decision ledger records WHAT each gate decided. This module records WHAT
HAPPENED NEXT. The join enables: "did blocking GOOG on 07-02 save money?"
"is P-WF-GATE adding value?" — the attribution query that makes gate tuning
evidence-based instead of opinion-based.

## Tests

12 new tests covering: write/idempotency, value report (basic + filtered),
gate VOI computation, outcome coverage, multiple horizons, metadata.
All 1927 tests pass.

## Round 2 (review): coverage-ratio grain-mismatch bug

Codex found a real correctness bug in `outcome_coverage()`: the denominator
counted distinct `gate|scope` pairs per date (the ledger's own grain —
`decision_ledger`'s PK is `run_id/scope/gate`, it has **no ticker column at
all**), while the numerator counted distinct `gate|scope|ticker` triples from
`decision_outcomes` (which is ticker-level — one gate/scope/date decision can
have many ticker outcomes attached). Any date where a single covered ledger
row had outcomes for >1 ticker inflated `coverage_ratio` above 1.0 — not
merely a display quirk, a mathematically meaningless metric feeding the S5
`>=95%` acceptance criterion.

**Root cause confirmed**: the ledger has no per-ticker decision rows to join
against at that grain (matching grains via ticker-level ledger rows is not
available; the schema doesn't carry a ticker dimension). **Fix**: redefined
`n_outcomes`/`coverage_ratio` at the ledger's own `(gate, scope)` grain on
*both* sides — `n_outcomes` now counts distinct ledger rows that have **at
least one** matching outcome (an existence check via `CASE WHEN o.gate IS
NOT NULL`), not a per-ticker outcome count. `coverage_ratio` is bounded to
[0, 1] by construction since the numerator is now a subset-count of the
denominator, never an independently-larger population.

Added 2 regression tests proving boundedness (`test_outcome_coverage_bounded_with_multi_ticker_outcomes`:
multiple tickers on one covered gate → ratio stays 1.0, not inflated;
`test_outcome_coverage_partial_when_gate_missing_outcomes`: one of two gates
covered → ratio is 0.5) and tightened the original coverage test to assert
`0 <= coverage_ratio <= 1.0` generally.

**No claim in this doc depended on a specific coverage-ratio number** (the
`>=95%` S5 AC is a target for the real, aged-decision production ledger, not
a number this PR asserted was already achieved) — the fix does not retract
any prior stated result, only corrects the metric's definition so that
number will be meaningful once measured against real data.

1931/1931 relevant repo tests pass (2 pre-existing failures in
`test_bundle_consistency_ci_gate.py` reproduce identically on a clean
`origin/main` checkout — unrelated to this change).

## Round 3 (review): run_id grain not carried through

Codex round 2 found that the coverage query still collapsed same-day reruns:
`decision_ledger` PK is `(run_id, scope, gate)`, but coverage counted only
`DISTINCT gate || '|' || scope` — two runs on 07-01 with the same gate/scope
were one denominator entry, not two.

**Fix**: both sides now count `DISTINCT run_id || '|' || gate || '|' || scope`,
matching the ledger's actual PK grain. Column renamed `n_outcomes` → `n_covered`
to reflect that the numerator counts covered *decisions*, not outcome rows.

Added `test_outcome_coverage_counts_distinct_runs_not_collapsed`: two runs on
the same date with the same gate/scope → `n_verdicts` = 2, `n_covered` = 2,
`coverage_ratio` = 1.0.

15/15 attribution tests pass.
