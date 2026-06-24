"""Tests for scripts/data_freshness_audit.py."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "data_freshness_audit",
    Path(__file__).resolve().parent.parent / "scripts" / "data_freshness_audit.py",
)
dfa = importlib.util.module_from_spec(_SPEC)
# Register before exec so dataclass annotation resolution can find the module.
sys.modules[_SPEC.name] = dfa
_SPEC.loader.exec_module(dfa)


# ── classify() ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lag,exp", [
    (0, dfa.FRESH), (3, dfa.FRESH),
    (4, dfa.STALE), (44, dfa.STALE),
    (45, dfa.CRITICAL), (200, dfa.CRITICAL),
    (None, dfa.UNKNOWN),
])
def test_classify_boundaries(lag, exp):
    # warn at 4, critical at 45 (mirrors the fundamentals thresholds)
    assert dfa.classify(lag, warn_days=4, critical_days=45) == exp


def test_classify_warn_equals_critical_prefers_critical():
    assert dfa.classify(10, warn_days=10, critical_days=10) == dfa.CRITICAL


# ── lag_in_days() ─────────────────────────────────────────────────────────
def test_lag_in_days_basic():
    assert dfa.lag_in_days(date(2026, 6, 20), date(2026, 6, 23)) == 3


def test_lag_in_days_future_clamped_to_zero():
    assert dfa.lag_in_days(date(2026, 6, 25), date(2026, 6, 23)) == 0


def test_lag_in_days_none():
    assert dfa.lag_in_days(None, date(2026, 6, 23)) is None


# ── summarize() worst-status escalation ───────────────────────────────────
def test_summarize_reports_worst_status_icon():
    results = [
        dfa.FreshnessResult("ohlcv", dfa.FRESH, 0, "2026-06-23"),
        dfa.FreshnessResult("fundamentals", dfa.CRITICAL, 91, "2026-03-24"),
    ]
    line = dfa.summarize(results)
    assert line.startswith("DATA FRESHNESS " + dfa._ICON[dfa.CRITICAL])
    assert "ohlcv" in line and "fundamentals" in line
    assert "91d" in line


def test_summarize_all_fresh():
    results = [dfa.FreshnessResult("ohlcv", dfa.FRESH, 1, "2026-06-22")]
    assert dfa.summarize(results).startswith("DATA FRESHNESS " + dfa._ICON[dfa.FRESH])


# ── audit() end-to-end against a tiny temp repo ───────────────────────────
def _write_ohlcv(repo: Path, ticker: str, last: date):
    d = repo / "data" / "ohlcv" / ticker
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"date": pd.to_datetime([last]), "close": [100.0]})
    df.to_parquet(d / "1d.parquet", index=False)


def _write_fundamentals(repo: Path, last: date, complete: bool):
    d = repo / "data"
    d.mkdir(parents=True, exist_ok=True)
    row = {"ticker": "AAPL", "date": pd.Timestamp(last),
           "earnings_yield": 0.05, "book_to_price": 0.1,
           "gross_profitability": 0.3, "roe": 0.2,
           "asset_growth": 0.1 if complete else None}
    pd.DataFrame([row]).to_parquet(d / "sec_fundamentals_daily.parquet", index=False)


def test_audit_flags_stale_fundamentals(tmp_path):
    today = date(2026, 6, 23)
    _write_ohlcv(tmp_path, "AAPL", today)
    _write_fundamentals(tmp_path, date(2026, 3, 24), complete=True)
    results = {r.key: r for r in dfa.audit(tmp_path, today, tickers=["AAPL"])}
    assert results["ohlcv"].status == dfa.FRESH
    assert results["ohlcv"].lag_days == 0
    assert results["fundamentals"].status == dfa.CRITICAL
    assert results["fundamentals"].lag_days == 91


def test_audit_missing_source_is_unknown_not_crash(tmp_path):
    # No files at all → every source degrades to UNKNOWN, no exception.
    results = {r.key: r for r in dfa.audit(tmp_path, date(2026, 6, 23))}
    assert results["ohlcv"].status == dfa.UNKNOWN
    assert results["fundamentals"].status == dfa.UNKNOWN


def test_audit_fundamentals_completeness_note(tmp_path):
    _write_fundamentals(tmp_path, date(2026, 6, 23), complete=False)
    results = {r.key: r for r in dfa.audit(tmp_path, date(2026, 6, 23), tickers=["AAPL"])}
    # 0/1 complete because asset_growth is NaN
    assert "0/1" in results["fundamentals"].note


def test_per_ticker_source_uses_oldest_latest_date_not_newest(tmp_path):
    today = date(2026, 6, 23)
    _write_ohlcv(tmp_path, "AAPL", today)
    _write_ohlcv(tmp_path, "MSFT", date(2026, 6, 10))
    results = {r.key: r for r in dfa.audit(tmp_path, today, tickers=["AAPL", "MSFT"])}
    assert results["ohlcv"].status == dfa.CRITICAL
    assert results["ohlcv"].lag_days == 13
    assert results["ohlcv"].last_date == "2026-06-10"
    assert results["ohlcv"].detail["oldest_latest"] == "2026-06-10"
    assert results["ohlcv"].detail["newest_latest"] == "2026-06-23"


def _write_sentiment(repo: Path, ticker: str, last: date):
    d = repo / "data" / "news_sentiment_alpaca"
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"date": pd.to_datetime([last]), "sentiment": [0.1]})
    df.to_parquet(d / f"{ticker}.parquet", index=False)


def test_sentiment_freshness_uses_feed_ingestion_newest_not_quiet_ticker(tmp_path):
    # A quiet-but-valid ticker (old news) must NOT false-RED the feed when the
    # feed is demonstrably alive (another ticker has fresh news).
    today = date(2026, 6, 23)
    _write_sentiment(tmp_path, "AAPL", today)            # feed alive today
    _write_sentiment(tmp_path, "MSFT", date(2026, 5, 1))  # simply quiet
    results = {r.key: r for r in dfa.audit(tmp_path, today, tickers=["AAPL", "MSFT"])}
    assert results["sentiment"].status == dfa.FRESH
    assert results["sentiment"].lag_days == 0
    assert results["sentiment"].detail["freshness_basis"] == "newest"
    # the quiet ticker is still visible in the detail, just not failing
    assert results["sentiment"].detail["oldest_latest"] == "2026-05-01"


def test_sentiment_stale_feed_is_flagged_when_even_newest_is_old(tmp_path):
    # If even the freshest ticker is old, the feed itself is stale → flagged.
    today = date(2026, 6, 23)
    _write_sentiment(tmp_path, "AAPL", date(2026, 5, 1))
    _write_sentiment(tmp_path, "MSFT", date(2026, 4, 1))
    results = {r.key: r for r in dfa.audit(tmp_path, today, tickers=["AAPL", "MSFT"])}
    assert results["sentiment"].status == dfa.CRITICAL  # 53d > 10d critical
    assert results["sentiment"].last_date == "2026-05-01"


def test_sentiment_missing_coverage_downgrades_from_fresh(tmp_path):
    # Feed is fresh for present tickers, but an active name has no file at all →
    # coverage gap downgrades FRESH → STALE (not a silent green).
    today = date(2026, 6, 23)
    _write_sentiment(tmp_path, "AAPL", today)
    results = {r.key: r for r in dfa.audit(tmp_path, today, tickers=["AAPL", "MSFT"])}
    assert results["sentiment"].status == dfa.STALE
    assert results["sentiment"].detail["missing_count"] == 1


def test_per_ticker_source_surfaces_partial_missing_coverage(tmp_path):
    today = date(2026, 6, 23)
    _write_ohlcv(tmp_path, "AAPL", today)
    results = {r.key: r for r in dfa.audit(tmp_path, today, tickers=["AAPL", "MSFT"])}
    assert results["ohlcv"].status == dfa.STALE
    assert results["ohlcv"].detail["missing_count"] == 1
    assert "MSFT" in results["ohlcv"].detail["missing_tickers"]


def test_load_watchlist_reads_strategy_config(tmp_path):
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text('{"watchlist": ["msft", "AAPL", "AAPL"]}', encoding="utf-8")
    assert dfa.load_watchlist(tmp_path, cfg) == ["AAPL", "MSFT"]


# ── --fail-on-critical exit code ──────────────────────────────────────────
def test_main_fail_on_critical_exit_code(tmp_path, capsys):
    _write_fundamentals(tmp_path, date(2026, 3, 24), complete=True)
    rc = dfa.main(["--repo-dir", str(tmp_path), "--fail-on-critical", "--summary-only"])
    assert rc == 2


def test_main_default_exit_zero_even_when_critical(tmp_path):
    _write_fundamentals(tmp_path, date(2026, 3, 24), complete=True)
    rc = dfa.main(["--repo-dir", str(tmp_path), "--summary-only"])
    assert rc == 0


def test_main_fail_on_unknown_exit_code(tmp_path):
    rc = dfa.main(["--repo-dir", str(tmp_path), "--fail-on-unknown", "--summary-only"])
    assert rc == 3
