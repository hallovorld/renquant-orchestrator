"""Tests for ``intraday_pairing_logger`` — renquant105 Stage-1 OPERATIONS-ONLY
paired RAW-OBSERVATION logger.

Fully hermetic and deterministic: pure-function cases for the timing-vs-execution
decomposition and the FROZEN first-eligible-tick selection, an in-memory sqlite DB
that mimics ``pipeline_runs`` / ``candidate_scores`` / ``trades`` for the read-only
loaders, tmp JSONL tick / batch-arrival sources, and a tmp pilot output file. No
wall-clock is read; every timestamp is injected. Never touches live state.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from renquant_orchestrator.intraday_pairing_logger import (
    FILL_MODEL,
    FROZEN_PREREG,
    AdmittedName,
    ArmObservation,
    PriceRef,
    QuoteRef,
    append_records,
    build_paired_record,
    collect,
    decompose,
    execution_shortfall,
    existing_pair_keys,
    load_admitted,
    load_batch_arrivals,
    load_batch_fills,
    load_intraday_ticks,
    pair_key,
    pair_records,
    select_first_eligible_tick,
    summarize,
    timing_component,
)

# --- fixed, injected timestamps (no wall-clock) ----------------------------
DATE = "2026-06-30"
OPEN_REF_TS = "2026-06-30T09:30:00-04:00"  # batch arm arrival (session-T open)
ELIGIBLE_TS = "2026-06-30T09:35:00-04:00"  # intraday conviction / open+5min
TICK_TS = "2026-06-30T09:36:00-04:00"  # first eligible intraday tick
FILL_TIME = "2026-07-01"


def _batch_arm(fill=102.0, arrival_mid=101.0):
    """Batch arm: a real fill plus its own arrival (open) reference quote."""
    return ArmObservation(
        arm="batch",
        eligible_ts=OPEN_REF_TS,
        arrival_quote=QuoteRef(mid=arrival_mid, source_ts=OPEN_REF_TS,
                               source="opening_auction_print")
        if arrival_mid is not None
        else None,
        fill=PriceRef(fill, FILL_TIME) if fill is not None else None,
    )


def _intraday_arm(arrival_mid=100.0):
    """Intraday arm: an arrival quote at the first eligible tick, NO real fill."""
    return ArmObservation(
        arm="intraday",
        eligible_ts=ELIGIBLE_TS,
        arrival_quote=QuoteRef(mid=arrival_mid, source_ts=TICK_TS,
                               source="first_eligible_tick")
        if arrival_mid is not None
        else None,
        fill=None,
    )


# ---------------------------------------------------------------------------
# Pure within-path execution shortfall + timing component
# ---------------------------------------------------------------------------
def test_execution_shortfall_buy_sign_and_magnitude():
    # buy above the arm's own arrival mid => positive (paid up / worse)
    assert execution_shortfall(101.0, 100.0, "buy") == pytest.approx(1.0)
    assert execution_shortfall(99.5, 100.0, "buy") == pytest.approx(-0.5)


def test_execution_shortfall_sell_sign_flips():
    assert execution_shortfall(99.0, 100.0, "sell") == pytest.approx(1.0)
    assert execution_shortfall(100.5, 100.0, "sell") == pytest.approx(-0.5)


def test_execution_shortfall_missing_input_is_none_not_imputed():
    assert execution_shortfall(None, 100.0, "buy") is None
    assert execution_shortfall(101.0, None, "buy") is None


def test_timing_component_is_arrival_to_arrival_move_not_execution():
    # batch arrival mid 101 vs intraday arrival mid 100 => +1 for a buy: the batch
    # arm's arrival instant was 1.0 worse purely because of the market move.
    assert timing_component(101.0, 100.0, "buy") == pytest.approx(1.0)
    assert timing_component(101.0, 100.0, "sell") == pytest.approx(-1.0)
    assert timing_component(None, 100.0, "buy") is None
    assert timing_component(101.0, None, "buy") is None


# ---------------------------------------------------------------------------
# decompose — timing kept STRICTLY separate from within-path execution
# ---------------------------------------------------------------------------
def test_decompose_identity_when_both_arms_have_a_fill():
    # Hypothetical both-fill case (a real intraday fill only exists in a future
    # stage) — proves the algebraic identity total = timing + exec_b - exec_i.
    batch = ArmObservation(
        arm="batch",
        arrival_quote=QuoteRef(mid=101.0),
        fill=PriceRef(102.0),
    )
    intraday = ArmObservation(
        arm="intraday",
        arrival_quote=QuoteRef(mid=100.0),
        fill=PriceRef(100.4),  # imagined real intraday fill
    )
    d = decompose(batch, intraday, "buy")
    assert d["timing_component"] == pytest.approx(1.0)  # 101 - 100
    assert d["execution_shortfall_batch"] == pytest.approx(1.0)  # 102 - 101
    assert d["execution_shortfall_intraday"] == pytest.approx(0.4)  # 100.4 - 100
    assert d["total_difference"] == pytest.approx(1.6)  # 102 - 100.4
    # identity: total == timing + exec_batch - exec_intraday
    assert d["total_difference"] == pytest.approx(
        d["timing_component"] + d["execution_shortfall_batch"]
        - d["execution_shortfall_intraday"]
    )
    # never an execution-quality verdict
    assert d["is_execution_quality"] is False
    assert d["fill_model"] == FILL_MODEL


def test_decompose_stage1_no_intraday_fill_leaves_execution_and_total_null():
    # THE Stage-1 case: intraday arm is hypothetical (no real fill). The overnight
    # move must NOT be smuggled into an execution number, and the intraday
    # execution must NOT default to zero.
    d = decompose(_batch_arm(fill=102.0, arrival_mid=101.0), _intraday_arm(100.0),
                  "buy")
    assert d["timing_component"] == pytest.approx(1.0)  # 101 - 100 (opportunity cost)
    assert d["execution_shortfall_batch"] == pytest.approx(1.0)  # 102 - 101
    # no real intraday fill => not imputed to the midpoint (would have been 0.0)
    assert d["execution_shortfall_intraday"] is None
    assert d["total_difference"] is None
    assert d["is_execution_quality"] is False


def test_decompose_no_batch_arrival_censors_timing_and_exec_batch():
    d = decompose(_batch_arm(fill=102.0, arrival_mid=None), _intraday_arm(100.0),
                  "buy")
    assert d["timing_component"] is None  # needs both arrival mids
    assert d["execution_shortfall_batch"] is None  # needs the batch arrival mid
    assert d["execution_shortfall_intraday"] is None


# ---------------------------------------------------------------------------
# build_paired_record — raw per-arm arrival observations + censoring
# ---------------------------------------------------------------------------
def test_paired_record_records_raw_arrival_quotes_per_arm():
    rec = build_paired_record(
        date=DATE,
        ticker="NVDA",
        side="buy",
        batch_arm=ArmObservation(
            arm="batch",
            eligible_ts=OPEN_REF_TS,
            arrival_quote=QuoteRef(bid=100.9, ask=101.1, source_ts=OPEN_REF_TS,
                                   source="opening_auction_print"),
            fill=PriceRef(102.0, FILL_TIME),
        ),
        intraday_arm=ArmObservation(
            arm="intraday",
            eligible_ts=ELIGIBLE_TS,
            arrival_quote=QuoteRef(bid=99.9, ask=100.1, source_ts=TICK_TS,
                                   source="first_eligible_tick"),
            fill=None,
        ),
        signal_version="2026-06-30-live-abc",
    )
    assert rec["censored_reason"] is None
    assert rec["filled"] is True
    assert rec["intraday_entry_hypothetical"] is True
    # each arm carries its OWN arrival quote bid/ask/source-ts + eligibility ts
    ba = rec["batch_arm"]
    assert ba["arrival_quote"] == {
        "bid": 100.9, "ask": 101.1, "mid": pytest.approx(101.0),
        "source_ts": OPEN_REF_TS, "source": "opening_auction_print",
    }
    assert ba["eligible_ts"] == OPEN_REF_TS
    assert ba["fill_model"] == FILL_MODEL
    ia = rec["intraday_arm"]
    assert ia["arrival_quote"]["source_ts"] == TICK_TS
    assert ia["eligible_ts"] == ELIGIBLE_TS
    assert ia["fill"] is None  # no real intraday order in Stage-1
    # decomposition: timing kept separate; intraday exec NOT imputed to zero
    d = rec["decomposition"]
    assert d["timing_component"] == pytest.approx(1.0)  # 101 - 100
    assert d["execution_shortfall_batch"] == pytest.approx(1.0)  # 102 - 101
    assert d["execution_shortfall_intraday"] is None
    assert d["total_difference"] is None
    # OBSERVE-ONLY: no verdict / execution-quality claim leaks
    assert d["is_execution_quality"] is False
    assert "verdict" not in rec and "pass" not in rec
    assert "implementation_shortfall_batch" not in rec  # biased v1 metric is gone
    # the frozen pre-registration travels on the row
    assert rec["prereg"] == FROZEN_PREREG


def test_paired_record_no_batch_fill_is_censored():
    rec = build_paired_record(
        date=DATE,
        ticker="MU",
        side="buy",
        batch_arm=ArmObservation(arm="batch", arrival_quote=QuoteRef(mid=50.0),
                                 fill=None),  # admitted but never bought
        intraday_arm=_intraday_arm(50.1),
        signal_version="sv1",
    )
    assert "no_batch_fill" in rec["censored_reason"]
    assert rec["filled"] is False
    assert rec["decomposition"]["execution_shortfall_batch"] is None  # no fill


def test_paired_record_no_intraday_tick_is_censored():
    rec = build_paired_record(
        date=DATE,
        ticker="NFLX",
        side="buy",
        batch_arm=_batch_arm(fill=72.0, arrival_mid=71.5),
        intraday_arm=ArmObservation(arm="intraday", arrival_quote=None, fill=None),
        signal_version="sv1",
    )
    assert rec["censored_reason"] == "no_intraday_tick"
    assert rec["filled"] is True
    assert rec["decomposition"]["timing_component"] is None  # no intraday arrival


def test_paired_record_no_intraday_fill_is_NOT_a_censoring_anomaly():
    # The intraday arm having no real fill is the normal Stage-1 state, not a
    # censoring reason — only missing OBSERVED inputs are flagged.
    rec = build_paired_record(
        date=DATE,
        ticker="NVDA",
        side="buy",
        batch_arm=_batch_arm(fill=102.0, arrival_mid=101.0),
        intraday_arm=_intraday_arm(100.0),
        signal_version="sv1",
    )
    assert rec["censored_reason"] is None  # complete OBSERVATION despite no i-fill
    assert rec["intraday_arm"]["fill"] is None


# ---------------------------------------------------------------------------
# FROZEN first-eligible-tick selection — as-of enforced, no post-hoc favorable tick
# ---------------------------------------------------------------------------
def _tick(ts, mid):
    return {"source_ts": ts, "mid": mid, "bid": mid - 0.05, "ask": mid + 0.05}


def test_first_eligible_tick_picks_earliest_at_or_after_eligibility():
    ticks = [
        _tick("2026-06-30T09:36:00-04:00", 100.0),
        _tick("2026-06-30T09:40:00-04:00", 100.5),
        _tick("2026-06-30T10:00:00-04:00", 101.0),
    ]
    sel = select_first_eligible_tick(ticks, "2026-06-30T09:35:00-04:00")
    assert sel["source_ts"] == "2026-06-30T09:36:00-04:00"


def test_first_eligible_tick_later_favorable_tick_is_NOT_selected():
    # A later tick has a much better (lower, for a buy) price; the rule must still
    # pick the FIRST eligible tick, never the favorable later one.
    ticks = [
        _tick("2026-06-30T09:36:00-04:00", 100.0),  # first eligible
        _tick("2026-06-30T11:00:00-04:00", 90.0),   # tempting, but post hoc
    ]
    sel = select_first_eligible_tick(ticks, "2026-06-30T09:35:00-04:00")
    assert sel["mid"] == 100.0  # NOT 90.0


def test_first_eligible_tick_ignores_ticks_before_eligibility():
    ticks = [
        _tick("2026-06-30T09:30:30-04:00", 99.0),  # before eligibility (as-of)
        _tick("2026-06-30T09:36:00-04:00", 100.0),
    ]
    sel = select_first_eligible_tick(ticks, "2026-06-30T09:35:00-04:00")
    assert sel["source_ts"] == "2026-06-30T09:36:00-04:00"


def test_first_eligible_tick_respects_no_entry_cutoff():
    ticks = [_tick("2026-06-30T15:45:00-04:00", 100.0)]  # inside last 30 min
    sel = select_first_eligible_tick(
        ticks, "2026-06-30T09:35:00-04:00", not_after="2026-06-30T15:30:00-04:00"
    )
    assert sel is None  # censored — no eligible tick before the cutoff


def test_first_eligible_tick_no_eligibility_instant_selects_nothing():
    # Without a declared as-of we refuse to pick a tick (closes the post-hoc loophole).
    ticks = [_tick("2026-06-30T09:36:00-04:00", 100.0)]
    assert select_first_eligible_tick(ticks, None) is None


def test_first_eligible_tick_out_of_order_feed_is_sorted():
    ticks = [
        _tick("2026-06-30T10:00:00-04:00", 101.0),
        _tick("2026-06-30T09:36:00-04:00", 100.0),  # earlier, later in feed order
    ]
    sel = select_first_eligible_tick(ticks, "2026-06-30T09:35:00-04:00")
    assert sel["source_ts"] == "2026-06-30T09:36:00-04:00"


# ---------------------------------------------------------------------------
# pair_records — the join (selection happens here, not in the loader)
# ---------------------------------------------------------------------------
def test_pair_records_joins_selects_and_censors():
    admitted = [
        AdmittedName(DATE, "NVDA", "buy", "sv1"),
        AdmittedName(DATE, "MU", "buy", "sv1"),   # no tick
        AdmittedName(DATE, "NFLX", "buy", "sv1"),  # no fill
    ]
    batch_fills = {
        ("sv1", "NVDA"): PriceRef(102.0, FILL_TIME),
        ("sv1", "MU"): PriceRef(1062.0, FILL_TIME),
    }
    batch_arrivals = {
        (DATE, "NVDA"): QuoteRef(mid=101.0, source_ts=OPEN_REF_TS),
        (DATE, "MU"): QuoteRef(mid=1060.0, source_ts=OPEN_REF_TS),
        (DATE, "NFLX"): QuoteRef(mid=71.5, source_ts=OPEN_REF_TS),
    }
    intraday_ticks = {
        (DATE, "NVDA"): [
            _tick("2026-06-30T09:30:30-04:00", 99.0),  # before eligibility
            _tick(TICK_TS, 100.0),                     # first eligible
            _tick("2026-06-30T10:00:00-04:00", 98.0),  # later favorable -> ignored
        ],
        (DATE, "NFLX"): [_tick(TICK_TS, 72.0)],
    }
    eligibility = {
        (DATE, "NVDA"): ELIGIBLE_TS,
        (DATE, "NFLX"): ELIGIBLE_TS,
    }
    recs = pair_records(
        admitted, batch_fills, intraday_ticks,
        batch_arrivals=batch_arrivals, eligibility=eligibility,
    )
    by_ticker = {r["ticker"]: r for r in recs}

    nvda = by_ticker["NVDA"]
    assert nvda["censored_reason"] is None
    # first-eligible tick selected (mid 100.0), NOT the later favorable 98.0
    assert nvda["intraday_arm"]["arrival_quote"]["mid"] == 100.0
    assert nvda["decomposition"]["timing_component"] == pytest.approx(1.0)  # 101-100
    assert nvda["decomposition"]["execution_shortfall_batch"] == pytest.approx(1.0)
    assert nvda["decomposition"]["execution_shortfall_intraday"] is None

    assert by_ticker["MU"]["censored_reason"] == "no_intraday_tick"
    assert "no_batch_fill" in by_ticker["NFLX"]["censored_reason"]


def test_pair_records_falls_back_to_tick_stamped_eligibility():
    admitted = [AdmittedName(DATE, "NVDA", "buy", "sv1")]
    batch_fills = {("sv1", "NVDA"): PriceRef(102.0)}
    ticks = {
        (DATE, "NVDA"): [
            {"source_ts": TICK_TS, "mid": 100.0, "eligible_after": ELIGIBLE_TS},
        ]
    }
    # no explicit eligibility map -> falls back to the tick's own eligible_after
    rec = pair_records(admitted, batch_fills, ticks)[0]
    assert rec["intraday_arm"]["arrival_quote"]["mid"] == 100.0
    assert rec["intraday_arm"]["eligible_ts"] == ELIGIBLE_TS


def test_pair_records_falls_back_to_date_keyed_fill():
    admitted = [AdmittedName(DATE, "NVDA", "buy", "sv1")]
    batch_fills = {(DATE, "NVDA"): PriceRef(101.0, FILL_TIME)}  # date-keyed
    ticks = {(DATE, "NVDA"): [{"source_ts": TICK_TS, "mid": 100.0}]}
    rec = pair_records(
        admitted, batch_fills, ticks, eligibility={(DATE, "NVDA"): ELIGIBLE_TS}
    )[0]
    assert rec["filled"] is True


# ---------------------------------------------------------------------------
# summarize — counts only, no verdict; analysis unit = session date
# ---------------------------------------------------------------------------
def test_summarize_counts_and_analysis_unit():
    recs = pair_records(
        [
            AdmittedName(DATE, "NVDA", "buy", "sv1"),
            AdmittedName(DATE, "MU", "buy", "sv1"),
            AdmittedName(DATE, "NFLX", "buy", "sv1"),
        ],
        {("sv1", "NVDA"): PriceRef(102.0), ("sv1", "MU"): PriceRef(1062.0)},
        {(DATE, "NVDA"): [{"source_ts": TICK_TS, "mid": 100.0}]},
        batch_arrivals={(DATE, "NVDA"): QuoteRef(mid=101.0)},
        eligibility={(DATE, "NVDA"): ELIGIBLE_TS},
    )
    s = summarize(recs)
    assert s["analysis_unit"] == "session_date"
    assert s["n_sessions"] == 1
    assert s["n_admitted_pairs"] == 3
    assert s["n_complete_observations"] == 1  # only NVDA
    assert s["n_censored_pairs"] == 2
    assert s["n_with_batch_fill"] == 2
    assert s["n_with_intraday_tick"] == 1
    assert s["n_timing_computable"] == 1
    assert s["n_exec_batch_computable"] == 1
    # no comparison / verdict / bps key leaks into the summary
    assert not any(
        k in s for k in ("verdict", "edge", "non_inferiority", "mean_is")
    )


# ---------------------------------------------------------------------------
# JSONL accumulation — idempotent append
# ---------------------------------------------------------------------------
def test_append_and_idempotent(tmp_path):
    out = tmp_path / "renquant105_pilot" / "paired_is.jsonl"
    recs = pair_records(
        [AdmittedName(DATE, "NVDA", "buy", "sv1"), AdmittedName(DATE, "MU", "buy", "sv1")],
        {("sv1", "NVDA"): PriceRef(102.0)},
        {(DATE, "NVDA"): [{"source_ts": TICK_TS, "mid": 100.0}]},
        eligibility={(DATE, "NVDA"): ELIGIBLE_TS},
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
        {(DATE, "NVDA"): [{"source_ts": TICK_TS, "mid": 100.0}]},
        eligibility={(DATE, "NVDA"): ELIGIBLE_TS},
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
        batch_arm=_batch_arm(),
        intraday_arm=_intraday_arm(),
        signal_version="sv1",
    )
    assert pair_key(rec) == (DATE, "NVDA", "sv1")


# ---------------------------------------------------------------------------
# Read-only loaders over an in-memory DB + JSONL sources + end-to-end collect
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


def test_load_intraday_ticks_returns_raw_list_not_collapsed(tmp_path):
    src = tmp_path / "ticks.jsonl"
    src.write_text(
        json.dumps({"date": DATE, "ticker": "NVDA", "mid": 100.0, "source_ts": TICK_TS})
        + "\n"
        + json.dumps({"date": DATE, "ticker": "NVDA", "mid": 100.5,
                      "source_ts": "2026-06-30T10:00:00-04:00"})
        + "\n"
        + json.dumps({"date": "2026-06-29", "ticker": "NVDA", "mid": 1.0,
                      "source_ts": "x"})  # other day
        + "\n"
        + "not-json\n"  # malformed line skipped
    )
    ticks = load_intraday_ticks(src, DATE)
    assert set(ticks) == {(DATE, "NVDA")}
    # BOTH ticks retained (raw) — selection is deferred to the frozen rule.
    assert len(ticks[(DATE, "NVDA")]) == 2


def test_load_intraday_ticks_missing_file_is_empty(tmp_path):
    assert load_intraday_ticks(tmp_path / "absent.jsonl", DATE) == {}


def test_load_batch_arrivals_first_wins(tmp_path):
    src = tmp_path / "arrivals.jsonl"
    src.write_text(
        json.dumps({"date": DATE, "ticker": "NVDA", "bid": 100.9, "ask": 101.1,
                    "source_ts": OPEN_REF_TS})
        + "\n"
        + json.dumps({"date": DATE, "ticker": "NVDA", "mid": 999.0})  # dup -> ignored
        + "\n"
    )
    arrivals = load_batch_arrivals(src, DATE)
    assert arrivals[(DATE, "NVDA")].resolved_mid() == pytest.approx(101.0)
    assert arrivals[(DATE, "NVDA")].source == "opening_auction_print"


def test_load_batch_arrivals_missing_file_is_empty(tmp_path):
    assert load_batch_arrivals(tmp_path / "absent.jsonl", DATE) == {}


def test_collect_end_to_end(tmp_path):
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
            {"date": DATE, "ticker": "NVDA", "mid": 100.0, "source_ts": TICK_TS,
             "eligible_after": ELIGIBLE_TS}
        )
        + "\n"
    )
    arrivals = tmp_path / "arrivals.jsonl"
    arrivals.write_text(
        json.dumps({"date": DATE, "ticker": "NVDA", "mid": 101.0,
                    "source_ts": OPEN_REF_TS})
        + "\n"
    )

    recs = collect(date=DATE, runs_db=db, tick_source=ticks,
                   batch_arrival_source=arrivals)
    by_ticker = {r["ticker"]: r for r in recs}
    assert set(by_ticker) == {"NVDA", "MU"}

    nvda = by_ticker["NVDA"]
    assert nvda["censored_reason"] is None
    assert nvda["decomposition"]["timing_component"] == pytest.approx(1.0)  # 101-100
    assert nvda["decomposition"]["execution_shortfall_batch"] == pytest.approx(1.0)
    # intraday execution NOT imputed to zero
    assert nvda["decomposition"]["execution_shortfall_intraday"] is None

    # MU: admitted, no tick and no fill -> censored, recorded not dropped
    assert by_ticker["MU"]["filled"] is False
    assert "no_intraday_tick" in by_ticker["MU"]["censored_reason"]

    s = summarize(recs)
    assert s["n_admitted_pairs"] == 2
    assert s["n_complete_observations"] == 1
