"""Campaign B5 lockstep tests: every former hand-copied NYSE-session
implementation in this repo is now the ONE canonical
``renquant_common.market_calendar`` (audit #296 §4.1 / XC-2).

Two lockstep styles per the campaign method:

* SAME-OBJECT — the re-exported names ARE the canonical objects (identity),
  so they cannot drift by construction.
* GOLDEN-VECTOR — thin delegating adapters (kept as named seams / for their
  repo-local error contracts) return byte-identical results to the canonical
  on real-calendar vectors including weekend/holiday/half-day cases.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
sys.path.insert(0, os.path.join(REPO_ROOT, "ops", "renquant105"))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from renquant_common import market_calendar as mc  # noqa: E402

from renquant_orchestrator import intraday_quote_logger as iql  # noqa: E402
from renquant_orchestrator import intraday_session_inputs as isi  # noqa: E402
from renquant_orchestrator import retrain_alpha158_fund as retrain  # noqa: E402

import batch_scores_bundle as bundle  # noqa: E402
import kpi_scorecard as kpi  # noqa: E402


# ---------------------------------------------------------------------------
# Same-object: the quote-logger primitive IS the canonical
# ---------------------------------------------------------------------------
def test_quote_logger_reexports_are_the_canonical_objects() -> None:
    assert iql.NyseSessionCalendar is mc.NyseSessionCalendar
    assert iql.SessionBounds is mc.SessionBounds
    assert iql.SessionCalendar is mc.SessionCalendar
    assert iql.default_session_calendar is mc.default_session_calendar


# ---------------------------------------------------------------------------
# Golden-vector: retrain freshness guard == canonical
# ---------------------------------------------------------------------------
def test_retrain_last_completed_session_lockstep() -> None:
    vectors = [
        ("2025-11-25 14:00", dt.date(2025, 11, 24)),  # intra-session -> prior
        ("2025-11-25 16:30", dt.date(2025, 11, 25)),  # after close -> today
        ("2025-11-28 14:00", dt.date(2025, 11, 28)),  # half-day close passed
        ("2025-11-28 12:00", dt.date(2025, 11, 26)),  # half-day open (Thu hol)
        ("2026-06-28 09:00", dt.date(2026, 6, 26)),   # Sunday -> Friday
    ]
    for now, expected in vectors:
        ts = pd.Timestamp(now, tz="America/New_York")
        got = retrain._expected_last_completed_session("NYSE", ts)
        assert got == expected
        assert got == mc.last_completed_session(ts)


def test_retrain_session_gap_lockstep() -> None:
    pairs = [
        (dt.date(2026, 6, 22), dt.date(2026, 6, 29)),
        (dt.date(2026, 6, 30), dt.date(2026, 6, 30)),
        (dt.date(2026, 7, 2), dt.date(2026, 7, 6)),   # Jul-4-observed + weekend
        (dt.date(2026, 11, 25), dt.date(2026, 11, 30)),  # Thanksgiving + half day
    ]
    for start, end in pairs:
        expected = (
            0
            if start >= end
            else len(mc.sessions_between(start + dt.timedelta(days=1), end))
        )
        assert retrain._default_session_gap("NYSE", start, end) == expected


# ---------------------------------------------------------------------------
# Golden-vector: rq105 bundle previous-session == canonical
# ---------------------------------------------------------------------------
def test_bundle_expected_previous_session_lockstep() -> None:
    for day in ("2026-07-02", "2026-06-29", "2026-07-06", "2025-11-28"):
        assert bundle.expected_previous_session(day) == mc.previous_session(day).isoformat()


def test_bundle_expected_previous_session_fail_closed() -> None:
    with pytest.raises(ValueError, match="fail-closed"):
        bundle.expected_previous_session("2026-07-06", lookback_days=1)


# ---------------------------------------------------------------------------
# Golden-vector: session-inputs day-walk == canonical (and error contract)
# ---------------------------------------------------------------------------
def test_session_inputs_previous_session_lockstep() -> None:
    cal = mc.default_session_calendar()
    for day in ("2026-07-06", "2026-07-01", "2026-06-28"):
        assert isi.previous_session(cal, day) == mc.previous_session(day).isoformat()


def test_session_inputs_previous_session_raises_frozen_signal_error() -> None:
    class NeverOpen:
        name = "FAKE"

        def session_bounds(self, day):  # noqa: ANN001, ANN202
            return None

    with pytest.raises(isi.FrozenSignalError, match="no exchange session"):
        isi.previous_session(NeverOpen(), "2026-07-06", max_lookback_days=3)


# ---------------------------------------------------------------------------
# Golden-vector: kpi scorecard session keys == canonical
# ---------------------------------------------------------------------------
def test_kpi_ledger_session_keys_lockstep() -> None:
    dates = pd.Series(
        ["2026-04-10", "2026-04-11", "2026-04-12", "2026-04-13", "2026-07-03"]
    )
    keys, kind = kpi._ledger_session_keys(dates)
    assert kind == "nyse"
    expected = mc.session_keys(dates)
    assert list(keys) == list(expected)
    # Weekend rows share Friday's session; the holiday Friday rolls back.
    assert keys.iloc[1] == keys.iloc[0] == pd.Timestamp("2026-04-10")
    assert keys.iloc[4] == pd.Timestamp("2026-07-02")


# ---------------------------------------------------------------------------
# No hand-copied calendar remains in this repo (grep-level ratchet)
# ---------------------------------------------------------------------------
def test_no_direct_mcal_import_remains() -> None:
    """Production code must consume renquant_common.market_calendar, never
    construct its own pandas_market_calendars calendar. After B5 there are
    ZERO direct imports in this repo (the XNYS ``exchange_calendars``
    research scripts — audit §4.1 row 8 — use a different package and stay
    note-only)."""
    offenders = []
    for sub in ("src", "scripts", "ops"):
        for root, _dirs, files in os.walk(os.path.join(REPO_ROOT, sub)):
            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(root, f)
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                if "import pandas_market_calendars" in text:
                    offenders.append(os.path.relpath(path, REPO_ROOT))
    assert offenders == [], (
        f"hand-rolled market-calendar use crept back in: {offenders}; "
        f"import renquant_common.market_calendar instead (campaign B5)"
    )
