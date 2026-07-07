"""SQLite result store for sweep results — crash-safe, per-variant INSERT."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS sweep_runs (
    sweep_id                      TEXT PRIMARY KEY,
    created_at                    TIMESTAMP NOT NULL,
    backend                       TEXT NOT NULL,
    volume_commit                 TEXT,
    image_id                      TEXT,
    subrepo_pins_json             TEXT,
    subrepo_pins_sha256           TEXT,
    strategy_config_fingerprint   TEXT,
    data_manifest_fingerprint     TEXT,
    artifact_manifest_fingerprint TEXT,
    backtest_start                TEXT NOT NULL,
    backtest_end                  TEXT NOT NULL,
    initial_cash                  REAL NOT NULL,
    grid_spec_json                TEXT NOT NULL,
    n_variants                    INTEGER NOT NULL,
    n_completed                   INTEGER DEFAULT 0,
    n_failed                      INTEGER DEFAULT 0,
    aa_sharpe_lift                REAL,
    aa_passed                     INTEGER,
    status                        TEXT DEFAULT 'running',
    total_seconds                 REAL,
    cost_usd                      REAL
);

CREATE TABLE IF NOT EXISTS variant_results (
    sweep_id            TEXT NOT NULL,
    variant_name        TEXT NOT NULL,
    role                TEXT NOT NULL,
    entry_cap           REAL,
    drift_buffer        REAL,
    topup_threshold     REAL,
    config_fingerprint  TEXT NOT NULL,
    worker_id           TEXT,
    elapsed_seconds     REAL,
    peak_memory_mb      REAL,
    tier3_ready         INTEGER,
    verdict_json        TEXT,
    error               TEXT,
    received_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (sweep_id, variant_name),
    FOREIGN KEY (sweep_id) REFERENCES sweep_runs(sweep_id)
);

CREATE TABLE IF NOT EXISTS seed_metrics (
    sweep_id        TEXT NOT NULL,
    variant_name    TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    apy             REAL,
    sharpe          REAL,
    sharpe_net_of_cost REAL,
    max_dd          REAL,
    calmar          REAL,
    turnover_ann    REAL,
    cost_bps        REAL,
    winner_cont_pct REAL,
    equity_path     TEXT,
    trade_log_path  TEXT,
    PRIMARY KEY (sweep_id, variant_name, seed),
    FOREIGN KEY (sweep_id, variant_name)
        REFERENCES variant_results(sweep_id, variant_name)
);

CREATE TABLE IF NOT EXISTS regime_metrics (
    sweep_id        TEXT NOT NULL,
    variant_name    TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    regime          TEXT NOT NULL,
    apy             REAL,
    sharpe          REAL,
    sharpe_net_of_cost REAL,
    max_dd          REAL,
    n_days          INTEGER,
    PRIMARY KEY (sweep_id, variant_name, seed, regime),
    FOREIGN KEY (sweep_id, variant_name, seed)
        REFERENCES seed_metrics(sweep_id, variant_name, seed)
);
"""


class ResultStore:
    """Crash-safe sweep result persistence backed by SQLite."""

    def __init__(self, sweep_id: str, base_dir: Path | str):
        self.sweep_id = sweep_id
        self.base = Path(base_dir) / sweep_id
        self.base.mkdir(parents=True, exist_ok=True)
        self._db_path = self.base / "results.db"
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def init_sweep(
        self,
        *,
        backend: str,
        backtest_start: str,
        backtest_end: str,
        initial_cash: float,
        grid_spec: Any,
        n_variants: int,
        volume_commit: str | None = None,
        image_id: str | None = None,
        subrepo_pins_json: str | None = None,
        subrepo_pins_sha256: str | None = None,
        strategy_config_fingerprint: str | None = None,
        data_manifest_fingerprint: str | None = None,
        artifact_manifest_fingerprint: str | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT OR IGNORE INTO sweep_runs
               (sweep_id, created_at, backend, volume_commit, image_id,
                subrepo_pins_json, subrepo_pins_sha256,
                strategy_config_fingerprint, data_manifest_fingerprint,
                artifact_manifest_fingerprint,
                backtest_start, backtest_end, initial_cash,
                grid_spec_json, n_variants)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                self.sweep_id,
                datetime.now(timezone.utc).isoformat(),
                backend,
                volume_commit,
                image_id,
                subrepo_pins_json,
                subrepo_pins_sha256,
                strategy_config_fingerprint,
                data_manifest_fingerprint,
                artifact_manifest_fingerprint,
                backtest_start,
                backtest_end,
                initial_cash,
                json.dumps(grid_spec, default=str),
                n_variants,
            ),
        )
        self._conn.commit()

    def insert_variant(
        self,
        variant_name: str,
        role: str,
        config_fingerprint: str,
        per_seed: list[dict[str, Any]],
        *,
        entry_cap: float | None = None,
        drift_buffer: float | None = None,
        topup_threshold: float | None = None,
        worker_id: str | None = None,
        elapsed_seconds: float | None = None,
        peak_memory_mb: float | None = None,
        error: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO variant_results
               (sweep_id, variant_name, role, entry_cap, drift_buffer,
                topup_threshold, config_fingerprint, worker_id,
                elapsed_seconds, peak_memory_mb, error, received_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                self.sweep_id,
                variant_name,
                role,
                entry_cap,
                drift_buffer,
                topup_threshold,
                config_fingerprint,
                worker_id,
                elapsed_seconds,
                peak_memory_mb,
                error,
                now,
            ),
        )
        for seed_row in per_seed:
            seed = seed_row["seed"]
            self._conn.execute(
                """INSERT OR REPLACE INTO seed_metrics
                   (sweep_id, variant_name, seed, apy, sharpe,
                    sharpe_net_of_cost, max_dd, calmar, turnover_ann,
                    cost_bps, winner_cont_pct)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.sweep_id,
                    variant_name,
                    seed,
                    seed_row.get("apy"),
                    seed_row.get("sharpe"),
                    seed_row.get("sharpe_net_of_cost"),
                    seed_row.get("max_dd"),
                    seed_row.get("calmar"),
                    seed_row.get("turnover", {}).get("turnover_annualized")
                    if isinstance(seed_row.get("turnover"), dict)
                    else seed_row.get("turnover_ann"),
                    seed_row.get("turnover", {}).get("modeled_cost_bps")
                    if isinstance(seed_row.get("turnover"), dict)
                    else seed_row.get("cost_bps"),
                    seed_row.get("winner_continuation", {}).get(
                        "winner_continuation_pct"
                    )
                    if isinstance(seed_row.get("winner_continuation"), dict)
                    else seed_row.get("winner_cont_pct"),
                ),
            )
            for regime, rm in (seed_row.get("per_regime") or {}).items():
                if rm is None:
                    continue
                self._conn.execute(
                    """INSERT OR REPLACE INTO regime_metrics
                       (sweep_id, variant_name, seed, regime, apy, sharpe,
                        sharpe_net_of_cost, max_dd, n_days)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        self.sweep_id,
                        variant_name,
                        seed,
                        regime,
                        rm.get("apy"),
                        rm.get("sharpe"),
                        rm.get("sharpe_net_of_cost"),
                        rm.get("max_dd"),
                        rm.get("n_days"),
                    ),
                )
        self._conn.commit()

    def insert_error(self, variant_name: str, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO variant_results
               (sweep_id, variant_name, role, config_fingerprint, error, received_at)
               VALUES (?,?,?,?,?,?)""",
            (self.sweep_id, variant_name, "candidate", "", error, now),
        )
        self._conn.execute(
            "UPDATE sweep_runs SET n_failed = n_failed + 1 WHERE sweep_id = ?",
            (self.sweep_id,),
        )
        self._conn.commit()

    def update_verdict(
        self, variant_name: str, verdict: dict[str, Any]
    ) -> None:
        self._conn.execute(
            """UPDATE variant_results
               SET tier3_ready = ?, verdict_json = ?
               WHERE sweep_id = ? AND variant_name = ?""",
            (
                1 if verdict.get("tier3_ready") else 0,
                json.dumps(verdict, default=str),
                self.sweep_id,
                variant_name,
            ),
        )
        self._conn.execute(
            "UPDATE sweep_runs SET n_completed = n_completed + 1 WHERE sweep_id = ?",
            (self.sweep_id,),
        )
        self._conn.commit()

    def completed_variants(self) -> set[str]:
        rows = self._conn.execute(
            "SELECT variant_name FROM variant_results WHERE sweep_id = ? AND error IS NULL",
            (self.sweep_id,),
        ).fetchall()
        return {r[0] for r in rows}

    def count_completed(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM variant_results WHERE sweep_id = ? AND error IS NULL",
            (self.sweep_id,),
        ).fetchone()
        return row[0] if row else 0

    def finalize(
        self,
        total_seconds: float,
        cost_usd: float = 0.0,
        aa_sharpe_lift: float | None = None,
        aa_passed: bool | None = None,
    ) -> None:
        n_ok = self.count_completed()
        n_err = self._conn.execute(
            "SELECT COUNT(*) FROM variant_results WHERE sweep_id = ? AND error IS NOT NULL",
            (self.sweep_id,),
        ).fetchone()[0]
        status = "completed" if n_err == 0 else "partial"
        self._conn.execute(
            """UPDATE sweep_runs
               SET status = ?, total_seconds = ?, cost_usd = ?,
                   n_completed = ?, n_failed = ?,
                   aa_sharpe_lift = ?, aa_passed = ?
               WHERE sweep_id = ?""",
            (
                status,
                total_seconds,
                cost_usd,
                n_ok,
                n_err,
                aa_sharpe_lift,
                1 if aa_passed else (0 if aa_passed is not None else None),
                self.sweep_id,
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
