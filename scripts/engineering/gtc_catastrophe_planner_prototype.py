#!/usr/bin/env python3
"""G1 GTC catastrophe-stop planner prototype (#108 Week-0 disaster guard).

If this Mac dies, positions at the broker are NAKED — every stop lives in
this process. G1 keeps broker-resident GTC stop orders (-20% from entry) as
the dead-box catastrophe line, synced on each rebalance.

This prototype is READ-ONLY: it loads the real live state + real broker
positions and prints the order plan (place/replace/cancel) without
submitting anything. Production wiring = S0-PR-G1.
"""
from __future__ import annotations

import json
from pathlib import Path

CATASTROPHE_DD = 0.20     # broker-resident line: -20% from entry
R = Path("/Users/renhao/git/github/RenQuant")


def plan(holdings: dict, existing_stops: dict) -> list[dict]:
    """holdings: {ticker: {entry_price, shares}}; existing_stops:
    {ticker: stop_price}. Returns idempotent order plan."""
    actions = []
    for t, h in sorted(holdings.items()):
        want = round(h["entry_price"] * (1 - CATASTROPHE_DD), 2)
        have = existing_stops.get(t)
        if have is None:
            actions.append({"action": "PLACE", "ticker": t, "type": "stop",
                            "tif": "gtc", "stop_price": want,
                            "qty": h["shares"]})
        elif abs(have - want) / want > 0.01:
            actions.append({"action": "REPLACE", "ticker": t,
                            "from": have, "to": want})
    for t in sorted(set(existing_stops) - set(holdings)):
        actions.append({"action": "CANCEL", "ticker": t,
                        "reason": "position closed"})
    return actions


if __name__ == "__main__":
    raw = json.loads((R / "backtesting/renquant_104/live_state.alpaca.json").read_text())
    holdings = {}
    for t, d in (raw.get("entry_dates") or {}).items():
        hwm = (raw.get("position_hwm") or {}).get(t)
        if hwm:
            holdings[t] = {"entry_price": float(hwm), "shares": 1}
    stops = {t: s.get("stop_price") for t, s in (raw.get("stop_orders") or {}).items()
             if isinstance(s, dict) and s.get("stop_price")}
    p = plan(holdings, stops)
    print(f"holdings={list(holdings)}  existing broker stops={list(stops) or 'NONE'}")
    print(f"catastrophe plan ({len(p)} actions):")
    for a in p:
        print(" ", a)
    # invariants
    assert all(a["action"] != "PLACE" or a["stop_price"] > 0 for a in p)
    again = plan(holdings, {**stops, **{a["ticker"]: a["stop_price"]
                                        for a in p if a["action"] == "PLACE"}})
    assert not [a for a in again if a["action"] == "PLACE"], "idempotency violated"
    print("IDEMPOTENT: re-planning after placement yields no new PLACE actions")
