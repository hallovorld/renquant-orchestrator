# M4-b sign-laundering measurement — first production audit

DATE: 2026-07-04

## What

Ran `sign_laundering_harness.audit_laundering_history()` against the production
candidate_scores DB (4,520 rows across 33 trading dates). This is the first
quantified measurement of the sign-laundering problem using the M4-b harness
built during the sprint.

## Findings

- Production calibrator neutral_raw = −0.2667 (refit; previously cited −0.2902)
- Mean laundering rate: 7.9% (median 6.4%)
- Trend: worsening — early 3.3% → late 10.1%
- Most recent run (07-02): 16/83 = 19.3%
- Prior "44/90" figure not reproduced (different definition or calibrator vintage)

## Impact

Confirms sign-laundering is a real, worsening problem — not a one-off. ~15-20%
of recent buy candidates carry model-contradicted signals. The matched-breadth
protocol (forward-return comparison) requires S5 decision-ledger pipeline wiring
to accumulate the data needed for the definitive measurement.

## Next

- Update 107 as-built with measured laundering statistics
- Matched-breadth comparison blocked on S5 forward-return data
- Recalibration would fix mechanically but is a behavior change (fix-wave rule 1)
