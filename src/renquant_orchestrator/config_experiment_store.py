"""Config experiment store for S6 lambda sweep results.

Provides the DDL and writer for config_experiments — the table the S6 lambda
sweep writes to and the readiness_monitor checks. Each row records one
pipeline-run-equivalent decision under a specific config variant (e.g. a
different cash_drag_lambda value), enabling A/B comparison of deployment-gap
metrics across configurations.

The table lives in runs.alpaca.db alongside pipeline_runs and candidate_scores.
It is append-only (INSERT OR IGNORE on the PK).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

CONFIG_EXPERIMENTS_DDL = """
CREATE TABLE IF NOT EXISTS config_experiments (
  experiment_id TEXT NOT NULL,
  run_date TEXT NOT NULL,
  config_name TEXT NOT NULL,
  config_json TEXT NOT NULL,
  baseline_run_id TEXT,
  deployed_frac REAL,
  n_names_selected INTEGER,
  turnover REAL,
  max_weight REAL,
  solver_status TEXT,
  cash_drag_lambda REAL,
  min_invested_pct REAL,
  turnover_max REAL,
  metric_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  PRIMARY KEY (experiment_id)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_config_exp_date
  ON config_experiments(run_date);
CREATE INDEX IF NOT EXISTS idx_config_exp_config
  ON config_experiments(config_name);
"""


def ensure_table(conn: sqlite3.Connection) -> None:
    """Create the config_experiments table if it doesn't exist."""
    conn.executescript(CONFIG_EXPERIMENTS_DDL)


def write_experiment(
    conn: sqlite3.Connection,
    experiment: Mapping[str, Any],
) -> bool:
    """Write one experiment row. Returns True if a new row was inserted."""
    before = conn.total_changes
    conn.execute(
        "INSERT OR IGNORE INTO config_experiments VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            experiment["experiment_id"],
            experiment["run_date"],
            experiment["config_name"],
            json.dumps(experiment.get("config", {}), sort_keys=True),
            experiment.get("baseline_run_id"),
            experiment.get("deployed_frac"),
            experiment.get("n_names_selected"),
            experiment.get("turnover"),
            experiment.get("max_weight"),
            experiment.get("solver_status"),
            experiment.get("cash_drag_lambda"),
            experiment.get("min_invested_pct"),
            experiment.get("turnover_max"),
            json.dumps(experiment.get("metrics", {}), sort_keys=True),
            experiment.get(
                "created_at",
                datetime.now(timezone.utc).isoformat(),
            ),
        ),
    )
    conn.commit()
    return conn.total_changes > before


def write_experiments(
    conn: sqlite3.Connection,
    experiments: Iterable[Mapping[str, Any]],
) -> int:
    """Write multiple experiment rows. Returns count of new rows inserted."""
    total = 0
    for exp in experiments:
        if write_experiment(conn, exp):
            total += 1
    return total


def read_experiments(
    conn: sqlite3.Connection,
    *,
    config_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Read experiment rows with optional filters."""
    where_parts = ["1=1"]
    params: list[str] = []
    if config_name:
        where_parts.append("config_name = ?")
        params.append(config_name)
    if start_date:
        where_parts.append("run_date >= ?")
        params.append(start_date)
    if end_date:
        where_parts.append("run_date <= ?")
        params.append(end_date)

    where = " AND ".join(where_parts)
    cur = conn.execute(
        f"SELECT * FROM config_experiments WHERE {where} ORDER BY run_date, config_name",
        params,
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
