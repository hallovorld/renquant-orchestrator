# Wire decision_pnl_attribution into CLI

STATUS: delivered
WHAT: Add `decision-pnl` subcommand to the orchestrator CLI.
WHY/DIR: The `decision_pnl_attribution` module (192 lines, 15 tests) was fully
implemented but not reachable from the CLI. Sibling modules `decision_ledger`
(`ledger-query`) and `ledger_attribution` (`gate-value`) were already wired.
This was a gap in the 107 decision-ledger tooling surface.

## Changes

- `src/renquant_orchestrator/cli.py`: Added `decision-pnl` subparser (accepts
  `--db` for run DB path) and handler that runs the full attribution pipeline
  (load -> classify -> attribute_by_class -> selection_edge) and emits JSON
  with `return_column`, `n_decisions`, `edge` dict, and `by_class` breakdown.
- `tests/test_cli.py`: Added `test_decision_pnl_cli_emits_attribution` using a
  hermetic tmp_path sqlite DB seeded with candidate_scores and
  ticker_forward_returns.

## Evidence

```
tests/test_cli.py::test_decision_pnl_cli_emits_attribution PASSED
tests/test_decision_pnl_attribution.py (15/15 passed)
```

NEXT: none -- module is now fully wired and queryable via
`renquant-orchestrator decision-pnl [--db <path>]`.
