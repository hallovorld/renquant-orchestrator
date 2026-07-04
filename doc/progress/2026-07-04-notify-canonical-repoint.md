# 2026-07-04 — Re-point ntfy senders to the canonical (campaign B6, audit XC-4)

## What

Deletes this repo's 5 local `post_ntfy` transport copies + 1 local
`post_critical_ntfy` transport + 2 ops `_alert` curl copies + 8 hand-rolled
wrapper curl blocks; every sender now routes through `renquant_common.notify`
(Python) / `$RQ_ROOT/scripts/notify.sh` (shell). renquant-common floor bumped
to 0.10.0 (lockstep; `test_dependency_contracts` updated).

## The behavior change (the fix's purpose)

**The orchestrator's monitors GAIN `RENQUANT_NO_NOTIFY` honoring** — before
this, no orchestrator sender checked it (audit #296 XC-4), so the documented
ops-mute env could not silence the orchestrator's monitors. They are mutable
now. Verified by A/B harness (stubbed transports, main vs branch): under
`RENQUANT_NO_NOTIFY=1` main still POSTs at all 7 re-pointed monitor seams,
branch sends nothing.

## Re-pointed sites (Python 8 + shell 8)

- `weekly_apy_monitor.post_ntfy` (def deleted → import alias; its 3 importers
  `model_freshness_monitor` / `scorer_identity_monitor` / `retrain_alpha158_fund`
  re-pointed to common directly)
- `weekly_promote_monitor.post_ntfy` (byte-near copy deleted → import alias)
- `daily_trading_health.post_ntfy` (thin seam keeps priority=4,
  tags=warning,chart; fixes XC-10 — the docstring claimed reuse over a copy)
- `state_backup.post_ntfy` (thin seam keeps priority=3, tags=warning)
- `execution_reconciler.post_ntfy` (thin seam keeps priority=4, tags=warning,
  returns bool; injectable poster seam unchanged)
- `intraday_live_executor.post_critical_ntfy` (thin seam keeps priority=5,
  tags=rotating_light; suppression + never-raise now from common)
- `ops/pit/pit_liveness_check._alert` + `ops/renquant105/rq105_liveness_check._alert`
  (curl+.env-parse copies deleted; lazy guarded import so a stale venv logs the
  loss loudly instead of crashing the check)
- 8 wrapper curl blocks (`run_quote_logger` / `run_session_scheduler` /
  `run_postclose_loggers` / `run_shadow_serving` ×3 blocks /
  `run_c1_feature_builder` / `run_estimate_snapshotter` /
  `run_risk_budget_statement` / `run_scorer_identity_monitor`) → source
  `$RQ_ROOT/scripts/notify.sh`, call `rq_notify` (fail-soft if not yet synced)

NOT re-pointed: `native_live_run._post_live_persistence_alert` — already a
delegation to `renquant_execution.post_live_persistence_alert` (event build +
dedupe state on the live order path, another repo); flagged for an
execution-repo follow-up, out of B6's 3-repo scope.

## A/B deltas (enumerated; everything else byte-identical on the wire)

1. `RENQUANT_NO_NOTIFY=1` now suppresses all orchestrator senders (the fix).
2. ops `_alert` transport curl→urllib; scheme `ntfy.sh/…` (curl http default)
   → `https://ntfy.sh/…`; unconfigured topic now falls back to the fleet
   default `renquant` instead of silently skipping.
3. Wrapper curl gains `--max-time 5` (previously no timeout) + explicit https.
4. Never-raise broadened: all exceptions swallowed+counted (was URLError/OSError
   only — a non-latin-1 title could previously raise out of a monitor).

## Tests

`tests/test_notify_repoint.py` (14): per-seam wire shape preserved
(priority/tags/topic/timeout), NO_NOTIFY muting at every seam, reconciler bool
contract, ops `_alert` routing + muting. Full suite green (1871 passed).

## Deploy ordering

common 0.10.0 installed/synced + umbrella `scripts/notify.sh` synced BEFORE
this repo's ops pin bump (all fail-soft in the interim: Python alerts warn to
stderr, shell alerts log 127; job exit codes unaffected).
