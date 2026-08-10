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
    _pairing_buyhalt_reclassify,
    _live_buy_submissions_since,
)

STALE = "path last complete row date='2026-08-05' != today '2026-08-10' (stale)"


def test_buyhalt_downgrades_to_info_never_green():
    # (n_buys=0, n_any>0): a positive buy-halt shape downgrades the PAGE to
    # a non-paging INFO — never a healthy "ok" green (the ledger cannot
    # prove buy-write completeness)
    status, reason = _pairing_buyhalt_reclassify(False, STALE, "2026-08-05", "2026-08-10", (0, 6))
    assert status == "info_buy_halt"
    assert status != "ok"
    assert "P-WF-GATE" in reason and "cannot prove buy-write completeness" in reason


def test_stale_ledger_zero_rows_keeps_page():
    # (n_buys=0, n_any=0): no other activity -> cannot even prove the ledger
    # is live -> the PAGE stands
    status, reason = _pairing_buyhalt_reclassify(False, STALE, "2026-08-05", "2026-08-10", (0, 0))
    assert status == "stale_or_missing" and reason == STALE


def test_buys_happened_but_stale_keeps_page():
    status, reason = _pairing_buyhalt_reclassify(False, STALE, "2026-08-05", "2026-08-10", (3, 9))
    assert status == "stale_or_missing" and reason == STALE


def test_undeterminable_keeps_page():
    status, reason = _pairing_buyhalt_reclassify(False, STALE, "2026-08-05", "2026-08-10", None)
    assert status == "stale_or_missing" and reason == STALE


def test_healthy_row_stays_ok():
    status, reason = _pairing_buyhalt_reclassify(True, "", "2026-08-10", "2026-08-10", (0, 6))
    assert status == "ok"


def _mkdb(tmp: Path, rows):
    (tmp / "data").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(tmp / "data" / "runs.alpaca.db")
    con.execute("CREATE TABLE trades (action TEXT, trade_date TEXT)")
    con.executemany("INSERT INTO trades VALUES (?,?)", rows)
    con.commit(); con.close()


def test_buy_count_reads_only_buy_pending_after_since(tmp_path):
    _mkdb(tmp_path, [
        ("buy_pending", "2026-08-04"),   # on/before since -> excluded
        ("sell_pending", "2026-08-06"),  # non-buy in window -> n_any only
        ("buy_pending", "2026-08-07"),   # buy in window -> both
        ("buy_pending", "2026-08-11"),   # after as_of -> excluded
    ])
    n_buys, n_any = _live_buy_submissions_since(tmp_path, "2026-08-05", dt.date(2026, 8, 10))
    assert n_buys == 1 and n_any == 2  # buy_pending 08-07 + sell_pending 08-06


def test_missing_db_is_none_fail_closed(tmp_path):
    assert _live_buy_submissions_since(tmp_path, "2026-08-05", dt.date(2026, 8, 10)) is None


def test_schema_drift_is_none_fail_closed(tmp_path):
    (tmp_path / "data").mkdir(parents=True)
    con = sqlite3.connect(tmp_path / "data" / "runs.alpaca.db")
    con.execute("CREATE TABLE trades (foo TEXT)")  # missing action/trade_date
    con.commit(); con.close()
    assert _live_buy_submissions_since(tmp_path, "2026-08-05", dt.date(2026, 8, 10)) is None
