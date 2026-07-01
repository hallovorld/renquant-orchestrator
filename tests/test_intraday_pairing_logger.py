"""Tests for ``intraday_pairing_logger`` — renquant105 Stage-1 OPERATIONS-ONLY
paired IS logger.

Fully hermetic and deterministic: pure-function cases for the pairing/shortfall
logic, an in-memory sqlite DB that mimics ``pipeline_runs`` / ``candidate_scores``
/ ``trades`` for the read-only loaders, a tmp JSONL tick source, and a tmp pilot
output file. No wall-clock is read; every timestamp is injected. Never touches
live state.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from renquant_orchestrator.intraday_pairing_logger import (
    AdmittedName,
    PriceRef,
    append_records,
    build_paired_record,
    collect,
    existing_pair_keys,
    implementation_shortfall,
    load_admitted,
    load_batch_fills,
    load_intraday_ticks,
    pair_key,
    pair_records,
    summarize,
)

# --- fixed, injected timestamps (no wall-clock) ----------------------------
DATE = "2026-06-30"
TICK_TIME = "2026-06-30T10:00:00-04:00"
FILL_TIME = "2026-07-01"


# ---------------------------------------------------------------------------
# Pure implementation-shortfall logic
# ---------------------------------------------------------------------------
def test_shortfall_buy_sign_and_magnitude():
    # buy above the reference mid => positive (paid up / worse)
    assert implementation_shortfall(101.0, 100.0, "buy") == pytest.approx(1.0)
    # buy below the reference mid => negative (got a better price)
    assert implementation_shortfall(99.5, 100.0, "buy") == pytest.approx(-0.5)


def test_shortfall_sell_sign_flips():
    # sell below the reference mid => positive (sold low / worse)
    assert implementation_shortfall(99.0, 100.0, "sell") == pytest.approx(1.0)
    # sell above the reference mid => negative (better)
    assert implementation_shortfall(100.5, 100.0, "sell") == pytest.approx(-0.5)


def test_shortfall_missing_input_is_none_not_imputed():
    assert implementation_shortfall(None, 100.0, "buy") is None
    assert implementation_shortfall(101.0, None, "buy") is None


# ---------------------------------------------------------------------------
# build_paired_record — pairing + censoring
# ---------------------------------------------------------------------------
def test_paired_record_complete():
    rec = build_paired_record(
        date=DATE,
        ticker="NVDA",
        side="buy",
        reference_mid=100.0,
        batch_entry_ref=PriceRef(102.0, FILL_TIME),  # next-open, paid up
        intraday_entry_ref=PriceRef(100.2, TICK_TIME),  # near the arrival mid
        signal_version="2026-06-30-live-abc",
    )
    assert rec["censored_reason"] is None
    assert rec["filled"] is True
    assert rec["admitted"] is True
    assert rec["intraday_entry_hypothetical"] is True
    assert rec["implementation_shortfall_batch"] == pytest.approx(2.0)
    assert rec["implementation_shortfall_intraday"] == pytest.approx(0.2)
    assert rec["batch_entry_ref"] == {"price": 102.0, "time": FILL_TIME}
    assert rec["intraday_entry_ref"] == {"price": 100.2, "time": TICK_TIME}
    # OBSERVE-ONLY: no verdict / comparison field is emitted.
    assert "verdict" not in rec and "pass" not in rec
    assert "non_inferiority" not in rec


def test_paired_record_no_batch_fill_is_censored():
    rec = build_paired_record(
        date=DATE,
        ticker="MU",
        side="buy",
        reference_mid=50.0,
        batch_entry_ref=None,  # admitted but never bought
        intraday_entry_ref=PriceRef(50.1, TICK_TIME),
        signal_version="sv1",
    )
    assert rec["censored_reason"] == "no_batch_fill"
    assert rec["filled"] is False
    assert rec["implementation_shortfall_batch"] is None  # not imputed
    assert rec["implementation_shortfall_intraday"] == pytest.approx(0.1)


def test_paired_record_no_intraday_tick_is_censored():
    rec = build_paired_record(
        date=DATE,
        ticker="NFLX",
        side="buy",
        reference_mid=None,  # no decision-time mid without a tick
        batch_entry_ref=PriceRef(72.0, FILL_TIME),
        intraday_entry_ref=None,
        signal_version="sv1",
    )
    assert rec["censored_reason"] == "no_intraday_tick"
    assert rec["filled"] is True
    # Without a reference neither shortfall is computable — recorded, not imputed.
    assert rec["implementation_shortfall_batch"] is None
    assert rec["implementation_shortfall_intraday"] is None


def test_paired_record_both_missing_combines_reasons():
    rec = build_paired_record(
        date=DATE,
        ticker="AAPL",
        side="buy",
        reference_mid=None,
        batch_entry_ref=None,
        intraday_entry_ref=None,
    )
    assert rec["censored_reason"] == "no_intraday_tick+no_batch_fill"
    assert rec["filled"] is False


# ---------------------------------------------------------------------------
# pair_records — the join
# ---------------------------------------------------------------------------
def test_pair_records_joins_and_censors():
    admitted = [
        AdmittedName(DATE, "NVDA", "buy", "sv1"),
        AdmittedName(DATE, "MU", "buy", "sv1"),  # no tick
        AdmittedName(DATE, "NFLX", "buy", "sv1"),  # no fill
    ]
    batch_fills = {
        ("sv1", "NVDA"): PriceRef(102.0, FILL_TIME),
        ("sv1", "MU"): PriceRef(1062.0, FILL_TIME),
    }
    intraday_ticks = {
        (DATE, "NVDA"): {"mid": 100.0, "entry_price": 100.3, "tick_time": TICK_TIME},
        (DATE, "NFLX"): {"mid": 72.0, "tick_time": TICK_TIME},  # entry defaults to mid
    }
    recs = pair_records(admitted, batch_fills, intraday_ticks)
    by_ticker = {r["ticker"]: r for r in recs}

    assert by_ticker["NVDA"]["censored_reason"] is None
    assert by_ticker["NVDA"]["implementation_shortfall_batch"] == pytest.approx(2.0)
    assert by_ticker["NVDA"]["implementation_shortfall_intraday"] == pytest.approx(0.3)

    assert by_ticker["MU"]["censored_reason"] == "no_intraday_tick"
    assert by_ticker["NFLX"]["censored_reason"] == "no_batch_fill"
    # entry_price defaulted to mid => intraday shortfall exactly 0
    assert by_ticker["NFLX"]["implementation_shortfall_intraday"] == pytest.approx(0.0)


def test_pair_records_falls_back_to_date_keyed_fill():
    admitted = [AdmittedName(DATE, "NVDA", "buy", "sv1")]
    # fill keyed by (date, ticker) rather than (signal_version, ticker)
    batch_fills = {(DATE, "NVDA"): PriceRef(101.0, FILL_TIME)}
    ticks = {(DATE, "NVDA"): {"mid": 100.0, "tick_time": TICK_TIME}}
    rec = pair_records(admitted, batch_fills, ticks)[0]
    assert rec["filled"] is True
    assert rec["implementation_shortfall_batch"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# summarize — counts only, no verdict
# ---------------------------------------------------------------------------
def test_summarize_counts():
    recs = pair_records(
        [
            AdmittedName(DATE, "NVDA", "buy", "sv1"),
            AdmittedName(DATE, "MU", "buy", "sv1"),
            AdmittedName(DATE, "NFLX", "buy", "sv1"),
        ],
        {("sv1", "NVDA"): PriceRef(102.0), ("sv1", "MU"): PriceRef(1062.0)},
        {(DATE, "NVDA"): {"mid": 100.0}},
    )
    s = summarize(recs)
    assert s["n_admitted_pairs"] == 3
    assert s["n_complete_pairs"] == 1  # only NVDA
    assert s["n_censored_pairs"] == 2
    assert s["n_with_batch_fill"] == 2
    assert s["n_with_intraday_tick"] == 1
    # MU: has a batch fill but no tick -> no_intraday_tick.
    # NFLX: neither tick nor fill -> combined reason.
    assert s["censored_by_reason"]["no_intraday_tick"] == 1
    assert s["censored_by_reason"]["no_intraday_tick+no_batch_fill"] == 1
    # no comparison / verdict key leaks into the summary
    assert not any("verdict" in k or "edge" in k for k in s)


# ---------------------------------------------------------------------------
# JSONL accumulation — idempotent append
# ---------------------------------------------------------------------------
def test_append_and_idempotent(tmp_path):
    out = tmp_path / "renquant105_pilot" / "paired_is.jsonl"
    recs = pair_records(
        [AdmittedName(DATE, "NVDA", "buy", "sv1"), AdmittedName(DATE, "MU", "buy", "sv1")],
        {("sv1", "NVDA"): PriceRef(102.0)},
        {(DATE, "NVDA"): {"mid": 100.0}, (DATE, "MU"): {"mid": 50.0}},
    )
    n1 = append_records(out, recs)
    assert n1 == 2
    assert out.exists()

    # Re-running the same session writes nothing new (idempotent on pair key).
    n2 = append_records(out, recs)
    assert n2 == 0
    assert len(out.read_text().strip().splitlines()) == 2

    # A new session (different signal_version) is appended.
    more = pair_records(
        [AdmittedName(DATE, "NVDA", "buy", "sv2")],
        {("sv2", "NVDA"): PriceRef(103.0)},
        {(DATE, "NVDA"): {"mid": 100.0}},
    )
    n3 = append_records(out, more)
    assert n3 == 1
    assert len(out.read_text().strip().splitlines()) == 3

    keys = existing_pair_keys(out)
    assert (DATE, "NVDA", "sv1") in keys
    assert (DATE, "NVDA", "sv2") in keys


def test_existing_pair_keys_missing_file(tmp_path):
    assert existing_pair_keys(tmp_path / "nope.jsonl") == set()


def test_pair_key_shape():
    rec = build_paired_record(
        date=DATE,
        ticker="NVDA",
        reference_mid=100.0,
        batch_entry_ref=PriceRef(101.0),
        intraday_entry_ref=PriceRef(100.0),
        signal_version="sv1",
    )
    assert pair_key(rec) == (DATE, "NVDA", "sv1")


# ---------------------------------------------------------------------------
# Read-only loaders over an in-memory DB + end-to-end collect
# ---------------------------------------------------------------------------
def _seed_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT
        );
        CREATE TABLE candidate_scores (
            run_id TEXT, ticker TEXT, role TEXT, selected INTEGER
        );
        CREATE TABLE trades (
            run_id TEXT, ticker TEXT, action TEXT, price REAL, trade_date DATE
        );
        """
    )
    conn.executemany(
        "INSERT INTO pipeline_runs VALUES (?,?,?)",
        [
            ("2026-06-30-live-aaa", DATE, "live"),
            ("2026-06-30-sim-zzz", DATE, "sim"),  # must be excluded
        ],
    )
    conn.executemany(
        "INSERT INTO candidate_scores VALUES (?,?,?,?)",
        [
            ("2026-06-30-live-aaa", "NVDA", "candidate", 1),
            ("2026-06-30-live-aaa", "MU", "candidate", 1),  # admitted, no fill
            ("2026-06-30-live-aaa", "AAPL", "candidate", 0),  # not selected
            ("2026-06-30-sim-zzz", "TSLA", "candidate", 1),  # sim, excluded
        ],
    )
    conn.executemany(
        "INSERT INTO trades VALUES (?,?,?,?,?)",
        [
            ("2026-06-30-live-aaa", "NVDA", "buy", 102.0, FILL_TIME),
            ("2026-06-30-live-aaa", "NVDA", "sell", 90.0, FILL_TIME),  # ignored
        ],
    )
    conn.commit()
    return conn


def test_load_admitted_filters_selected_and_run_type():
    conn = _seed_db()
    admitted = load_admitted(conn, DATE)
    tickers = sorted(n.ticker for n in admitted)
    assert tickers == ["MU", "NVDA"]  # AAPL not selected; TSLA is sim
    assert all(n.signal_version == "2026-06-30-live-aaa" for n in admitted)


def test_load_batch_fills_joins_on_run_id_and_buy_only():
    conn = _seed_db()
    admitted = load_admitted(conn, DATE)
    fills = load_batch_fills(conn, admitted)
    assert fills[("2026-06-30-live-aaa", "NVDA")].price == pytest.approx(102.0)
    assert fills[("2026-06-30-live-aaa", "NVDA")].time == FILL_TIME
    assert ("2026-06-30-live-aaa", "MU") not in fills  # no buy trade


def test_load_intraday_ticks_from_jsonl(tmp_path):
    src = tmp_path / "ticks.jsonl"
    src.write_text(
        json.dumps({"date": DATE, "ticker": "NVDA", "mid": 100.0, "tick_time": TICK_TIME})
        + "\n"
        + json.dumps({"date": "2026-06-29", "ticker": "NVDA", "mid": 1.0})  # other day
        + "\n"
        + "not-json\n"  # malformed line skipped
    )
    ticks = load_intraday_ticks(src, DATE)
    assert set(ticks) == {(DATE, "NVDA")}
    assert ticks[(DATE, "NVDA")]["mid"] == 100.0


def test_load_intraday_ticks_missing_file_is_empty(tmp_path):
    assert load_intraday_ticks(tmp_path / "absent.jsonl", DATE) == {}


def test_collect_end_to_end(tmp_path, monkeypatch):
    # DB on disk so the read-only mode=ro connect() URI can open it.
    db = tmp_path / "runs.db"
    seeded = _seed_db()
    disk = sqlite3.connect(db)
    seeded.backup(disk)
    disk.close()
    seeded.close()

    ticks = tmp_path / "ticks.jsonl"
    ticks.write_text(
        json.dumps(
            {"date": DATE, "ticker": "NVDA", "mid": 100.0, "entry_price": 100.5,
             "tick_time": TICK_TIME}
        )
        + "\n"
    )

    recs = collect(date=DATE, runs_db=db, tick_source=ticks)
    by_ticker = {r["ticker"]: r for r in recs}
    assert set(by_ticker) == {"NVDA", "MU"}

    nvda = by_ticker["NVDA"]
    assert nvda["censored_reason"] is None
    assert nvda["implementation_shortfall_batch"] == pytest.approx(2.0)
    assert nvda["implementation_shortfall_intraday"] == pytest.approx(0.5)

    # MU: admitted, has a tick? no -> censored no_intraday_tick (and no fill too)
    assert by_ticker["MU"]["filled"] is False
    assert "no_intraday_tick" in by_ticker["MU"]["censored_reason"]

    s = summarize(recs)
    assert s["n_admitted_pairs"] == 2
    assert s["n_complete_pairs"] == 1
