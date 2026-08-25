# S3-c package: live_config_fingerprint bound to the first pinned STARTUP (completion pending)

STATUS: docs-only, r2 after codex. Records STARTUP-RESOLUTION evidence; the
prerequisite flips to SATISFIED only after today's session closes cleanly
(same-day completion note to follow).

§4(b), corrected per review:

- The 2026-08-25 06:25 scheduler process — first after the orch#1041/#1044
  deploy (orch-run aaf06a2d) — recorded `strategy_config_fingerprint =
  sha256:af2344af…` AT STARTUP, with manifest errors=[] at read time
  [VERIFIED — manifest read 06:36 PT]. The session was still in progress;
  this is config-resolution evidence, not a completed clean session, and
  clean-session counting toward S3-c does NOT start until close.
- WHICH path was read is proven by the deployed wrapper, not by hash
  uniqueness: `run_session_scheduler.sh` resolves the config via
  `rq105_pinned_common --verify-file` (lock+HEAD+bytes, fail-closed) and
  passes it explicitly — a mismatch refuses startup. The 08-24 hash
  discrimination vs the sibling is HISTORICAL (sibling then at
  feat/qp-reenable-min-invested, different bytes); the sibling has since
  returned to main (8a395e4) and now carries identical bytes, so hash
  uniqueness no longer holds and is no longer claimed.
- The `_DRAFT` marker now states the two remaining gaps in order
  (completion tonight; then operator identity/date/expiry/allowlist)
  instead of contradicting the prerequisite note.
