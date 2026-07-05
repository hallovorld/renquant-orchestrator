# Wire all remaining entry-point modules into CLI

**Date:** 2026-07-05
**Status:** Ready for review
**Supersedes:** #375, #376, #377, #378, #379, #380, #381, #382

## Summary

Consolidates 8 separate wiring PRs into one to avoid serial merge conflicts
on `cli.py` and `strategy_snapshot.json`. All modules with `main()` entry
points that were unreachable from the CLI are now wired.

## New CLI subcommands (9 total)

| Subcommand | Module | Sprint area |
|---|---|---|
| `parking-sleeve` | `parking_sleeve` | S7 cash-drag |
| `transfer-coefficient` | `transfer_coefficient` | S-TC evidence |
| `readiness-monitor` | `readiness_monitor` | ops/105 |
| `edgar-harvest` | `sec_edgar_harvester` | N3 data |
| `entry-timing` | `entry_timing_policy` | 105 entry |
| `train-gbdt` | `train_gbdt` | training |
| `patchtst-cutoff` | `patchtst_weekly_cutoff` | training |
| `replay-audit` | `intraday_replay_audit` | 105 audit |
| `risk-budget-report` | `risk_budget.report` | 107 risk |

## New scheduled jobs (2)

- `parking_sleeve_shadow` — daily parking-sleeve shadow allocation
- `readiness_monitor` — daily data-accumulation readiness check

## Test results

2889 passed, 2 skipped, 0 failures.

## Round 2 (Codex review)

STATUS:   fixed and pushed.
WHAT:     `parking_sleeve.py` had no `main()` — the CLI/scheduled-job wiring
          dispatched to a symbol that did not exist on this branch. Fixed by
          adding a `main()` entry point that reads book state from a
          `--book-state-json` file (portfolio_value/positions_value/
          cash_value/beta_positions/regime), computes the allocation, and
          optionally appends a shadow-log record — a deliberately minimal
          CLI surface; it does not fetch live book state itself. Separately,
          writing CLI delegation coverage surfaced a real, distinct bug:
          `nargs=argparse.REMAINDER` positionals do not reliably capture a
          leading flag-like token (e.g. `--json` as the first pass-through
          arg) — it leaks into `unknown` and previously hit a hard
          `parser.error`. Fixed for all affected REMAINDER subcommands by
          reattaching `unknown` to each target module's argv (extending the
          pattern `edgar-harvest` already used). Added a functional test for
          `parking-sleeve` (real book-state JSON in, allocation JSON out) and
          8 delegation tests (one per remaining wired subcommand, via the
          monkeypatch-main pattern already used elsewhere in `test_cli.py`)
          covering `transfer-coefficient`, `readiness-monitor`,
          `edgar-harvest`, `entry-timing`, `train-gbdt`, `patchtst-cutoff`,
          `replay-audit`, `risk-budget-report`.
WHY/DIR:  Codex: "the command is wired to a symbol that does not exist...
          CI stayed green only because this PR no longer carries the CLI
          test coverage that the fragmented superseded PRs had... I also
          want at least focused CLI delegation coverage for the nontrivial
          pass-through cases kept here, especially replay-audit and
          edgar-harvest." Writing that coverage is what surfaced the
          REMAINDER bug — a real operator running e.g.
          `renquant-orchestrator transfer-coefficient --json` would have hit
          the same `SystemExit(2)` the missing tests would have caught.
EVIDENCE: reproduced the REMAINDER bug directly before the fix landed:
          `parser.parse_known_args(['transfer-coefficient', '--json'])` →
          `args.tc_args == []`, `unknown == ['--json']`. Full suite: 2895
          passed, 3 skipped, 2 pre-existing unrelated failures in
          `test_bundle_consistency_ci_gate.py` (confirmed reproducing
          identically on clean `origin/main` earlier this session).
          `[VERIFIED — pytest + manual argparse repro, this session]`
NEXT:     none — `parking-sleeve`'s book-state-JSON-input design is a
          disclosed scope choice, not a gap; a future PR could add a live
          book-state-fetching wrapper if a real caller needs one.
