# rq105 intraday pairing logger — zero-sessions root cause + fix

STATUS:   fix implemented and verified read-only against the real 2026-07-02
          inputs (runs DB `mode=ro`, output redirected to a scratchpad path —
          the live pilot JSONL was not touched). Full suite green
          (1256 passed, 3 skipped).
REVISION: r1
WHAT:     the first scheduled run of `intraday_pairing_logger` (2026-07-02
          13:15 PT, `--date 2026-07-02`) reported every counter zero —
          `sessions: 0`, `admitted pairs: 0`, `rows written: 0` — despite the
          previous session's batch having submitted a real OXY entry and
          34,463 valid intraday ticks existing for the session. Three defects
          inside the logger, all against the CURRENT live DB contract:
          (a) DEAD ADMIT PREDICATE — `load_admitted` requires
              `candidate_scores.selected = 1`, which the live pipeline stopped
              stamping after 2026-05-22 (last: `2026-05-22-live-ff554178`).
              A submitted entry is now `selected = 0` with
              `blocked_by = 'broker_pending_submitted'` plus a `trades` row
              `action='buy_pending'`, `order_type='NEW_BUY'`. The query matches
              nothing on every live session, so the logger was structurally
              zero forever, not just on 07-02.
          (b) SESSION SEMANTICS — `collect(date=T)` used T for BOTH the
              admitting `pipeline_runs.run_date` AND the tick-file date key,
              but the batch that fills at session T's open runs post-close on
              the PREVIOUS session (run_date = T−1). The two can never both
              match; the fill's session was excluded by construction.
          (c) NON-DERIVABLE ELIGIBILITY — the frozen first-eligible-tick rule
              refuses to select without an eligibility instant, and the real
              #216 tick lines stamp `session_open`/`session_close` but never
              `eligible_after`, so `with intraday tick` was 0 despite a full
              day of valid quotes.
          Fix: admits for session T now come from the previous session's
          NEW_BUY/TOP_UP submissions (`load_submitted_entries` +
          `resolve_admitting_run_date`; legacy `selected=1` path kept for
          sim/backfill DBs, deduplicated defensively), and the frozen §11b
          window (open+5min .. close−30min) is derived from the ticks' own
          session stamps as the last eligibility fallback (`derive_frozen_window`
          — pre-registered rule applied to stamped bounds, not a new DOF).
          Regression tests reproduce the exact zero-session condition against a
          current-live-schema DB (0/0/0 on old code → 1/1/1 fixed).
WHY/DIR:  Stage-1 pilot data collection (#208 §9, #231 N1) is DATA-BOUND; a
          collector that structurally collects nothing is a silent failure of
          the whole stage. Direction: pair from what the live path actually
          stamps, censor what it does not, never impute.
EVIDENCE: run log `logs/rq105/intraday_pairing_logger_2026-07-02.log` (all
          zeros); runs DB: zero `selected=1` rows on any live run after
          2026-05-22, OXY stamped `buy_pending`/`NEW_BUY` on
          `2026-07-01-live-01c54b39`; broker ground truth (read-only orders
          API): the OXY order was CANCELED pre-open at 2026-07-02T02:56:04Z
          with `filled_qty=0` — the task premise "OXY filled at today's open"
          is corrected; the only 07-02 fill was a CRWD SELL @192.065. The
          fixed logger on real inputs emits exactly the honest row: 1 session,
          1 admitted pair (OXY, signal_version=admitting run), intraday
          arrival = first eligible tick 15:11:49Z, censored
          `no_batch_fill+no_batch_arrival_quote`.
          EXTERNAL PRECONDITIONS (not fixable in this repo, #236-hardening
          class): (1) the batch FILL leg — live runs no longer write
          `action='buy'` fill-confirmation rows (last: 2026-05-22), and the
          `buy_pending.price` is a submit-time reference, not a fill; a
          broker-fill confirmation writer into the runs DB is umbrella-side
          work (orchestrator must not implement broker adapters). Until it
          lands, `with batch fill` stays 0 and rows are censored
          `no_batch_fill` — the designed §9.2d state, not a logger bug.
          (2) the batch ARRIVAL quote source `batch_arrival_quotes.jsonl`
          (§9.2c session-open reference producer) does not exist yet — already
          a known open item; until then `timing_component` stays null.
NEXT:     deploy = sync the run checkout
          (`/Users/renhao/git/github/renquant-orchestrator-run`) to the merged
          pin — merged is not deployed. Once synced, the next 13:15 PT run
          (`--date 2026-07-03`) will emit the GRMN pair row (admitted by
          `2026-07-02-live-85496d1c`), with the intraday-tick leg populated and
          the fill leg censored until the fill-confirmation writer exists.
          Note the GRMN order itself may be canceled pre-open like OXY was
          (after-hours submissions have been canceled and selectively
          resubmitted ~11:00Z by the umbrella order lifecycle); the pair row is
          emitted either way — a canceled entry is a censored observation, not
          a dropped one.
