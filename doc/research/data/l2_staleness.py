"""Single source of truth for the L2 backtest score-staleness rule (review r1 P2).

THE RULE: a score dated s may drive trading on day t iff 0 < (t - s) <= 7
CALENDAR days. r1 of the record stated the rule three ways (report: 7
calendar days; derivation header: "5 trading days"; code: 7 calendar days).
The code's rule produced the committed CSV, so 7 calendar days is canonical.
Pinned by tests/test_l2_backtest_staleness.py, including a date pair where
the two candidate rules disagree.
"""

STALENESS_CALENDAR_DAYS = 7


def is_fresh(trade_date, score_date):
    """True iff a score dated score_date is usable on trade_date.

    Calendar-day arithmetic only (no exchange calendar). Works for any date
    type whose difference exposes .days (datetime.date, datetime,
    pandas.Timestamp). Same-day scores are never usable: the score must be
    dated <= t-1.
    """
    delta = (trade_date - score_date).days
    return 0 < delta <= STALENESS_CALENDAR_DAYS
