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
