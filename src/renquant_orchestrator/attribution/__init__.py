"""Decision-ledger attribution engine (107 sprint D3).

Per-decision P&L decomposition into SIGNAL / TIMING / SIZING / COST legs
(plus the explicit MARKET/benchmark leg and a must-be-zero RESIDUAL), built
on the read model that joins ``candidate_scores`` + ``trades`` +
``ticker_forward_returns`` + ``pipeline_runs`` in the run DB.

Extends (does not replace) ``decision_pnl_attribution`` (#145), which
answers the *class-level* question "what did SELECTED vs VETOED earn in
forward returns". This package answers the *per-decision dollar* question:
"of what this decision made or lost, how much was the pick, how much the
entry/exit prices, how much the sizing pipeline, how much cost".

Modules
-------
- ``ledger``    — the unified per-decision read model + round-trip builder.
- ``decompose`` — the attribution identity and its enforced sum-check.
- ``report``    — book-level rollups, coverage/censoring report, CLI.
"""
from renquant_orchestrator.attribution.decompose import (
    LEG_NAMES,
    assert_identity,
    decompose_round_trip,
)
from renquant_orchestrator.attribution.ledger import (
    build_round_trips,
    connect,
    load_decision_ledger,
)
from renquant_orchestrator.attribution.report import (
    build_report,
    coverage_report,
    render_markdown,
)

__all__ = [
    "LEG_NAMES",
    "assert_identity",
    "decompose_round_trip",
    "build_round_trips",
    "connect",
    "load_decision_ledger",
    "build_report",
    "coverage_report",
    "render_markdown",
]
