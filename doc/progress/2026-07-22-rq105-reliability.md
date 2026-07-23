# rq105 collector reliability — un-missable alert + fail-loud capture + auto-restart   (PR #567)

STATUS:    delivered
WHAT:      Three fixes for a class of silent rq105 tick-collector stalls
           observed 07-14/16/17/20/22 (`logs/renquant105_pilot/intraday_ticks.jsonl`
           froze ~08:37 PT while the session ran to 13:00 PT, with no error
           logged and no actionable ntfy):
           (1) `ops/renquant105/rq105_liveness_check.py` — the 14:00 PT
           liveness check now alerts at `priority=urgent` +
           `tags=rotating_light,rq105` + title `"🚨 rq105 DOWN …"` instead of
           default priority on the shared `"renquant"` topic, where it was
           getting lost in the noise; optional `RQ105_NTFY_TOPIC` routes to a
           dedicated topic, defaulting back to the working `"renquant"` topic
           if unset.
           (2) `ops/renquant105/run_quote_logger.sh` — rewritten to run the
           collector in the background under `trap … EXIT/TERM/INT/HUP` +
           `wait` instead of foreground-then-check-$?, so a hang or a
           process-group kill is captured instead of silently losing the
           wrapper too. Any termination writes a non-empty crash log
           (`logs/rq105/quote_logger_crash_<date>.log`) with exit code +
           timestamp + day-log tail, then fires the Fix-1 alert. A background
           feed-staleness watchdog fires the same alert + a `SILENT STALL`
           crash record within `WATCHDOG_STALE_SECONDS` (default 15 min)
           instead of waiting for the 14:00 PT check. A normal full-session
           completion stays silent.
           (3) `com.renquant.rq105-quote-logger.plist` +
           `ops/launchd_manifest.json` — added
           `KeepAlive={SuccessfulExit:false}` (+ `ThrottleInterval=60`) so a
           mid-session crash auto-restarts instead of being fatal for the
           rest of the day; the wrapper's session-window guard stops
           KeepAlive from thrashing off-session; the watchdog can kill a
           hung collector so KeepAlive restarts it; an alert cooldown
           (default 30 min) rate-limits the urgent ntfy on a respawn loop.
           `ProgramArguments` is unchanged, so `program_args_sha256` and the
           run-surface drift scan stay valid.
           Does not touch the observe-only collector module itself (no
           order path, no state). Root cause of the underlying stall is
           still unknown — these fixes make the next occurrence
           diagnosable, loud, and recoverable, not the stall itself.
           (4) [fix pass, codex CHANGES_REQUESTED] `run_quote_logger.sh` —
           the wall-clock session-window guard alone let a weekday NYSE
           holiday through; the collector's own calendar then exits it
           cleanly within seconds and the old code misread that as an
           unexpected "stopped early" crash, false-paging urgent. Added an
           exchange-calendar guard (reuses the same fail-closed
           `liveness_common.is_session_day()` primitive
           `rq105_liveness_check.py` already uses) that clean-no-ops BEFORE
           the collector launches on a real holiday, and fails CLOSED
           (proceeds to launch) if the calendar check itself errors.
WHY/DIR:   GOAL-5 (daily-run reliability). rq105 has been silently losing
           collector coverage on live-session days with no operator signal;
           this closes the detection/capture/recovery gap so the next stall
           is caught same-session instead of discovered hours later (or not
           at all).
EVIDENCE:  n/a
           This PR is operational/reliability tooling (alerting, process
           supervision, launchd config), not a model or data claim — no
           IC/Sharpe/APY number is reported.
NEXT:      Machine-landing (installing/reloading the new plist) is
           operator-gated and NOT done by this PR:
           `launchctl bootout gui/$(id -u)/com.renquant.rq105-quote-logger`
           then `launchctl bootstrap gui/$(id -u) <installed>/com.renquant.rq105-quote-logger.plist`
           after syncing the `renquant-orchestrator-run` checkout to the
           merged pin. A follow-up could extend
           `ops/run_surface_drift_check.py` to track `KeepAlive` as a
           first-class field (it currently only tracks `ProgramArguments`).
           Live failure observation is still needed to find the stall's
           root cause; these fixes only make that observation possible.
           RESOLVED this pass: codex's holiday-false-alarm BLOCKER (see
           Fix 4 above) and the progress-doc `EVIDENCE:` exact-match gap
           (the mechanical checker requires `EVIDENCE:` to be literally
           `n/a` on its own line for the no-model-claim exemption; the
           prior wording appended prose on the same line).

## Revert steps

- `git revert` the merge (or restore the four files to their `origin/main`
  state): `ops/renquant105/run_quote_logger.sh`,
  `ops/renquant105/rq105_liveness_check.py`,
  `ops/renquant105/com.renquant.rq105-quote-logger.plist`,
  `ops/launchd_manifest.json`.
- If the new plist is already installed and `KeepAlive` misbehaves:
  reinstall the pre-change plist (no `KeepAlive`) and `bootout`+`bootstrap`,
  or set `RQ105_WATCHDOG_KILL=0` (alert-only) / raise
  `RQ105_ALERT_COOLDOWN_SECONDS` via the job's environment. All new
  thresholds are env-overridable with the previous behavior recoverable by
  env alone.

## Tests

- `tests/test_rq105_quote_logger_failloud.py` (new): drives the wrapper
  end-to-end with a stub collector + stub ntfy sender (no venv, no
  network) — non-zero exit -> crash record + urgent/tagged alert; silent
  hang -> watchdog alert + kill for KeepAlive restart; hang alert-only when
  kill disabled; off-window clean no-op; clean full-session silence;
  holiday no-op (stubbed calendar check) -> no crash log, no alert;
  calendar-check-unavailable fails closed and still runs the collector;
  text guardrails. (Skips off darwin / without zsh.) Confirmed the new
  holiday test FAILS pre-fix (`proc.returncode == 1` instead of `0`) and
  passes post-fix.
- `tests/test_rq105_liveness.py` (extended): `_alert` forwards urgent
  priority + distinctive tags; `RQ105_NTFY_TOPIC` routing; end-to-end stale
  fixture -> `main` sends an urgent, tagged, `🚨 … DOWN` alert.
- `tests/test_rq105_ops_wrappers.py` (extended): plist carries
  `KeepAlive=SuccessfulExit:false`; manifest records the reviewed intent
  with `ProgramArguments` unchanged.

Suite: full `pytest` green except pre-existing, unrelated failures
(`test_bundle_seal.py` collection — stale `renquant_artifacts` sibling; and
3 `test_retrain_sigma_head_rawlabel` data-pin cases) present on
`origin/main` before this change.

Focused re-run (this fix pass): `pytest -q tests/test_rq105_quote_logger_failloud.py
tests/test_rq105_liveness.py tests/test_rq105_ops_wrappers.py` -> 25 passed
(23 prior + 2 new holiday-guard tests).
