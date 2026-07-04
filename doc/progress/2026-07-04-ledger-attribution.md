# Forward-outcome observation scaffold (107 skeleton, S5 substrate)

**Date**: 2026-07-04
**PR**: (this PR)
**Master plan ref**: S5 substrate, 107 skeleton

## What

Adds `ledger_attribution.py` — a forward-outcome logging and reporting surface
co-located in the decision-ledger DB. This is an **outcome-observation scaffold**,
not a finished attribution engine: it logs realized per-ticker returns and
computes per-gate summary statistics, but does NOT enforce a join-key
relationship to ledger decisions (see Limitations below).

### Schema
- `decision_outcomes` table: one row per (as_of, scope, ticker, gate) recording
  realized forward returns at 5d/20d/60d horizons, entry/exit prices, metadata.
  Gate/verdict are free input fields — no FK to `decision_ledger`.

### API
- `write_outcomes()` — append realized outcomes (append-only, idempotent)
- `gate_value_report()` — per-gate per-verdict summary of recorded outcomes
- `gate_information_value()` — directional value signal: allow avg − block avg
- `outcome_coverage()` — per-date (as_of, scope, gate) cluster coverage ratio

### CLI
- `renquant-orchestrator gate-value [--gate G --horizon 20 --start-date --end-date]`
  — outcome summary report or single-gate directional signal

### Limitations (by design at this skeleton stage)
- No FK constraint or consistency check against `decision_ledger` rows
- The ledger has no ticker dimension; outcomes are ticker-level; the association
  is a convention of the writer, not a structural guarantee
- `gate_value_report()` reads recorded outcomes, not verified ledger decisions
- `outcome_coverage()` measures date/scope/gate cluster coverage, deliberately
  collapsing same-day reruns (see round 4 below)
- A future ledger-linked attribution layer (requiring an explicit decision→ticker
  mapping written by the pipeline) will close this gap

## Why

Substrate for the S5 AC ("fwd-outcome join >=95%") and future gate-tuning
analysis. Records per-ticker forward returns alongside the ledger so that
gate-level outcome statistics are queryable. The scaffold is useful now for
directional signals (which gates have positive VOI?) while the real
ledger-linked attribution requires the pipeline to write both sides with
an explicit mapping.

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

## Round 4 (review): run_id was added to the counter, not the evidence

Codex round 3 found round 3's own fix incomplete: `run_id` was added to the
`COUNT(DISTINCT ...)` keys on both sides, but the `LEFT JOIN` predicate was
still only `l.as_of = o.as_of AND l.scope = o.scope AND l.gate = o.gate` — no
`run_id`. So the query counted at `(run_id, scope, gate)` grain while proving
coverage only at `(as_of, scope, gate)` existence grain: one outcome cluster
still silently "covered" every same-day rerun. The round-3 regression test
(`test_outcome_coverage_counts_distinct_runs_not_collapsed`) encoded this
exact overclaim — asserting `n_covered == 2` from one outcome row shared
across two distinct `run_id`s.

**Investigated whether option 1 (carry a true per-decision identity into
`decision_outcomes` and join on it) is viable**: it is not. Traced
`decision_ledger`'s `run_id` usage (`daily_trading_health.py`:
`resolved_run_id = run_id or f"{as_of_str}-trading-health"`) — `run_id` is a
per-invocation/process identity for the gate-registry run that produced a
verdict. `decision_outcomes` rows are per-ticker *realized market returns*,
recorded independently of which run evaluated the gate; a stock's forward
return does not belong to a specific `run_id`, so there is no principled way
to attribute an outcome to run-001 versus run-002 when both fired the same
gate/scope on the same day. `decision_ledger` also has no ticker column at
all (confirmed in round 2), reinforcing that these two tables simply do not
share a join key finer than `(as_of, scope, gate)`.

**Fix (option 2 — redefine honestly)**: reverted `COVERAGE_SQL` to count
`DISTINCT gate || '|' || scope` per `as_of` (dropping `run_id` from the
counters, since it can't be joined on and was misleading). Rewrote
`outcome_coverage()`'s docstring to state explicitly: this measures
date/scope/gate *outcome-cluster* coverage, not per-decision or per-run
coverage; same-day reruns of the same gate/scope are deliberately collapsed
because `decision_outcomes` cannot distinguish them. Replaced the round-3 test
with `test_outcome_coverage_collapses_same_day_reruns_by_design`, which
asserts the HONEST behavior (`n_verdicts=1`, `n_covered=1` for two same-day
reruns sharing one outcome) and documents in its docstring why asserting
`n_covered=2` would be the overclaim.

1963/1963 relevant repo tests pass, 15/15 attribution tests pass (2
pre-existing failures in `test_bundle_consistency_ci_gate.py` reproduce
identically on a clean `origin/main` checkout — unrelated to this change).

## Round 5 (review): attribution claims ahead of data model

Codex round 4 pointed out a deeper architectural gap: `gate_value_report()` and
`gate_information_value()` read directly from `decision_outcomes` without
joining to `decision_ledger` — there is no enforced relationship, no
foreign-key check, and no validation that outcome rows are consistent with
what the ledger actually recorded. The module docstring and progress doc
claimed "ledger-linked attribution" but the data model doesn't support it:
`decision_ledger` has no ticker dimension, `decision_outcomes` is ticker-level,
and gate/verdict in outcomes are free input fields.

**Fix (option 2 — narrow scope)**: rewrote the module docstring to describe
this as a "forward-outcome observation scaffold," not an "attribution engine."
Explicitly documents:
  - no foreign-key or consistency check against ledger decisions
  - gate/verdict in outcomes are writer-convention, not structural guarantees
  - `gate_value_report` measures recorded outcomes, not verified ledger joins
  - a future ledger-linked attribution layer (requiring an explicit
    decision→ticker mapping written by the pipeline) will close this gap

Updated `gate_value_report()` and `gate_information_value()` docstrings to
state they read from outcomes directly, not from a verified ledger join.
No API or schema changes — the code is useful as-is, only the claims were
overstated.

15/15 attribution tests pass.
