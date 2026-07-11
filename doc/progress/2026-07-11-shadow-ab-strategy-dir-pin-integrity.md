STATUS:   fixed
WHAT:     `scripts/shadow_ab_daily.sh` accepted `RENQUANT_SHADOW_AB_STRATEGY_DIR` as a SEPARATE,
          independent required input, passed unchanged to `--strategy-dir` on the shadow-ab
          CLI — even though the run manifest's own `renquant-strategy-104` entry (verified
          commit + clean tree by `verify_run_manifest` before either arm) already resolves the
          SAME repo for arm configs. Removed the independent input entirely: `STRATEGY_DIR` is
          now derived from the same manifest-resolved path used to build `STRATEGY_CONFIGS`,
          so there is exactly one resolved path for both, and no parameter through which a
          caller could thread a divergent, unverified checkout into artifact-fingerprint
          resolution.
WHY/DIR:  Codex re-review of #460 (on the round-1/round-2 reconciliation commit 2df8440a):
          "the wrapper resolves CONFIG_A/B and the data manifest from the run-manifest
          strategy checkout, but it separately accepts RENQUANT_SHADOW_AB_STRATEGY_DIR and
          passes it as --strategy-dir. run_shadow_ab_session then honors that explicit
          argument over the manifest path for artifact fingerprint resolution. A mismatched
          external strategy directory can therefore pair pinned configs with artifacts from
          an arbitrary checkout."
EVIDENCE: Added `test_rogue_strategy_dir_env_var_cannot_diverge_the_cli_argument`: sets a
          rogue `RENQUANT_SHADOW_AB_STRATEGY_DIR` pointing at an unverified directory, captures
          the stub's OWN argv (not what the stubbed-out runner would do with it — the CLI
          argument itself), and asserts `--strategy-dir` always carries the manifest-resolved
          path, never the rogue one. First draft of this test asserted on the market
          snapshot's watchlist instead and PASSED even against the pre-fix script — the
          watchlist was never actually at risk (CONFIG_A/B were already manifest-derived in
          both versions); rewrote to capture and check the actual `--strategy-dir` CLI
          argument, which correctly FAILS against the pre-fix script (asserts equal to the
          rogue path) and passes against the fix. 10 tests total in the file now. Full suite:
          3402 passed, 4 skipped, 1 pre-existing unrelated failure (hardcoded-sibling-path
          artifact of running from an isolated worktree, reproduces identically on main).
          shellcheck clean.
NEXT:     none for this round. Codex noted "Then this PR is ready for final review" pending
          this fix.
