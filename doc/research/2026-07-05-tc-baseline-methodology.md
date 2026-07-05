# S-TC baseline methodology — transfer coefficient measurement

DATE: 2026-07-05
STATUS: REFERENCE (methodology documentation for the TC measurement program)

## Theory

The Grinold-Kahn fundamental law of active management decomposes information
ratio as:

    IR = TC × IC × √BR

where TC (transfer coefficient) = corr(w_unconstrained, w_constrained) measures
how much of the model's information survives the portfolio construction stack.
A TC of 0.4 means 60% of the model's cross-sectional signal is lost to
constraints (position limits, sector caps, correlation caps, whole-share
rounding, cash constraints, etc.).

Source: Clarke, de Silva, Thorley (2002) "Portfolio Constraints and the
Fundamental Law of Active Management."

## Implementation history

Three artifacts exist, each building on the previous:

1. **POC** (`scripts/poc_transfer_coefficient.py`, PR #234, 3 Codex review
   rounds) — exploratory diagnostic; two measurements (full-book + buy-side
   decision-TC); 12 tests. Not scheduled.

2. **transfer_coefficient.py** (PR #305, merged) — TC = corr(kelly_target_pct,
   qp_target_w) per run from candidate_scores. CLI via `rq-tc`. Measures the
   QP-stage transfer specifically.

3. **tc_measurement.py** (PR #391, under review) — standing daily batch job
   computing buy-side decision-TC per canonical run, persisting to
   `decision_ledger.db::tc_metrics`. Evolution of the POC methodology.

## Buy-side decision-TC methodology (tc_measurement.py)

### Population

For each canonical daily run (one per run_date, latest `created_at`):

1. **Eligible candidates**: `role='candidate' AND mu >= 0.03 AND
   kelly_target_pct IS NOT NULL`. Minimum 4 eligible to proceed.

2. **Admission taxonomy** (3-round refinement, derived from pipeline writer
   code — not guessed from string values):

   | Category | `blocked_by` values | Pipeline stage |
   |---|---|---|
   | PRE_SELECTION | wash_sale, sector, correlation, tier, defensive_non_bear, candidate_not_selected | Before sizing (selection.py::run_selection_loop) |
   | SIZING_FAILED | buy_blocked, skip_buys, size_bad_price, size_insufficient_cash, size_cash_invariant, kelly_zero:capped_zero, bear_defensive_slot_cap, bear_defensive_insufficient_cash | After selection (task_selection.py::SizeAndEmitTask) |
   | SELECTED_SUBMITTED | broker_pending_submitted | Selected + submitted; fill unconfirmed at trace time |
   | BROKER_OUTCOME | broker_skip:* | Post-selection broker-stage skip |
   | UNCLASSIFIED | anything else | Excluded from both sides |

3. **Sizing population** (`n_survived_admission`): everyone EXCEPT
   `pre_selection_blocked` and `unclassified`. Minimum 4 to proceed.

4. **Correlation population** (`n_corr_population`): sizing population MINUS
   `selected_submitted` names with no confirmed fill (their true delivered
   weight is unknown, not zero).

### Computation

- **w_star** = `kelly_target_pct` (the model's unconstrained Kelly weight)
- **w_actual** = `target_pct` from `trades` table for buy actions; 0.0 for
  names in the correlation population that were not bought

TC = Pearson corr(w_star, w_actual) over the correlation population.

### Category assignment

Each run gets exactly one category:

| Category | Condition | TC reported |
|---|---|---|
| `insufficient_sizing_population` | < 4 names survived admission | None |
| `insufficient_corr_population` | < 4 in correlation population | None |
| `no_deployment` | 0 buys in corr population | None |
| `zero_dispersion` | All buys at same target_pct (Pearson undefined) | None |
| `measured` | Genuine Pearson correlation computable | Yes |

Only `measured` runs enter the rolling mean/SE.

### Exposure transfer ratio (ETR)

Complement metric for magnitude sensitivity. Pearson TC is scale-invariant —
it cannot detect uniform deployment shrinkage (if w_actual = k × w_star for
constant k, Pearson reads 1.0 regardless of k).

ETR = dot(w_actual, w_star) / dot(w_star, w_star)

This is the OLS-through-origin slope: if w_actual is a uniformly shrunk copy
of w_star, ETR ≈ k. Reported alongside, never instead of, TC.

### Persistence

Results are appended to `decision_ledger.db::tc_metrics` (WAL mode, busy
timeout 5s). Schema:

```sql
CREATE TABLE tc_metrics (
  run_id TEXT PRIMARY KEY,
  run_date TEXT NOT NULL,
  category TEXT NOT NULL,
  buy_side_tc REAL,
  exposure_transfer_ratio REAL,
  n_eligible INTEGER NOT NULL,
  n_survived_admission INTEGER NOT NULL,
  n_corr_population INTEGER NOT NULL,
  n_bought INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Supersede-on-rerun, not append-only: each write reads existing rows keyed
by `run_date` (not `run_id`) before persisting. If the canonical run for a
`run_date` is unchanged from the last write, the run is a no-op. If a later
rerun has become the new canonical run for a date that was already measured
under an older `run_id`, that date's row is deleted before the new row is
inserted (`INSERT OR REPLACE`) — so `tc_metrics` never holds two rows for
the same trading day, and the rolling mean/SE cannot double-count a date.
This closed a round-3 Codex review finding on #391, where an earlier
`INSERT OR IGNORE`-on-`run_id` scheme would leave both the old and new
run's rows in place for the same date.

`--dry-run` reads existing rows through a separate, genuinely read-only
SQLite connection (`mode=ro` URI) and skips the write path entirely — it
cannot create or alter `decision_ledger.db`, even if the file doesn't yet
exist. This was also a round-3 finding: an earlier `--dry-run` still opened
the ledger read-write, enabled WAL, and ran `_ensure_table()`, which could
create/alter the file despite the "compute but don't persist" contract.

## Canonical run selection

A "canonical daily run" is defined as:

1. `run_id LIKE '%-live-%'` (live runs only)
2. `>= 80` candidate_scores rows (MIN_FULL_RUN_CANDIDATES — excludes partial
   or test runs)
3. One per `run_date`: the row with max `created_at` (last completed run that
   day supersedes an earlier same-day attempt)

This deduplication was added in round 2 to fix double-counting on dates with
multiple runs (e.g., 2026-06-09 had two entries in the raw pipeline_runs
table). Round 3 further hardened this at the persistence layer (see
"Persistence" above): the selection rule alone was not sufficient, because a
LATER rerun replacing an EARLIER same-day run as canonical would previously
still leave the earlier run's already-written row in `tc_metrics`. The
selection rule decides which run is canonical; the persistence layer must
separately enforce that only that run's row survives.

### Why `max(created_at)`, and what else was considered

`max(created_at)` — the last completed run for a trading day — is the
estimator wanted for the baseline because a same-day rerun in this pipeline
is evidence that the earlier attempt was superseded, not that both attempts
are independent, equally-valid observations of that day's decision-TC. Same-
day reruns arise from operational recovery (a crashed or partial run
restarted) or a corrected input being re-fed through the pipeline after the
first attempt; in both cases the earlier attempt's `trades` rows reflect a
run whose fills either never happened as intended or were superseded by the
rerun's own submissions. Treating the earlier attempt as a second, valid
data point would silently measure decision-TC against a stale, non-canonical
version of that day's actual portfolio actions.

Alternative selection rules considered and rejected:

- **`min(created_at)` (first run of the day)**: would measure TC against
  whichever attempt happened to run first, even when that attempt was the
  one that got aborted or corrected — the opposite of "the run whose fills
  actually reflect that trading day."
- **Average across all same-day runs**: would blend a superseded attempt's
  `w_actual` (fills that may not reflect the day's final book) with the
  canonical run's, diluting the signal with data from an attempt the
  pipeline itself effectively discarded. It would also make `n_survived_admission`
  and `n_corr_population` ambiguous — averaged over what population?
- **Exclude days with any rerun**: the simplest way to sidestep the
  ambiguity, but at current sample sizes (see limitation 1 below) this would
  discard a nontrivial fraction of the already-small `measured` set for no
  benefit over just picking the canonical run correctly.

`max(created_at)` is not a purely definitional choice — it is a claim, still
unvalidated at n=4 `measured` runs, that same-day reruns in this pipeline are
reliably "correction of an earlier attempt" and not "two independently
meaningful decisions on the same day." If a future operational pattern
emerges where legitimate same-day reruns represent genuinely distinct
decisions (e.g., an intentional midday re-run to react to new information,
not a recovery from a crash), this selection rule would need revisiting.

## Known limitations

1. **Small sample**: as of 2026-07-02, only 4 `measured`-category runs exist
   (mean TC = 0.288, SE = 0.167, n=4). Far too small for a stable estimate.
   The standing job accumulates more observations automatically.

2. **No full-book same-day TC**: the POC's full-book measurement pairs live
   broker positions against the latest run's desired vector — a cross-day
   pairing (explicitly flagged `same_day_aligned: false`). A genuine
   same-timestamp measurement requires the S5 decision ledger to persist
   per-run position snapshots.

3. **Taxonomy completeness**: the `_classify_reason` taxonomy covers all
   `blocked_by` values observed in the data through 2026-07-02
   (`n_unclassified = 0` on every run). New pipeline reasons would fall to
   `unclassified` and be excluded from both populations — safe by default but
   requiring taxonomy updates.

4. **Kelly-target vs QP-target**: `tc_measurement.py` measures TC against
   `kelly_target_pct` (unconstrained intent). `transfer_coefficient.py` (PR
   #305) measures against `qp_target_w` (QP-constrained weight). These are
   complementary: kelly→actual captures the FULL stack; kelly→qp captures
   the QP optimizer specifically.

## Readiness monitor integration

`readiness_monitor.py` check `S_TC_baseline` requires ≥10 `measured`-category
sessions before reporting READY. This gates downstream automation that depends
on a stable TC baseline.

## Cross-references

- POC script: `scripts/poc_transfer_coefficient.py`
- POC progress (3 rounds): `doc/progress/2026-07-02-s-tc-measurement.md`
- QP-stage TC module: `src/renquant_orchestrator/transfer_coefficient.py`
- Standing measurement: `tc_measurement.py` (PR #391)
- Unified master plan TC term: #231 §1
