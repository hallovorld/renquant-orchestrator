STATUS:   fixed (reconciliation)
WHAT:     `scripts/shadow_ab_daily.sh` and `tests/test_shadow_ab_daily_script.py` had silently
          reverted to a PRE-round-1 state by the time round-3's fix (immutable run manifest,
          explicit runtime inputs, bar validity — landed as commit 11e81c24 by a concurrent
          session working the same PR) got pushed: the canonical `native-live-market-snapshot`
          artifact with real LocalStore prices + a universe-matches-pinned-watchlist assertion
          (round-1) and the portable `timeout`/`gtimeout`/bash-watchdog enforcement with the
          GNU-timeout exit-124 remap (round-1/round-2) were both gone, and
          `tests/test_shadow_ab_daily_script.py` (7 tests across 3 rounds) did not exist in that
          commit's tree at all. This round reconciles: reapplies the market-snapshot and
          portable-timeout fixes ON TOP OF round-3's explicit-runtime-input / immutable-manifest
          / bar-validity work (which is legitimate, valuable, and kept as-is), and rebuilds the
          test file adapted to the NEW required-env-var interface
          (RENQUANT_SHADOW_AB_PYTHON/_RUN_MANIFEST/_REPO_ROOT/_STRATEGY_DIR, replacing the old
          sibling-lookup/umbrella-default interface the original tests assumed).
WHY/DIR:  Two independent agents (this session's dispatched fork + a concurrent session,
          Claude-Session session_01DV6yNCNn64pEgDn325os3i) were both fixing round-2 findings on
          #460 at the same time; the concurrent session's push landed with a base predating this
          session's round-1/round-2 commits, and neither side's local history carried the other's
          work forward. Caught by directly reading the current file content after this session's
          fork reported a rate-limit error mid-task (rather than trusting a summary) — the actual
          diff showed the OLD hand-rolled snapshot JSON (no "prices" field) and the OLD
          unconditional `timeout_cmd=()` with no watchdog fallback, both silently back.
EVIDENCE: Recreated `tests/test_shadow_ab_daily_script.py` (9 cases): explicit-required-env
          fail-closed, no-umbrella-path-default (checked both as "no default value" and "concept
          only in comments", since the concept is legitimately named in prose explaining its own
          absence), run-manifest wrong-commit/dirty-tree rejection via REAL git repos (not
          stubbed — the stubbed shadow-ab call in the other tests would trivially "pass"
          regardless of manifest correctness, so these two specifically let the real Python
          verify_run_manifest execute), missing-local-close-price fail-closed, sealed-snapshot-
          universe-matches-watchlist, and the two portable-timeout cases (hung session killed +
          marked exit=4 regardless of whether this host's PATH happens to have a real
          timeout/gtimeout; fast exit code passes through unchanged). Verified meaningful via
          stash-revert: 6/9 failed against the pre-reconciliation script. Fixed one fixture bug
          along the way (the fake strategy-104 git repo was written-into AFTER its initial
          commit, leaving it permanently "dirty" and silently masking the dirty/wrong-commit
          rejection tests' actual validity in earlier drafts of this fix). Full suite: 3401
          passed, 4 skipped, 1 pre-existing unrelated failure (hardcoded-sibling-path artifact of
          running from an isolated worktree, reproduces identically on main). shellcheck clean.
NEXT:     none for this reconciliation. Codex's round-3 review (this same commit) is still
          pending its own first look at the manifest/bar-validity work; this reconciliation only
          restores round-1/round-2 coverage alongside it, it does not re-litigate round-3.
