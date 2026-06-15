"""GateRegistry (#108 S2) — the one decision choke point + verdict algebra.

Every risk/admission gate submits a ``GateVerdict`` to one registry; the
registry aggregates them with a formal, order-independent algebra and persists
the lot to the decision ledger. That gives S2 its payoff: one place that decides,
and one query that explains the decision afterwards.

Verdict algebra (lattice ``allow < halve < block``):
  * **max-join**: the book/ticker verdict is the most restrictive submitted —
    so adding a gate is risk-monotone (never more permissive).
  * **halve composition**: each ``halve`` multiplies the size by 0.5, applied
    BEFORE any caps; ``block`` forces the multiplier to 0.
  * **order-independent**: the result does not depend on submission order.
  * **block dominance**: any ``block`` in scope ⇒ verdict ``block``, multiplier 0.

``scope`` is ``"book"`` (applies to every ticker) or a ticker symbol (applies to
that ticker only).
"""
from __future__ import annotations

from typing import Literal, NamedTuple

Verdict = Literal["allow", "halve", "block"]

# Lattice order — higher is more restrictive.
ORDER: dict[str, int] = {"allow": 0, "halve": 1, "block": 2}


class GateVerdict(NamedTuple):
    gate: str
    scope: str            # "book" | ticker symbol
    verdict: Verdict
    reason: str
    inputs: dict


class GateRegistry:
    """Collect gate verdicts, aggregate them, persist them."""

    def __init__(self) -> None:
        self._verdicts: list[GateVerdict] = []

    def submit(self, verdict: GateVerdict) -> None:
        self._verdicts.append(verdict)

    def _in_scope(self, scope: str) -> list[GateVerdict]:
        # Book-level verdicts bind every ticker; ticker verdicts bind only it.
        return [v for v in self._verdicts if v.scope in ("book", scope)]

    def aggregate(self, scope: str) -> tuple[Verdict, float, list[GateVerdict]]:
        """Return (verdict, size_multiplier, contributing_verdicts) for a scope.

        Empty ⇒ ("allow", 1.0, []). The multiplier is 0.0 on block, else
        0.5 ** (number of halve verdicts).
        """
        vs = self._in_scope(scope)
        if not vs:
            return "allow", 1.0, []
        top = max(vs, key=lambda v: ORDER[v.verdict])
        n_halve = sum(1 for v in vs if v.verdict == "halve")
        mult = 0.0 if ORDER[top.verdict] == ORDER["block"] else 0.5 ** n_halve
        contributing = sorted(vs, key=lambda v: -ORDER[v.verdict])
        return top.verdict, mult, contributing

    def ledger_rows(self) -> list[dict]:
        """All submitted verdicts as decision_ledger row dicts (every gate is
        recorded, not just the aggregate winner — that is the audit trail)."""
        return [
            {"scope": v.scope, "gate": v.gate, "verdict": v.verdict,
             "reason": v.reason, "inputs": v.inputs}
            for v in self._verdicts
        ]

    def persist(self, conn, run_id: str, as_of: str) -> int:
        """Write every submitted verdict to the decision ledger. Returns the
        number of new rows (idempotent per (run_id, scope, gate))."""
        from renquant_orchestrator.decision_ledger import write_verdicts
        return write_verdicts(conn, run_id, as_of, self.ledger_rows())
