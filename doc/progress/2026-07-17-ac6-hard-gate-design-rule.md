# GOAL-5 AC6: HARD-gate design rule added to the control-plane contract

STATUS: delivered
WHAT: doc/agent-pr-workflows.md gains the HARD-gate design rule — every PR
introducing/tightening a capital-path HARD gate must document (1) its
governed exception path (identity+expiry+scope binding) or why none can
exist, (2) its fail-closed shape incl. risk-exit preservation, (3) its
detection surface; absence = CHANGES_REQUESTED.
WHY/DIR: GOAL-5 AC6 — the 07-15 admission gate shipped with no override
path and the retrofit happened under incident pressure; this rule makes
the exception path a design-time requirement.
EVIDENCE: n/a (process rule; enforcement = review checklist).
NEXT: none.
