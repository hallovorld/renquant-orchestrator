"""L3 dataset builder: pairing, provenance, and refusal contracts. Tmp only."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from renquant_orchestrator import l3_dataset_builder as l3


def _db(path: Path, rows: list[tuple]) -> Path:
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE trades (run_id TEXT, ticker TEXT, action TEXT, trade_date TEXT,"
                    " broker_order_id TEXT, pnl_pct REAL, hold_days REAL,"
                    " exit_reason TEXT, regime TEXT, confidence REAL,"
                    " panel_score REAL, mu REAL, sigma REAL, expected_return REAL,"
                    " sector TEXT, active_scorer TEXT, rank_score REAL,"
                    " kelly_target_pct REAL)")
        for r in rows:
            con.execute("INSERT INTO trades (ticker,action,trade_date,broker_order_id,"
                        "pnl_pct,regime,panel_score,run_id) VALUES (?,?,?,?,?,?,?,"
                        "COALESCE(?3,'2099-01-01')||'-sim-x')", r)
    return path


def test_pairing_provenance_and_counts(tmp_path):
    db = _db(tmp_path / "runs.db", [
        ("AAPL", "buy",  "2026-01-01", "ord-1", None, "BULL_CALM", 2.0),   # live
        ("AAPL", "sell", "2026-02-01", None,    0.05, None, None),          # win
        ("MSFT", "buy",  "2026-01-05", None,    None, "BEAR", 1.0),         # sim
        ("MSFT", "sell", "2026-01-20", None,   -0.02, None, None),          # loss
        ("NVDA", "buy",  "2026-03-01", None,    None, None, None),          # unclosed
    ])
    rows, manifest = l3.build_rows(db)
    assert manifest["n_rows"] == 2 and manifest["n_unclosed_buys_excluded"] == 1
    assert manifest["provenance_counts"] == {"live": 0, "sim": 2}  # live needs BOTH legs
    by = {r["ticker"]: r for r in rows}
    assert by["AAPL"]["provenance"] == "sim" and by["AAPL"]["entry_live"] == 1 and by["AAPL"]["win"] == 1
    assert by["MSFT"]["provenance"] == "sim" and by["MSFT"]["win"] == 0
    assert by["AAPL"]["regime"] == "BULL_CALM" and by["AAPL"]["panel_score"] == 2.0


def test_null_trade_date_falls_back_to_run_id_prefix(tmp_path):
    """THE production path: 12,391/12,493 real rows have NULL trade_date and
    date only via the run_id prefix. A NULL-date buy/sell pair must still
    pair, dated from run_id."""
    db = tmp_path / "runs.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE trades (run_id TEXT, ticker TEXT, action TEXT,"
                    " trade_date TEXT, broker_order_id TEXT, pnl_pct REAL,"
                    " hold_days REAL, exit_reason TEXT, regime TEXT,"
                    " confidence REAL, panel_score REAL, mu REAL, sigma REAL,"
                    " expected_return REAL, sector TEXT, active_scorer TEXT,"
                    " rank_score REAL, kelly_target_pct REAL)")
        con.execute("INSERT INTO trades (run_id,ticker,action) VALUES"
                    " ('2026-01-01-sim-aa','AAPL','buy')")
        con.execute("INSERT INTO trades (run_id,ticker,action,pnl_pct) VALUES"
                    " ('2026-02-01-sim-bb','AAPL','sell',0.03)")
    rows, manifest = l3.build_rows(db)
    assert manifest["n_rows"] == 1
    assert rows[0]["entry_date"] == "2026-01-01"
    assert rows[0]["exit_date"] == "2026-02-01"
    assert rows[0]["win"] == 1 and rows[0]["provenance"] == "sim"


def test_sell_before_buy_never_pairs_backwards(tmp_path):
    db = _db(tmp_path / "runs.db", [
        ("AAPL", "sell", "2025-12-01", None, 0.10, None, None),   # earlier sell
        ("AAPL", "buy",  "2026-01-01", None, None, None, None),
        ("AAPL", "sell", "2026-02-01", None, -0.01, None, None),
    ])
    rows, manifest = l3.build_rows(db)
    assert manifest["n_rows"] == 1
    assert rows[0]["exit_date"] == "2026-02-01" and rows[0]["win"] == 0


def test_concurrent_lots_are_flagged_ambiguous_both_sides(tmp_path):
    """Two overlapping AAPL lots: FIFO assigns deterministically, but WHICH
    exit belongs to WHICH entry is unobservable -- BOTH rows flagged."""
    db = _db(tmp_path / "runs.db", [
        ("AAPL", "buy",  "2026-01-01", None, None, None, 1.0),
        ("AAPL", "buy",  "2026-01-05", None, None, None, 2.0),   # overlaps lot 1
        ("AAPL", "sell", "2026-01-20", None, 0.05, None, None),
        ("AAPL", "sell", "2026-02-10", None, -0.01, None, None),
        ("MSFT", "buy",  "2026-01-01", None, None, None, 3.0),   # clean lot
        ("MSFT", "sell", "2026-01-15", None, 0.02, None, None),
    ])
    rows, manifest = l3.build_rows(db)
    assert manifest["n_rows"] == 3 and manifest["n_pairing_ambiguous"] == 2
    aapl = [r for r in rows if r["ticker"] == "AAPL"]
    assert all(r["pairing_ambiguous"] == 1 for r in aapl)
    msft = [r for r in rows if r["ticker"] == "MSFT"]
    assert msft[0]["pairing_ambiguous"] == 0
    # deterministic FIFO: first buy got the first sell
    first = min(aapl, key=lambda r: r["entry_date"])
    assert first["exit_date"] == "2026-01-20" and first["win"] == 1


def test_open_buy_overlapping_a_paired_lot_flags_it(tmp_path):
    db = _db(tmp_path / "runs.db", [
        ("AAPL", "buy",  "2026-01-01", None, None, None, 1.0),
        ("AAPL", "sell", "2026-02-01", None, 0.05, None, None),
        ("AAPL", "buy",  "2026-01-15", None, None, None, 2.0),  # stays open, overlaps
    ])
    rows, manifest = l3.build_rows(db)
    assert manifest["n_rows"] == 1 and manifest["n_unclosed_buys_excluded"] == 1
    assert rows[0]["pairing_ambiguous"] == 1


def test_cli_writes_csv_and_manifest_or_refuses_empty(tmp_path, capsys):
    db = _db(tmp_path / "runs.db", [
        ("AAPL", "buy", "2026-01-01", None, None, None, None),   # unclosed only
    ])
    out = tmp_path / "ds" / "meta.csv"
    assert l3.main(["--db", str(db), "--out", str(out)]) == 1
    assert "zero paired rows" in capsys.readouterr().out
    db2 = _db(tmp_path / "runs2.db", [
        ("AAPL", "buy",  "2026-01-01", None, None, None, None),
        ("AAPL", "sell", "2026-02-01", None, 0.05, None, None),
    ])
    assert l3.main(["--db", str(db2), "--out", str(out)]) == 0
    assert out.exists() and out.with_suffix(".manifest.json").exists()
    m = json.loads(out.with_suffix(".manifest.json").read_text())
    assert m["schema"] == l3.SCHEMA and m["n_rows"] == 1
