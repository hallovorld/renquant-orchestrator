# Progress: shadow staleness horizon design memo

Date: 2026-07-28
PR: design/shadow-staleness-horizon

Design memo only (no code): the shadow health/sentinel staleness gate
measures from `effective_train_cutoff_date` with a 28d limit that no
fwd60-label model can satisfy by construction (floor = horizon + embargo
≈ 82–90d). Today's clf `stale_91d` flag and the fresh PatchTST corpus
(trained 2026-07-28, cutoff 2025-12-05) both demonstrate it.

Memo presents two options (A: two-axis horizon-aware check, recommended;
B: trained_date-only) for operator decision. No behavior change in this
PR; the flag remains correctly reported and documented benign until the
decision.
