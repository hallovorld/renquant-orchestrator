"""Tests for the shadow analyst-panel builder — an_rev3 derivation (point-in-time)
and the row-count-preserving merge."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "bsap", Path(__file__).resolve().parent.parent / "scripts" / "build_shadow_analyst_panel.py")
bsap = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bsap)


def _grades(ticker: str, dates, strong_buy):
    """grades-historical rows with only StrongBuy varying → consensus moves with it."""
    return pd.DataFrame({
        "ticker": ticker,
        "date": pd.to_datetime(dates),
        "analystRatingsStrongBuy": strong_buy,
        "analystRatingsBuy": 0, "analystRatingsHold": 0,
        "analystRatingsSell": 0, "analystRatingsStrongSell": 0,
    })


def test_an_rev3_is_three_month_consensus_change(tmp_path):
    # consensus = (2*SB)/SB = 2.0 whenever SB>0 (all other buckets 0) → constant 2.0,
    # so a pure-StrongBuy series has an_rev3 == 0 once the count is positive throughout.
    g = _grades("AAA", pd.date_range("2020-01-01", periods=6, freq="MS"), [3, 4, 5, 6, 7, 8])
    p = tmp_path / "g.parquet"; g.to_parquet(p, index=False)
    rev = bsap.build_an_rev3(p)
    assert set(rev.columns) == {"ticker", "date", "an_rev3"}
    assert (rev["an_rev3"].abs() < 1e-9).all()        # consensus constant → revision 0
    assert rev["an_rev3"].notna().all()               # first 3 (NaN diff) are dropped


def test_an_rev3_moves_when_mix_shifts(tmp_path):
    # shift from all-StrongSell (consensus -2) to all-StrongBuy (consensus +2) → rev3 > 0
    rows = pd.concat([
        _grades("BBB", ["2020-01-01", "2020-02-01", "2020-03-01"], [0, 0, 0]).assign(
            analystRatingsStrongSell=5),
        _grades("BBB", ["2020-04-01"], [5]),
    ], ignore_index=True)
    p = tmp_path / "g.parquet"; rows.to_parquet(p, index=False)
    rev = bsap.build_an_rev3(p)
    apr = rev[rev["date"] == pd.Timestamp("2020-04-01")]["an_rev3"].iloc[0]
    assert apr > 0                                     # consensus rose (−2 → +2)


def test_merge_preserves_rows_and_is_backward(tmp_path):
    panel = pd.DataFrame({
        "ticker": ["AAA"] * 4,
        "date": pd.to_datetime(["2020-01-15", "2020-02-15", "2020-03-15", "2020-04-15"]),
        "KMID": [0.1, 0.2, 0.3, 0.4], "fwd_60d_excess": [0.0, 0.0, 0.0, 0.0],
    })
    rev = pd.DataFrame({"ticker": ["AAA", "AAA"],
                        "date": pd.to_datetime(["2020-02-01", "2020-04-01"]),
                        "an_rev3": [0.5, 0.9]})
    out = bsap.merge_panel(panel, rev)
    assert len(out) == len(panel)                     # row count preserved
    assert "an_rev3" in out.columns
    s = out.sort_values("date").set_index("date")["an_rev3"]
    assert pd.isna(s.loc["2020-01-15"])               # before first revision → NaN
    assert s.loc["2020-02-15"] == 0.5                 # backward as-of (2020-02-01)
    assert s.loc["2020-03-15"] == 0.5                 # still the Feb value (no newer yet)
    assert s.loc["2020-04-15"] == 0.9                 # picks up Apr revision
