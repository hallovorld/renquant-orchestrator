"""The L2 backtest staleness rule is SINGULAR: 7 CALENDAR days. AUDIT
REGRESSION GUARD for review r1 P2 on orch#926.

r1 of the backtest record stated the rule three ways (report: <= 7 calendar
days; derivation header: "<= 5 trading days"; code: <= 7 calendar days). The
committed CSV was produced by the code's rule, so the calendar rule is
canonical, single-sourced in doc/research/data/l2_staleness.py. This test
pins it, including a date pair where the two candidate rules disagree.
"""
import datetime as dt
import importlib.util
from pathlib import Path

_MOD = Path(__file__).resolve().parents[1] / 'doc' / 'research' / 'data' / 'l2_staleness.py'
_spec = importlib.util.spec_from_file_location('l2_staleness', _MOD)
l2_staleness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(l2_staleness)


class TestL2StalenessRegressionGuard:
    def test_constant_is_seven_calendar_days(self):
        assert l2_staleness.STALENESS_CALENDAR_DAYS == 7

    def test_fresh_through_seven_calendar_days(self):
        score = dt.date(2026, 6, 1)
        for gap in range(1, 8):
            assert l2_staleness.is_fresh(score + dt.timedelta(days=gap), score)

    def test_stale_at_eight_calendar_days(self):
        score = dt.date(2026, 6, 1)
        assert not l2_staleness.is_fresh(score + dt.timedelta(days=8), score)

    def test_same_day_score_not_usable(self):
        d = dt.date(2026, 6, 1)
        assert not l2_staleness.is_fresh(d, d)

    def test_calendar_rule_not_trading_day_rule(self):
        # 2026-07-01 (Wed) -> 2026-07-09 (Thu) is 8 calendar days but only 5
        # trading days (July 3 was the observed Independence Day holiday). A
        # "<= 5 trading days" rule would accept this pair; the singular
        # 7-calendar-day rule rejects it.
        assert not l2_staleness.is_fresh(dt.date(2026, 7, 9), dt.date(2026, 7, 1))
