# Ack the two remaining undiagnosed last-exits (now diagnosed)

STATUS: delivered
WHAT: sentinel_acks.json gains the final two entries with real diagnoses:
monthly-meta-label-retrain (stale 07-01 spend-limit-era failure, died mid
snapshot-sim; supervised re-run before Aug 1 = task #73) and
retrain-panel104 (legacy per-ticker tournament weekly retrain, frozen
since 2026-04 per the documented timeout class; logs end 2026-04-26;
fix-vs-retire decision = task #74, tied to the G4 ladder Phase C).
WHY/DIR: GOAL-5 — the alert surface now carries zero undispositioned
rows; every nonzero last-exit names its diagnosis and clear event.
EVIDENCE: plist/log forensics in-session; sentinel module tests 22/22.
NEXT: tasks #73/#74.
