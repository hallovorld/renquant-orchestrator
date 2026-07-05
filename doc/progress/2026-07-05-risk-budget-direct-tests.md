# +59 direct unit tests for risk_budget/budget + report

STATUS:   fixed and pushed; progress-doc gate was the only CI failure.
WHAT:     added `tests/test_risk_budget_budget.py` (39 tests: connect, equity curve,
          HWM, positions, SPY returns, sleeve thresholds, dd censoring, drawdown edge
          cases, beta composition) and `tests/test_risk_budget_report.py` (20 tests:
          build_statement edge paths, render_markdown, write_statement, forbidden
          paths, CLI args) — no production code changed.
WHY/DIR:  closes the 0-direct-test gap flagged in the 104-107 completion report for
          risk_budget/budget.py and risk_budget/report.py; the CI progress-doc gate
          failed because no doc/progress artifact was included with the original push.
EVIDENCE: `make test` → 2684 passed, 2 skipped. `[VERIFIED — make test, this session]`
NEXT:     none — test-only PR, no follow-up required.
