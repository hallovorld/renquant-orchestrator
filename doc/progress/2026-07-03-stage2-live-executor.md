# Stage-2 live executor built dark behind the §9.3a quadruple gate (sprint D2)

STATUS:   CODE-COMPLETE on branch `feat/stage2-live-executor`. New module
          `src/renquant_orchestrator/intraday_live_executor.py` + tests +
          design note `doc/design/2026-07-03-stage2-live-executor.md`.
          NOTHING running today changes: enablement stays behind the
          pre-registered §9.3a authorization gate (hard boundary).
OUTCOME:  The `mode:"live"` tick path exists end-to-end and DARK: pipeline
          tick intents → slice-1 `OrderStateBook` (renquant-execution #20 —
          consumed, its one-open-child / §7 economic invariants finally get
          their live consumer) → a REAL `AlpacaBrokerPort` (client-order-id
          = the child id, DAY limit/market per the recorded authorization,
          GET-only reads per the AlpacaLiveStateSource pattern) →
          fills/cancels reconciled back → book snapshot persisted per
          slice-1's shape to `data/rq105/order_state_book.json` (state
          file; Stage-1's reservations reader parses it, pinned by test).
GATE:     QUADRUPLE (§9.3a), all four or shadow-with-counter:
          (1) pinned config `intraday_decisioning.mode=="live"` (st104
          still pins "shadow" — flipping it IS the future act);
          (2) schema-validated `data/rq105/stage2_authorization.json`
          {authorized_by, date, evidence:{shadow_sessions_clean>=5,
          replay_audits_green, entry_timing_report},
          daily_entry_notional_cap (default proposal $500), expiry<=31d};
          (3) env `RENQUANT_INTRADAY_LIVE=1`;
          (4) kill-switch file absent. Port factory only invoked AFTER
          arming — an unarmed session cannot construct a submitting client.
INVARIANTS (runtime-asserted): entries/day notional never exceeds the
          authorization cap (pre-check + hard assert, GROSS-submitted,
          restart-safe from the book; EXITS NEVER CAPPED); one open child
          per parent (slice 1 enforces, this PR consumes); reconcile-
          before-emit on EVERY session start (fresh book included; mismatch
          halts entries, exits continue); every mutating broker call
          write-ahead-journaled (fsync) to
          `logs/renquant105_pilot/intraday_live_actions.jsonl` BEFORE the
          call + outcome after; dead-man: >=3 consecutive broker
          rejects/errors halt entries for the session, exits run to the
          bell; parent-intent-id pipeline/execution byte-lockstep guard
          (mismatch = hard halt).
TESTS:    tests/test_intraday_live_executor.py — the 16 gate combinations
          (only all-four arms); 15+ authorization schema rejections;
          mode="live" WITHOUT the file still shadows (counted, zero broker
          construction); cap incl. exit exemption + cross-tick gross;
          write-ahead ordering observed at the broker-call boundary;
          dead-man trip/reset; fake-broker round trip submit→partial→
          fill→snapshot→restore→reconcile with slice-1 shape parity;
          Alpaca request shaping vs an injected fake client (importorskip;
          NO live broker call anywhere). Full suite 1521 passed, 3 skipped.
          strategy-104 untouched (its shadow-only config test still pins
          the bar this PR builds against).
NEXT:     (all future, none in this PR) the authorization act = 3 steps:
          (1) st104 PR flipping mode:"live" + its test pin, then pin bump;
          (2) operator writes the signed stage2_authorization.json with the
          evidence block + $500 cap + <=31d expiry; (3) machine landing of
          RENQUANT_INTRADAY_LIVE=1 (ask-first). Until then every session
          runs the unchanged Stage-1 shadow path.
