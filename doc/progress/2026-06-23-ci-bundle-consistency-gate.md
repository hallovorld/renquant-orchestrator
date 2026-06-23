# CI gate for model<->config bundle consistency

STATUS:   merge-pending (PR #173). Additive; the production check script is unchanged.
WHAT:     .github/workflows/bundle-consistency.yml + tests/test_bundle_consistency_ci_gate.py run the
          merged #172 check_bundle as a hard CI gate on model/config/bundle PRs.
WHY-DIR:  the 2026-06-23 deploy hit 4 contracts one-by-one in PROD; #172 added the check but nothing
          enforced it pre-merge. Now model<->config drift fails in CI, not on the live tree.
EVIDENCE: 14 tests pass; reported contract names asserted == live preflight; CLI non-zero on a broken
          fixture; the bundle-consistency CI check ran green on the PR. `[VERIFIED — CI + pytest]`
NEXT:     widen the trigger path globs as new artifact families appear.
