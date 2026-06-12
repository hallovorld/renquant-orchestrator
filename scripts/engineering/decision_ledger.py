#!/usr/bin/env python3
"""Decision ledger (#108 IV / III.6) — DDL, writer, and the forensics demo.

Append-only EVENT table (16.1 taxonomy: never UPDATE), WAL mode,
busy_timeout (three agents contend). Demo backfills the REAL 2026-06-11
false-BEAR decision from the audited run and shows the autopsy that took
~3 hours of log archaeology as one SQL query.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB = Path.home() / "renquant-data/decision_ledger.db"
DDL = """
CREATE TABLE IF NOT EXISTS decision_ledger (
  run_id TEXT NOT NULL, as_of DATE NOT NULL, scope TEXT NOT NULL,
  gate TEXT NOT NULL, verdict TEXT NOT NULL CHECK(verdict IN ('allow','halve','block')),
  reason TEXT NOT NULL, inputs_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (run_id, scope, gate)
) WITHOUT ROWID;
"""


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.executescript(DDL)
    return c


def write_verdicts(c, run_id: str, as_of: str, verdicts: list[dict]):
    c.executemany(
        "INSERT OR IGNORE INTO decision_ledger VALUES (?,?,?,?,?,?,?)",
        [(run_id, as_of, v["scope"], v["gate"], v["verdict"], v["reason"],
          json.dumps(v.get("inputs", {}), sort_keys=True)) for v in verdicts])
    c.commit()


if __name__ == "__main__":
    c = connect()
    # backfill the REAL 2026-06-11 false-BEAR run from the audit (#92 numbers)
    write_verdicts(c, "2026-06-11-live-f68231b0", "2026-06-11", [
        {"scope": "book", "gate": "bear_override", "verdict": "block",
         "reason": "hard_bear via 5d_vol route", "inputs": {"vol_5d": 0.26, "thr": 0.25, "ret_5d": -0.0257}},
        {"scope": "book", "gate": "drawdown_breaker", "verdict": "block",
         "reason": "dd 5.94% > BEAR halt 5%", "inputs": {"dd": 0.0594, "halt": 0.05}},
        {"scope": "book", "gate": "transition_window", "verdict": "block",
         "reason": "regime flip cooldown", "inputs": {"bars": 3}},
        {"scope": "book", "gate": "kelly_sizing", "verdict": "block",
         "reason": "capped_zero all 12 candidates", "inputs": {"n": 12}},
    ])
    # idempotency: re-running the same backfill must not duplicate
    write_verdicts(c, "2026-06-11-live-f68231b0", "2026-06-11", [
        {"scope": "book", "gate": "bear_override", "verdict": "block", "reason": "dup", "inputs": {}}])
    # THE AUTOPSY — one query instead of three hours:
    rows = c.execute(
        "SELECT gate, verdict, reason, inputs_json FROM decision_ledger "
        "WHERE as_of='2026-06-11' AND scope='book' ORDER BY gate").fetchall()
    print("SELECT gate, verdict, reason FROM decision_ledger WHERE as_of='2026-06-11' AND scope='book';")
    for g, v, r, i in rows:
        print(f"  {g:20s} {v:6s} {r}  {i}")
    n = c.execute("SELECT COUNT(*) FROM decision_ledger").fetchone()[0]
    assert n == 4, n   # idempotent: dup insert ignored
    assert all(row[1] == "block" for row in rows)
    print(f"\n{n} rows; idempotency ✓; append-only EVENT table in WAL mode at {DB}")
    print("the 2026-06-11 cascade is now ONE query — wiring target: GateRegistry "
          "aggregation step writes here every run.")
