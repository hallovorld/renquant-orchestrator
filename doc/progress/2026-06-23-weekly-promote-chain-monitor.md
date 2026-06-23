# Weekly model-promote chain liveness/health monitor + alert

STATUS:   merge-pending (PR #178). Additive, strictly read-only on live artifacts/state.
WHAT:     weekly_promote_monitor.py (build_weekly_promote_health) + a weekly-promote-health CLI + a
          registered ops job + tests. Stale = newest *.weekly_*.staging.json vs cadence (>8d); error =
          the per-run promote-log VERDICT line + tracebacks. Alerts on stale/error.
WHY-DIR:  the weekly WF-gate promote chain was silently broken ~a month with no alert; #174 (daily
          trading-health) does not watch the weekly pipeline — a distinct gap.
EVIDENCE: make test 449 passed; ran read-only against LIVE artifacts/prod -> ok, file count unchanged
          46->46; simulated 30-day-stale -> stale, alert, exit 2. `[VERIFIED — make test + live RO]`
NEXT:     install the launchd entry that runs it after the Saturday chain + publish its exit into scheduled_health.
