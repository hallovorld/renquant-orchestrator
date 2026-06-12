#!/usr/bin/env python3
"""GateRegistry prototype (#108 S2-PR7) — formal verdict algebra + property tests.

Algebra (codex blocker C): lattice allow(0) < halve(1) < block(2);
aggregate = max-join => risk-monotone; halve composes 0.5^k BEFORE caps;
order-independent. Properties proven with 2000 randomized trials.
"""
from __future__ import annotations

import random
from typing import Literal, NamedTuple

ORDER = {"allow": 0, "halve": 1, "block": 2}


class GateVerdict(NamedTuple):
    gate: str
    scope: str                       # "book" | ticker
    verdict: Literal["allow", "halve", "block"]
    reason: str
    inputs: dict


class GateRegistry:
    def __init__(self):
        self._v: list[GateVerdict] = []

    def submit(self, v: GateVerdict):
        self._v.append(v)

    def _for(self, scope):
        return [v for v in self._v if v.scope in ("book", scope)]

    def aggregate(self, scope: str) -> tuple[str, float, list[GateVerdict]]:
        vs = self._for(scope)
        if not vs:
            return "allow", 1.0, []
        top = max(vs, key=lambda v: ORDER[v.verdict])
        k = sum(1 for v in vs if v.verdict == "halve")
        mult = 0.0 if ORDER[top.verdict] == 2 else 0.5 ** k
        return top.verdict, mult, sorted(vs, key=lambda v: -ORDER[v.verdict])


def _rand_verdicts(n):
    return [GateVerdict(f"g{i}", random.choice(["book", "AAPL"]),
                        random.choice(list(ORDER)), "r", {}) for i in range(n)]


if __name__ == "__main__":
    random.seed(7)
    for _trial in range(2000):
        vs = _rand_verdicts(random.randint(0, 8))
        r = GateRegistry()
        for v in vs:
            r.submit(v)
        v1, m1, _ = r.aggregate("AAPL")
        # P1 order independence
        r2 = GateRegistry()
        for v in random.sample(vs, len(vs)):
            r2.submit(v)
        assert (v1, m1) == r2.aggregate("AAPL")[:2]
        # P2 risk monotone: adding a gate never increases permissiveness
        r.submit(GateVerdict("extra", "AAPL", random.choice(list(ORDER)), "r", {}))
        v2, m2, _ = r.aggregate("AAPL")
        assert ORDER[v2] >= ORDER[v1] and m2 <= m1 + 1e-12
        # P3 block dominance
        if any(v.verdict == "block" for v in vs if v.scope in ("book", "AAPL")):
            assert v1 == "block" and m1 == 0.0
    print("2000 randomized trials: order-independence, risk-monotonicity, block-dominance hold")
