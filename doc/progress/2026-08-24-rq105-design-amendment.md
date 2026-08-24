# rq105 design amendment: S3-P1 already existed — the twin guard proved it

STATUS:   delivered (design correction). pipeline#297 withdrawn.
WHAT:     doc/design/2026-08-23-rq105-stage3-live-entries.md corrected: the
          claim "nothing persists the served feature vectors — verified" was
          FALSE. PersistServedMatrixTask (orch#703) has written
          logs/served_matrix/<date>/<lane>__<run_id>.parquet daily since
          2026-08-04 (verified live: 90×180, prod lane, through 08-21).
          S3-P1 is absorbed into S3-P2, which now READS the existing artifact.
WHY/DIR:  the wrong claim survived design review because the verification
          searched data/ for an EXPECTED FILENAME instead of searching the
          codebase for the CONCEPT. The duplicate implementation it induced
          was caught by renquant-pipeline's twin-pairs guard in CI — the
          guard's exact purpose — and the pin file's own _repin note names
          orch#703 and the rationale. Read the pins before building.
EVIDENCE:
  artifact:      the amended design doc.
  prod or exp:   neither — documentation.
  existing data: served_matrix listing + parquet shape read from the live
                 tree [VERIFIED]; the twin-guard CI failure on pipeline#297.
  best-known?:   yes — zero pipeline changes now needed for Stage-3.
  scope:        design text only.
REVIEW:    codex (haorensjtu-dev).
