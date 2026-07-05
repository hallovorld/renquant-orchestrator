"""Tests for scripts/s10_open_auction_is.py's sensitivity-analysis helpers.

Codex review (PR #333): the round-1 memo picked one outlier-exclusion
threshold and treated the resulting number as the finding, and silently
dropped 30/67 trades whose run_date fell on a weekend rather than
investigating them. These tests cover the two functions added to make both
choices explicit, EX ANTE parameters instead of post-hoc judgment calls:
``remap_weekend_run_dates`` and ``apply_outlier_exclusion``.
"""
import importlib.util
import os
import sys

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "s10_open_auction_is.py",
)
_spec = importlib.util.spec_from_file_location("s10_open_auction_is", _SCRIPT)
s10 = importlib.util.module_from_spec(_spec)
sys.modules["s10_open_auction_is"] = s10
_spec.loader.exec_module(s10)


def _trade(date, ticker="AAPL", shares=1.0, fill_price=100.0, invest=100.0):
    return s10.Trade(date=date, ticker=ticker, shares=shares, fill_price=fill_price, invest=invest)


def _is_result(is_vs_open_bps, matched=True):
    r = s10.ISResult(trade=_trade("2026-05-01"))
    r.matched = matched
    r.is_vs_open_bps = is_vs_open_bps
    return r


class TestRemapWeekendRunDates:
    def test_saturday_remaps_to_friday(self):
        # 2026-05-16 is a Saturday.
        trades = [_trade("2026-05-16")]
        out = s10.remap_weekend_run_dates(trades)
        assert out[0].date == "2026-05-15"

    def test_sunday_remaps_to_friday(self):
        # 2026-05-17 is a Sunday.
        trades = [_trade("2026-05-17")]
        out = s10.remap_weekend_run_dates(trades)
        assert out[0].date == "2026-05-15"

    def test_weekday_unchanged(self):
        # 2026-05-18 is a Monday.
        trades = [_trade("2026-05-18")]
        out = s10.remap_weekend_run_dates(trades)
        assert out[0].date == "2026-05-18"

    def test_preserves_other_trade_fields(self):
        trades = [_trade("2026-05-16", ticker="MSFT", shares=3.0, fill_price=250.0, invest=750.0)]
        out = s10.remap_weekend_run_dates(trades)
        assert out[0].ticker == "MSFT"
        assert out[0].shares == 3.0
        assert out[0].fill_price == 250.0
        assert out[0].invest == 750.0


class TestApplyOutlierExclusion:
    def test_none_threshold_excludes_nothing(self):
        results = [_is_result(50.0), _is_result(-5000.0)]
        kept, excluded = s10.apply_outlier_exclusion(results, threshold_bps=None)
        assert len(kept) == 2
        assert len(excluded) == 0

    def test_exceeding_threshold_excluded(self):
        results = [_is_result(50.0), _is_result(-5000.0)]
        kept, excluded = s10.apply_outlier_exclusion(results, threshold_bps=1000.0)
        assert len(kept) == 1
        assert len(excluded) == 1
        assert excluded[0].is_vs_open_bps == -5000.0

    def test_threshold_is_symmetric_absolute_value(self):
        results = [_is_result(1500.0), _is_result(-1500.0), _is_result(500.0)]
        kept, excluded = s10.apply_outlier_exclusion(results, threshold_bps=1000.0)
        assert len(kept) == 1
        assert len(excluded) == 2

    def test_unmatched_trades_never_excluded(self):
        results = [_is_result(None, matched=False)]
        kept, excluded = s10.apply_outlier_exclusion(results, threshold_bps=100.0)
        assert len(kept) == 1
        assert len(excluded) == 0

    def test_exactly_at_threshold_not_excluded(self):
        results = [_is_result(1000.0)]
        kept, excluded = s10.apply_outlier_exclusion(results, threshold_bps=1000.0)
        assert len(kept) == 1
        assert len(excluded) == 0
