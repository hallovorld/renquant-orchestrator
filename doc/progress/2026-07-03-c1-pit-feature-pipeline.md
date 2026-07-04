# C1 PIT revision-drift feature pipeline — serving-path pre-build (sprint D2)

STATUS:   ops scheduling files for review (repo files only — NOTHING installed/executed by
          this PR; the landing rides the next operator batch per the landing-actions rule).
          Companion base-data PR carries the actual pipeline (`pit_revision_features.py`).
REVISION: r1.
WHAT:     `ops/pit/run_c1_feature_builder.sh` + `com.renquant.pit-c1-features.plist`
          (15:30 PT weekdays, after the 14:30 snapshotter and 15:00 liveness): incremental
          daily build of the C1 estimate-revision-drift feature table from the PIT snapshot
          lake — `data/estimate_snapshots/<date>/` (READ-ONLY) →
          `data/pit_features/c1_revision_drift.parquet` + evidence manifest (per-day input
          sha256 from the lake's own manifests + code sha). Same kernel-released
          `run_with_lock.py` flock guard, own dedicated lock file; wrapped command is a
          single non-forking python invocation per that launcher's documented caveat.
          README table/install/smoke updated; 4 wrapper tests + the new plist joins the
          schedule-verification matrix.
WHY/DIR:  M-SIG spec (doc/design/2026-07-02-m-sig-signal-stack-spec.md §1.1) froze C1's
          methodology but its data only accrues forward (N2, anchor = first real snapshot
          2026-07-02); the confirmatory read unlocks at anchor + 6 calendar months =
          **2027-01-02** (second checkpoint 2027-04-02, monitoring bounded 2027-Q4).
          Pre-building the serving path flag-off now means that at maturity, testing +
          serving C1 is parameter tuning, not new engineering — and avoids the
          built-but-dark pathology by shipping WITH its schedule while still touching no
          production input (`data/pit_features/` is a research lake nothing consumes yet;
          C1 is INFORMATIVE-ONLY per the spec and never gates GO/KILL).
SPLIT:    feature derivation in base-data (`renquant_base_data.pit_revision_features`,
          companion PR — frozen 1m/21td primary drift with matched fiscal target +
          no-update EXCLUSION, exploratory 5d/3m/breadth/target-drift/grade-migration all
          documented, STRICT PIT ≤ as_of with no backfill, out-root structurally guarded);
          scheduling here (orchestrator owns base-data primitive scheduling per the #27
          docstring + #210 ownership split — same split as the N2 package itself).
EVIDENCE: base-data suite 206 passed (21 new contract tests: adversarial PIT — a D+1
          snapshot with a 10x jump and a new symbol cannot influence features at ≤ D;
          frozen-formula hand checks; |denominator|; fiscal-roll matching; exclusion rules;
          missing-day tolerance; byte-stable incremental idempotence; readiness arithmetic
          incl. month-end clamping; out-root guard). Real-lake run (2 days accrued,
          2026-07-02..03, 136 symbols, 272 rows): drifts honestly NaN
          (`no_lag_snapshot` — lake younger than every window), FY1 levels correct
          (AAPL FY1 2026-09-27 epsAvg 8.755), re-run = `up_to_date` no-op; report prints
          CONFIRMATORY UNLOCK 2027-01-02, window maturity 5d/1m/3m =
          2026-07-09 / 2026-07-31 / 2026-09-29.
NEXT:     Operator landing batch: install the plist per ops/pit/README (chmod + bootstrap;
          no other change — the wrapper is inert until then). At window maturity the
          exploratory report starts showing non-null drift coverage; at 2027-01-02 run the
          spec's confirmatory procedure (block=1mo bootstrap, informative-only) on the
          accrued table.
