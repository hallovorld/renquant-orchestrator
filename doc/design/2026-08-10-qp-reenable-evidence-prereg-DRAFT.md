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

## 5. Power (MUST be computed BEFORE this freezes — currently absent)

The G-B lesson (orch#917): no gate whose reachable power at a plausible
MDE is ≈ α. Required before freeze:
1. variance of daily benchmark-relative selection returns estimated on
   PRE-2026 data only (no peeking at the candidate window);
2. MDE at 80% power / α=0.05 for candidate window lengths (63d / 126d /
   252d), stationary-bootstrap test as in §2;
3. the freeze then fixes ONE window length whose MDE is economically
   meaningful (a bar stated in annualized bps, chosen and justified in
   this section), or — if no feasible window reaches that — this
   document records that the condition is NOT currently testable at
   policy grade and states what accrual period would make it so.

## 6. Outcome semantics

PASS ⇒ the recorded condition is met; the deliverable is a
strategy-104 PR flipping `qp_min_invested_pct` (and λ if the sweep's
zero-effect finding is revisited) THROUGH REVIEW — never a live-tree
hand-edit (containment protocol otherwise).
FAIL ⇒ the locks stay; the report states which component failed.
Either way the run publishes the full table; no silent outcomes.
