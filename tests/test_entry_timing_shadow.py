"""Tests for ``entry_timing_shadow`` — renquant105 Stage-1 OBSERVE-ONLY
entry-timing shadow evaluator.

Fully hermetic and deterministic: every tick timestamp is INJECTED (no wall-clock
is ever read on the evaluation path), the policies are pure functions over the tick
series, and the pilot output goes to a tmp file. The suite proves, per policy, that
(i) the entry selection is correct, (ii) the choice is AS-OF correct — a later, more
favorable tick is never chosen, (iii) censoring (never-triggered) is recorded by
cause and never imputed, (iv) the JSONL append is idempotent, and (v) the module
holds NO order-placement surface (observe-only, no-order invariant). Never touches
live state.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator import entry_timing_shadow as ets
from renquant_orchestrator.entry_timing_shadow import (
    DEFAULT_CONFIG,
    POLICY_IMMEDIATE,
    POLICY_OPENING_RANGE_BREAKOUT,
    POLICY_PULLBACK_TO_REF,
    POLICY_VWAP_CROSS,
    REGISTERED_POLICIES,
    AdmittedName,
    EntryTimingConfig,
    append_records,
    build_record,
    collect,
    evaluate_name,
    evaluate_session,
    existing_keys,
    load_admitted_from_json,
    load_tick_records,
    normalize_ticks,
    preregistration_manifest,
    record_key,
    summarize,
)

# --- fixed, injected timestamps (no wall-clock; ET offset -04:00 = EDT) -----
DATE = "2026-06-30"


def _et(hh: int, mm: int, ss: int = 0) -> str:
    """An ET (EDT) ISO timestamp on the fixed session date."""
    return f"{DATE}T{hh:02d}:{mm:02d}:{ss:02d}-04:00"


def _tick(ticker: str, hh: int, mm: int, mid: float, *, ss: int = 0, **extra) -> dict:
    """Build a raw #216-shaped feed row with a fresh (age-0) quote by default."""
    t = _et(hh, mm, ss)
    row = {
        "date": DATE,
        "ticker": ticker,
        "mid": mid,
        "tick_time": t,
        "ts": t,
        "quote_ts": t,
    }
    row.update(extra)
    return row


def _series(ticker: str, points) -> list[dict]:
    """``points`` = iterable of (hh, mm, mid)."""
    return [_tick(ticker, hh, mm, mid) for (hh, mm, mid) in points]


def _outcome(rows, policy):
    """The single row for a policy from an evaluate_name/evaluate_session result."""
    match = [r for r in rows if r["policy"] == policy]
    assert len(match) == 1, f"expected exactly one row for {policy}, got {len(match)}"
    return match[0]


# ===========================================================================
# Pre-registration (frozen config + params)
# ===========================================================================
def test_registered_policy_set_is_the_four_candidates():
    assert REGISTERED_POLICIES == (
        POLICY_IMMEDIATE,
        POLICY_VWAP_CROSS,
        POLICY_OPENING_RANGE_BREAKOUT,
        POLICY_PULLBACK_TO_REF,
    )
    assert DEFAULT_CONFIG.policies == REGISTERED_POLICIES


def test_config_fingerprint_is_stable_and_pins_params():
    # A frozen, regression-pinned fingerprint: if a param changes, this must change.
    assert DEFAULT_CONFIG.fingerprint() == "656e8f36b1f58130"
    changed = EntryTimingConfig(pullback_pct=0.01)
    assert changed.fingerprint() != DEFAULT_CONFIG.fingerprint()


def test_preregistration_manifest_declares_every_policy_and_params():
    manifest = preregistration_manifest()
    assert manifest["observe_only"] is True
    assert manifest["config_fingerprint"] == DEFAULT_CONFIG.fingerprint()
    assert manifest["policies"] == list(REGISTERED_POLICIES)
    # every policy carries its frozen params (window is always present)
    for policy in REGISTERED_POLICIES:
        params = manifest["policy_params"][policy]
        assert params["entry_open_offset_min"] == 5
        assert params["entry_close_cutoff_min"] == 30
    assert manifest["policy_params"][POLICY_OPENING_RANGE_BREAKOUT]["opening_range_minutes"] == 30
    assert manifest["policy_params"][POLICY_PULLBACK_TO_REF]["pullback_pct"] == pytest.approx(0.003)


# ===========================================================================
# normalize_ticks — session / causality / freshness rules (reuse #216)
# ===========================================================================
def test_normalize_sorts_ascending_and_keeps_priceable_in_session():
    raw = [
        _tick("AAA", 11, 0, 101.0),
        _tick("AAA", 10, 0, 100.0),  # earlier — must sort first
    ]
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    assert [t.mid for t in ticks] == [100.0, 101.0]


def test_normalize_drops_out_of_session_ticks():
    raw = [
        _tick("AAA", 9, 15, 99.0),   # before 09:30 open — dropped
        _tick("AAA", 10, 0, 100.0),  # in session — kept
        _tick("AAA", 16, 30, 105.0),  # after 16:00 close — dropped
    ]
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    assert [t.mid for t in ticks] == [100.0]


def test_normalize_drops_stale_quotes_beyond_hard_threshold():
    fresh = _tick("AAA", 10, 0, 100.0)
    # quote_ts 20s older than the sample ts => age 20s > 15s hard-skip => dropped
    stale = {
        "date": DATE,
        "ticker": "AAA",
        "mid": 100.5,
        "tick_time": _et(10, 30, 20),
        "ts": _et(10, 30, 20),
        "quote_ts": _et(10, 30, 0),
    }
    ticks = normalize_ticks([fresh, stale], ticker="AAA", date=DATE)
    assert [t.mid for t in ticks] == [100.0]


def test_normalize_skips_unpriceable_and_derives_mid_from_bid_ask():
    rows = [
        {"date": DATE, "ticker": "AAA", "tick_time": _et(10, 0), "ts": _et(10, 0),
         "quote_ts": _et(10, 0)},  # no mid/bid/ask/last — unpriceable, skipped
        {"date": DATE, "ticker": "AAA", "bid": 99.0, "ask": 101.0,
         "tick_time": _et(10, 5), "ts": _et(10, 5), "quote_ts": _et(10, 5)},
    ]
    ticks = normalize_ticks(rows, ticker="AAA", date=DATE)
    assert len(ticks) == 1
    assert ticks[0].mid == pytest.approx(100.0)  # (99+101)/2


def test_normalize_filters_by_ticker_and_date():
    raw = [
        _tick("AAA", 10, 0, 100.0),
        _tick("BBB", 10, 0, 200.0),
        {**_tick("AAA", 10, 0, 100.0), "date": "2026-06-29"},
    ]
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    assert [t.ticker for t in ticks] == ["AAA"]
    assert len(ticks) == 1


# ===========================================================================
# policy: immediate_first_eligible_tick
# ===========================================================================
def test_immediate_picks_first_eligible_not_later_favorable():
    # First eligible tick is 100.0 at 10:00; a later, cheaper 98.0 at 11:00 exists.
    raw = _series("AAA", [(10, 0, 100.0), (11, 0, 98.0)])
    name = AdmittedName(date=DATE, ticker="AAA")
    row = _outcome(evaluate_name(name, normalize_ticks(raw, ticker="AAA", date=DATE)), POLICY_IMMEDIATE)
    assert row["eligible"] is True
    # AS-OF: the FIRST eligible tick is chosen, never the later cheaper one.
    assert row["entry_ref_quote"] == 100.0
    assert row["entry_tick_time"] == _et(10, 0)


def test_immediate_excludes_open_and_close_windows():
    # 09:33 is inside the first 5 min (excluded); 15:45 is inside the last 30 min
    # (excluded); 10:00 is the first eligible.
    raw = _series("AAA", [(9, 33, 100.0), (10, 0, 101.0), (15, 45, 102.0)])
    name = AdmittedName(date=DATE, ticker="AAA")
    row = _outcome(evaluate_name(name, normalize_ticks(raw, ticker="AAA", date=DATE)), POLICY_IMMEDIATE)
    assert row["entry_tick_time"] == _et(10, 0)


def test_immediate_respects_conviction_time():
    raw = _series("AAA", [(10, 0, 100.0), (11, 0, 101.0)])
    # conviction only at 10:30 => the 10:00 tick is ineligible; 11:00 is first eligible.
    name = AdmittedName(date=DATE, ticker="AAA", conviction_time=_et(10, 30))
    row = _outcome(evaluate_name(name, normalize_ticks(raw, ticker="AAA", date=DATE)), POLICY_IMMEDIATE)
    assert row["entry_tick_time"] == _et(11, 0)


def test_immediate_censored_when_no_eligible_tick():
    # Only ticks are inside the excluded open window.
    raw = _series("AAA", [(9, 31, 100.0), (9, 34, 101.0)])
    name = AdmittedName(date=DATE, ticker="AAA")
    row = _outcome(evaluate_name(name, normalize_ticks(raw, ticker="AAA", date=DATE)), POLICY_IMMEDIATE)
    assert row["eligible"] is False
    assert row["entry_tick_time"] is None
    assert row["entry_ref_quote"] is None
    assert row["censored_reason"] == "no_eligible_tick"


# ===========================================================================
# policy: vwap_cross
# ===========================================================================
def test_vwap_cross_picks_first_bullish_cross_up():
    # Falling below the running mean then crossing above it.
    raw = _series("AAA", [(10, 0, 100.0), (10, 12, 98.0), (10, 24, 99.0), (10, 36, 103.0)])
    name = AdmittedName(date=DATE, ticker="AAA")
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    row = _outcome(evaluate_name(name, ticks), POLICY_VWAP_CROSS)
    assert row["eligible"] is True
    # The 10:36 tick (103) is the first to exceed the running VWAP after dipping below.
    assert row["entry_tick_time"] == _et(10, 36)


def test_vwap_cross_is_as_of_not_the_highest_later_tick():
    raw = _series("AAA", [(10, 0, 100.0), (10, 12, 98.0), (10, 24, 101.0), (10, 36, 120.0)])
    name = AdmittedName(date=DATE, ticker="AAA")
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    row = _outcome(evaluate_name(name, ticks), POLICY_VWAP_CROSS)
    # First cross-up is at 10:24 (101 > running vwap), NOT the later, higher 120 tick.
    assert row["entry_tick_time"] == _et(10, 24)
    assert row["entry_ref_quote"] == 101.0


def test_vwap_cross_censored_when_monotone_down():
    raw = _series("AAA", [(10, 0, 100.0), (10, 12, 99.0), (10, 24, 98.0)])
    name = AdmittedName(date=DATE, ticker="AAA")
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    row = _outcome(evaluate_name(name, ticks), POLICY_VWAP_CROSS)
    assert row["eligible"] is False
    assert row["censored_reason"] == "no_vwap_cross"


# ===========================================================================
# policy: opening_range_breakout
# ===========================================================================
def test_orb_picks_first_break_above_opening_range_high():
    # Opening range [09:30, 10:00): high = 101. Breakout is first tick > 101 after 10:00.
    raw = _series("AAA", [(9, 40, 100.0), (9, 50, 101.0), (10, 5, 100.5), (10, 20, 102.0), (10, 40, 103.0)])
    name = AdmittedName(date=DATE, ticker="AAA")
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    row = _outcome(evaluate_name(name, ticks), POLICY_OPENING_RANGE_BREAKOUT)
    assert row["eligible"] is True
    # 10:05 (100.5) does NOT clear 101; 10:20 (102) is the first breakout — not the later 103.
    assert row["entry_tick_time"] == _et(10, 20)
    assert row["entry_ref_quote"] == 102.0


def test_orb_never_enters_inside_the_opening_range_window():
    # A high tick INSIDE the opening range is the range itself, not a breakout entry.
    raw = _series("AAA", [(9, 40, 100.0), (9, 55, 105.0), (10, 30, 104.0)])
    name = AdmittedName(date=DATE, ticker="AAA")
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    row = _outcome(evaluate_name(name, ticks), POLICY_OPENING_RANGE_BREAKOUT)
    # OR high = 105; nothing after 10:00 exceeds it => censored.
    assert row["eligible"] is False
    assert row["censored_reason"] == "no_breakout"


def test_orb_censored_when_no_opening_range_ticks():
    # Feed only starts after the opening-range window closes.
    raw = _series("AAA", [(10, 30, 100.0), (11, 0, 105.0)])
    name = AdmittedName(date=DATE, ticker="AAA")
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    row = _outcome(evaluate_name(name, ticks), POLICY_OPENING_RANGE_BREAKOUT)
    assert row["eligible"] is False
    assert row["censored_reason"] == "no_opening_range"


# ===========================================================================
# policy: pullback_to_ref
# ===========================================================================
def test_pullback_uses_batch_ref_and_picks_first_dip():
    # batch_ref = 100; threshold = 100 * (1 - 0.003) = 99.7. First tick <= 99.7 wins.
    raw = _series("AAA", [(10, 0, 100.0), (10, 12, 99.6), (10, 24, 99.0)])
    name = AdmittedName(date=DATE, ticker="AAA")
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    row = _outcome(evaluate_name(name, ticks, batch_ref=100.0), POLICY_PULLBACK_TO_REF)
    assert row["eligible"] is True
    # First dip below threshold is 10:12 (99.6), NOT the deeper later 99.0.
    assert row["entry_tick_time"] == _et(10, 12)
    assert row["entry_ref_quote"] == 99.6
    assert row["batch_ref"] == 100.0


def test_pullback_falls_back_to_first_tick_mid_without_batch_ref():
    # No batch_ref => reference is the first tick mid (100). threshold 99.7.
    raw = _series("AAA", [(10, 0, 100.0), (10, 12, 99.5)])
    name = AdmittedName(date=DATE, ticker="AAA")
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    row = _outcome(evaluate_name(name, ticks), POLICY_PULLBACK_TO_REF)
    assert row["eligible"] is True
    assert row["entry_tick_time"] == _et(10, 12)


def test_pullback_censored_when_never_dips():
    raw = _series("AAA", [(10, 0, 100.0), (10, 12, 100.5), (10, 24, 101.0)])
    name = AdmittedName(date=DATE, ticker="AAA")
    ticks = normalize_ticks(raw, ticker="AAA", date=DATE)
    row = _outcome(evaluate_name(name, ticks, batch_ref=100.0), POLICY_PULLBACK_TO_REF)
    assert row["eligible"] is False
    assert row["censored_reason"] == "no_pullback"


# ===========================================================================
# record shape — raw refs only, NO shortfall / fill / verdict
# ===========================================================================
def test_record_has_required_keys_and_no_fill_quality():
    raw = _series("AAA", [(10, 0, 100.0)])
    name = AdmittedName(date=DATE, ticker="AAA", signal_version="run-123")
    rows = evaluate_name(name, normalize_ticks(raw, ticker="AAA", date=DATE))
    row = _outcome(rows, POLICY_IMMEDIATE)
    for key in ("date", "ticker", "policy", "entry_tick_time", "entry_ref_quote",
                "eligible", "censored_reason"):
        assert key in row
    # provenance / observe-only markers
    assert row["observe_only"] is True
    assert row["places_orders"] is False
    assert row["config_fingerprint"] == DEFAULT_CONFIG.fingerprint()
    assert row["signal_version"] == "run-123"
    # NO execution-quality / verdict fields leak in.
    forbidden = {"shortfall", "implementation_shortfall", "fill", "fill_price",
                 "pnl", "slippage", "pass", "fail", "verdict", "non_inferiority", "bps"}
    assert forbidden.isdisjoint(row.keys())


def test_evaluate_name_emits_one_row_per_registered_policy():
    raw = _series("AAA", [(10, 0, 100.0)])
    rows = evaluate_name(AdmittedName(date=DATE, ticker="AAA"),
                         normalize_ticks(raw, ticker="AAA", date=DATE))
    assert sorted(r["policy"] for r in rows) == sorted(REGISTERED_POLICIES)


def test_evaluate_session_all_censored_when_no_ticks():
    # No feed for the name => every policy censors (recorded, not imputed).
    rows = evaluate_session([AdmittedName(date=DATE, ticker="AAA")], [])
    assert len(rows) == len(REGISTERED_POLICIES)
    assert all(r["eligible"] is False for r in rows)
    assert all(r["entry_ref_quote"] is None for r in rows)
    assert all(r["censored_reason"] for r in rows)


def test_evaluation_is_deterministic_repeatable():
    raw = _series("AAA", [(10, 0, 100.0), (10, 12, 99.0)])
    a = evaluate_session([AdmittedName(date=DATE, ticker="AAA")], raw)
    b = evaluate_session([AdmittedName(date=DATE, ticker="AAA")], raw)
    assert a == b


# ===========================================================================
# summarize — counts only, no verdict/comparison
# ===========================================================================
def test_summarize_counts_eligible_and_censored_only():
    raw = _series("AAA", [(10, 0, 100.0)])  # immediate eligible; others censor
    rows = evaluate_session([AdmittedName(date=DATE, ticker="AAA")], raw)
    summary = summarize(rows)
    assert summary["n_rows"] == len(REGISTERED_POLICIES)
    assert summary["n_names"] == 1
    assert summary["per_policy"][POLICY_IMMEDIATE]["n_eligible"] == 1
    assert summary["per_policy"][POLICY_VWAP_CROSS]["n_censored"] == 1
    # no execution-quality aggregate leaks into the summary
    assert "shortfall" not in summary and "verdict" not in summary


# ===========================================================================
# idempotent JSONL append
# ===========================================================================
def test_append_is_idempotent(tmp_path: Path):
    out = tmp_path / "logs" / "renquant105_pilot" / "entry_timing_shadow.jsonl"
    raw = _series("AAA", [(10, 0, 100.0)])
    rows = evaluate_session([AdmittedName(date=DATE, ticker="AAA")], raw)

    first = append_records(out, rows)
    assert first == len(REGISTERED_POLICIES)
    # re-appending the same rows writes nothing new (dedup on (date,ticker,policy))
    second = append_records(out, rows)
    assert second == 0

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(REGISTERED_POLICIES)
    keys = {record_key(json.loads(ln)) for ln in lines}
    assert len(keys) == len(REGISTERED_POLICIES)


def test_append_adds_new_names_without_duplicating(tmp_path: Path):
    out = tmp_path / "entry_timing_shadow.jsonl"
    raw = _series("AAA", [(10, 0, 100.0)])
    append_records(out, evaluate_session([AdmittedName(date=DATE, ticker="AAA")], raw))
    # a new ticker's rows append; AAA's do not duplicate
    raw2 = _series("BBB", [(10, 0, 50.0)]) + raw
    added = append_records(
        out,
        evaluate_session(
            [AdmittedName(date=DATE, ticker="AAA"), AdmittedName(date=DATE, ticker="BBB")],
            raw2,
        ),
    )
    assert added == len(REGISTERED_POLICIES)  # only BBB's rows are new
    assert existing_keys(out) == {
        (DATE, tk, p) for tk in ("AAA", "BBB") for p in REGISTERED_POLICIES
    }


# ===========================================================================
# no-order invariant — the module holds NO order-placement surface
# ===========================================================================
def test_no_order_placement_surface_in_module():
    src = Path(ets.__file__).read_text(encoding="utf-8")
    lowered = src.lower()
    forbidden = [
        "submit_order", "place_order", "tradingclient", "trading_client",
        "create_order", "market_order", "limit_order", "broker.", ".buy(",
        ".sell(", "cancel_order",
    ]
    hits = [tok for tok in forbidden if tok in lowered]
    assert not hits, f"observe-only module must hold no order surface, found: {hits}"


def test_every_record_marks_observe_only_no_orders():
    raw = _series("AAA", [(10, 0, 100.0)])
    rows = evaluate_session([AdmittedName(date=DATE, ticker="AAA")], raw)
    assert rows and all(r["observe_only"] is True for r in rows)
    assert all(r["places_orders"] is False for r in rows)


# ===========================================================================
# read-only loaders + end-to-end collect (no writes)
# ===========================================================================
def test_load_tick_records_filters_by_date_and_missing_file(tmp_path: Path):
    src = tmp_path / "intraday_ticks.jsonl"
    assert load_tick_records(src, DATE) == []  # missing file -> []
    src.write_text(
        json.dumps(_tick("AAA", 10, 0, 100.0)) + "\n"
        + json.dumps({**_tick("AAA", 10, 0, 100.0), "date": "2026-06-29"}) + "\n",
        encoding="utf-8",
    )
    recs = load_tick_records(src, DATE)
    assert len(recs) == 1 and recs[0]["date"] == DATE


def test_load_admitted_from_json_roundtrip(tmp_path: Path):
    p = tmp_path / "admitted.json"
    p.write_text(json.dumps([
        {"date": DATE, "ticker": "AAA"},
        {"date": DATE, "ticker": "BBB", "side": "buy", "signal_version": "run-9",
         "conviction_time": _et(10, 0)},
    ]), encoding="utf-8")
    admitted = load_admitted_from_json(p)
    assert [a.ticker for a in admitted] == ["AAA", "BBB"]
    assert admitted[1].signal_version == "run-9"
    assert admitted[1].conviction_time == _et(10, 0)


def test_collect_end_to_end_reads_feed_writes_nothing(tmp_path: Path):
    src = tmp_path / "intraday_ticks.jsonl"
    src.write_text("\n".join(json.dumps(r) for r in _series("AAA", [(10, 0, 100.0)])) + "\n",
                   encoding="utf-8")
    rows = collect(date=DATE, tick_source=src,
                   admitted=[AdmittedName(date=DATE, ticker="AAA")])
    assert _outcome(rows, POLICY_IMMEDIATE)["eligible"] is True
    # collect() writes nothing — no pilot file created as a side effect.
    assert not (tmp_path / "entry_timing_shadow.jsonl").exists()


def test_collect_missing_feed_yields_all_censored(tmp_path: Path):
    rows = collect(date=DATE, tick_source=tmp_path / "absent.jsonl",
                   admitted=[AdmittedName(date=DATE, ticker="AAA")])
    assert rows and all(r["eligible"] is False for r in rows)


# ===========================================================================
# CLI — observe-only surfaces (pre-registration + dry-run write nothing)
# ===========================================================================
def test_cli_print_preregistration_writes_nothing(capsys):
    rc = ets.main(["--print-preregistration"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["config_fingerprint"] == DEFAULT_CONFIG.fingerprint()
    assert out["policies"] == list(REGISTERED_POLICIES)


def test_cli_dry_run_places_and_writes_nothing(tmp_path: Path, capsys):
    src = tmp_path / "intraday_ticks.jsonl"
    src.write_text("\n".join(json.dumps(r) for r in _series("AAA", [(10, 0, 100.0)])) + "\n",
                   encoding="utf-8")
    out = tmp_path / "pilot.jsonl"
    rc = ets.main(["--date", DATE, "--tick-source", str(src), "--tickers", "AAA",
                   "--out", str(out), "--dry-run", "--json"])
    assert rc == 0
    assert not out.exists()  # dry-run writes nothing
    summary = json.loads(capsys.readouterr().out)
    assert summary["mode"] == "dry-run"
    assert summary["rows_written"] == 0
