# rq105 shadow decision loop — transient class-C read timeout no longer kills the session

STATUS: delivered (fix + regression; SHADOW / never-submit posture unchanged)
WHAT:   makes the Stage-1 renquant105 shadow session loop RESILIENT to a transient
        broker read timeout on the READ-ONLY class-C snapshot. `AlpacaLiveStateSource.snapshot`
        now surfaces a retry-exhausted TRANSIENT broker failure (timeout / throttle /
        connection reset on `get_account` / `get_all_positions`) as the new
        `TickInputUnavailable`; the `SessionScheduler` loop catches it, records the tick as
        skipped in the manifest (`skipped_ticks` + `tick_input_error_count`), and CONTINUES
        the observe-only session. A sustained outage (`MAX_CONSECUTIVE_TICK_INPUT_FAILURES=5`
        in a row) still HARD-halts loudly. Every Tier-1 critical path is untouched:
        `ShadowModeViolation` -> `halted_shadow_violation`; a non-transient / unknown error ->
        `halted_tick_error`; class-A leak / class-B mutation still abort/halt.
WHY/DIR: RFC #208 §9.3 — "any *critical* reject ... -> HARD halt ... transient non-critical
        rejects (venue/throttle/no-quote) are counted for the ledger." The loop was
        conflating a transient non-critical read timeout with a Tier-1 critical condition
        and losing the whole day's shadow session. This is the single nearest engineering
        notch: the "≥5 clean recorded shadow sessions" evidence every downstream gate needs
        cannot accrue while one broker blip kills a session (2 of ~5 pilot sessions died this
        way, then the loop was disabled by env flag from 2026-07-17 on).

EVIDENCE: read-only diagnosis, path-pinned. Pilot corpus is a DURABLE operator artifact
          (`/Users/renhao/git/github/RenQuant/logs/renquant105_pilot/`); code is main ==
          the 2026-07 pin for the two touched files (verified `git merge-base --is-ancestor`).

  Claim 1 — the 2026-07-14 halt was a transient broker read timeout on the class-C GET,
            NOT a critical safety condition.
    artifact:   logs/renquant105_pilot/intraday_session_manifest_2026-07-14.json
    prod or exp:   production pilot corpus (read-only)
    existing data:   `"status": "halted_tick_error"`, `"errors": ["APIError: {\"code\":50410000,
                \"message\":\"request timed out\"}"]`, `tick_count: 1`, `last_tick_at
                09:37:05`, `updated_at 09:52:58` (~16 min of ret+ retries then give-up).
                2026-07-13 twin: same `halted_tick_error`, `errors: ["ReadTimeout:
                HTTPSConnectionPool(host='paper-api.alpaca.markets', ...): Read timed out"]`,
                `tick_count: 9`. Shadow log confirms 1 recorded tick on 07-14, 9 on 07-13 —
                i.e. the halt hit the NEXT tick's live-state snapshot, not a decision fault.
    best-known?: n/a — the incident under diagnosis
    scope:      2 halted sessions (07-13, 07-14); both broker read timeouts on read-only GETs
    [VERIFIED — the two manifests + intraday_decisions_shadow.jsonl, read-only]

  Claim 2 — the raise site is the scheduler's broad `except Exception` that stamps
            `halted_tick_error` and re-raises for ANY non-ShadowModeViolation tick error.
    artifact:   src/renquant_orchestrator/intraday_session_scheduler.py (run_session loop)
                + src/renquant_orchestrator/intraday_session_inputs.py
                (`AlpacaLiveStateSource.snapshot` -> `_broker_call_with_retry`)
    prod or exp:   production code (main)
    existing data:   pre-fix `except Exception as exc: self._stamp("halted_tick_error", ...); raise`
                catches the retry-exhausted broker timeout raised by `snapshot()` via
                `live_state_provider`; `main()` returns 1 -> launchd wrapper fires a FAILED
                alert. `_broker_call_with_retry` already rides out transients (3 attempts /
                60s) but RE-RAISES on exhaustion — with no resilient landing in the loop.
    best-known?: n/a
    scope:      the Stage-1 shadow scheduler tick loop
    [VERIFIED — code read, main == pilot-run pin for both files]

  Claim 3 — with the fix a transient snapshot timeout SKIPS one tick and the session
            completes shadow-clean; a sustained outage still hard-halts; non-transient and
            never-submit faults still hard-halt.
    artifact:   tests/test_intraday_session_scheduler.py, tests/test_intraday_session_inputs.py
    prod or exp:   experiment (regression tests)
    existing data:   new tests — `test_transient_input_failure_skips_tick_and_completes` (07-14
                repro: status `completed`, `tick_input_error_count==1`, 4 recorded ticks),
                `test_persistent_input_outage_still_hard_halts` (fuse -> `halted_tick_error`),
                `test_intermittent_input_failures_reset_the_fuse`,
                `test_non_transient_tick_error_still_hard_halts`,
                `test_snapshot_wraps_transient_broker_timeout` (+ by-message +
                non-transient-reraise + happy-path). Full suite green.
    best-known?: n/a
    scope:      scheduler loop + class-C snapshot; shadow mode only
    [VERIFIED — pytest, see PR CI]

SAFETY: no live arming. `mode` stays shadow (`assert_shadow_never_submits` untouched); no
        order/submit path added; `AlpacaLiveStateSource` remains GET-only; the default-OFF
        triple gate, the §9.4 economic-authorization gate, and `intraday_session_runner`'s
        live path are all untouched. No live-tree / umbrella / launchd writes in this PR.

NEXT: (lead, NOT done here — merged != deployed) after codex approval + merge, advance the
      `renquant-orchestrator-run` pin to include this fix, then re-arm the shadow loop by
      uncommenting `export RENQUANT_INTRADAY_DECISIONING=1` in
      `ops/renquant105/run_session_scheduler.sh` (launchd label
      `com.renquant.rq105-session-scheduler`; mode MUST stay `shadow`). Confirm never-submit:
      the manifest `mode_effective` is `shadow` and 0 orders exist at the broker
      (`AlpacaLiveStateSource` has no submit path). Target: ≥5 clean recorded shadow sessions
      + green §6 replay audit.
