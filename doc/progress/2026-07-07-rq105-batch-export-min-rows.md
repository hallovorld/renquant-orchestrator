# 2026-07-07 — Fix rq105 batch-scores-export MIN_ROWS gate

**PR**: orchestrator fix

## Problem

rq105's entire intraday pipeline has been broken since at least 07-03:
- `batch-scores-export` refuses to export because no 07-06 run meets `MIN_ROWS=80`
- Without batch scores, `shadow-serving` fails (missing required inputs)
- Without shadow serving, no intraday observation data is collected

## Root cause

`MIN_ROWS = 80` is an absolute floor in the SQL query that selects qualifying
daily runs. But the actual pipeline typically scores 35-84 candidates (out of
145 watchlist), depending on alpha158 feature data availability. In the last
20 trading days, **12 out of 20** fell below 80 — the gate rejects more runs
than it accepts.

Historical scored-candidate counts:
```
07-06: 35  <<<
07-02: 83
07-01: 83
06-30: 83
06-29: 43  <<<
06-26: 79  <<<
06-25: 76  <<<
06-24: 73  <<<
```

The real quality gate is `MIN_COVERAGE_FRACTION = 0.9` (90% of the run's own
candidate roster must have non-null scores). But the SQL `HAVING n >= 80`
kills runs before they reach the coverage check.

## Fix

Lower `MIN_ROWS` from 80 to 30. This is the floor for "non-trivially-empty
run" (rejects partial writes / ghost runs). The meaningful quality gate
remains `MIN_COVERAGE_FRACTION = 0.9`.

## Separate issue (NOT fixed here)

`shadow-serving` also fails because `--feature-snapshot-json` is a required
CLI arg but no producer exists. The feature snapshot file is never created.
This is a design gap that needs its own PR.

## Scope

1 line changed in `ops/renquant105/export_batch_scores.py`.

## Round 2 (codex review)

STATUS: fixed
WHAT: `MIN_COVERAGE_FRACTION`'s denominator is the run's OWN persisted
`role='candidate'` roster (self-referential, per the module's own
docstring), not an external expected-universe count. That makes `MIN_ROWS`
the ONLY protection against a partial/degraded run whose truncated roster
happens to be internally 100% scored — the coverage gate alone would pass
such a run trivially. Lowering `MIN_ROWS` to 30 off an 8-session sample
therefore risked weakening that protection, and separately, 30 was itself
not safely justified by the sample it cited.
WHY-DIR: investigated whether a real expected-universe check (e.g. the
145-name watchlist from `strategy_config.json`, following the exact pattern
`readiness_monitor.py` already uses for its own coverage check) could
replace the self-referential denominator — rejected this after finding the
pipeline legitimately scores only 24-58% of the watchlist on ordinary days
(alpha158 feature-data availability, not a defect; the historical
35-84-candidate range in this doc's own Root Cause section IS that legitimate
range). Requiring 90% watchlist coverage would reject every real run, so
Option 1 (a true completeness check) does not fit this specific pipeline;
this residual gap is the same one `#227`'s still-unshipped Stage-1 census
requirement is meant to eventually close (see module docstring).
Chose Option 2 instead: queried the real `runs.alpaca.db` directly
(read-only copy, not the live checkout) for every `run_type='live'`,
strategy-not-null run from 2026-04-23 through 2026-07-06 — 85 runs, not the
original 8-session sample. Two findings: (1) the real legitimate low end is
29 (2026-05-17, three same-day runs: 29/30/31, all 100% covered) — the
originally-proposed `MIN_ROWS=30` would have REJECTED that exact legitimate
run; (2) a genuinely anomalous pre-operational cluster (2026-04-23 through
04-27) has candidate counts as low as 2-10, clearly not representative of
the pipeline's stable operational period and correctly excluded by any
reasonable floor.
EVIDENCE: set `MIN_ROWS=25` — real margin below the observed legitimate
minimum (29) and real margin above the anomalous cluster's ceiling (10), an
evidence-based split rather than an arbitrary round number. Added
`test_run_at_evidence_based_floor_with_full_coverage_is_accepted` (25
candidates, 100% covered — mirrors the real 2026-05-17 pattern) and
`test_run_below_evidence_based_floor_with_full_coverage_is_still_rejected`
(10 candidates, 100% covered — mirrors the real anomalous-cluster pattern,
directly testing Codex's exact concern). Confirmed the first test fails
against the originally-proposed `MIN_ROWS=30` (proving 30 was itself
unjustified) and both pass against the corrected `25`. Full suite
3165/3168 (no new failures). The residual structural limitation (denominator
is still self-referential, not a true census) is now stated explicitly in
the module's `MIN_COVERAGE_FRACTION` comment, deferring fully to `#227` as
before — this PR narrows the gap with real evidence, it does not close it.
NEXT: `#227` (Stage-1 measurement-integrity census) remains the eventual
real fix for the self-referential-denominator limitation. The separate
`--feature-snapshot-json` producer gap noted above is still unresolved and
still needs its own PR — this PR does not restore full shadow-serving
functionality on its own.
