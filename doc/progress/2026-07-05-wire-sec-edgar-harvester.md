# Wire sec_edgar_harvester into CLI

STATUS: delivered
WHAT: Added `edgar-harvest` subcommand to `renquant-orchestrator` CLI, wiring
      `sec_edgar_harvester.main()` as a pass-through REMAINDER command. All
      harvester arguments (`--repo-dir`, `--output`, `--tickers`/`--watchlist`,
      `--dry-run`) are forwarded transparently.
WHY: The SEC EDGAR harvester module (N3 data collection) existed as a standalone
     module but had no CLI surface. Without a subcommand, scheduling and manual
     invocation required direct `python -m` calls instead of the unified
     `renquant-orchestrator edgar-harvest` entrypoint.
WHY-DIR: Follows the existing REMAINDER pass-through pattern used by
     `model-freshness`, `sign-laundering`, `gate-calibration`, etc.
     Added `edgar-harvest` to the `parse_known_args` exclusion set (alongside
     `live-bridge`/`daily-bridge`) because REMAINDER positional args with
     flag-style values (`--repo-dir`, etc.) leak into `unknown` with
     `parse_known_args`; the dispatch merges `unknown` back into the argv.
EVIDENCE: `test_edgar_harvest_dry_run` passes (verifies CLI delegates to
     `sec_edgar_harvester.main` with correct args). `test_snapshot_not_stale`
     and `test_cli_subcommand_count_sanity` pass (snapshot regenerated).
NEXT: None -- ready for review.
