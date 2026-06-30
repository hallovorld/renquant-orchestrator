# Estimate-revision forward snapshotter — progress   (PR #205)

STATUS:   in-progress / reference implementation, NOT the merge point. Collector
          script + design note only. Superseded by a two-PR split (base-data
          collector PR first, then a thin orchestrator schedule/fingerprint/
          freshness PR = the operational merge point). No cron, no canonical
          writes, no model change. Merging this script alone does NOT make
          "history accrue" (no scheduler).

WHY/DIR:  The analyst estimate-REVISION signal (best large-cap orthogonal lead;
          Womack 1996 / Gleason-Lee 2003; surfaced by the 2026-06-23 trade review)
          is un-buildable today: our FMP harvest (umbrella PR #409,
          data/fmp_harvest/) is a single CURRENT snapshot with no revision history.
          Using today's consensus on past dates = look-ahead the WF gate must catch.
          The fix needs only TIME: snapshot estimates forward from today so a real
          as-of revision history accrues, leakage-free. DIRECTION: builds the data
          substrate for a future orthogonal feature (post-revision drift) that the
          2026-06-23 trade review flagged as the highest-value missing lens; it does
          NOT itself add a feature or change any model.

EVIDENCE: §4(b) block (this PR makes a data-provenance claim — "the current harvest
          cannot build PIT revision history" — and a fetch-coverage claim):
          - artifact:      scripts/snapshot_fmp_estimates.py (this PR);
                           tests/test_snapshot_fmp_estimates.py (24 tests).
          - prod or exp:   experiment / reference-implementation. NOT wired to prod;
                           writes only data/estimate_snapshots/<date>/ (a NEW path)
                           or a /tmp demo path; no canonical/live path is touched.
          - existing data: the umbrella FMP harvest (data/fmp_harvest/*.parquet +
                           *.manifest.json, umbrella PR #409) is a SINGLE current
                           snapshot — its manifests carry one harvest-day consensus
                           per endpoint, with no per-date series, so "what consensus
                           was 1m/3m ago" cannot be reconstructed from it. No
                           estimate_snapshots series exists yet (this PR creates the
                           collector that would accrue it forward).
          - best-known?:   yes — this is the only forward PIT-safe accrual path for
                           FMP estimate revisions in-repo; the alternative (stamping
                           today's consensus onto past dates) is the look-ahead this
                           script structurally refuses (resolve_as_of rejects past
                           AND future --as-of).
          - scope:         "this is scripts/snapshot_fmp_estimates.py, experiment,
                           a leakage-free FORWARD collector; vs existing best =
                           data/fmp_harvest (a single non-PIT snapshot that cannot
                           express revision history)."
          Fetch-coverage demo (live, pre-fix run to /tmp, NOT live data/): 134–135
          of 142 names returned per endpoint, 1338 analyst-estimate rows; the ~7–8
          misses are plan-locked FMP names, not transient. Contract behaviour
          (as-of rejection, idempotent no-op, partial-not-published, atomic publish,
          path guard incl symlink, manifest sha256) is covered by the 24 focused
          tests with a fake fetch + /tmp output (no live FMP).
          `[VERIFIED — 24 tests pass in a requests-ABSENT CI-simulation venv
          (pytest numpy pandas scipy pyarrow pydantic scikit-learn, no requests):
          PYTHONPATH=src python -m pytest -q tests/test_snapshot_fmp_estimates.py ->
          24 passed; py_compile OK; dry-run + live-path-error verified; 2026-06-29
          this session]`

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
          `requests` is imported LAZILY (live network path only) so module import /
          test collection / dry-run do not require it.
          doc/design/2026-06-28-estimate-revision-snapshotter.md — design note.

GUARDS:   Structural is_canonical_path() refuses fmp_harvest / sec_fundamentals_daily
          / rawlabel.parquet / score_db / any non-`estimate_snapshots` leaf;
          follows symlinks (resolve()) so a link into a forbidden tree is rejected;
          /tmp scratch allowed for demos. FMP key read READ-ONLY from umbrella .env.

CODEX REVIEW — ROUND 3 (PR #205, CHANGES_REQUESTED 2026-06-28, all addressed):
  R3.1 CI STILL red — the pyproject dep is not enough. .github/workflows/ci.yml
       installs an EXPLICIT package list (pytest numpy pandas scipy xgboost
       pyarrow pydantic cvxpy scikit-learn) and does NOT install project
       dependencies, so declaring `requests` in pyproject did not reach CI;
       test collection still hit ModuleNotFoundError: No module named 'requests'.
       FIXED by the "import shape" path Codex offered: `requests` is now imported
       LAZILY (TYPE_CHECKING for the type hints + a _require_requests() on-demand
       import on the live network path only). The tests exercise the pure contract
       functions with a fake fetch and never touch the network, so importing the
       module — i.e. CI test collection — no longer needs `requests` at all. The
       live path raises a clear, actionable error if the dependency is genuinely
       missing; dry-run works without it. The `requests>=2.28` pyproject
       declaration is kept (correct for the live path) but is no longer
       load-bearing for CI. VERIFIED: 24 tests pass in a requests-ABSENT venv
       built from CI's exact package subset (see EVIDENCE).
  R3.2 Progress doc did not match the mandatory C5 field set. Converted `WHY:` →
       `WHY/DIR:` and added an `EVIDENCE:` section ending in a `[VERIFIED — …]`
       tag, matching doc/AGENT-RETROSPECTIVE.md §4(c).
  R3.3 No explicit §4(b) evidence block for the data/provenance claims. Added the
       full block (artifact / prod-or-exp / existing-data / best-known? / scope)
       under EVIDENCE, scoping the forward collector against the existing non-PIT
       fmp_harvest snapshot.

CODEX REVIEW — ROUND 2 (PR #205, CHANGES_REQUESTED 2026-06-28, all addressed):
  R2.1 CI red — missing dep. The script imports `requests` but it was not
       declared in pyproject.toml, so CI test-collection hit ModuleNotFoundError.
       Added `requests>=2.28` to [project].dependencies. (Round 3 found this was
       insufficient for THIS repo's CI install path and switched to a lazy import.)
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
