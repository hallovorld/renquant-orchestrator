# Estimate-revision forward snapshotter — progress   (PR #205)

STATUS:   docs / decision-record ONLY. The COLLECTOR has MOVED to
          renquant-base-data — base-data PR #27
          (https://github.com/hallovorld/renquant-base-data/pull/27),
          module `renquant_base_data.fmp_estimate_revisions` + 24 ported tests.
          This orchestrator PR no longer adds any collector code; it is the
          design/decision record for the estimate-revision substrate and a
          pointer to the base-data collector. The orchestrator's remaining piece
          — a thin schedule / fingerprint / freshness-alert WIRING PR that invokes
          the base-data primitive and persists its fingerprint — is a SEPARATE,
          FUTURE PR (NOT this one). No cron, no canonical writes, no model change.

BOUNDARY: Data acquisition + storage is a renquant-base-data responsibility — a
          hard boundary in this repo's CLAUDE.md and the canonical subrepo
          operating model. Codex flagged the boundary on #205; the operator chose
          option (1): move the collector + tests to renquant-base-data, leave only
          orchestration wiring here. Done: base-data PR #27 owns the collector;
          this PR is trimmed to the design/decision record. The future thin
          orchestrator PR is where scheduling/fingerprint/freshness lives (the
          orchestrator schedules base-data primitives and persists their
          fingerprints; it does not own the fetch/write logic).

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

EVIDENCE: §4(b) block (this PR's durable claim is now a DECISION/provenance claim —
          "the current harvest cannot build PIT revision history, so a forward
          collector is needed, and it belongs in renquant-base-data"):
          - artifact:      the collector + its 24 contract tests now live in
                           renquant-base-data PR #27
                           (renquant_base_data.fmp_estimate_revisions +
                           tests/test_fmp_estimate_revisions.py). This orchestrator
                           PR carries the design notes only.
          - prod or exp:   reference/decision record. The base-data collector writes
                           only data/estimate_snapshots/<date>/ (a NEW path) or a
                           /tmp demo path; no canonical/live path is touched.
          - existing data: the umbrella FMP harvest (data/fmp_harvest/*.parquet +
                           *.manifest.json, umbrella PR #409) is a SINGLE current
                           snapshot — its manifests carry one harvest-day consensus
                           per endpoint, with no per-date series, so "what consensus
                           was 1m/3m ago" cannot be reconstructed from it. No
                           estimate_snapshots series exists yet (base-data PR #27
                           adds the collector that would accrue it forward).
          - best-known?:   yes — the only forward PIT-safe accrual path for FMP
                           estimate revisions in-repo; the alternative (stamping
                           today's consensus onto past dates) is the look-ahead the
                           collector structurally refuses (resolve_as_of rejects past
                           AND future --as-of).
          - scope:         "the collector is a leakage-free FORWARD accrual primitive
                           now owned by renquant-base-data; vs existing best =
                           data/fmp_harvest (a single non-PIT snapshot that cannot
                           express revision history). This orchestrator PR = the
                           design/decision record + pointer."
          `[VERIFIED — base-data PR #27: 24 tests pass + full base-data suite 138
          passed (114 pre-existing + 24 new); module imports and --dry-run run with
          `requests` ABSENT, live path raises a clean error when missing. The two
          collector files were removed from THIS orchestrator branch and the
          `requests>=2.28` dep (added only for the collector) reverted from
          pyproject; 2026-06-29 this session]`

WHAT:     This PR (#205) now ships DOCS ONLY:
          - doc/design/2026-06-28-estimate-revision-snapshotter.md — design note
            (what is collected / PIT invariant / atomic-publish + partial contract /
            scheduling proposal / how the revision feature is built later), reframed
            so the collector is owned by renquant-base-data PR #27 and the
            orchestrator role is the future thin wiring PR.
          - this progress doc.
          The COLLECTOR + TESTS are in renquant-base-data PR #27 — NOT here.

REMOVED FROM THIS PR (moved to base-data PR #27):
          - scripts/snapshot_fmp_estimates.py  -> renquant_base_data.fmp_estimate_revisions
          - tests/test_snapshot_fmp_estimates.py -> tests/test_fmp_estimate_revisions.py
          - the `requests>=2.28` pyproject dependency (added only for the collector;
            the live FMP fetch now lives in base-data, whose pyproject already
            declares `requests>=2.31`).

CODEX REVIEW — REPO-BOUNDARY BLOCKER (PR #205, resolved by the move):
  The collector belongs in renquant-base-data (hard boundary). Operator chose
  option (1): move the collector + tests to renquant-base-data and leave only
  orchestration wiring here. ACTIONED: base-data PR #27 now owns
  renquant_base_data.fmp_estimate_revisions + tests; this orchestrator PR is
  trimmed to the design/decision record. The orchestrator's remaining work — a
  thin schedule/fingerprint/freshness-alert PR — is a separate future PR.

CODEX REVIEW — EARLIER ROUNDS (1–3, on the reference collector; now in base-data):
  R1/R2/R3 hardened the collector contracts: as-of backdating AND future-dating
  forbidden (snapshot_as_of = actual UTC fetch date); atomic publish + partial-safe
  + non-destructive idempotency; structural canonical-path guard (symlink-following);
  lazy `requests` import so CI test-collection / dry-run need no network dep;
  progress doc to C5 field set with a §4(b) evidence block. All of that travelled
  with the collector into base-data PR #27 (24 tests pass there).

DEMO:     (in base-data PR #27) past --as-of AND future --as-of both rejected exit=2;
          dry-run resolves the universe from golden config; a fake-fetch end-to-end
          run proved atomic all-ok publish, idempotent rerun = no-op (no refetch),
          and force+all-fail = partial / not published / prior snapshot intact / no
          stage residue. Earlier live demo (pre-fix) returned 134-135/142.

COST:     ~free (~570 light requests/day; free FMP already returns these endpoints).

NOT DONE (this orchestrator PR, by design):
          - the collector itself (now in renquant-base-data PR #27);
          - scheduling (cron/launchd) — the future thin orchestrator
            schedule/fingerprint/freshness PR (history does NOT accrue from merging
            docs);
          - feature engineering / retrain (needs ~3-6 months accrued history + its
            own per-regime WF/placebo gate).
          Discussion still open: path layout, cadence/endpoints, history bar,
          universe breadth (carried in the design note for the base-data + future
          wiring PRs).

NEXT:     (1) land base-data PR #27 (the collector); (2) a thin orchestrator
          schedule/fingerprint/freshness-alert PR that invokes the base-data
          primitive on the daily-run host and persists its fingerprint (the
          operational merge point that actually accrues history); (3) revisit
          signal validation in ~3-6 months once the dated series exists.
