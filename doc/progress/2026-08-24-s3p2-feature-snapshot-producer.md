# S3-P2: the missing producer — served matrix → FeatureSnapshot

STATUS:   delivered. First implementation PR of the amended rq105 Stage-3 plan
          (#1026 as corrected by #1030). Zero pipeline changes, as promised by
          the amendment.
WHAT:     `feature_snapshot_producer.py` + `ops/renquant105/
          build_feature_snapshot.sh`: read the PROD-lane served matrix
          (`logs/served_matrix/<prior-session>/alpaca__<run_id>.parquet` +
          manifest, written daily by PersistServedMatrixTask since 08-04),
          re-key to the FeatureSnapshot contract, validate through the REAL
          class (same repo), write `data/rq105/feature_snapshot_<date>.json`
          + meta atomically.
WHY/DIR:  run_shadow_serving.sh has skipped every session since 2026-08-12
          with `SKIP not-wired: no producer exists`. This is that producer.
          It computes nothing — the features are the ones the prod scorer was
          actually served. S3-P3 (next PR) wires run_shadow_serving to call
          the wrapper, which kills the not-wired skip.
EVIDENCE:
  artifact:      the module, the ops wrapper, 15 hermetic tests.
  prod or exp:   exp — end-to-end verified against the REAL 2026-08-21 served
                 matrix into scratch (90 tickers, cutoff 2026-08-21, real
                 consumer parses it, digest computed); production data/ was
                 NOT written.
  existing data: manifest schema read from the live artifact (schema_version
                 'served-matrix-1', feature_cols=172 authoritative, lane,
                 run_id, scorer identity) [VERIFIED].
  best-known?:   yes — validating through FeatureSnapshot.from_mapping makes
                 the contract-mirror mistake impossible (the withdrawn
                 pipeline#297 used `builder_version` where the contract says
                 `feature_builder_version`; the round-trip catches that class
                 of error at build time).
  scope:        one module + one ops script + tests. No launchd job, no
                config, no wiring into run_shadow_serving (that is S3-P3),
                no order path. The orchestrator test suite runs the whole
                tests/ directory, so the new file is covered by CI as-is.
  provenance:   fail-closed on: stale source (> max-gap-days), ambiguous
                source (≠1 prod pair), schema/lane drift, manifest feature
                cols absent from the parquet. Vintage honesty: builder_version
                carries `partial-bar-1355` per the #1030 amendment.
REVIEW:    codex (haorensjtu-dev).
