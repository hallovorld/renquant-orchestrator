# import-resolution checker resolves like the daily, not like the invoking shell

**Date:** 2026-08-03 · `renquant-orchestrator` · GOAL-3 / ops-audit burn-down #769 item 5

STATUS:    code + tests; deploys via the routine run-checkout sync.
WHAT:      `_ensure_daily_resolution()` — the checker APPENDS each sibling
           checkout's src/ (the same repo set scripts/daily_104.sh builds via
           renquant_subrepo_pythonpath) before resolving. Append, not
           prepend: a caller-exported PYTHONPATH keeps precedence, so under
           the daily's environment the checker measures THAT resolution
           unchanged, and bare (launchd / ops-audit) it measures the sibling
           set — never a third thing.
WHY:       ops-audit's first scheduled run: `import-resolution exit=1 —
           renquant_backtesting.BacktestPipeline unresolvable
           (ModuleNotFoundError)` + renquant_execution ×2. Reproduced bare;
           the same imports succeed under the daily's path set — the checker
           was measuring the invoking shell's environment, the inverse of
           the tests-that-measure-the-operators-disk class.  [VERIFIED]

EVIDENCE:

```
pre-fix bare:  3 unresolvable (BacktestPipeline, get_broker,
               BrokerExecutionPipeline), rc=0-with-problems into the
               aggregator's findings bucket
post-fix bare: "import-resolution OK — 14 symbols resolve as reviewed" rc=0
               [VERIFIED — this session]
suite:         5496 passed / 0 failed (2 new: bare-subprocess regression,
               caller-precedence)
```

## Revert

git revert; the checker returns to shell-relative resolution and the
ops-audit finding returns.
