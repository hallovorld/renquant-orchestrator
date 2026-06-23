# Daily trading-health reporter + decision-ledger persistence + alert

STATUS:   merge-pending (PR #174). Additive, strictly read-only on the live broker/state.
WHAT:     daily_trading_health.py (account_trading / model_health / cash_deployment) + a
          daily-trading-health CLI + tests; persists verdicts via the unwired GateRegistry->
          decision_ledger bridge; alerts via post_ntfy on a bad day.
WHY-DIR:  the account was sell-only / under-deployed for weeks with no surfacing; the #133 / #108-S2
          ledger was merged but unwired.
EVIDENCE: 15 tests (mocked broker+ledger): healthy=no alert; sell-only / stale-artifact / no-orders
          all alert; fail-soft. make test 452 passed; make doctor ok. `[VERIFIED — make test]`
NEXT:     register the launchd entry + inline a post-run call in daily.py (left out to stay read-only).
