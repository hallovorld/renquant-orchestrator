"""Decision ledger (#108 S2) — append-only gate-verdict event store.

One row per (run_id, scope, gate): the verdict a gate returned, its reason, and
the inputs it saw. Append-only (16.1 taxonomy — never UPDATE), WAL mode, busy
timeout (multiple agents contend on the same DB). The payoff: the kind of
sell-only / false-BEAR autopsy that took ~3 hours of log archaeology becomes one
SQL query (see ``verdicts_for``).

This is the persistence half of S2; ``gate_registry.GateRegistry`` produces the
verdicts and calls ``write_verdicts`` once per run.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

DEFAULT_DB = Path.home() / "renquant-data/decision_ledger.db"

_VALID_VERDICTS = ("allow", "halve", "block")

DDL = """
CREATE TABLE IF NOT EXISTS decision_ledger (
  run_id TEXT NOT NULL, as_of DATE NOT NULL, scope TEXT NOT NULL,
  gate TEXT NOT NULL, verdict TEXT NOT NULL CHECK(verdict IN ('allow','halve','block')),
  reason TEXT NOT NULL, inputs_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (run_id, scope, gate)
) WITHOUT ROWID;
"""


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open (and create) the ledger DB. Pass an explicit path (or ``:memory:``)
    for tests; defaults to the shared production DB."""
    if db_path is None:
        db_path = DEFAULT_DB
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(db_path), timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.executescript(DDL)
    return c


def write_verdicts(
    conn: sqlite3.Connection,
    run_id: str,
    as_of: str,
    verdicts: Iterable[Mapping[str, Any]],
) -> int:
    """Append verdicts for a run. INSERT OR IGNORE keeps the table append-only
    and idempotent: re-running the same (run_id, scope, gate) is a no-op, never
    a duplicate or an overwrite. Returns the number of new rows.

    Verdicts are validated app-side and fail loud: ``OR IGNORE`` would otherwise
    silently swallow a CHECK violation (an invalid verdict value) along with the
    intended PK-conflict no-op, so a bad gate value would vanish instead of
    surfacing.
    """
    rows = []
    for v in verdicts:
        verdict = v["verdict"]
        if verdict not in _VALID_VERDICTS:
            raise ValueError(
                f"invalid verdict {verdict!r} for gate {v.get('gate')!r} "
                f"(scope {v.get('scope')!r}); must be one of {_VALID_VERDICTS}"
            )
        rows.append(
            (run_id, as_of, v["scope"], v["gate"], verdict, v["reason"],
             json.dumps(dict(v.get("inputs", {})), sort_keys=True))
        )
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO decision_ledger VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn.total_changes - before


def verdicts_for(
    conn: sqlite3.Connection,
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
