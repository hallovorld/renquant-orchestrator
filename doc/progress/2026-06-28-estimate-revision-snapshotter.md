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
          (as_of, endpoint, sha256, ticker_count, coverage, status, fetched_at).
          Each row stamped snapshot_as_of = ACTUAL UTC fetch date.
          --as-of / --force / --min-coverage / --universe / --out / --dry-run.
          doc/design/2026-06-28-estimate-revision-snapshotter.md — design note.

GUARDS:   Structural is_canonical_path() refuses fmp_harvest / sec_fundamentals_daily
          / rawlabel.parquet / score_db / any non-`estimate_snapshots` leaf;
          follows symlinks (resolve()) so a link into a forbidden tree is rejected;
          /tmp scratch allowed for demos. FMP key read READ-ONLY from umbrella .env.

CODEX REVIEW FIXES (PR #205, CHANGES_REQUESTED — all 5 addressed):
  1. as-of backdating FORBIDDEN. resolve_as_of() derives snapshot_as_of from the
     actual UTC fetch date; a PAST --as-of errors (today/future only). No live
     fetch can manufacture historical PIT.
  2. Atomic publish + partial-safe. Staged temp dir → coverage floor + status
     (ok/partial) per endpoint → atomic os.replace ONLY if all ok. Partial =
     NOT published, prior good snapshot intact, non-zero exit. Default
     idempotency = no-op verify (NOT destructive refetch); --force to re-publish.
  3. Base-data ownership FLAGGED (not moved). Design states the collector's proper
     home is renquant-base-data (orchestrator only schedules/invokes + persists
     fingerprint); relocation proposed as an explicit operator decision. No
     base-data PR opened.
  4. Focused tests added: tests/test_snapshot_fmp_estimates.py (22 tests) —
     historical-as-of rejection, snapshot_as_of from fetch date, idempotent no-op
     (asserts NO refetch) + --force, partial-endpoint failure, partial not
     overwriting a good prior, atomic publication (no half-dir/residue), canonical
     path guard incl symlink (into forbidden tree + scratch-symlink-into-data),
     manifest sha256 == parquet. Fake/mocked fetch + /tmp output, NO live FMP.
  5. Scheduling = PROPOSAL only. Design specifies owner / daily cadence /
     retry-backfill policy (NO fake timestamps; a missed day stays a genuine gap) /
     freshness alert. No cron/launchd installed.

DEMO:     Re-demoed to /tmp (NOT live data/): past --as-of (2025-01-01) rejected
          exit=2; dry-run resolves 142 tickers from golden config; a fake-fetch
          end-to-end run proved atomic all-ok publish, idempotent rerun = no-op (no
          refetch), and force+all-fail = partial / not published / prior snapshot
          intact / no stage residue. Earlier live demo (pre-fix) returned 134-135/142.

COST:     ~free (~570 light requests/day; free FMP already returns these endpoints).

NOT DONE: scheduling (cron/launchd) = separate operator deploy decision; relocation
          to renquant-base-data = operator decision; feature engineering / retrain
          (needs ~3-6 months accrued history + its own per-regime WF/placebo gate).
          Discussion: relocate-to-base-data, path layout, cadence/endpoints, history
          bar to test, universe breadth.

NEXT:     operator decides ownership (relocate?) / path / cadence / breadth in
          review; if accepted, operator schedules the daily run; history accrues;
          revisit signal validation in ~3-6 months.
