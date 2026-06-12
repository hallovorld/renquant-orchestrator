#!/usr/bin/env python3
"""Broker reconciliation state machine (#108 III.4) — replaces improvised warnings.

Invariants: broker = source of truth for POSITIONS; state = source of truth
for INTENT/derived (streaks, anchors, clocks). Idempotent client_order_id.
Table-driven tests cover every transition incl. the real STATE-EXT-SELL
case from 2026-06-11 (GE/META/HON vanished after a stale state restore).
"""
from __future__ import annotations

import hashlib
from typing import NamedTuple


class Action(NamedTuple):
    kind: str          # OK|EXT_SELL|QUARANTINE|ADOPT_QTY|FORCED_COVER
    ticker: str
    detail: str


def reconcile(state_positions: dict[str, float],
              broker_positions: dict[str, float]) -> list[Action]:
    acts = []
    for t in sorted(set(state_positions) | set(broker_positions)):
        s, b = state_positions.get(t), broker_positions.get(t)
        if s is not None and b is None:
            acts.append(Action("EXT_SELL", t,
                               "stamp wash-sale clock today; GC streaks/anchors; ledger row"))
        elif s is None and b is not None:
            acts.append(Action("QUARANTINE", t,
                               "unknown external position: NO orders on this name; alert"))
        elif s is not None and b is not None and abs(s - b) > max(0.01, abs(b) * 1e-4):
            if s > 0 > b or (s > 0 and b < 0):
                acts.append(Action("FORCED_COVER", t, "sign flip = buy-in/external short event"))
            else:
                acts.append(Action("ADOPT_QTY", t, f"adopt broker qty {b} (was {s}); ledger row"))
        else:
            acts.append(Action("OK", t, ""))
    return acts


def client_order_id(run_id: str, ticker: str, intent: str, qty: float) -> str:
    """Idempotency: a crash between submit and persist cannot double-submit —
    the broker dedups on this id."""
    return hashlib.sha1(f"{run_id}|{ticker}|{intent}|{qty:.4f}".encode()).hexdigest()[:24]


if __name__ == "__main__":
    CASES = [
        # (state, broker, expected kinds) — first row is the REAL 2026-06-11 event
        ({"MU": 1, "GE": 1, "EQIX": 1, "META": 1, "HON": 1}, {"MU": 1, "EQIX": 1},
         {"GE": "EXT_SELL", "META": "EXT_SELL", "HON": "EXT_SELL", "MU": "OK", "EQIX": "OK"}),
        ({"MU": 1}, {"MU": 1, "TSLA": 5}, {"TSLA": "QUARANTINE", "MU": "OK"}),
        ({"MU": 2}, {"MU": 1}, {"MU": "ADOPT_QTY"}),
        ({"MU": 1}, {"MU": -1}, {"MU": "FORCED_COVER"}),
        ({}, {}, {}),
    ]
    for state, broker, want in CASES:
        got = {a.ticker: a.kind for a in reconcile(state, broker)}
        assert got == want, (state, broker, got, want)
    # idempotency proofs
    a = client_order_id("r1", "MU", "SELL", 1.0)
    assert a == client_order_id("r1", "MU", "SELL", 1.0)            # deterministic
    assert a != client_order_id("r1", "MU", "SELL", 2.0)            # qty-sensitive
    assert a != client_order_id("r2", "MU", "SELL", 1.0)            # run-scoped
    print(f"{len(CASES)} table-driven transitions ✓ (incl. the real 2026-06-11 "
          "GE/META/HON EXT_SELL event); client_order_id idempotency ✓")
