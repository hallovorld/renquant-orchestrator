# QP feasibility fix design

DATE: 2026-07-04

## What

Design doc for fixing the 68% QP infeasibility rate that drives TC = -0.43.
Four-stage plan: C2 retry policy → turnover cap bump → soft turnover →
fallback improvement. All changes are pipeline-side; orchestrator owns
measurement via the S-TC module.

See doc/design/2026-07-04-qp-feasibility-fix.md for full design.
