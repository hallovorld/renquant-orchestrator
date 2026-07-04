"""Risk-budget ledger (107 sprint D3) — OBSERVE-ONLY.

Budgets as data (DD 15% HARD per the G* bar; β 0.6 planning per RS-1 §2;
per-name concentration per the pinned strategy config's regime caps; the
parking sleeve's DD sub-budget per pipeline #157) + CURRENT consumption from
read-only sources, an attribution-engine bridge answering which P&L leg
consumes the DD budget, and the monthly statement with breach semantics
(>80% WARN exit 2 / >=100% CRITICAL exit 1).

No gates, no sizing, no trading behavior. Enforcement stays with the pinned
strategy config's existing controls — this package only measures them.

Modules
-------
- ``budget``             — budget definitions + consumption readers.
- ``attribution_bridge`` — per-leg DD-budget consumption (consumes the
  merged attribution engine, re-implements nothing).
- ``report``             — the statement, markdown/JSON writer, CLI.
"""
from renquant_orchestrator.risk_budget.attribution_bridge import leg_dd_consumption
from renquant_orchestrator.risk_budget.budget import (
    BETA_BUDGET_PLANNING,
    DD_BUDGET_HARD,
    build_budgets,
    burn_rate,
    connect,
    load_strategy_risk_controls,
    running_drawdown,
)
from renquant_orchestrator.risk_budget.report import (
    breach_status,
    build_statement,
    render_markdown,
    write_statement,
)

__all__ = [
    "BETA_BUDGET_PLANNING",
    "DD_BUDGET_HARD",
    "breach_status",
    "build_budgets",
    "build_statement",
    "burn_rate",
    "connect",
    "leg_dd_consumption",
    "load_strategy_risk_controls",
    "render_markdown",
    "running_drawdown",
    "write_statement",
]
