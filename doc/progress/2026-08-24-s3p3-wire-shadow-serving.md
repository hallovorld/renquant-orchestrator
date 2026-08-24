# S3-P3: the shadow lane produces its own snapshot — the not-wired era ends

STATUS:   delivered. Two-part change: run_shadow_serving.sh invokes
          build_feature_snapshot.sh before its availability check, and the
          skip taxonomy is updated (producer-refused replaces not-wired).
WHAT:     since 2026-08-12 every session logged `SKIP not-wired: no producer
          exists`. With #1032 merged the producer exists; this PR closes the
          gap INSIDE the wrapper, so the daily flow needs no human step:
          scheduler → producer (from the prior session's prod served matrix)
          → serving replay. A producer REFUSAL (fail-closed provenance) keeps
          the calm EXIT_NOT_WIRED=4 skip with the reason and a pointer to the
          producer's own log — a refusal is the producer working.
WHY/DIR:  this starts the S3-a/S3-b shadow window of the #1026 ladder: from
          the first post-merge session, paired intraday-vs-batch rows accrue
          automatically. ≥10 clean sessions is the gate before S3-c — which
          remains an explicit operator ask.
EVIDENCE:
  artifact:      the wrapper change + tests/test_shadow_serving_skips_leave_
                 evidence.py (updated messages + a new positive-path test that
                 builds a real served matrix in a fake root and asserts the
                 wrapper produced its own snapshot).
  prod or exp:   exp — no launchd change, no config; the deployed behaviour
                 changes only after merge + orch-run sync.
  existing data: mutation-verified the RIGHT way after doing it wrong once
                 (a stash swept the tests along with the wrapper, proving
                 nothing): NEW tests vs the UNWIRED wrapper = 3 failed —
                 exactly the refusal-message, distinguishability, and
                 positive-path tests; wired = 6 passed [VERIFIED].
  best-known?:   yes — checkout-relative invocation ($(dirname $0)) so the
                 deployed run checkout calls its own producer.
  scope:        one wrapper + its test file. No entry loop (S3-P4), no ntfy
                policy change (refusals stay calm; only real failures page).
REVIEW:    codex (haorensjtu-dev).
