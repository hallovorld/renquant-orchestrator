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

ROUND 2 (codex review):
FINDING 1 (fixed): "do not implement broker adapters here" is a hard
          CLAUDE.md boundary this PR violated by defining `AlpacaBrokerPort`
          locally. Moved it to renquant-execution (renquant-execution#21) —
          `order_state_machine.BrokerPort`'s own docstring already said
          "Alpaca adapter implements this later," confirming that's where it
          belonged. This repo now only IMPORTS it
          (`renquant_execution.alpaca_broker_port.AlpacaBrokerPort`) as the
          CLI's default `port_factory`; `LiveTickExecutor`/`LiveSessionRunner`
          already took the port as an injected `BrokerPort` dependency and
          never changed. The adapter's one "no positive reference price"
          contract check now raises a new execution-owned
          `BrokerPortContractError` (not this repo's `Stage2ContractError`) —
          no reverse dependency from execution back onto orchestrator. The
          matching test moved to renquant-execution's test suite verbatim
          (request-shaping only, no network). Net: -148 lines here (was
          1795, now ~1650), no orchestrator behavior change. Verified: full
          suite still 1532 passed / 3 skipped locally against the fixed
          renquant-execution branch; hosted CI on THIS repo will stay red
          until renquant-execution#21 merges to main (cross-repo dependency
          ordering — same pattern as this session's common/base-data pin
          cascade), since CI checks out renquant-execution's main, not this
          feature branch.
FINDING 2 (acknowledged, not resolved by this fix): "the execution plan is
          ahead of the evidence plan" — the §9.3a quadruple gate (all flags
          OFF) remains the runtime safety mechanism, but the §9.4 economic
          authorization decision this concern raises is a SEPARATE,
          not-yet-settled gate. This fix does not attempt to resolve it —
          only finding 1 (the architecture-boundary violation) was in scope
          for a code change.

ROUND 3 (codex follow-up, pursuing option (a) — shrink to the minimum seam):
FINDING 2, REVISITED: codex confirmed finding 1 fixed, then sharpened
          finding 2 into two options — (a) shrink to the minimum
          orchestrator integration seam needed to exercise the gate and
          state-book contract, or (b) pair with a preregistered canary
          packet stating exact go/no-go metrics before this much live-path
          machinery lands. Pursued (a): (b) would require authoring an
          experimental-design/capital-risk protocol that isn't this fix's
          call to make unilaterally.
WHAT MOVED: removed `LiveSessionRunner` (the session-driving loop: gate
          evaluation → live-tick dispatch → shadow fallback → manifest
          tracking, ~270 lines) and its CLI entry point (`main()` +
          `argparse` wiring, ~220 lines) from
          `intraday_live_executor.py` entirely — not stubbed, genuinely
          removed, since a stub still carries import/test/interface
          maintenance surface. `LiveTickExecutor` (the actual
          gate→OrderStateBook→broker-port integration seam, fully testable
          against a fake port) and everything upstream of it (the §9.3a
          quadruple gate, `Stage2Authorization`, `ArmDecision`,
          `LiveActionLog`, `DeadManSwitch`, entry-cap enforcement) is
          UNCHANGED and fully implemented/tested — this is what codex
          named as the genuinely exercisable seam.
WHY KEPT SEPARATE FROM STUBBING: a stub (e.g. `LiveSessionRunner` raising
          `NotImplementedError`) still needs an import, a constructor
          signature to keep in sync with its dependencies, and either
          dead tests or maintained tests-for-a-stub — none of which
          reduces the "long-lived maintenance surface... review burden"
          codex named as the actual cost. Full removal does; the design
          is preserved instead (design doc §7 + this PR's git history at
          commit `21583e93`, the pre-round-3 state).
EVIDENCE: diff size 4 files / 2885 lines (design+progress docs unchanged,
          impl 1666→1194 lines [-472, -28%], tests 905→660 lines [-245]).
          Removed 3 session-runner-level tests
          (`test_mode_live_without_authorization_file_still_shadows`,
          `test_armed_live_session_submits_through_the_fake_port`,
          `test_armed_session_with_kill_switch_present_stays_shadow`) plus
          their `make_runner`/`run_full_session`/`FakeCalendar`/
          `ManualClock`/`fake_signal`/`fake_live_state`/`fake_tick_runner`
          fixtures — all specific to the removed class, not the
          gate/executor contract. Cleaned ~25 now-dead imports
          (`argparse`, `SessionScheduler`, `ShadowTickWriter`,
          `TickRunner`, session-input helpers, path defaults) that were
          only reachable from the removed code. 46/46 module tests pass;
          1634/1634 repo-wide (was 1566 before this PR's own additions
          netted against the cut — confirms zero regression to anything
          else in the repo).
NOT RESOLVED: this still does not settle whether the canary is the right
          experiment to run (§9.4) — that decision remains the actual
          blocker for ever rebuilding `LiveSessionRunner`, per design doc
          §7's "what would need to be true to rebuild this."
CONCURRENT ROUND 3 (independently landed while this round was in
          progress — now superseded): a parallel fix made the
          `AlpacaBrokerPort` import lazy (`_load_alpaca_broker_port_cls()`,
          invoked inside the CLI's default `port_factory` only after
          arming, so merge order with renquant-execution#21 stayed free
          and a session arming without the adapter failed closed with
          `Stage2ContractError`). Since this round removes the CLI/
          `port_factory`/`LiveSessionRunner` entirely, that loader is now
          unreachable dead code and was removed along with them — the
          insight (defer the adapter import, fail closed at arming, not
          at module import) is preserved in design doc §7's rebuild
          sketch for whoever eventually builds the session runner.
