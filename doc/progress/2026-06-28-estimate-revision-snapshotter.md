# Estimate-revision forward snapshotter — progress

STATUS:   reference implementation, NOT the merge point. Collector script + design
          note only. Superseded by a two-PR split (base-data collector PR first,
          then a thin orchestrator schedule/fingerprint/freshness PR = the
          operational merge point). No cron, no canonical writes, no model change.
          Merging this script alone does NOT make "history accrue" (no scheduler).

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
          Each row stamped snapshot_as_of = ACTUAL UTC fetch date; --as-of may
          only EQUAL today's UTC date (both past AND future rejected).
          --as-of / --force / --min-coverage / --universe / --out / --dry-run.
          doc/design/2026-06-28-estimate-revision-snapshotter.md — design note.

GUARDS:   Structural is_canonical_path() refuses fmp_harvest / sec_fundamentals_daily
          / rawlabel.parquet / score_db / any non-`estimate_snapshots` leaf;
          follows symlinks (resolve()) so a link into a forbidden tree is rejected;
          /tmp scratch allowed for demos. FMP key read READ-ONLY from umbrella .env.

CODEX REVIEW — ROUND 2 (PR #205, CHANGES_REQUESTED 2026-06-28, all addressed):
  R2.1 CI red — missing dep. The script imports `requests` but it was not
       declared in pyproject.toml, so CI test-collection hit ModuleNotFoundError.
       Added `requests>=2.28` to [project].dependencies. Focused tests still pass.
  R2.2 Future --as-of was still fake provenance. resolve_as_of() previously
       allowed today OR future and wrote it into every row's snapshot_as_of.
       FIXED to the exact invariant: --as-of must EQUAL today's UTC date; BOTH
       past AND future are now rejected. snapshot_as_of = the actual UTC fetch
       date; fetched_at recorded in the manifest. Scheduling picks the dir at run
       time from the real fetch date — no pre-named future slot. Test updated:
       the old "accepts future" expectation now asserts future is REJECTED
       (+ test_main_rejects_future_as_of).
  R2.3 Base-data ownership reframed as a TWO-PR SPLIT (not just "flagged"). The
       collector WILL move to renquant-base-data (hard boundary): (a) base-data
       collector PR first, then (b) a thin orchestrator schedule/fingerprint/
       freshness-alert PR = the operational merge point. THIS PR marked
       reference-implementation / superseded-by-split / NOT the merge point. The
       cross-repo move stays an operator decision (like the umbrella ADR) — no
       base-data PR opened here.
  R2.4 Doc states plainly: merging this script alone does NOT achieve "history
       accrues" (no deployed scheduler) — the operational merge point is the
       future orchestrator schedule PR.

CODEX REVIEW — ROUND 1 (PR #205, CHANGES_REQUESTED — all 5 addressed):
  1. as-of backdating FORBIDDEN. resolve_as_of() derives snapshot_as_of from the
     actual UTC fetch date; a PAST --as-of errors. (Round 2 tightened this to also
     reject FUTURE — today's UTC date only.) No live fetch can manufacture PIT.
  2. Atomic publish + partial-safe. Staged temp dir → coverage floor + status
     (ok/partial) per endpoint → atomic os.replace ONLY if all ok. Partial =
     NOT published, prior good snapshot intact, non-zero exit. Default
     idempotency = no-op verify (NOT destructive refetch); --force to re-publish.
  3. Base-data ownership FLAGGED (Round 2: hardened into the explicit two-PR
     split above — collector WILL move; this PR is reference / not the merge
     point). No base-data PR opened here (operator decision).
  4. Focused tests added: tests/test_snapshot_fmp_estimates.py (~24 tests) —
     historical AND future as-of rejection, snapshot_as_of from fetch date,
     idempotent no-op
     (asserts NO refetch) + --force, partial-endpoint failure, partial not
     overwriting a good prior, atomic publication (no half-dir/residue), canonical
     path guard incl symlink (into forbidden tree + scratch-symlink-into-data),
     manifest sha256 == parquet. Fake/mocked fetch + /tmp output, NO live FMP.
  5. Scheduling = PROPOSAL only. Design specifies owner / daily cadence /
     retry-backfill policy (NO fake timestamps; a missed day stays a genuine gap) /
     freshness alert. No cron/launchd installed.

DEMO:     Re-demoed to /tmp (NOT live data/): past --as-of (2025-01-01) AND future
          --as-of both rejected exit=2; dry-run resolves 142 tickers from golden
          config; a fake-fetch end-to-end run proved atomic all-ok publish,
          idempotent rerun = no-op (no refetch), and force+all-fail = partial / not
          published / prior snapshot intact / no stage residue. Earlier live demo
          (pre-fix) returned 134-135/142.

COST:     ~free (~570 light requests/day; free FMP already returns these endpoints).

NOT DONE: scheduling (cron/launchd) = separate operator deploy decision (history
          does NOT accrue from merging this script); relocation to
          renquant-base-data = the base-data collector PR (step 1, operator
          sequences the cross-repo move); feature engineering / retrain (needs
          ~3-6 months accrued history + its own per-regime WF/placebo gate).
          Discussion: path layout, cadence/endpoints, history bar, universe breadth.

NEXT:     operator sequences the two-PR split — (1) base-data collector PR, then
          (2) thin orchestrator schedule/fingerprint/freshness PR (the operational
          merge point that actually accrues history); revisit signal validation in
          ~3-6 months once the dated series exists.
