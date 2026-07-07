# 2026-07-07 — Fix rq105 session-scheduler shell script

**PR**: orchestrator bugfix

## Bug

`run_session_scheduler.sh` in the repo was missing two changes that the
operator manually applied to the `-run` deployment checkout on 2026-07-06:

1. **subrepo PYTHONPATH**: the scheduler imports from pipeline/model/execution
   subrepos at runtime, but the repo script only had orchestrator+common on
   PYTHONPATH. Without subrepo paths, the scheduler fails on import.

2. **RENQUANT_INTRADAY_DECISIONING=1**: the triple-gate activation was
   uncommented in `-run` but still commented out in the repo.

The `-run` checkout also had a stale `--mode paper` argument that the CLI
does not accept (mode is controlled via config, not CLI). This caused the
deployed scheduler to fail with `unrecognized arguments: --mode paper`.
The repo version correctly does NOT have `--mode paper`.

## Test

Added `test_session_scheduler_wrapper_cli_args_are_valid` — extracts CLI
args from the shell script and validates them against the real argparse
definition. Would have caught the `--mode paper` bug.

## Root cause

Shell scripts fell behind operator hotfixes applied directly to the `-run`
deployment checkout. This PR syncs the repo to match the correct deployed
behavior (minus the `--mode paper` bug).
