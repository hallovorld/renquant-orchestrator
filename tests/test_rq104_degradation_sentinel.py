"""Tests for ops/renquant104/rq104_degradation_sentinel.py (GOAL-5 AC1).

Each degraded state is injected via fixtures and must alarm; each healthy
state must stay silent. Session-day gating is mocked so holidays/weekends
never depend on the real calendar in tests.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant104"))

import rq104_degradation_sentinel as sentinel  # noqa: E402

AS_OF = "2026-07-16"
D0 = dt.date(2026, 7, 16)
D1 = dt.date(2026, 7, 15)


def _make_db(tmp_path, rows):
    """rows: list of (run_date, n_candidates, n_buys, buy_blocked, created_at)."""
    db = tmp_path / "runs.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE pipeline_runs (run_id TEXT, run_date DATE, run_type TEXT,"
        " n_candidates INTEGER, n_buys INTEGER, buy_blocked INTEGER,"
        " created_at TIMESTAMP)"
    )
    for i, (run_date, n_cand, n_buys, blocked, created) in enumerate(rows):
        conn.execute(
            "INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?,?)",
            (f"r{i}", run_date, "live", n_cand, n_buys, blocked, created),
        )
    conn.commit()
    conn.close()
    return str(db)


def _run(tmp_path, db_rows, *, daily_log: str | None = None, launchctl: str = ""):
    """Run main() with all environment seams patched; return (rc, alerts)."""
    db = _make_db(tmp_path, db_rows)
    log_dir = tmp_path / "daily_104"
    log_dir.mkdir(exist_ok=True)
    if daily_log is not None:
        (log_dir / f"{AS_OF}.log").write_text(daily_log)
    alerts: list[tuple[str, str]] = []

    with (
        patch.object(sentinel, "is_session_day", return_value=True),
        patch.object(sentinel, "DAILY_LOG_DIR", str(log_dir)),
        patch.object(sentinel, "alert", lambda t, b, **kw: alerts.append((t, b))),
        patch.object(
            sentinel.subprocess, "run",
            lambda *a, **kw: type("R", (), {"stdout": launchctl})(),
        ),
    ):
        rc = sentinel.main(["--as-of", AS_OF, "--db", db])
    return rc, alerts


HEALTHY_ROWS = [
    (D1.isoformat(), 7, 2, 0, f"{D1} 21:00:00"),
    (D0.isoformat(), 5, 3, 0, f"{D0} 21:00:00"),
]

ZERO_ROWS = [
    (D1.isoformat(), 0, 0, 0, f"{D1} 21:00:00"),
    (D0.isoformat(), 0, 0, 0, f"{D0} 21:00:00"),
]


class TestZeroCandidateStreak:
    def test_two_zero_days_alarm(self, tmp_path):
        rc, alerts = _run(tmp_path, ZERO_ROWS)
        assert rc == 1
        assert "zero-candidate streak" in alerts[0][1]

    def test_healthy_days_silent(self, tmp_path):
        rc, alerts = _run(tmp_path, HEALTHY_ROWS)
        assert rc == 0
        assert not alerts

    def test_single_zero_day_silent(self, tmp_path):
        rows = [
            (D1.isoformat(), 7, 2, 0, f"{D1} 21:00:00"),
            (D0.isoformat(), 0, 0, 0, f"{D0} 21:00:00"),
        ]
        rc, alerts = _run(tmp_path, rows)
        assert rc == 0

    def test_zero_candidates_but_buys_silent(self, tmp_path):
        # top-up buys with no scan candidates is a functioning book
        rows = [
            (D1.isoformat(), 0, 3, 0, f"{D1} 21:00:00"),
            (D0.isoformat(), 0, 1, 0, f"{D0} 21:00:00"),
        ]
        rc, alerts = _run(tmp_path, rows)
        assert rc == 0

    def test_day_with_no_rows_is_not_a_degradation(self, tmp_path):
        # missing rows entirely = liveness checker's domain, not sentinel's
        rows = [(D0.isoformat(), 0, 0, 0, f"{D0} 21:00:00")]
        rc, alerts = _run(tmp_path, rows)
        assert rc == 0


class TestBuyBlockedStreak:
    def test_two_blocked_days_alarm(self, tmp_path):
        rows = [
            (D1.isoformat(), 5, 0, 1, f"{D1} 21:00:00"),
            (D0.isoformat(), 5, 0, 1, f"{D0} 21:00:00"),
        ]
        rc, alerts = _run(tmp_path, rows)
        assert rc == 1
        assert "buy-path blocked streak" in alerts[0][1]

    def test_log_pattern_counts_as_blocked(self, tmp_path):
        rows = [
            (D1.isoformat(), 5, 0, 1, f"{D1} 21:00:00"),
            (D0.isoformat(), 5, 0, 0, f"{D0} 21:00:00"),
        ]
        # D0 not flagged in the DB but the log carries the decision line
        rc, alerts = _run(
            tmp_path, rows,
            daily_log="ntfy sent: RENQUANT-104 [full] BUY-BLOCKED | ...\n",
        )
        assert rc == 1
        assert any("buy-path blocked streak" in b for _, b in alerts)

    def test_last_run_unblocked_wins_the_day(self, tmp_path):
        # earlier blocked run superseded by a later clean full run
        rows = [
            (D1.isoformat(), 5, 2, 0, f"{D1} 21:00:00"),
            (D0.isoformat(), 0, 0, 1, f"{D0} 14:00:00"),
            (D0.isoformat(), 5, 3, 0, f"{D0} 21:00:00"),
        ]
        rc, alerts = _run(tmp_path, rows)
        assert rc == 0


class TestTracebackInLog:
    def test_traceback_alarms_even_with_healthy_rows(self, tmp_path):
        rc, alerts = _run(
            tmp_path, HEALTHY_ROWS,
            daily_log="ok\nTraceback (most recent call last):\n  ...\n",
        )
        assert rc == 1
        assert "Traceback" in alerts[0][1]

    def test_contract_fail_alarms(self, tmp_path):
        rc, alerts = _run(
            tmp_path, HEALTHY_ROWS,
            daily_log="LoadGlobalCalibrationTask contract fail: fingerprint mismatch\n",
        )
        assert rc == 1

    def test_clean_log_silent(self, tmp_path):
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, daily_log="all good\n")
        assert rc == 0

    def test_missing_log_silent(self, tmp_path):
        # log presence is the liveness checker's job
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, daily_log=None)
        assert rc == 0


class TestLaunchdExits:
    def test_nonzero_exit_alarms(self, tmp_path):
        text = "123\t0\tcom.renquant.daily104\n-\t1\tcom.renquant.weekly-wf-promote\n"
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, launchctl=text)
        assert rc == 1
        assert "weekly-wf-promote" in alerts[0][1]

    def test_zero_and_dash_silent(self, tmp_path):
        text = "-\t0\tcom.renquant.daily104\n-\t-\tcom.renquant.backup\n"
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, launchctl=text)
        assert rc == 0

    def test_non_renquant_jobs_ignored(self, tmp_path):
        text = "-\t78\tcom.apple.something\n"
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, launchctl=text)
        assert rc == 0

    def test_parser_units(self):
        text = "1\t0\tcom.renquant.a\n-\t9\tcom.renquant.b\n-\t-\tcom.renquant.c\njunk line\n"
        fails = sentinel.parse_launchctl_failures(text)
        assert fails == ["com.renquant.b (last exit 9)"]


class TestGating:
    def test_non_session_day_skips(self, tmp_path):
        db = _make_db(tmp_path, ZERO_ROWS)
        with patch.object(sentinel, "is_session_day", return_value=False):
            rc = sentinel.main(["--as-of", AS_OF, "--db", db])
        assert rc == 0

    def test_unreadable_db_alarms(self, tmp_path):
        alerts: list = []
        with (
            patch.object(sentinel, "is_session_day", return_value=True),
            patch.object(sentinel, "alert", lambda t, b, **kw: alerts.append(b)),
            patch.object(sentinel, "DAILY_LOG_DIR", str(tmp_path)),
            patch.object(
                sentinel.subprocess, "run",
                lambda *a, **kw: type("R", (), {"stdout": ""})(),
            ),
            patch.object(sentinel, "_open_db_readonly", lambda p: None),
        ):
            rc = sentinel.main(["--as-of", AS_OF, "--db", str(tmp_path / "nope.db")])
        assert rc == 1
        assert any("unreadable" in b for b in alerts)

    def test_last_session_days_walks_calendar(self):
        with patch.object(
            sentinel, "is_session_day",
            side_effect=lambda d: d.weekday() < 5,
        ):
            days = sentinel.last_session_days(dt.date(2026, 7, 13), 2)  # Monday
        assert days == [dt.date(2026, 7, 13), dt.date(2026, 7, 10)]  # Mon, Fri


class TestTopUpAwareness:
    def test_day_with_topup_buys_not_flagged(self, tmp_path):
        """2026-07-17 first-firing false alarm: a day whose pipeline_runs rows
        show 0 candidates / 0 buys but whose trades table records emitted
        top-up buy orders is buy-active, not silently fail-closed."""
        import sqlite3
        from rq104_degradation_sentinel import day_run_state
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE pipeline_runs (run_id TEXT, run_type TEXT, run_date TEXT, n_candidates INT, n_buys INT, buy_blocked INT, created_at TEXT)")
        db.execute("INSERT INTO pipeline_runs VALUES ('r1','live','2026-07-16',0,0,0,'2026-07-16 21:00:00')")
        db.execute("CREATE TABLE trades (run_id TEXT, action TEXT)")
        db.execute("INSERT INTO trades VALUES ('r1','buy_pending')")
        db.execute("INSERT INTO trades VALUES ('r1','buy_pending')")
        import datetime as dt
        state = day_run_state(db, dt.date(2026, 7, 16))
        assert state["max_buys"] == 2  # trades ground truth wins
