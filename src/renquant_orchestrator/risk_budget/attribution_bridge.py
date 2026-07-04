"""Bridge: attribution engine legs → DD-budget consumption (107 sprint D3).

Answers ONE question for the risk-budget statement: **which leg of the
decision P&L identity (market / signal / sizing / timing / cost) is consuming
the drawdown budget?**

It consumes the merged attribution engine
(:mod:`renquant_orchestrator.attribution`) as its read model — round trips
from ``ledger.build_round_trips``, legs from ``decompose.decompose_round_trip``
with the enforced sum-check — and only AGGREGATES. No decomposition logic is
re-implemented here.

Censoring propagates explicitly (#253 and the attribution engine's other
censor reasons): a censored leg contributes nothing to any total and is
COUNTED, with its notional, in the ``censoring`` block. June-2026-era records
have TIMING/SIZING/COST censored by the fill-confirmation boundary — a leg
table that silently summed only what survives would be quietly wrong about
exactly the window the current drawdown lives in, so the coverage statement
is part of the answer, not a footnote.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from renquant_orchestrator.attribution import decompose as dc
from renquant_orchestrator.attribution import ledger as lg

LEG_NAMES = dc.LEG_NAMES


def decomposed_results(
    conn: sqlite3.Connection,
    run_type: str = "live",
    half_spread_bps: float = 0.0,
    allow_sim: bool = False,
) -> list[dict[str, Any]]:
    """Round trips → per-decision leg decompositions, identity-checked."""
    trips = lg.build_round_trips(conn, run_type=run_type, allow_sim=allow_sim)
    results = [dc.decompose_round_trip(t, half_spread_bps=half_spread_bps) for t in trips]
    dc.assert_identity(results)
    return results


def _in_window(result: dict[str, Any], start: str, end: str) -> bool:
    """A decision participates in the DD window when its holding span
    [entry date, exit date or still-open] intersects [start, end]."""
    entry = result.get("date")
    if entry is None or entry > end:
        return False
    exit_date = result.get("exit_date")
    return exit_date is None or exit_date >= start


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, float] = {leg: 0.0 for leg in LEG_NAMES}
    n_present: dict[str, int] = {leg: 0 for leg in LEG_NAMES}
    censored: dict[str, dict[str, int]] = {leg: {} for leg in LEG_NAMES}
    total_pnl = 0.0
    n_decomposed = 0
    for r in results:
        if r.get("total_pnl") is not None:
            total_pnl += r["total_pnl"]
            n_decomposed += 1
        for leg in LEG_NAMES:
            v = r["legs"].get(leg)
            if v is not None:
                totals[leg] += v
                n_present[leg] += 1
            else:
                reason = r["censored"].get(leg, "absent")
                censored[leg][reason] = censored[leg].get(reason, 0) + 1
    ranking = sorted(
        (
            {"leg": leg, "total": totals[leg], "n": n_present[leg]}
            for leg in LEG_NAMES
        ),
        key=lambda row: row["total"],
    )
    return {
        "n_records": len(results),
        "n_decomposed": n_decomposed,
        "total_pnl_decomposed": total_pnl,
        "leg_totals": totals,
        "leg_n": n_present,
        "leg_censored": censored,
        # most negative first: the DD-budget consumers
        "dd_consumers": [row for row in ranking if row["total"] < 0],
        "ranking": ranking,
    }


def leg_dd_consumption(
    conn: sqlite3.Connection,
    dd_window: tuple[str, str] | None = None,
    run_type: str = "live",
    half_spread_bps: float = 0.0,
    allow_sim: bool = False,
) -> dict[str, Any]:
    """Per-leg P&L totals overall AND restricted to the current drawdown
    window (peak date → as-of), with explicit censoring counts for both
    views. ``dd_window`` comes from the budget module's running-drawdown
    reading (``max_drawdown_peak_date`` → ``as_of``)."""
    results = decomposed_results(
        conn, run_type=run_type, half_spread_bps=half_spread_bps, allow_sim=allow_sim
    )
    out: dict[str, Any] = {"overall": _aggregate(results)}
    if dd_window is not None:
        start, end = dd_window
        in_window = [r for r in results if _in_window(r, start, end)]
        out["dd_window"] = {"start": start, "end": end, **_aggregate(in_window)}
    return out
