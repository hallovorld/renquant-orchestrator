# 2026-07-05 rq105 paper trading readiness checker + setup docs

## What

Added `ops/renquant105/check_paper_trading_readiness.py` -- a read-only
diagnostic that verifies all prerequisites for enabling rq105 paper trading.
Updated `ops/renquant105/README.md` with the paper trading setup process.

## Why

PR #365 merged the paper-mode authorization gate. The operator needs a
pre-flight checklist before Monday's paper trading enablement. Without it,
the operator would have to manually trace through intraday_session_runner.py
and intraday_live_executor.py to understand which files/flags/thresholds the
session runner will check at startup.

## What the checker verifies

1. `data/rq105/` directory exists
2. `section_9_4_economic_authorization.json` present with correct paper content
   (`authorized: true`, `prereg_id: rq105-paper-canary-prereg-v1`)
3. `PaperBrokerPort` importable from `renquant_execution`
4. Quintuple arming gate prerequisites:
   - G1: `intraday_decisioning.enabled=true` + `mode=live` in strategy config
   - G2: `stage2_authorization.json` present with required schema keys
   - G3: `RENQUANT_INTRADAY_LIVE` env flag set truthy
   - G4: `intraday_decisioning.KILL` file absent
   - G5: `stage2_canary_state.json` accessible (or absent = OK for first run)
5. Shadow session manifest count >= `MIN_SHADOW_SESSIONS_CLEAN_PAPER` (1)

Prints a clear pass/fail checklist with remediation instructions for failures.
Exit 0 = ready, exit 1 = blocked.

## Safety

The script is strictly read-only -- it checks files but never creates or
modifies any. Follows the same pattern as `check_activation_prereqs.py`.
