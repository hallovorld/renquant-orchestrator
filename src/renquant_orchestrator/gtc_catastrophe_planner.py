"""GTC catastrophe-stop planner (#108 G1) — the dead-box broker-resident line.

If this Mac dies, the positions at the broker are NAKED: every soft stop lives
in *this* process and dies with it. G1 keeps a broker-resident GTC stop order at
a fixed catastrophe drawdown below entry (``-20%`` by default) for every open
holding, re-synced on each rebalance, so the catastrophe line survives a host
failure even when the orchestrator is down.

This module is the **planner only** — it is pure and side-effect free. It maps
the current holdings and the broker's existing GTC stops onto an *idempotent*
order plan (``PLACE`` / ``REPLACE`` / ``CANCEL``). It never talks to a broker and
never mutates live state; production order submission is wired separately
(S0-PR-G1). That split is what makes the plan testable and auditable.

Plan contract (idempotent, fail-closed on sizing):
  * **PLACE** a GTC stop for a holding with no broker stop, at
    ``round(entry_price * (1 - catastrophe_dd), 2)``.
  * **REPLACE** an existing stop only when it drifts more than ``tolerance``
    (1% by default) from the wanted price — small rounding noise never churns
    the broker book.
  * **CANCEL** any broker stop whose ticker is no longer held (position closed).
  * Re-planning after the plan is applied yields **no new PLACE** actions
    (idempotency), and every PLACE carries a strictly positive ``stop_price``.

The planner is deterministic and order-independent: tickers are processed in
sorted order so the emitted plan is stable across runs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

# Broker-resident catastrophe line: stop at this fraction below entry.
CATASTROPHE_DD = 0.20

# Re-place a stop only when it drifts more than this fraction from the target,
# so sub-cent rounding never churns the broker order book.
DEFAULT_TOLERANCE = 0.01


def catastrophe_stop_price(entry_price: float, catastrophe_dd: float = CATASTROPHE_DD) -> float:
    """The broker-resident GTC stop price for a holding, rounded to cents."""
    return round(entry_price * (1 - catastrophe_dd), 2)


def plan(
    holdings: Mapping[str, Mapping[str, Any]],
    existing_stops: Mapping[str, float],
    *,
    catastrophe_dd: float = CATASTROPHE_DD,
    tolerance: float = DEFAULT_TOLERANCE,
) -> list[dict]:
    """Map holdings + existing broker stops onto an idempotent order plan.

    Args:
        holdings: ``{ticker: {"entry_price": float, "shares": int}}`` — the open
            positions whose catastrophe line must be broker-resident.
        existing_stops: ``{ticker: stop_price}`` — the GTC stops the broker
            currently holds.
        catastrophe_dd: drawdown below entry for the catastrophe line.
        tolerance: fractional drift above which an existing stop is REPLACEd.

    Returns:
        A list of action dicts (``PLACE`` / ``REPLACE`` / ``CANCEL``), tickers in
        sorted order. Re-running ``plan`` after applying the PLACEs yields no new
        PLACE actions (idempotent).
    """
    actions: list[dict] = []
    for ticker, holding in sorted(holdings.items()):
        want = catastrophe_stop_price(holding["entry_price"], catastrophe_dd)
        have = existing_stops.get(ticker)
        if have is None:
            actions.append({
                "action": "PLACE", "ticker": ticker, "type": "stop",
                "tif": "gtc", "stop_price": want, "qty": holding["shares"],
            })
        elif abs(have - want) / want > tolerance:
            actions.append({
                "action": "REPLACE", "ticker": ticker, "from": have, "to": want,
            })
    for ticker in sorted(set(existing_stops) - set(holdings)):
        actions.append({
            "action": "CANCEL", "ticker": ticker, "reason": "position closed",
        })
    return actions


def holdings_from_live_state(raw: Mapping[str, Any]) -> dict[str, dict]:
    """Extract ``{ticker: {entry_price, shares}}`` from a live_state dict.

    Mirrors the read-only prototype: a holding is the per-ticker high-water mark
    (``position_hwm``) for each ticker present in ``entry_dates``. Holdings with
    no recorded HWM are skipped (no entry anchor to stop against). ``shares`` is
    a unit placeholder — share counts are resolved against the broker at
    submission time, not by the planner.
    """
    holdings: dict[str, dict] = {}
    entry_dates = raw.get("entry_dates") or {}
    position_hwm = raw.get("position_hwm") or {}
    for ticker in entry_dates:
        hwm = position_hwm.get(ticker)
        if hwm:
            holdings[ticker] = {"entry_price": float(hwm), "shares": 1}
    return holdings


def stops_from_live_state(raw: Mapping[str, Any]) -> dict[str, float]:
    """Extract ``{ticker: stop_price}`` from a live_state ``stop_orders`` block."""
    stop_orders = raw.get("stop_orders") or {}
    return {
        ticker: order["stop_price"]
        for ticker, order in stop_orders.items()
        if isinstance(order, Mapping) and order.get("stop_price")
    }


def plan_from_live_state(
    raw: Mapping[str, Any],
    *,
    catastrophe_dd: float = CATASTROPHE_DD,
    tolerance: float = DEFAULT_TOLERANCE,
) -> list[dict]:
    """Plan the catastrophe stops directly from a loaded live_state dict."""
    return plan(
        holdings_from_live_state(raw),
        stops_from_live_state(raw),
        catastrophe_dd=catastrophe_dd,
        tolerance=tolerance,
    )


def plan_from_live_state_file(
    path: str | Path,
    *,
    catastrophe_dd: float = CATASTROPHE_DD,
    tolerance: float = DEFAULT_TOLERANCE,
) -> list[dict]:
    """Read a live_state JSON file and plan its catastrophe stops (read-only)."""
    raw = json.loads(Path(path).read_text())
    return plan_from_live_state(raw, catastrophe_dd=catastrophe_dd, tolerance=tolerance)
