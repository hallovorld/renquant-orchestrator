"""Decision ledger (#108 S2) — append-only gate-verdict event store.

Persistence primitives (connect, write_verdicts, DDL) live in
renquant-common and are re-exported here for backward compatibility.
Query helpers (verdicts_for) remain orchestrator-local.

V-003 remediation: pipeline was importing connect/write_verdicts from
this module, creating a reverse dependency.  Now both repos import from
renquant_common.decision_ledger.
"""
from __future__ import annotations

import json

from renquant_common.decision_ledger import (  # noqa: F401 — re-export
    DDL,
    DEFAULT_DB,
    _VALID_VERDICTS,
    connect,
    write_verdicts,
)


def verdicts_for(
    conn,
    as_of: str,
    scope: str,
) -> list[dict]:
    """The autopsy query: every gate verdict for a day+scope, ordered by gate.
    Replaces hours of log archaeology for 'why was this run sell-only?'."""
    cur = conn.execute(
        "SELECT gate, verdict, reason, inputs_json FROM decision_ledger "
        "WHERE as_of = ? AND scope = ? ORDER BY gate",
        (as_of, scope),
    )
    return [
        {"gate": g, "verdict": v, "reason": r, "inputs": json.loads(i)}
        for g, v, r, i in cur.fetchall()
    ]
