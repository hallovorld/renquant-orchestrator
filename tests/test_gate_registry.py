"""Tests for ``gate_registry`` (#108 S2) — the verdict algebra.

Specific cases pin the semantics; seeded randomized trials (no Hypothesis in
this env) prove the three structural properties the codex blocker required:
order-independence, risk-monotonicity, block-dominance.
"""
from __future__ import annotations

import random

from renquant_orchestrator.gate_registry import ORDER, GateRegistry, GateVerdict


def _v(gate, scope, verdict):
    return GateVerdict(gate, scope, verdict, "r", {})


def test_empty_is_allow():
    assert GateRegistry().aggregate("AAPL") == ("allow", 1.0, [])


def test_single_verdicts():
    for verdict, mult in [("allow", 1.0), ("halve", 0.5), ("block", 0.0)]:
        r = GateRegistry()
        r.submit(_v("g", "AAPL", verdict))
        v, m, _ = r.aggregate("AAPL")
        assert (v, m) == (verdict, mult)


def test_halve_composes_before_caps():
    r = GateRegistry()
    r.submit(_v("a", "AAPL", "halve"))
    r.submit(_v("b", "book", "halve"))
    v, m, _ = r.aggregate("AAPL")
    assert v == "halve" and m == 0.25  # 0.5 ** 2


def test_block_dominates_halves():
    r = GateRegistry()
    r.submit(_v("a", "AAPL", "halve"))
    r.submit(_v("b", "AAPL", "block"))
    v, m, _ = r.aggregate("AAPL")
    assert v == "block" and m == 0.0


def test_book_scope_binds_every_ticker():
    r = GateRegistry()
    r.submit(_v("breaker", "book", "block"))
    r.submit(_v("local", "AAPL", "allow"))
    assert r.aggregate("AAPL")[0] == "block"
    assert r.aggregate("MSFT")[0] == "block"  # book applies to a ticker with no local verdict


def test_ticker_scope_is_isolated():
    r = GateRegistry()
    r.submit(_v("local", "AAPL", "block"))
    assert r.aggregate("AAPL")[0] == "block"
    assert r.aggregate("MSFT") == ("allow", 1.0, [])  # AAPL block does not leak


def test_ledger_rows_records_every_submitted_verdict():
    r = GateRegistry()
    r.submit(_v("a", "book", "halve"))
    r.submit(_v("b", "AAPL", "block"))
    rows = r.ledger_rows()
    assert len(rows) == 2
    assert {row["gate"] for row in rows} == {"a", "b"}
    assert all(set(row) == {"scope", "gate", "verdict", "reason", "inputs"}
               for row in rows)


def _rand_verdicts(n, rng):
    return [GateVerdict(f"g{i}", rng.choice(["book", "AAPL"]),
                        rng.choice(list(ORDER)), "r", {}) for i in range(n)]


def test_properties_over_randomized_trials():
    rng = random.Random(7)
    for _ in range(2000):
        vs = _rand_verdicts(rng.randint(0, 8), rng)
        r = GateRegistry()
        for v in vs:
            r.submit(v)
        v1, m1, _ = r.aggregate("AAPL")

        # P1 order-independence
        r2 = GateRegistry()
        for v in rng.sample(vs, len(vs)):
            r2.submit(v)
        assert (v1, m1) == r2.aggregate("AAPL")[:2]

        # P2 risk-monotonicity: adding a gate never increases permissiveness
        r.submit(GateVerdict("extra", "AAPL", rng.choice(list(ORDER)), "r", {}))
        v2, m2, _ = r.aggregate("AAPL")
        assert ORDER[v2] >= ORDER[v1] and m2 <= m1 + 1e-12

        # P3 block-dominance
        if any(v.verdict == "block" for v in vs if v.scope in ("book", "AAPL")):
            assert v1 == "block" and m1 == 0.0
