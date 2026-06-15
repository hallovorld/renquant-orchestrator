"""Tests for ``decision_ledger`` (#108 S2) — append-only verdict store.

Uses an in-memory DB so the suite never touches the shared production ledger.
Centres on the autopsy query (the S2 payoff) and append-only idempotency, plus
the GateRegistry → ledger bridge.
"""
from __future__ import annotations

import pytest

from renquant_orchestrator.decision_ledger import (
    connect,
    verdicts_for,
    write_verdicts,
)
from renquant_orchestrator.gate_registry import GateRegistry, GateVerdict


# The real 2026-06-11 false-BEAR cascade (#92 audit numbers) — the run whose
# autopsy took ~3 hours of log archaeology.
_FALSE_BEAR = [
    {"scope": "book", "gate": "bear_override", "verdict": "block",
     "reason": "hard_bear via 5d_vol route",
     "inputs": {"vol_5d": 0.26, "thr": 0.25, "ret_5d": -0.0257}},
    {"scope": "book", "gate": "drawdown_breaker", "verdict": "block",
     "reason": "dd 5.94% > BEAR halt 5%", "inputs": {"dd": 0.0594, "halt": 0.05}},
    {"scope": "book", "gate": "transition_window", "verdict": "block",
     "reason": "regime flip cooldown", "inputs": {"bars": 3}},
    {"scope": "book", "gate": "kelly_sizing", "verdict": "block",
     "reason": "capped_zero all 12 candidates", "inputs": {"n": 12}},
]


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def test_schema_created(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(decision_ledger)")]
    assert cols == ["run_id", "as_of", "scope", "gate", "verdict", "reason",
                    "inputs_json"]


def test_write_returns_new_row_count(conn):
    n = write_verdicts(conn, "run-1", "2026-06-11", _FALSE_BEAR)
    assert n == 4


def test_append_only_idempotent(conn):
    write_verdicts(conn, "run-1", "2026-06-11", _FALSE_BEAR)
    # re-writing the same (run_id, scope, gate) with a different reason is ignored
    dup = [{"scope": "book", "gate": "bear_override", "verdict": "block",
            "reason": "MUTATED", "inputs": {}}]
    added = write_verdicts(conn, "run-1", "2026-06-11", dup)
    assert added == 0
    total = conn.execute("SELECT COUNT(*) FROM decision_ledger").fetchone()[0]
    assert total == 4
    # original reason preserved (append-only, never overwritten)
    reason = conn.execute(
        "SELECT reason FROM decision_ledger WHERE gate='bear_override'"
    ).fetchone()[0]
    assert reason == "hard_bear via 5d_vol route"


def test_autopsy_query_one_shot(conn):
    """The S2 payoff: 'why was 2026-06-11 sell-only?' is one query."""
    write_verdicts(conn, "2026-06-11-live-f68231b0", "2026-06-11", _FALSE_BEAR)
    rows = verdicts_for(conn, "2026-06-11", "book")
    assert [r["gate"] for r in rows] == [
        "bear_override", "drawdown_breaker", "kelly_sizing", "transition_window"]
    assert all(r["verdict"] == "block" for r in rows)
    # inputs round-trip as parsed dicts
    bear = next(r for r in rows if r["gate"] == "bear_override")
    assert bear["inputs"]["vol_5d"] == 0.26


def test_invalid_verdict_fails_loud(conn):
    """OR IGNORE would silently swallow a CHECK violation, so an invalid verdict
    must be rejected app-side (fail-loud), not vanish."""
    with pytest.raises(ValueError, match="invalid verdict"):
        write_verdicts(conn, "run-1", "2026-06-11",
                       [{"scope": "book", "gate": "g", "verdict": "BOGUS",
                         "reason": "r", "inputs": {}}])
    # nothing partially written
    assert conn.execute("SELECT COUNT(*) FROM decision_ledger").fetchone()[0] == 0


def test_registry_persist_bridge(conn):
    """GateRegistry.persist writes every submitted verdict; it reads back."""
    r = GateRegistry()
    r.submit(GateVerdict("bear_override", "book", "block", "hard_bear", {"vol_5d": 0.26}))
    r.submit(GateVerdict("kelly_sizing", "book", "block", "capped_zero", {"n": 12}))
    added = r.persist(conn, "2026-06-11-live-f68231b0", "2026-06-11")
    assert added == 2
    rows = verdicts_for(conn, "2026-06-11", "book")
    assert {row["gate"] for row in rows} == {"bear_override", "kelly_sizing"}
