# Diagnosis: monthly meta-label retrain fails on a CORRECT leakage guard

STATUS: delivered (diagnosis; redesign tracked separately)
WHAT: supervised re-run reproduced the 07-01 failure and captured the
real error: the SimAdapter leakage guard refuses the snapshot sim because
the job's fixed 12-month window (ending ~T-60d) predates the ACTIVE
model's trained_date (2026-06-21) — replaying the past with a
future-trained model to generate meta-label training events is look-ahead
by construction. Pre-July runs passed only because the then-active
vintage happened to predate the window end; under the 28-day freshness
policy the mismatch is now structural.
WHY/DIR: closes the last undiagnosed ack two weeks ahead of the Aug-1
commitment; the guard is working exactly as designed.
EVIDENCE: logs/monthly_meta_label/2026-07-17.log leakage ValueError
(anchor=2026-06-21, lookahead_days=60).
NEXT: task #75 — redesign the job to sim with as-of model vintages (the
WF corpus has them) or redefine the window; until then the prod
meta-label artifact stays at its last healthy state.
