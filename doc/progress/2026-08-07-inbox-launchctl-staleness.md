# 2026-08-07 — An exit code is not the newest run, and the inbox said it was

STATUS:   READY FOR REVIEW. 6 new tests
          `[VERIFIED — git diff origin/main...HEAD -- tests/test_agent_inbox.py,
          six added `test_` functions under "launchctl staleness", 2026-08-07]`;
          inbox suite 33 passed
          `[VERIFIED — python3 -m pytest tests/test_agent_inbox.py -q, 2026-08-07]`.
          Full suite 6122 passed / 2 skipped / 3 failed
          `[VERIFIED — python3 -m pytest tests/ -q, 2026-08-07]`; all three failures
          (`test_goal3_public_export_resolution`,
          `test_ops_audit_disposition_trend`, `test_twin_parity`) are
          pre-existing on `main` and untouched by this change.

WHAT:     Every launchd row now carries `newest_log` — the date of that job's
          newest dated log, or `None` when none is discoverable — and the
          rendered output states the limitation that makes it necessary.

WHY/DIR:  `launchctl list` reports the last exit of the last run **launchd
          itself started**. A run started by hand does not update it. Measured
          2026-08-07
          `[VERIFIED — launchctl list | grep com.renquant.weekly-wf-promote;
          ls logs/weekly_wf_promote/]`:

```
com.renquant.weekly-wf-promote   launchctl last exit = 1
schedule                         Weekday=6 Hour=4  (Saturdays)
logs/weekly_wf_promote/2026-08-01.log   "started at Sat Aug  1 04:00:05"  -> exit 1
logs/weekly_wf_promote/2026-08-04.log   "started at Tue Aug  4 08:04:46"  -> exit 0,
                                        "governance nominal, calm notify"
```

          Both numbers were correct and they described **different events**: the
          retained code came from Saturday's scheduled run, the newest log from a
          manual Tuesday run three days later. I spent a round treating the
          code as current and reporting a five-day-old condition as today's.

          The same shape is live right now on another job
          `[VERIFIED — launchctl list | grep com.renquant.rq104-risk-budget;
          ls logs/rq104/risk_budget_*.log, 2026-08-07]`: `rq104-risk-budget`
          sits at exit 1 (documented CRITICAL, >=100% of a budget) with
          `newest log 2026-08-01`. Re-running the module today gives
          `book_beta consumption=145.4% CRITICAL` but
          `per_name_concentration=78.5% OK`
          `[VERIFIED — python3 -m renquant_orchestrator.risk_budget.report
          --out-dir <scratch dir>, 2026-08-07]` — the retained code no longer
          describes the live state, and nothing said so.

          This is the defect the inbox exists to end — reading a proxy as the
          operative value — and it was in the inbox. `newest_log` does NOT
          resolve which run produced the code (launchctl does not say) and
          deliberately does not guess. It puts the ambiguity in front of the
          reader instead of hiding it.

EVIDENCE:
artifact:      `ops/agent_inbox.py`, `tests/test_agent_inbox.py`
prod or exp:   **neither** — read-only reporting; no job, config, or live
               surface changes.
existing data: `launchctl list`; `logs/weekly_wf_promote/`; `logs/rq104/`;
               the launchd plists.
best-known?:   yes for the limitation. **No** for coverage — 3 of 16 rows
               resolve a date, 13 do not
               `[VERIFIED — python3 -c "from ops import agent_inbox as inbox;
               rows = inbox.read_launchd_exits(); print(len(rows),
               sum(r['newest_log'] is not None for r in rows))" -> 16 3,
               2026-08-07]`; the rest write under names this lookup does not
               reach, and `None` is labelled "undiscoverable", never "no logs".
scope:         one helper + the render note; no classification logic changed.

Two log layouts are supported because both are in use
`[VERIFIED — ls logs/weekly_wf_promote/ logs/rq104/ logs/rq105/, 2026-08-07]`:
`logs/<job_with_underscores>/YYYY-MM-DD.log` and
`logs/<rq104|rq105>/<basename>_YYYY-MM-DD.log`. Only dated names count —
`manual_20260601-225243.log` and `final_test_20260608-082722.log` exist in the
same directory and are deliberately not treated as runs.

NEXT:     Raise coverage past 3/16 by reading each remaining job's wrapper for
          where it actually writes — **from the wrapper, not by guessing a
          convention**, which is the mistake that produced this module's
          earlier false "no documentation" verdicts. Then consider whether a
          row whose code predates its newest log by more than one schedule
          period should be demoted from the work list; that needs the schedule,
          which this change does not read.

## NOT ESTABLISHED

1. **Which run produced any given retained code.** `launchctl` does not expose
   it. This change surfaces the ambiguity; it does not resolve it.
2. **That the 13 `None` rows have no logs**
   `[VERIFIED — same `read_launchd_exits()` count as EVIDENCE/best-known?
   above, 2026-08-07]`. They have no log this lookup finds. The distinction
   is the point.
3. **That `rq104-risk-budget`'s CRITICAL is resolved.** Today's re-run shows
   `book_beta` still CRITICAL at 145.4%; only `per_name_concentration`
   recovered `[VERIFIED — python3 -m renquant_orchestrator.risk_budget.report
   --out-dir <scratch dir>, same run as WHY/DIR above, 2026-08-07]`.

## REVERT

Delete `_LOG_BASENAME`, `_FLAT_LOG_DIRS`, `_newest_log_date`, the
`row["newest_log"]` assignment, the two render additions, and the six tests
appended to `tests/test_agent_inbox.py`; restore the dict-equality assertion in
`test_an_unlisted_code_is_unknown_not_assumed_fine`. No other file changes.
