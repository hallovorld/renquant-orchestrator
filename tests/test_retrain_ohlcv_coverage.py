"""Tests for the full-universe OHLCV refresh + partial-freeze guard.

These cover the load-bearing model-staleness root cause: the panel training
universe (tier_A + tier_B, ~292 tickers) is half-frozen because only the
~142-ticker live watchlist gets fresh daily bars. The refresh task must iterate
the FULL panel universe (not just the watchlist), a single ticker's failure /
delisting must not abort the retrain, and the guard must fire when more than a
configurable fraction of the panel universe is stale while staying quiet at the
expected fwd_60d frontier.

All fetch / freshness IO is mocked or uses tmp fixtures — no real network fetch
and no production data write ever happens here.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest

from renquant_orchestrator import retrain_alpha158_fund as mod


def _ohlcv(end: dt.date, periods: int = 5) -> pd.DataFrame:
    """A small OHLCV frame whose newest bar is ``end`` (a DatetimeIndex, as the
    real ``fetch_ohlcv_incremental`` returns)."""
    idx = pd.bdate_range(end=pd.Timestamp(end), periods=periods)
    return pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100},
        index=idx,
    )


def _ctx(tmp_path: Path, **kw) -> mod.RetrainContext:
    return mod.RetrainContext(
        repo_dir=tmp_path,
        xgb_artifact_out=tmp_path / "x.json",
        calibrator_out=tmp_path / "c.json",
        **kw,
    )


# ─────────────────────────── refresh task ──────────────────────────────────


def test_refresh_iterates_full_panel_universe_not_just_watchlist(tmp_path) -> None:
    frontier = dt.date(2026, 6, 30)
    watchlist = ["AAPL", "MSFT"]
    research = ["XYZ", "QRS", "TUV", "WXY"]  # the names that had no refresh cadence
    universe = watchlist + research
    calls: list[str] = []

    def fake_fetch(sym, *, timeout_sec=None):
        calls.append(sym)
        return _ohlcv(frontier)

    ctx = _ctx(tmp_path, panel_universe=universe, fetch_fn=fake_fetch)

    assert mod.RefreshFullUniverseOhlcvTask().run(ctx) is True
    # The whole panel universe is refreshed, not just the live watchlist.
    assert set(calls) == set(universe)
    assert set(research).issubset(set(calls))
    summary = ctx.ohlcv_refresh_summary
    assert summary["n_universe"] == len(universe)
    assert summary["n_refreshed"] == len(universe)
    assert summary["n_failed"] == 0
    assert summary["n_delisted"] == 0


def test_refresh_sources_universe_from_inventory_tier_a_and_b(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "transformer_universe_inventory.json").write_text(
        json.dumps(
            {
                "tier_A_tickers": ["AAPL", "MSFT"],
                "tier_B_tickers": ["XYZ", "QRS", "TUV"],
                "ignored_key": ["NOPE"],
            }
        )
    )
    calls: list[str] = []

    def fake_fetch(sym, *, timeout_sec=None):
        calls.append(sym)
        return _ohlcv(dt.date(2026, 6, 30))

    ctx = _ctx(tmp_path, fetch_fn=fake_fetch)

    mod.RefreshFullUniverseOhlcvTask().run(ctx)

    assert set(calls) == {"AAPL", "MSFT", "XYZ", "QRS", "TUV"}


def test_refresh_delisted_and_failed_tickers_do_not_abort(tmp_path) -> None:
    frontier = dt.date(2026, 6, 30)
    universe = ["AAPL", "MSFT", "DEAD", "BOOM", "XYZ"]

    def fake_fetch(sym, *, timeout_sec=None):
        if sym == "BOOM":
            raise RuntimeError("network exploded")
        if sym == "DEAD":
            return pd.DataFrame()  # delisted: no bars
        return _ohlcv(frontier)

    ctx = _ctx(tmp_path, panel_universe=universe, fetch_fn=fake_fetch)

    # A single ticker's failure / delisting must NOT abort the retrain.
    assert mod.RefreshFullUniverseOhlcvTask().run(ctx) is True
    summary = ctx.ohlcv_refresh_summary
    assert summary["n_universe"] == 5
    assert summary["n_failed"] == 1
    assert summary["n_delisted"] == 1
    assert summary["n_refreshed"] == 3
    # counts partition the universe
    assert (
        summary["n_refreshed"]
        + summary["n_stale"]
        + summary["n_delisted"]
        + summary["n_failed"]
        == summary["n_universe"]
    )


def test_refresh_dry_run_makes_no_fetch(tmp_path) -> None:
    called: list[str] = []

    def fake_fetch(sym, *, timeout_sec=None):
        called.append(sym)
        return _ohlcv(dt.date(2026, 6, 30))

    ctx = _ctx(tmp_path, panel_universe=["A", "B"], fetch_fn=fake_fetch, dry_run=True)

    assert mod.RefreshFullUniverseOhlcvTask().run(ctx) is True
    assert called == []
    assert ctx.ohlcv_refresh_summary["n_universe"] == 2


def test_refresh_disabled_skips_fetch(tmp_path) -> None:
    called: list[str] = []

    def fake_fetch(sym, *, timeout_sec=None):
        called.append(sym)
        return _ohlcv(dt.date(2026, 6, 30))

    ctx = _ctx(tmp_path, panel_universe=["A", "B"], fetch_fn=fake_fetch, refresh_ohlcv=False)

    assert mod.RefreshFullUniverseOhlcvTask().run(ctx) is True
    assert called == []


def test_refresh_empty_universe_is_safe_noop(tmp_path) -> None:
    (tmp_path / "data").mkdir(parents=True)  # no inventory present
    ctx = _ctx(tmp_path)
    assert mod.RefreshFullUniverseOhlcvTask().run(ctx) is True
    assert ctx.ohlcv_refresh_summary["n_universe"] == 0


def test_refresh_resolves_default_fetch_fn_when_not_injected(tmp_path, monkeypatch) -> None:
    """Runtime-wiring seam: when no fetch_fn is injected, the task resolves the
    real base-data primitive via ``_default_fetch_fn`` (patched here so no
    network import happens)."""
    calls: list[str] = []

    def fake_fetch(sym, *, timeout_sec=None):
        calls.append(sym)
        return _ohlcv(dt.date(2026, 6, 30))

    monkeypatch.setattr(mod, "_default_fetch_fn", lambda: fake_fetch)
    ctx = _ctx(tmp_path, panel_universe=["A", "B", "C"])

    mod.RefreshFullUniverseOhlcvTask().run(ctx)

    assert set(calls) == {"A", "B", "C"}


# ─────────────────────────── freshness guard ───────────────────────────────


def test_guard_quiet_when_bars_fresh_despite_fwd60d_panel_frontier(tmp_path, monkeypatch) -> None:
    """The guard reads RAW OHLCV bars, whose frontier is ~today. A panel built
    from them legitimately ends ~60 trading days earlier (fwd_60d clip) — that
    expected frontier must NOT be mistaken for input staleness, so with all raw
    bars fresh the guard stays silent."""
    frontier = dt.date(2026, 6, 30)
    universe = [f"T{i}" for i in range(20)]
    ctx = _ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates={t: frontier for t in universe},
        freshness_stale_after_days=10,
        freshness_max_stale_fraction=0.10,
        freshness_fail_on_stale=True,
    )
    posted: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: posted.append(a))

    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert posted == []
    assert ctx.freshness_report["n_stale"] == 0
    assert ctx.freshness_report["as_of_frontier"] == frontier.isoformat()


def test_guard_quiet_below_threshold(tmp_path, monkeypatch) -> None:
    frontier = dt.date(2026, 6, 30)
    frozen = dt.date(2026, 5, 12)  # ~35 trading days behind
    universe = [f"T{i}" for i in range(20)]
    md = {t: frontier for t in universe}
    md["T0"] = frozen  # 1/20 = 5% <= 10%
    ctx = _ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates=md,
        freshness_max_stale_fraction=0.10,
        freshness_fail_on_stale=True,
    )
    posted: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: posted.append(a))

    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert posted == []
    assert ctx.freshness_report["n_stale"] == 1


def test_guard_fails_closed_on_partial_freeze(tmp_path, monkeypatch) -> None:
    frontier = dt.date(2026, 6, 30)
    frozen = dt.date(2026, 5, 12)
    fresh_tickers = [f"F{i}" for i in range(10)]  # watchlist-like, fresh
    frozen_tickers = [f"Z{i}" for i in range(10)]  # research, frozen (the May freeze)
    universe = fresh_tickers + frozen_tickers
    md = {t: frontier for t in fresh_tickers}
    md.update({t: frozen for t in frozen_tickers})
    ctx = _ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates=md,
        freshness_max_stale_fraction=0.10,
        freshness_fail_on_stale=True,
    )
    posted: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: posted.append(a))

    with pytest.raises(RuntimeError, match="panel tickers stale"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)

    assert len(posted) == 1  # LOUD alert fired
    assert ctx.freshness_report["n_stale"] == 10
    assert ctx.freshness_report["stale_fraction"] == 0.5


def test_guard_proceeds_with_warning_when_fail_disabled(tmp_path, monkeypatch) -> None:
    frontier = dt.date(2026, 6, 30)
    frozen = dt.date(2026, 5, 12)
    universe = [f"T{i}" for i in range(20)]
    md = {t: frontier for t in universe}
    for t in universe[:10]:
        md[t] = frozen
    ctx = _ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates=md,
        freshness_max_stale_fraction=0.10,
        freshness_fail_on_stale=False,
    )
    posted: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: posted.append(a))

    # proceeds (returns True) but still alerts loudly
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert len(posted) == 1


def test_guard_counts_missing_bars_as_stale(tmp_path, monkeypatch) -> None:
    frontier = dt.date(2026, 6, 30)
    universe = [f"T{i}" for i in range(10)]
    md = {t: frontier for t in universe}
    for t in universe[:3]:
        md[t] = None  # no bars at all (never fetched / delisted with no cache)
    ctx = _ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates=md,
        freshness_max_stale_fraction=0.10,
        freshness_fail_on_stale=True,
    )
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)

    with pytest.raises(RuntimeError):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    assert ctx.freshness_report["n_missing"] == 3
    assert ctx.freshness_report["n_stale"] == 3


def test_guard_uses_injected_ohlcv_reader(tmp_path, monkeypatch) -> None:
    frontier = dt.date(2026, 6, 30)
    universe = ["AAA", "BBB", "CCC"]
    ctx = _ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_date_fn=lambda t: frontier,
        freshness_fail_on_stale=True,
    )
    posted: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: posted.append(a))

    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert posted == []
    assert ctx.freshness_report["as_of_frontier"] == frontier.isoformat()


def test_guard_skips_when_no_dates_resolvable(tmp_path) -> None:
    ctx = _ctx(
        tmp_path,
        panel_universe=["A", "B"],
        ohlcv_max_date_fn=lambda t: None,
    )
    # cannot assess → soft skip (does not raise)
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True


# ─────────────────────────── end to end ────────────────────────────────────


def test_refresh_then_guard_catches_partial_freeze_end_to_end(tmp_path, monkeypatch) -> None:
    """Refresh the whole universe, then the guard catches the research-ticker
    freeze that the watchlist-only scan silently passed."""
    frontier = dt.date(2026, 6, 30)
    frozen = dt.date(2026, 5, 12)
    watchlist = [f"W{i}" for i in range(8)]
    research = [f"R{i}" for i in range(8)]
    universe = watchlist + research

    def fake_fetch(sym, *, timeout_sec=None):
        # fresh where the live path already refreshes; frozen for the research
        # tail that has no refresh cadence upstream
        return _ohlcv(frontier) if sym in watchlist else _ohlcv(frozen)

    ctx = _ctx(
        tmp_path,
        panel_universe=universe,
        fetch_fn=fake_fetch,
        freshness_max_stale_fraction=0.10,
        freshness_fail_on_stale=True,
    )
    posted: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: posted.append(a))

    assert mod.RefreshFullUniverseOhlcvTask().run(ctx) is True
    assert ctx.ohlcv_refresh_summary["n_stale"] == 8

    with pytest.raises(RuntimeError):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    assert len(posted) == 1
    assert ctx.freshness_report["n_stale"] == 8


# ─────────────────────────── helpers / disk reader ─────────────────────────


def test_default_ohlcv_max_date_reads_parquet(tmp_path) -> None:
    ohlcv_dir = tmp_path / "ohlcv"
    (ohlcv_dir / "AAA").mkdir(parents=True)
    _ohlcv(dt.date(2026, 6, 30)).to_parquet(ohlcv_dir / "AAA" / "1d.parquet")

    assert mod._default_ohlcv_max_date(ohlcv_dir, "AAA") == dt.date(2026, 6, 30)
    assert mod._default_ohlcv_max_date(ohlcv_dir, "MISSING") is None


def test_trading_days_between_is_business_day_gap() -> None:
    assert mod._trading_days_between(dt.date(2026, 6, 30), dt.date(2026, 6, 30)) == 0
    assert mod._trading_days_between(dt.date(2026, 7, 1), dt.date(2026, 6, 30)) == 0
    # Mon..Fri same week = 4 business days to the following Monday
    assert mod._trading_days_between(dt.date(2026, 6, 22), dt.date(2026, 6, 29)) == 5
    assert mod._trading_days_between(dt.date(2026, 5, 12), dt.date(2026, 6, 30)) > 10


def test_pipeline_includes_refresh_and_guard_first() -> None:
    tasks = [type(t).__name__ for t in mod.build_pipeline().jobs[0].tasks]
    assert tasks[:2] == ["RefreshFullUniverseOhlcvTask", "PanelUniverseFreshnessGuardTask"]
