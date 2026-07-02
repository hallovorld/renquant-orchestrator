# rq105 liveness: key on the tick DATA file — fix PR

STATUS:   ops fix (one logic change + comment).
WHAT:     rq105_liveness_check.py judged the quote loop by the wrapper LOG being non-empty;
          the first KPI scorecard (PR #247) caught the log at zero bytes while tick data
          flowed normally (module writes ticks directly; redirect stays empty) — a false
          alert waiting for 14:00 PT. Health now keys on logs/renquant105_pilot/
          intraday_ticks.jsonl existence + mtime (≤6h during a session day).
WHY:      liveness must watch the OUTPUT that matters (#212 rule) — the data, not the
          plumbing's chatter.
NEXT:     landing loop re-copies the script to the run checkout on merge (or the next
          ff-only pull picks it up before tomorrow's 14:00 check).
