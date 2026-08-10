# DRAFT — qp re-enable evidence prereg (issue orch#954; NOT YET FROZEN)

STATUS: DRAFT for iteration. This document becomes a freeze only when
its power section carries computed numbers and it merges under review.
Until then nothing here binds and no confirmatory computation may cite
it. The #942 operator fork is NOT decided here.

## 1. The condition being operationalized

The 05-23 record (Codex alpha-conversion fix) set
`qp_min_invested_pct = 0` + `qp_cash_drag_lambda = 0` with:
"re-enable only after WF shows benchmark-relative alpha survives the
strict admission gate." orch#945 measured `qp_min_invested_pct = 0` as
the operative lock. This prereg defines what evidence satisfies that
sentence, so the eventual strategy-104 two-knob PR cites a met
condition instead of an argument.

## 2. Estimand (one sentence)

Walk-forward, out-of-sample, net-of-costs portfolio return of the
SERVED scorer family's admission-gate-surviving selections, minus SPY
over the same days, on a window long enough that the test has
policy-grade power (§5).

Decomposition of the sentence's three components:
* "WF shows": an embargoed walk-forward split in the v2 CUTS convention
  (91-day gaps; per-row purge on the corpus's own calendar) — NOT the
  legacy run_wf folds (the model#211 embargo defect class).
* "benchmark-relative alpha": daily portfolio return of a top-k
  selection book minus SPY, net of the L2-S cost convention
  (10bps × Σ|Δh|), aggregated over the window; the statistic is the
  mean daily excess with a stationary-bootstrap CI.
* "survives the strict admission gate": selections are FILTERED by the
  admission gate as configured per the #942 resolution BEFORE portfolio
  formation — names the gate blocks do not enter the book.

## 3. The #942 fork — two frozen branches, one machinery

| branch | gate configuration | confirmatory when |
|---|---|---|
| A (repair) | trade-monotonicity stamps as designed; a served model must pass them per regime | operator picks #942(a): repair retrain/promote until a passing model serves |
| B (re-bar) | the reviewed replacement bar from the #942(b) review | operator picks #942(b) |

Identical estimand, window, costs, statistic; ONLY the gate predicate
differs. The non-chosen branch's numbers are diagnostic, never cited.

## 4. Data and non-inheritance

* Corpus: the frozen corpus + the orch#948 extension recipe; labels at
  the horizon the power section selects (§5 decides 5d-interim vs
  60d-confirmatory — the condition is about deployable capital, which
  argues for the longer horizon; the 60d extension labels realize
  ~2026-10, giving a natural confirmatory date).
* NON-INHERITANCE: orch#953's window and results informed this DESIGN;
  they may not be cited as confirmatory evidence, and any window
  overlapping #953's 05-20..07-31 must be labeled as contaminated-by-
  design-knowledge in the report.
* The serving record (`ticker_daily_state`) is admissible as the SERVED
  arm's score source per the #948/#949/#950 fidelity chain.

## 5. Power — COMPUTED 2026-08-10, and it settles the design question

Estimated on PRE-2026 data only (2023-01-01..2025-12-31, the corpus's
291-name universe, 400 seeded random held-5 books, 5-session holds):
daily excess-vs-SPY volatility of a 5-name equal-weight book
σ_d = 0.94%/day, lag-1 autocorrelation −0.016 (no material inflation)
[VERIFIED — qp_power_calc run 2026-08-10; script to be committed with
this doc's PR].

MDE at 80% power / α = 0.05 (two-sided):

| window | MDE (bps/day) | MDE annualized |
|---|---|---|
| 63d | 32.7 | **82.4%/yr** |
| 126d | 23.1 | **58.3%/yr** |
| 252d | 16.3 | **41.2%/yr** |

Detecting a PLAUSIBLE alpha (10%/yr) at this book width needs ~17
YEARS of accrual. **Conclusion: the literal reading of the 05-23
condition — statistically significant portfolio-level
benchmark-relative alpha of the ~5-name book — is NOT testable at
policy grade on any feasible window.** (The G-1 power-gate block,
recurring at the portfolio level: a 5-name book's idiosyncratic
volatility swamps any believable alpha.)

Therefore this prereg CANNOT freeze a portfolio-significance gate, and
the design fork becomes:
(a) **selection-level reinterpretation (RECOMMENDED)**: the condition's
    "WF shows benchmark-relative alpha" is testable at the
    cross-sectional level (n≈90-150 names/day × days — the #953
    machinery generalized), where power is orders of magnitude higher;
    the freeze would fix a selection-level statistic + a minimum
    effect. This REINTERPRETS a recorded condition and therefore needs
    the reinterpretation stated in the frozen doc and reviewed, not
    assumed;
(b) **policy-rule reading**: the operator accepts a non-significance
    decision rule (point estimate + guardrails + rollback) — a risk
    decision, not an evidence gate; outside this prereg's authority;
(c) **accrue**: record non-testability and revisit at a stated horizon
    (not a live option at 17-year scale).
This draft proceeds on (a) in its next revision unless review or the
operator directs otherwise; (b) remains available to the operator at
any time and is orthogonal to (a)'s evidence.

## 5b. Selection-level power (fork (a) inputs — COMPUTED 2026-08-10)

Same pre-2026 discipline (corpus z-labels 2023-2025, 400 seeded draws;
z→raw mapping from an 80-name OHLCV sample) [VERIFIED — qp-power
selection calc, committed alongside]:

| k | σ of daily mean-z statistic | MDE @63d | @126d | @252d |
|---|---|---|---|---|
| 5 | 0.443σ/day | 0.156σ | 0.110σ | 0.078σ |
| 10 | 0.310σ/day | 0.110σ | 0.078σ | 0.055σ |
| 20 | 0.215σ/day | 0.076σ | 0.054σ | 0.038σ |

z→raw: median per-day cross-sectional std of RAW 5d excess = 4.04%,
so 0.10σ/day ≈ 20.4%/yr GROSS selection alpha (median-day mapping,
pre-cost, pre-sizing — an upper bound on realizable, stated as such).

**Fork (a) is viable**: at k=5 a 126-252 trading-day evaluation has
80% power for 0.078-0.110σ/day — the same order as the served arm's
observed (diagnostic, contaminated-for-confirmation) point estimate
of +0.113σ/day in orch#953. The portfolio-level impossibility (§5)
does not recur at the selection level.

## 5c. The reinterpreted estimand (fork (a), to be frozen in rev 2)

"WF shows benchmark-relative alpha survives the strict admission gate"
is REINTERPRETED (explicitly, as a reviewed reinterpretation of the
05-23 recorded text) as: on embargoed walk-forward test folds (v2 CUTS
convention) over the corpus history EXCLUDING the contaminated
2026-05-20..07-31 window, the SERVED RECIPE's selections — the blend
construction replayed per fold (z(panel leg per WF fold) + z(momentum
leg per its frozen recipe)) and FILTERED by the admission gate per the
#942 resolution — have mean daily top-5 fwd_5d excess-z ≥ the MDE at
the realized fold-day count, with a stationary-bootstrap CI excluding
zero. Open items for rev 2 (each must be closed before freeze):
1. the momentum leg's historical replay recipe — RESOLVED FOR REV 2 as
   follows: replay the FROZEN recipe (the ledger's
   `momentum-v0-fd65161a…` params fingerprint pins it) at historical
   weekly cutoffs on the corpus calendar, mirroring the live weekly
   publish cadence; the leg is recomputed, not backfilled from
   artifacts (none exist pre-2026-08). VINTAGE CAVEAT stated in the
   frozen doc: historical OHLCV is today's vintage, not the
   as-of-then files — acceptable for a WF replay because both legs
   and the labels share one vintage, and the serving-fidelity line
   showed same-week reconstruction at 0.97+; the caveat is reported,
   not hidden. Fallback if the recipe replay fails golden checks at
   any cutoff: drop the leg for the historical window and state the
   composite degradation (z(panel) alone), reported alongside;
2. the exact gate predicate per #942 branch (unchanged from §3);
3. the realized fold-day count and therefore the numeric bar;
4. cost/turnover treatment at the selection level (report-only
   companion, since selection alpha is pre-cost by construction).

## 6. Outcome semantics

PASS ⇒ the recorded condition is met; the deliverable is a
strategy-104 PR flipping `qp_min_invested_pct` (and λ if the sweep's
zero-effect finding is revisited) THROUGH REVIEW — never a live-tree
hand-edit (containment protocol otherwise).
FAIL ⇒ the locks stay; the report states which component failed.
Either way the run publishes the full table; no silent outcomes.
