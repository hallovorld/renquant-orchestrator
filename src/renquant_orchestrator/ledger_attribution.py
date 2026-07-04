"""Decision-ledger attribution engine (107 skeleton, S5 fwd-outcome join).

Extends the S2 decision_ledger with forward-outcome tracking and per-gate
value-add analysis. The ledger records WHAT each gate decided; this module
records WHAT HAPPENED NEXT and computes WHETHER the gate decision was right.

The payoff: TC/IC/expectancy measurement becomes a SQL-grade operation instead
of one-off archaeology. The S5 AC: "fwd-outcome join >=95% for aged decisions."

Schema additions (append-only, same WAL/busy-timeout discipline as the ledger):
  - decision_outcomes: one row per (as_of, scope, ticker) with realized fwd returns
  - attribution_view: the join that answers "was blocking ticker X on date Y right?"

Usage:
    from renquant_orchestrator.ledger_attribution import (
        connect_attribution, write_outcomes, gate_value_report,
    )
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from .decision_ledger import DDL as LEDGER_DDL
from .decision_ledger import DEFAULT_DB

OUTCOMES_DDL = """
CREATE TABLE IF NOT EXISTS decision_outcomes (
  as_of DATE NOT NULL,
  scope TEXT NOT NULL,
  ticker TEXT NOT NULL,
  gate TEXT NOT NULL,
  verdict TEXT NOT NULL,
  fwd_5d_ret REAL,
  fwd_20d_ret REAL,
  fwd_60d_ret REAL,
  entry_price REAL,
  exit_price_5d REAL,
  exit_price_20d REAL,
  exit_price_60d REAL,
  recorded_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (as_of, scope, ticker, gate)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_outcomes_ticker ON decision_outcomes(ticker);
CREATE INDEX IF NOT EXISTS idx_outcomes_gate ON decision_outcomes(gate);
CREATE INDEX IF NOT EXISTS idx_outcomes_verdict ON decision_outcomes(verdict);
"""

GATE_VALUE_SQL = """
SELECT
  gate,
  verdict,
  COUNT(*) AS n,
  AVG(fwd_{horizon}d_ret) AS avg_fwd_ret,
  SUM(CASE WHEN fwd_{horizon}d_ret > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS hit_rate,
  MIN(fwd_{horizon}d_ret) AS worst,
  MAX(fwd_{horizon}d_ret) AS best
FROM decision_outcomes
WHERE 1=1 {where_clause}
GROUP BY gate, verdict
ORDER BY gate, verdict
"""

COVERAGE_SQL = """
SELECT
  l.as_of,
  COUNT(DISTINCT l.gate || '|' || l.scope) AS n_verdicts,
  COUNT(DISTINCT o.gate || '|' || o.scope || '|' || o.ticker) AS n_outcomes,
  CASE WHEN COUNT(DISTINCT l.gate || '|' || l.scope) > 0
    THEN COUNT(DISTINCT o.gate || '|' || o.scope || '|' || o.ticker) * 1.0
         / COUNT(DISTINCT l.gate || '|' || l.scope)
    ELSE NULL
  END AS coverage_ratio
FROM decision_ledger l
LEFT JOIN decision_outcomes o
  ON l.as_of = o.as_of AND l.scope = o.scope AND l.gate = o.gate
WHERE l.as_of BETWEEN ? AND ?
GROUP BY l.as_of
ORDER BY l.as_of
"""


def connect_attribution(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the ledger+attribution DB (creates both schemas if needed)."""
    if db_path is None:
        db_path = DEFAULT_DB
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(db_path), timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.executescript(LEDGER_DDL)
    c.executescript(OUTCOMES_DDL)
    return c


def write_outcomes(
    conn: sqlite3.Connection,
    outcomes: Iterable[Mapping[str, Any]],
) -> int:
    """Append realized outcomes for gate decisions. INSERT OR IGNORE for
    idempotency — re-recording an already-observed outcome is a no-op."""
    rows = []
    for o in outcomes:
        rows.append((
            o["as_of"],
            o["scope"],
            o["ticker"],
            o["gate"],
            o["verdict"],
            o.get("fwd_5d_ret"),
            o.get("fwd_20d_ret"),
            o.get("fwd_60d_ret"),
            o.get("entry_price"),
            o.get("exit_price_5d"),
            o.get("exit_price_20d"),
            o.get("exit_price_60d"),
            o["recorded_at"],
            json.dumps(dict(o.get("metadata", {})), sort_keys=True),
        ))
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO decision_outcomes VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return conn.total_changes - before


def gate_value_report(
    conn: sqlite3.Connection,
    *,
    horizon: int = 20,
    gate: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Per-gate, per-verdict value-add report at a given forward horizon.

    Returns rows with: gate, verdict, n, avg_fwd_ret, hit_rate, worst, best.
    This is the core attribution query: did blocking actually protect? Did
    allowing actually earn?
    """
    if horizon not in (5, 20, 60):
        raise ValueError(f"horizon must be 5, 20, or 60; got {horizon}")

    where_parts: list[str] = []
    params: list[str] = []
    if gate:
        where_parts.append("AND gate = ?")
        params.append(gate)
    if start_date:
        where_parts.append("AND as_of >= ?")
        params.append(start_date)
    if end_date:
        where_parts.append("AND as_of <= ?")
        params.append(end_date)

    where_clause = " ".join(where_parts)
    sql = GATE_VALUE_SQL.format(horizon=horizon, where_clause=where_clause)

    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def outcome_coverage(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Per-date coverage ratio: what fraction of ledger verdicts have
    corresponding outcome records? The S5 AC targets >=95% for aged decisions."""
    cur = conn.execute(COVERAGE_SQL, (start_date, end_date))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def gate_information_value(
    conn: sqlite3.Connection,
    gate: str,
    *,
    horizon: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Value of information for a single gate: the difference in average forward
    return between names the gate allowed vs blocked. Positive = gate is adding
    value (blocked names did worse than allowed names)."""
    report = gate_value_report(
        conn, horizon=horizon, gate=gate,
        start_date=start_date, end_date=end_date,
    )
    by_verdict = {r["verdict"]: r for r in report}
    allow = by_verdict.get("allow", {})
    block = by_verdict.get("block", {})

    allow_ret = allow.get("avg_fwd_ret")
    block_ret = block.get("avg_fwd_ret")

    voi = None
    if allow_ret is not None and block_ret is not None:
        voi = allow_ret - block_ret

    return {
        "gate": gate,
        "horizon": horizon,
        "allow_avg_ret": allow_ret,
        "allow_n": allow.get("n", 0),
        "allow_hit_rate": allow.get("hit_rate"),
        "block_avg_ret": block_ret,
        "block_n": block.get("n", 0),
        "block_hit_rate": block.get("hit_rate"),
        "value_of_information": voi,
        "start_date": start_date,
        "end_date": end_date,
    }
