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
    derive_frozen_window,
    execution_shortfall,
    existing_pair_keys,
    load_admitted,
    load_batch_arrivals,
    load_batch_fills,
    load_intraday_ticks,
    load_submitted_entries,
    pair_key,
    pair_records,
    resolve_admitting_run_date,
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
# QuoteRef validation — the collector enforces the consumer contract on ARBITRARY
# JSONL: a crossed / non-positive / non-finite quote never fabricates a mid.
# ---------------------------------------------------------------------------
def test_quote_ref_valid_bid_ask_midpoint():
    assert QuoteRef(bid=100.9, ask=101.1).resolved_mid() == pytest.approx(101.0)


def test_quote_ref_locked_market_bid_equals_ask_is_valid():
    # A locked (zero-spread) market is valid, not crossed.
    assert QuoteRef(bid=100.0, ask=100.0).resolved_mid() == pytest.approx(100.0)


def test_quote_ref_crossed_market_censors_mid():
    # bid > ask is a crossed market — invalid data, must NOT yield a midpoint.
    assert QuoteRef(bid=101.5, ask=100.5).resolved_mid() is None


def test_quote_ref_non_positive_price_censors_mid():
    assert QuoteRef(bid=0.0, ask=101.0).resolved_mid() is None
    assert QuoteRef(bid=100.0, ask=0.0).resolved_mid() is None
    assert QuoteRef(bid=-1.0, ask=101.0).resolved_mid() is None


def test_quote_ref_non_finite_price_censors_mid():
    assert QuoteRef(bid=float("nan"), ask=101.0).resolved_mid() is None
    assert QuoteRef(bid=100.0, ask=float("inf")).resolved_mid() is None
    assert QuoteRef(bid=float("-inf"), ask=float("inf")).resolved_mid() is None


def test_quote_ref_explicit_mid_validated_too():
    assert QuoteRef(mid=101.0).resolved_mid() == pytest.approx(101.0)
    assert QuoteRef(mid=0.0).resolved_mid() is None
    assert QuoteRef(mid=-5.0).resolved_mid() is None
    assert QuoteRef(mid=float("nan")).resolved_mid() is None
    assert QuoteRef(mid=float("inf")).resolved_mid() is None


def test_quote_ref_to_dict_keeps_raw_bid_ask_but_nulls_invalid_mid():
    # The RAW quote is still recorded (observe-only); only the DERIVED mid is
    # censored, so nothing is silently dropped.
    d = QuoteRef(bid=101.5, ask=100.5, source_ts=OPEN_REF_TS).to_dict()
    assert d["bid"] == 101.5 and d["ask"] == 100.5  # raw preserved
    assert d["mid"] is None  # crossed -> censored, not fabricated


def test_paired_record_crossed_intraday_quote_is_censored():
    # A crossed intraday arrival quote yields no arrival mid -> recorded, censored
    # by cause, never imputed.
    rec = build_paired_record(
        date=DATE,
        ticker="NVDA",
        side="buy",
        batch_arm=_batch_arm(fill=102.0, arrival_mid=101.0),
        intraday_arm=ArmObservation(
            arm="intraday",
            eligible_ts=ELIGIBLE_TS,
            arrival_quote=QuoteRef(bid=100.6, ask=100.4, source_ts=TICK_TS),  # crossed
            fill=None,
        ),
        signal_version="sv1",
    )
    assert rec["censored_reason"] == "no_intraday_arrival_mid"
    assert rec["intraday_arm"]["arrival_quote"]["mid"] is None  # not fabricated
    assert rec["decomposition"]["timing_component"] is None


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
# Timestamp CORRECTNESS — compare true instants, not raw strings (Codex 2026-07-01):
# mixed UTC offsets, Z-suffix, DST, and naive/malformed values.
# ---------------------------------------------------------------------------
def test_first_eligible_tick_mixed_offsets_order_by_instant_not_string():
    # -04:00 09:36 == 13:36Z; +00:00 13:35 == 13:35Z (an EARLIER instant). Lexical
    # string sort orders "2026-06-30T09:36:00-04:00" BEFORE "2026-06-30T13:35:00+00:00"
    # (the wrong order); by instant the +00:00 tick is first and must be selected.
    ticks = [
        _tick("2026-06-30T09:36:00-04:00", 100.0),  # 13:36Z
        _tick("2026-06-30T13:35:00+00:00", 99.0),   # 13:35Z -> earlier instant
    ]
    sel = select_first_eligible_tick(ticks, "2026-06-30T13:00:00+00:00")
    assert sel["source_ts"] == "2026-06-30T13:35:00+00:00"


def test_first_eligible_tick_pre_eligibility_across_offsets_is_excluded():
    # A tick whose LOCAL clock string looks "after" the as-of but whose true instant
    # is BEFORE it must be rejected. 09:31-04:00 = 13:31Z is before the 13:34Z as-of,
    # even though "09:31" > "09:30" lexically vs a -04:00 as-of string.
    ticks = [
        _tick("2026-06-30T09:31:00-04:00", 98.0),   # 13:31Z -> before as-of
        _tick("2026-06-30T09:36:00-04:00", 100.0),  # 13:36Z -> after as-of
    ]
    sel = select_first_eligible_tick(ticks, "2026-06-30T13:34:00+00:00")  # 09:34-04:00
    assert sel["source_ts"] == "2026-06-30T09:36:00-04:00"


def test_first_eligible_tick_z_suffix_parses_as_utc():
    # A 'Z' designator must parse identically to '+00:00'.
    ticks = [
        _tick("2026-06-30T13:36:00Z", 100.0),
        _tick("2026-06-30T14:00:00Z", 101.0),
    ]
    sel = select_first_eligible_tick(ticks, "2026-06-30T09:35:00-04:00")  # 13:35Z
    assert sel["source_ts"] == "2026-06-30T13:36:00Z"


def test_first_eligible_tick_equal_instant_across_encodings_is_admitted():
    # As-of is "at or after": a tick at the SAME instant as the eligibility bound,
    # even in a different encoding (13:35Z == 09:35-04:00), is admitted.
    ticks = [_tick("2026-06-30T13:35:00Z", 100.0)]
    sel = select_first_eligible_tick(ticks, "2026-06-30T09:35:00-04:00")
    assert sel is not None and sel["mid"] == 100.0


def test_first_eligible_tick_dst_offsets_order_by_instant():
    # Winter EST (-05:00) vs summer EDT (-04:00): the collector must not assume a
    # fixed offset. 14:36-05:00 = 19:36Z is LATER than 14:40-04:00 = 18:40Z, though
    # the local strings ("14:36" < "14:40") suggest otherwise.
    ticks = [
        _tick("2026-01-15T14:36:00-05:00", 100.0),  # 19:36Z (EST)
        _tick("2026-01-15T14:40:00-04:00", 99.0),   # 18:40Z (as if EDT) -> earlier
    ]
    sel = select_first_eligible_tick(ticks, "2026-01-15T18:00:00+00:00")
    assert sel["source_ts"] == "2026-01-15T14:40:00-04:00"


def test_first_eligible_tick_not_after_compared_by_instant():
    # not_after 13:40Z; a tick at 09:45-04:00 = 13:45Z is past the cutoff by instant
    # even though "09:45" < "13:40" lexically. It must be excluded -> censored.
    ticks = [_tick("2026-06-30T09:45:00-04:00", 100.0)]  # 13:45Z
    sel = select_first_eligible_tick(
        ticks, "2026-06-30T13:30:00+00:00", not_after="2026-06-30T13:40:00+00:00"
    )
    assert sel is None


def test_first_eligible_tick_naive_source_ts_is_ineligible():
    # A timezone-naive tick cannot be ordered as-of, so it is never admitted; a
    # later well-formed tick is selected instead of the ambiguous one.
    ticks = [
        _tick("2026-06-30T09:36:00", 100.0),        # naive -> ineligible
        _tick("2026-06-30T09:40:00-04:00", 101.0),  # valid
    ]
    sel = select_first_eligible_tick(ticks, "2026-06-30T09:35:00-04:00")
    assert sel["source_ts"] == "2026-06-30T09:40:00-04:00"


def test_first_eligible_tick_malformed_source_ts_is_ineligible():
    ticks = [
        _tick("not-a-timestamp", 100.0),            # malformed -> ineligible
        _tick("2026-06-30T09:40:00-04:00", 101.0),  # valid
    ]
    sel = select_first_eligible_tick(ticks, "2026-06-30T09:35:00-04:00")
    assert sel["source_ts"] == "2026-06-30T09:40:00-04:00"


def test_first_eligible_tick_all_ticks_unparseable_is_none():
    ticks = [_tick("2026-06-30T09:36:00", 100.0), _tick("garbage", 101.0)]
    assert select_first_eligible_tick(ticks, "2026-06-30T09:35:00-04:00") is None


def test_first_eligible_tick_naive_eligibility_raises():
    # A bad as-of is a CONTROL error: fail loud, never silently censor everything.
    ticks = [_tick("2026-06-30T09:36:00-04:00", 100.0)]
    with pytest.raises(ValueError):
        select_first_eligible_tick(ticks, "2026-06-30T09:35:00")  # naive


def test_first_eligible_tick_malformed_eligibility_raises():
    ticks = [_tick("2026-06-30T09:36:00-04:00", 100.0)]
    with pytest.raises(ValueError):
        select_first_eligible_tick(ticks, "not-a-timestamp")


def test_first_eligible_tick_bad_not_after_raises():
    ticks = [_tick("2026-06-30T09:36:00-04:00", 100.0)]
    with pytest.raises(ValueError):
        select_first_eligible_tick(
            ticks, "2026-06-30T09:35:00-04:00", not_after="2026-06-30T15:30:00"  # naive
        )


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


# ---------------------------------------------------------------------------
# REGRESSION: 2026-07-02 first scheduled run produced ALL-ZERO output (sessions 0,
# admitted pairs 0) against a real session. Root causes, reproduced here against a
# DB shaped like the CURRENT live schema:
#   (a) load_admitted requires candidate_scores.selected = 1, which the live
#       pipeline stopped stamping after 2026-05-22 — a submitted entry is now
#       selected = 0 / blocked_by = 'broker_pending_submitted' plus a trades row
#       action='buy_pending' / order_type='NEW_BUY';
#   (b) --date used one date for BOTH the admitting run_date and the tick-file
#       session, but the admitting batch runs post-close on the PREVIOUS session;
#   (c) the real #216 tick lines stamp session_open/session_close but never
#       eligible_after, so no tick was ever selectable.
# ---------------------------------------------------------------------------
SESSION = "2026-07-02"          # fill session T (ticks are stamped with this date)
ADMIT_DATE = "2026-07-01"       # the post-close batch that placed the entry
ADMIT_RUN = "2026-07-01-live-01c54b39"
SESSION_OPEN = "2026-07-02T09:30:00-04:00"
SESSION_CLOSE = "2026-07-02T16:00:00-04:00"


def _seed_current_live_schema_db(path) -> None:
    """A runs DB shaped like the CURRENT live pipeline output (2026-07 vintage):
    no selected=1 anywhere, entry recorded as a buy_pending/NEW_BUY submission on
    the previous session's run, and NO fill-confirmation ('buy') row."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT
        );
        CREATE TABLE candidate_scores (
            run_id TEXT, ticker TEXT, role TEXT, selected INTEGER, blocked_by TEXT
        );
        CREATE TABLE trades (
            run_id TEXT, ticker TEXT, action TEXT, price REAL, trade_date DATE,
            order_type TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO pipeline_runs VALUES (?,?,?)",
        [
            (ADMIT_RUN, ADMIT_DATE, "live"),
            ("2026-07-02-live-intraday1", SESSION, "live"),  # session-T liveness run
        ],
    )
    conn.executemany(
        "INSERT INTO candidate_scores VALUES (?,?,?,?,?)",
        [
            # The submitted entry itself is selected=0 on the current live path.
            (ADMIT_RUN, "OXY", "candidate", 0, "broker_pending_submitted"),
            (ADMIT_RUN, "AAPL", "candidate", 0, "veto:rank_score_below_floor"),
        ],
    )
    conn.executemany(
        "INSERT INTO trades VALUES (?,?,?,?,?,?)",
        [
            # The entry submission (reference price at submit — NOT a fill).
            (ADMIT_RUN, "OXY", "buy_pending", 47.94, ADMIT_DATE, "NEW_BUY"),
            # A sell and a QP_BUY must not be treated as batch entries here.
            (ADMIT_RUN, "NEE", "sell_pending", 87.5, ADMIT_DATE, "EXIT"),
            (ADMIT_RUN, "WFC", "buy", 76.4, ADMIT_DATE, "QP_BUY"),
        ],
    )
    conn.commit()
    conn.close()


def _real_shape_tick(ticker, source_ts, bid, ask):
    """A tick line shaped like the real #216 quote logger output: session bounds
    stamped, NO eligible_after field."""
    return {
        "date": SESSION,
        "ticker": ticker,
        "source_ts": source_ts,
        "bid": bid,
        "ask": ask,
        "mid": (bid + ask) / 2.0,
        "session_open": SESSION_OPEN,
        "session_close": SESSION_CLOSE,
        "status": "ok",
    }


def test_collect_current_live_schema_pairs_submitted_entry(tmp_path):
    """THE zero-session regression: a current-live-schema DB plus real-shape ticks
    must yield the admitted pair (censored on the missing fill), not zero rows."""
    db = tmp_path / "runs.db"
    _seed_current_live_schema_db(db)
    ticks = tmp_path / "ticks.jsonl"
    ticks.write_text(
        "\n".join(
            json.dumps(t)
            for t in [
                # Before open+5min: must NOT be selected (frozen window).
                _real_shape_tick("OXY", "2026-07-02T09:31:00-04:00", 48.00, 48.02),
                # First eligible tick at/after 09:35 — the arrival quote.
                _real_shape_tick("OXY", "2026-07-02T09:36:10-04:00", 48.55, 48.57),
                # Later, more favorable tick: must be ignored.
                _real_shape_tick("OXY", "2026-07-02T11:00:00-04:00", 47.10, 47.12),
            ]
        )
        + "\n"
    )

    recs = collect(date=SESSION, runs_db=db, tick_source=ticks)

    assert len(recs) == 1  # was 0 before the fix
    rec = recs[0]
    assert rec["ticker"] == "OXY"
    assert rec["date"] == SESSION  # the FILL session, not the admit date
    assert rec["signal_version"] == ADMIT_RUN  # admitting run id preserved
    # Intraday arm: first eligible tick under the DERIVED frozen window.
    assert rec["intraday_arm"]["arrival_quote"]["source_ts"] == (
        "2026-07-02T09:36:10-04:00"
    )
    assert rec["intraday_arm"]["arrival_quote"]["mid"] == pytest.approx(48.56)
    # No fill-confirmation row exists on the live path (and the broker canceled
    # this very order pre-open on the real 2026-07-02): censored, never imputed —
    # in particular the buy_pending submit reference price must NOT become a fill.
    assert rec["filled"] is False
    assert "no_batch_fill" in rec["censored_reason"]
    assert rec["batch_arm"]["fill"] is None

    s = summarize(recs)
    assert s["n_sessions"] == 1  # was 0
    assert s["n_admitted_pairs"] == 1
    assert s["n_with_intraday_tick"] == 1  # was 0 despite valid ticks
    assert s["n_with_batch_fill"] == 0  # honest: no fill confirmation in the DB


def test_resolve_admitting_run_date_previous_session(tmp_path):
    db = sqlite3.connect(":memory:")
    db.executescript(
        "CREATE TABLE pipeline_runs (run_id TEXT, run_date DATE, run_type TEXT);"
    )
    db.executemany(
        "INSERT INTO pipeline_runs VALUES (?,?,?)",
        [
            ("r-fri", "2026-06-26", "live"),
            ("r-fri-sim", "2026-06-29", "sim"),  # wrong run_type — ignored
            ("r-mon", "2026-06-29", "live"),
        ],
    )
    # Monday session pairs Friday's batch when Monday is the earliest live run...
    assert resolve_admitting_run_date(db, "2026-06-29") == "2026-06-26"
    # ...and a Tuesday session pairs Monday's batch.
    assert resolve_admitting_run_date(db, "2026-06-30") == "2026-06-29"
    # No earlier run at all -> None (collect then falls back to legacy admits only).
    assert resolve_admitting_run_date(db, "2026-06-26") is None


def test_load_submitted_entries_filters_and_session_date(tmp_path):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE pipeline_runs (run_id TEXT, run_date DATE, run_type TEXT);
        CREATE TABLE trades (
            run_id TEXT, ticker TEXT, action TEXT, price REAL, trade_date DATE,
            order_type TEXT
        );
        """
    )
    db.execute("INSERT INTO pipeline_runs VALUES ('r1', ?, 'live')", (ADMIT_DATE,))
    db.executemany(
        "INSERT INTO trades VALUES (?,?,?,?,?,?)",
        [
            ("r1", "OXY", "buy_pending", 47.94, ADMIT_DATE, "NEW_BUY"),
            ("r1", "MU", "buy_pending", 1062.0, ADMIT_DATE, "TOP_UP"),  # top-up entry
            ("r1", "NEE", "sell_pending", 87.5, ADMIT_DATE, "EXIT"),  # not an entry
            ("r1", "WFC", "buy", 76.4, ADMIT_DATE, "QP_BUY"),  # legacy path only
        ],
    )
    names = load_submitted_entries(db, ADMIT_DATE, session_date=SESSION)
    assert sorted(n.ticker for n in names) == ["MU", "OXY"]
    assert all(n.date == SESSION for n in names)  # ticks key on the FILL session
    assert all(n.signal_version == "r1" for n in names)
    assert all(n.side == "buy" for n in names)


def test_load_submitted_entries_schema_without_order_type_column():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE pipeline_runs (run_id TEXT, run_date DATE, run_type TEXT);
        CREATE TABLE trades (run_id TEXT, ticker TEXT, action TEXT, price REAL);
        """
    )
    db.execute("INSERT INTO pipeline_runs VALUES ('r1', ?, 'live')", (ADMIT_DATE,))
    db.execute("INSERT INTO trades VALUES ('r1', 'OXY', 'buy_pending', 47.94)")
    db.execute("INSERT INTO trades VALUES ('r1', 'NVDA', 'buy', 102.0)")  # ambiguous
    names = load_submitted_entries(db, ADMIT_DATE, session_date=SESSION)
    # Without order_type only the unambiguous buy_pending submissions qualify.
    assert [n.ticker for n in names] == ["OXY"]


def test_derive_frozen_window_from_session_stamps():
    ticks = [_real_shape_tick("OXY", "2026-07-02T09:31:00-04:00", 48.0, 48.02)]
    eligible_after, not_after = derive_frozen_window(ticks)
    # open 09:30 + 5min and close 16:00 - 30min, as true instants (UTC encoding ok).
    from renquant_orchestrator.intraday_pairing_logger import _parse_instant

    assert _parse_instant(eligible_after) == _parse_instant("2026-07-02T09:35:00-04:00")
    assert _parse_instant(not_after) == _parse_instant("2026-07-02T15:30:00-04:00")


def test_derive_frozen_window_missing_or_naive_stamps_is_none():
    assert derive_frozen_window([]) == (None, None)
    assert derive_frozen_window([{"source_ts": TICK_TS, "mid": 1.0}]) == (None, None)
    naive = {"session_open": "2026-07-02T09:30:00", "session_close": SESSION_CLOSE}
    assert derive_frozen_window([naive]) == (None, None)


def test_pair_records_derived_cutoff_censors_late_only_ticks():
    # Real-shape ticks (no eligible_after) whose only quotes fall INSIDE the last
    # 30 minutes: the derived close-30min cutoff must censor the pair.
    admitted = [AdmittedName(SESSION, "OXY", "buy", ADMIT_RUN)]
    ticks = {
        (SESSION, "OXY"): [
            _real_shape_tick("OXY", "2026-07-02T15:45:00-04:00", 48.0, 48.02),
        ]
    }
    rec = pair_records(admitted, {}, ticks)[0]
    assert "no_intraday_tick" in rec["censored_reason"]
    assert rec["intraday_arm"]["arrival_quote"] is None


def test_pair_records_explicit_eligibility_still_beats_derived_window():
    # Precedence: an explicit per-name eligibility instant overrides the derived
    # open+5min (here it admits an earlier tick the derived window would skip).
    admitted = [AdmittedName(SESSION, "OXY", "buy", ADMIT_RUN)]
    ticks = {
        (SESSION, "OXY"): [
            _real_shape_tick("OXY", "2026-07-02T09:31:00-04:00", 48.0, 48.02),
        ]
    }
    rec = pair_records(
        admitted, {}, ticks,
        eligibility={(SESSION, "OXY"): "2026-07-02T09:30:30-04:00"},
    )[0]
    assert rec["intraday_arm"]["arrival_quote"]["source_ts"] == (
        "2026-07-02T09:31:00-04:00"
    )


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
