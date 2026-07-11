# Workstream: exit-plane coherence + durable wash-sale ledger (#484 fixes 5+6)

STATUS:   proposed (design PR open, awaiting Codex + operator review; no
          implementation started). Design:
          `doc/design/2026-07-11-exit-plane-coherence-and-wash-ledger.md`.
GOAL:     (1) ModelProtectionExitTask may only fire on a scoring plane that
          passes the buy path's staleness axes AND is coherent with the
          admitting plane (defer→fail-closed hybrid, 3-stage flag-gated
          rollout); (2) wash-sale enforcement derives from an append-only,
          hash-chained, broker-fill ledger (owner renquant-execution;
          orchestrator runs invariant checker I-W1..6) instead of the
          mutable live_state.last_sell_dates.
EVIDENCE: 9 protection exits in 20 sessions, 8/9 against a positive panel
          view, 0 strike resets ever, 3/9 exits in 24 min; NFLX whipsaw
          −1.69% then +8.8%/5d; NFLX wash stamp erased 06-26 (H2), GE
          wrongly blocked 8 sessions (H3/#474).
          `[VERIFIED — design doc §2.2/§3.1, read-only sweep 2026-07-11]`
NEXT:     on design approval: Stage-0 telemetry PR (pipeline) + Phase-0/1
          ledger backfill+shadow PRs (execution + orchestrator checker);
          enforcement stages are separate approvals.
CONSTRAINT: exits-always-allowed — path-risk exits (stops/gate B/panel
          exit/broker GTC) stay unconditional; CrossSectionalPanelExit is
          predictive, do not relitigate; no new umbrella authority (R-PIN);
          live_state corrections before Phase 2 are ask-first operator
          actions.
