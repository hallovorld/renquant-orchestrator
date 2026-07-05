# S-TC baseline methodology reference

DATE: 2026-07-05
PR: #397

## What

171-line methodology reference doc for the transfer coefficient measurement
program (tc_measurement.py, PR #391). Covers: theory (Clarke-de Silva-Thorley
2002), buy-side decision-TC methodology, population definition, admission
taxonomy, computation, category assignment, ETR complement metric, persistence
schema, canonical run selection, and known limitations.

## Why

Master plan §1 Term TC, S-TC AC requires "TC time series on the ledger;
baseline memo." This is the baseline memo component.

## Round 2 (codex review)

STATUS: fixed
WHAT: codex offered two paths — (A) keep REFERENCE status but add explicit
sensitivity language on canonical-run selection, or (B) downgrade to
DRAFT/WORKING NOTE while #391 was still settling. Chose Path A: #391 has
since merged to main after 3 rounds of correctness fixes (most recently, a
round-3 fix superseding stale rerun rows by `run_date` and making `--dry-run`
genuinely read-only), so the methodology this doc describes is now settled,
not provisional.
WHY-DIR: read the actual merged `tc_measurement.py` directly rather than
trust the review's paraphrase — confirmed `_canonical_daily_runs()` still
selects `max(created_at)` per `run_date`, and `run_measurement()` now reads
existing rows by `run_date`, deletes a stale row when a different (older)
`run_id` had measured that date, and `INSERT OR REPLACE`s the new canonical
run's row.
EVIDENCE: (1) fixed the "Persistence" section's stale `INSERT OR IGNORE on
run_id` claim, which described pre-round-3 behavior — replaced with an
accurate description of the supersede-on-rerun + read-only-dry-run logic;
(2) added a new subsection under "Canonical run selection" arguing why
`max(created_at)` is the estimator wanted (same-day reruns are evidence of
superseding an earlier attempt, not two independent observations) and what
each rejected alternative (`min(created_at)`, averaging, excluding rerun
days) would do differently, plus an explicit caveat that this is an
unvalidated assumption about pipeline behavior, not a definitional fact;
(3) added a sentence to the deduplication paragraph noting round 3 hardened
the selection rule at the persistence layer, since selection alone wasn't
sufficient. `tests/test_doc_alignment.py` passes (2/2).
NEXT: none.
