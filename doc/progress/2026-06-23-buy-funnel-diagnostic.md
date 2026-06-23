# Read-only buy-funnel diagnostic

STATUS:   merge-pending (PR). Additive, strictly READ-ONLY (parses logs; no orders, no state change).
WHAT:     scripts/buy_funnel_report.py + tests. Parses logs/live_e2e/*.log into a structured
          per-run funnel (panel -> vol-gate -> VetoWeakBuys -> Kelly -> P-WF-GATE block -> buys)
          and names the BINDING constraint per run + its frequency.
WHY-DIR:  the account is under-deployed (2026-06-03 cash-drag study). The funnel is recorded ONLY
          in live_e2e logs (the pipeline_runs table has no funnel counters), so deciding which
          deployment lever to touch was a guess. This makes it measurable — the disciplined
          prerequisite to changing any live sizing/quality gate (a lesson from 2026-06-23: get a
          trustworthy measurement before changing live behaviour).
EVIDENCE: 5 tests pass (blocked-run -> P-WF-GATE binding + 0 buys; healthy-run -> Kelly-mu binding;
          missing stages degrade to None; last-match-wins on retries; report aggregates frequency).
          Run on the real logs: the 8 available runs (all 2026-05-30) were P-WF-GATE-blocked 8/8
          (0 buys) — quantifies the 2026-06-03 "pipeline down" finding. Caveat: those logs are
          stale; today P-WF-GATE is unblocked (XGB deploy this session), so the tool's value is
          surfacing the CURRENT binding constraint as fresh logs arrive. `[VERIFIED — pytest + real logs]`
NEXT:     it does NOT change deployment. It is the measurement layer for the entangled deployment
          levers (VetoWeakBuys rank floor, Kelly mu<edge gate, P-WF-GATE flicker) — those remain
          operator-gated risk decisions. Optional follow-up: a structured MeasureBuyFunnel recorder
          in the runner so the funnel is captured without log-parsing.
