# Wire intraday_replay_audit into CLI

STATUS: delivered
WHAT: Added `replay-audit` subcommand to `renquant-orchestrator` CLI
WHY/DIR: The 105 session replay audit module (`intraday_replay_audit.py`) existed
with its own `main()` entry point and tests but was not reachable from the
unified CLI, preventing operational use via `renquant-orchestrator replay-audit`.
EVIDENCE: 2888 passed, 3 skipped, 0 failed (full test suite)
NEXT: Operational use of `replay-audit` in daily 105 shadow session auditing

## Changes

- `src/renquant_orchestrator/cli.py`: Added `replay-audit` subparser and
  dispatch handler delegating to `intraday_replay_audit.main()`. Used pre-split
  argv approach (matching the `repos exec` pattern) to work around an argparse
  `parse_known_args` + `REMAINDER` interaction where `--` prefixed pass-through
  args are misrouted to the unknown bucket.
- `tests/test_cli.py`: Added `test_replay_audit_cli_delegates_to_module` that
  verifies the CLI subcommand delegates argv correctly to the module's `main()`.
