"""Buy-halt exemption for the rq105 pairing collector (orch: G-F-class fix).

rq105 pairs ENTRY submissions; a session with zero live buy submissions
produces zero entry-pairs — that empty output is correct, not a fault. The
sentinel used to alarm "stale" on it (answering "did a row arrive today"
instead of "should one have"). These controls pin the fix AND its
fail-closed scope: the exemption is granted ONLY on a positive proof of
zero buys; buys-happened-but-stale and undeterminable both keep the alarm.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant105"))

from rq105_liveness_check import (  # noqa: E402
    _pairing_buyhalt_exempt,
    _live_buy_submissions_since,
)

STALE = "path last complete row date='2026-08-05' != today '2026-08-10' (stale)"


def test_exempt_only_on_proven_zero():
    ok, reason = _pairing_buyhalt_exempt(False, STALE, "2026-08-05", "2026-08-10", 0)
    assert ok is True and "EXPECTED" in reason and "P-WF-GATE" in reason


def test_buys_happened_but_stale_still_fails():
    # a REAL break: buys were submitted yet pairing didn't log them
    ok, reason = _pairing_buyhalt_exempt(False, STALE, "2026-08-05", "2026-08-10", 3)
    assert ok is False and reason == STALE


def test_undeterminable_count_keeps_alarm():
    # None = cannot prove zero -> fail-closed, exemption NOT granted
    ok, reason = _pairing_buyhalt_exempt(False, STALE, "2026-08-05", "2026-08-10", None)
    assert ok is False and reason == STALE


def _mkdb(tmp: Path, rows):
    (tmp / "data").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(tmp / "data" / "runs.alpaca.db")
    con.execute("CREATE TABLE trades (action TEXT, trade_date TEXT)")
    con.executemany("INSERT INTO trades VALUES (?,?)", rows)
    con.commit(); con.close()


def test_buy_count_reads_only_buy_pending_after_since(tmp_path):
    _mkdb(tmp_path, [
        ("buy_pending", "2026-08-04"),   # on/before since -> excluded
        ("sell_pending", "2026-08-06"),  # not a buy -> excluded
        ("buy_pending", "2026-08-07"),   # in window -> counted
        ("buy_pending", "2026-08-11"),   # after as_of -> excluded
    ])
    n = _live_buy_submissions_since(tmp_path, "2026-08-05", dt.date(2026, 8, 10))
    assert n == 1


def test_missing_db_is_none_fail_closed(tmp_path):
    assert _live_buy_submissions_since(tmp_path, "2026-08-05", dt.date(2026, 8, 10)) is None


def test_schema_drift_is_none_fail_closed(tmp_path):
    (tmp_path / "data").mkdir(parents=True)
    con = sqlite3.connect(tmp_path / "data" / "runs.alpaca.db")
    con.execute("CREATE TABLE trades (foo TEXT)")  # missing action/trade_date
    con.commit(); con.close()
    assert _live_buy_submissions_since(tmp_path, "2026-08-05", dt.date(2026, 8, 10)) is None
