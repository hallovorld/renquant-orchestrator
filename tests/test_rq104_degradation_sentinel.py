"""Tests for ops/renquant104/rq104_degradation_sentinel.py (GOAL-5 AC1).

Each degraded state is injected via fixtures and must alarm; each healthy
state must stay silent. Session-day gating is mocked so holidays/weekends
never depend on the real calendar in tests.
"""
from __future__ import annotations

import datetime as dt
import json
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


def _make_db(tmp_path, rows, funnel=None):
    """rows: list of (run_date, n_candidates, n_buys, buy_blocked, created_at).
    funnel: optional list of (run_id, ticker, role, rank_score, blocked_by)
    candidate_scores rows; the table is only created when given, so the
    default fixture also proves the sentinel degrades on legacy DBs."""
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
    if funnel is not None:
        conn.execute(
            "CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT,"
            " role TEXT, rank_score REAL, blocked_by TEXT, selected INTEGER)"
        )
        for run_id, ticker, role, rank_score, blocked_by in funnel:
            conn.execute(
                "INSERT INTO candidate_scores VALUES (?,?,?,?,?,0)",
                (run_id, ticker, role, rank_score, blocked_by),
            )
    conn.commit()
    conn.close()
    return str(db)


def _run(tmp_path, db_rows, *, daily_log: str | None = None, launchctl: str = "",
         funnel=None, strategy_config: dict | None = None):
    """Run main() with all environment seams patched; return (rc, alerts)."""
    db = _make_db(tmp_path, db_rows, funnel=funnel)
    log_dir = tmp_path / "daily_104"
    log_dir.mkdir(exist_ok=True)
    if daily_log is not None:
        (log_dir / f"{AS_OF}.log").write_text(daily_log)
    # isolate from the real pinned strategy config: default is an ABSENT
    # file (guard deconfigured -> built-in N0), tests opt in via
    # strategy_config (see TestSmallNAllVeto)
    cfg_path = tmp_path / "strategy_config.json"
    if strategy_config is not None:
        cfg_path.write_text(json.dumps(strategy_config))
    alerts: list[tuple[str, str]] = []

    with (
        patch.object(sentinel, "is_session_day", return_value=True),
        patch.object(sentinel, "DAILY_LOG_DIR", str(log_dir)),
        # isolate from the real reviewed ack ledger: tests control acks via
        # an explicit tmp file (see TestAckLedger)
        patch.object(sentinel, "ACK_LEDGER", str(tmp_path / "acks.json")),
        patch.object(sentinel, "PINNED_STRATEGY_CONFIG", str(cfg_path)),
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


class TestAckLedger:
    def test_acked_job_moves_to_info(self, tmp_path):
        import json
        (tmp_path / "acks.json").write_text(json.dumps({
            "com.renquant.weekly-wf-promote": {
                "acked_at": "2026-07-17", "reason": "known chronic",
                "clears_when": "gate pass"}}))
        text = "-\t1\tcom.renquant.weekly-wf-promote\n"
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, launchctl=text)
        assert rc == 0
        assert not alerts

    def test_unacked_job_still_alarms(self, tmp_path):
        import json
        (tmp_path / "acks.json").write_text(json.dumps({
            "com.renquant.other-job": {"acked_at": "x", "reason": "y",
                                       "clears_when": "z"}}))
        text = "-\t1\tcom.renquant.weekly-wf-promote\n"
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, launchctl=text)
        assert rc == 1
        assert any("weekly-wf-promote" in b for _, b in alerts)


def _all_veto_funnel(n, run_id="r1"):
    """n candidate rows on run_id, every one rank-floor vetoed at a finite
    score (the 2026-07-16/17 shape: floor > max score by construction)."""
    return [
        (run_id, f"T{i:02d}", "candidate", 0.50 + 0.01 * i,
         "veto:rank_score_below_floor")
        for i in range(n)
    ]


GUARD_VALID_CONFIG = {
    "ranking": {"panel_scoring": {"buy_floor_min_n": 12,
                                  "buy_floor_absolute_smalln": 0.50}}
}


class TestSmallNAllVeto:
    """RFC pipeline#204 §2.3 / AC-d: the small-n all-veto funnel freeze rule."""

    def test_all_vetoed_small_n_alarms(self, tmp_path):
        # AC-d (a): synthetic all-vetoed n=5 day -> LOUD
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, funnel=_all_veto_funnel(5))
        assert rc == 1
        body = alerts[0][1]
        assert "small-n all-veto funnel freeze" in body
        assert "n=5" in body
        assert "N0_sentinel=12" in body
        assert "5/5" in body
        assert "pipeline#204" in body

    def test_fires_with_guard_configured_valid(self, tmp_path):
        # AC-d (b): guard VALID (min_n=12) -> still fires, n=5 < 12
        rc, alerts = _run(
            tmp_path, HEALTHY_ROWS, funnel=_all_veto_funnel(5),
            strategy_config=GUARD_VALID_CONFIG,
        )
        assert rc == 1
        assert any("small-n all-veto funnel freeze" in b for _, b in alerts)

    def test_normal_n_partial_veto_quiet(self, tmp_path):
        # AC-d (c): 85 scored / 67 vetoed is a normal functioning funnel
        funnel = _all_veto_funnel(67) + [
            ("r1", f"K{i:02d}", "candidate", 0.60, None) for i in range(18)
        ]
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, funnel=funnel)
        assert rc == 0
        assert not alerts

    def test_deconfigured_guard_fires_at_builtin_12(self, tmp_path):
        # AC-d (d): guard deconfigured (key absent) -> built-in N0=12 fires
        rc, alerts = _run(
            tmp_path, HEALTHY_ROWS, funnel=_all_veto_funnel(5),
            strategy_config={"ranking": {"panel_scoring": {}}},
        )
        assert rc == 1
        assert any("N0_sentinel=12" in b for _, b in alerts)

    def test_invalid_guard_value_fires_at_builtin_12(self, tmp_path):
        # out-of-bounds min_n (typo 100) is INVALID per §2.2 -> built-in 12
        rc, alerts = _run(
            tmp_path, HEALTHY_ROWS, funnel=_all_veto_funnel(5),
            strategy_config={"ranking": {"panel_scoring": {"buy_floor_min_n": 100}}},
        )
        assert rc == 1
        assert any("N0_sentinel=12" in b for _, b in alerts)

    def test_all_vetoed_n13_quiet(self, tmp_path):
        # AC-d (e): all-vetoed at n=13 >= N0 is the floor doing its job
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, funnel=_all_veto_funnel(13))
        assert rc == 0
        assert not alerts

    def test_latest_scan_wins_over_holding_only_runs(self, tmp_path):
        # live shape: intraday runs write holding-only rows; the funnel rule
        # must read the newest run that actually carries candidate rows
        funnel = _all_veto_funnel(5, run_id="r0") + [
            ("r1", f"H{i}", "holding", 0.55, None) for i in range(4)
        ]
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, funnel=funnel)
        assert rc == 1
        assert any("small-n all-veto funnel freeze" in b for _, b in alerts)

    def test_missing_candidate_table_quiet(self, tmp_path):
        # legacy/fixture DBs without candidate_scores: degrade, never abort
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, funnel=None)
        assert rc == 0

    def test_null_scores_excluded_from_finite_n(self, tmp_path):
        # 13 vetoed rows but 2 carry no finite score -> finite n=11 < 12
        funnel = _all_veto_funnel(11) + [
            ("r1", "N1", "candidate", None, "veto:rank_score_below_floor"),
            ("r1", "N2", "candidate", None, "veto:rank_score_below_floor"),
        ]
        rc, alerts = _run(tmp_path, HEALTHY_ROWS, funnel=funnel)
        assert rc == 1
        assert any("n=11" in b for _, b in alerts)


class TestN0SentinelResolution:
    def _cfg(self, tmp_path, payload) -> str:
        p = tmp_path / "strategy_config.json"
        p.write_text(payload if isinstance(payload, str) else json.dumps(payload))
        return str(p)

    def test_valid_larger_than_builtin_wins(self, tmp_path):
        cfg = self._cfg(tmp_path, {"ranking": {"panel_scoring": {"buy_floor_min_n": 15}}})
        assert sentinel.n0_sentinel(cfg) == 15

    def test_valid_smaller_than_builtin_floors_at_12(self, tmp_path):
        cfg = self._cfg(tmp_path, {"ranking": {"panel_scoring": {"buy_floor_min_n": 5}}})
        assert sentinel.n0_sentinel(cfg) == 12

    def test_invalid_values_fall_back_to_builtin(self, tmp_path):
        for bad in (100, 1, 0, -3, "12", 12.0, True, None):
            cfg = self._cfg(
                tmp_path, {"ranking": {"panel_scoring": {"buy_floor_min_n": bad}}})
            assert sentinel.n0_sentinel(cfg) == 12, bad

    def test_missing_file_falls_back_to_builtin(self, tmp_path):
        assert sentinel.n0_sentinel(str(tmp_path / "nope.json")) == 12

    def test_malformed_json_falls_back_to_builtin(self, tmp_path):
        assert sentinel.n0_sentinel(self._cfg(tmp_path, "{not json")) == 12
