# Sentinel ack ledger: dispositioned last-exits stop re-alarming

STATUS: delivered
WHAT: launchctl retains a job's last exit until its NEXT run, so
already-fixed failures on low-frequency jobs (monthly/weekly/
anomaly-triggered) re-alarm for days-to-weeks. New reviewed, git-tracked
`ops/renquant104/sentinel_acks.json`: an acked job's nonzero-exit row
moves to INFO carrying its disposition + clears_when; unacked rows stay
loud. Pre-populated with the 07-17 dispositioned set (8 entries, each
naming its fix PR and its expected clear event). Acks are named-event
scoped and pruned at review touches; the drift scan and the other sentinel
probes remain independent alarm paths.
WHY/DIR: GOAL-5 — the operator received the same wall of already-handled
rows twice in one evening; alarm fatigue is itself a reliability defect.
EVIDENCE: 22 module tests (ack→INFO, unacked→alarm, ledger isolation via
call-time path resolution); full suite 4010 passed.
NEXT: prune entries as jobs self-clear (next weekly cycle review).
