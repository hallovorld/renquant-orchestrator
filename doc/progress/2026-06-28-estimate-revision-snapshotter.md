# Estimate-revision forward snapshotter — progress

STATUS:   proposed PR. Collector script + design note only. No cron, no canonical
          data writes, no model change.

WHY:      The analyst estimate-REVISION signal (best large-cap orthogonal lead;
          Womack 1996 / Gleason-Lee 2003; surfaced by the 2026-06-23 trade review)
          is un-buildable today: our FMP harvest (umbrella PR #409,
          data/fmp_harvest/) is a single CURRENT snapshot with no revision history.
          Using today's consensus on past dates = look-ahead the WF gate must catch.
          The fix needs only TIME: snapshot estimates forward from today so a real
          as-of revision history accrues, leakage-free.

WHAT:     scripts/snapshot_fmp_estimates.py — fetches the renquant-104 universe
          (read read-only from the golden strategy_config watchlist, or --universe)
          from the same FMP `stable` endpoints the harvest uses (analyst_estimates,
          grades_consensus, price_target_consensus, price_target_summary) and writes
          a DATED snapshot to a NEW dedicated path
          data/estimate_snapshots/<YYYY-MM-DD>/<endpoint>.parquet + manifest
          (as_of, endpoint, sha256, ticker_count, fetched_at). Each row stamped
          snapshot_as_of (self-describing PIT). Idempotent per as-of date;
          --as-of / --universe / --out / --dry-run; flock note for cron-safety.
          doc/design/2026-06-28-estimate-revision-snapshotter.md — design note.

GUARDS:   Structural is_canonical_path() refuses fmp_harvest / sec_fundamentals_daily
          / rawlabel.parquet / score_db / any non-`estimate_snapshots` leaf; /tmp
          scratch allowed for demos. FMP key read READ-ONLY from umbrella .env.

DEMO:     Ran once to /tmp/snap_demo (NOT live data/): 134-135 of 142 names returned
          per endpoint (the ~8 misses are free-plan-locked, not rate limits), 1338
          analyst-estimate rows; manifests + example rows in the PR body. Dry-run
          resolves 142 tickers from the golden config. Canonical-path guard verified
          to reject fmp_harvest and a non-dedicated leaf.

COST:     ~free (~570 light requests/day; free FMP already returns these endpoints).

NOT DONE: scheduling (cron/launchd) = separate operator deploy decision; feature
          engineering / retrain (needs ~3-6 months accrued history + its own
          per-regime WF/placebo gate). Discussion: path layout, cadence/endpoints,
          history bar to test, universe breadth.

NEXT:     operator decides path/cadence/breadth in review; if accepted, operator
          schedules the daily run; history accrues; revisit signal validation in
          ~3-6 months.
