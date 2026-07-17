# GOAL-5 AC1: rq104 degradation sentinel

STATUS: delivered
WHAT: `ops/renquant104/rq104_degradation_sentinel.py` — alarms on
degraded-but-alive states the liveness checkers cannot see: (a)
zero-candidate streak (>=2 session days with live runs but 0 candidates +
0 buys), (b) Traceback / "contract fail" in today's daily log regardless
of exit code, (c) com.renquant.* launchd jobs with nonzero last exit, (d)
buy-path blocked streak (row flag or BUY-BLOCKED decision line). Alerts
via the canonical liveness_common.alert ntfy path; NYSE session-day gated;
all checks anchor to whole past sessions (no after-hours false-positive
window — the 105 stale-tick lesson). Read-only everywhere
(mode=ro&immutable=1). deploy/ plist TEMPLATE included; installation is an
operator-gated landing action.
WHY/DIR: GOAL-5 P0 week-1 — every condition of the 2026-07-16 incident
(3 silent zero-candidate days, swallowed calibrator Traceback,
weekly-wf-promote exit 1 for days) was visible the whole time; nothing
looked. AC1: detection within 1 session.
EVIDENCE: 19 injection/negative tests (each degraded state alarms; healthy
day, single bad day, top-up-only day, missing-rows day, non-session day
all stay silent). Drill: run with --as-of 2026-07-15 --db (prod, ro)
reproduces the incident alarm on real data.
NEXT: deploy = load the plist (operator landing); AC1 drill after one
live-scheduled firing.
