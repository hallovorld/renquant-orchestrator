"""Tests for the full-universe OHLCV refresh + partial-freeze guard.

These cover the load-bearing model-staleness root cause: the panel training
universe (tier_A + tier_B, ~292 tickers) is half-frozen because only the
~142-ticker live watchlist gets fresh daily bars. The refresh task must iterate
the FULL panel universe (not just the watchlist), a single ticker's failure /
delisting must not abort the retrain, and the guard must FAIL CLOSED when the
universe / freshness cannot be established or more than a configured fraction of
the panel is stale — while staying quiet at the expected fwd_60d frontier.

Fail-closed is the point (Codex review, PR #217): a missing/corrupt/empty
inventory, no resolvable OHLCV dates, or a globally-uniform freeze must BLOCK,
not resolve to an ``n_universe=0`` / "soft skip" success. Freshness is measured
against an INDEPENDENTLY-derived expected market session using the shared
exchange calendar (holiday / half-day aware), not ``max(known dates)``.

All fetch / freshness IO is mocked or uses tmp fixtures — no real network fetch
and no production data write ever happens here. The synthetic guard tests inject
``expected_session`` + a ``session_gap_fn`` so they never require the exchange
calendar; the real calendar semantics are covered separately (importorskip).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest

from renquant_orchestrator import retrain_alpha158_fund as mod


FRONTIER = dt.date(2026, 6, 30)
FROZEN = dt.date(2026, 5, 12)


def _ohlcv(end: dt.date, periods: int = 5) -> pd.DataFrame:
    """A small OHLCV frame whose newest bar is ``end`` (a DatetimeIndex, as the
    real ``fetch_ohlcv_incremental`` returns)."""
    idx = pd.bdate_range(end=pd.Timestamp(end), periods=periods)
    return pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100},
        index=idx,
    )


def _cal_day_gap(a: dt.date, b: dt.date) -> int:
    """Deterministic, calendar-day session-gap proxy for the synthetic guard
    tests (monotonic, no exchange-calendar dependency). The real exchange-session
    semantics are exercised in the ``importorskip`` calendar tests below."""
    return max((b - a).days, 0)


def _ctx(tmp_path: Path, **kw) -> mod.RetrainContext:
    return mod.RetrainContext(
        repo_dir=tmp_path,
        xgb_artifact_out=tmp_path / "x.json",
        calibrator_out=tmp_path / "c.json",
        **kw,
    )


def _guard_ctx(tmp_path: Path, **kw) -> mod.RetrainContext:
    """A guard context that never touches the real exchange calendar: expected
    session + gap fn injected unless the caller overrides them."""
    kw.setdefault("expected_session", FRONTIER)
    kw.setdefault("session_gap_fn", _cal_day_gap)
    return _ctx(tmp_path, **kw)


# ─────────────────────────── refresh task ──────────────────────────────────


def test_refresh_iterates_full_panel_universe_not_just_watchlist(tmp_path) -> None:
    watchlist = ["AAPL", "MSFT"]
    research = ["XYZ", "QRS", "TUV", "WXY"]  # the names that had no refresh cadence
    universe = watchlist + research
    calls: list[str] = []

    def fake_fetch(sym, *, timeout_sec=None):
        calls.append(sym)
        return _ohlcv(FRONTIER)

    ctx = _ctx(
        tmp_path,
        panel_universe=universe,
        fetch_fn=fake_fetch,
        expected_session=FRONTIER,
        session_gap_fn=_cal_day_gap,
    )

    assert mod.RefreshFullUniverseOhlcvTask().run(ctx) is True
    # The whole panel universe is refreshed, not just the live watchlist.
    assert set(calls) == set(universe)
    assert set(research).issubset(set(calls))
    summary = ctx.ohlcv_refresh_summary
    assert summary["n_universe"] == len(universe)
    assert summary["n_refreshed"] == len(universe)
    assert summary["n_failed"] == 0
    assert summary["n_delisted"] == 0
    assert summary["inventory_fingerprint"].startswith("sha256:")


def test_refresh_sources_universe_from_inventory_tier_a_and_b(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "transformer_universe_inventory.json").write_text(
        json.dumps(
            {
                "kind": "transformer_universe_inventory",
                "generated_utc": "2026-06-30T00:00:00+00:00",
                "tier_A_tickers": ["AAPL", "MSFT"],
                "tier_B_tickers": ["XYZ", "QRS", "TUV"],
                "ignored_key": ["NOPE"],
            }
        )
    )
    calls: list[str] = []

    def fake_fetch(sym, *, timeout_sec=None):
        calls.append(sym)
        return _ohlcv(FRONTIER)

    ctx = _ctx(
        tmp_path,
        fetch_fn=fake_fetch,
        expected_session=FRONTIER,
        session_gap_fn=_cal_day_gap,
    )

    mod.RefreshFullUniverseOhlcvTask().run(ctx)

    assert set(calls) == {"AAPL", "MSFT", "XYZ", "QRS", "TUV"}
    assert ctx.panel_universe_provenance["n_universe"] == 5


def test_refresh_delisted_and_failed_tickers_do_not_abort(tmp_path) -> None:
    universe = ["AAPL", "MSFT", "DEAD", "BOOM", "XYZ"]

    def fake_fetch(sym, *, timeout_sec=None):
        if sym == "BOOM":
            raise RuntimeError("network exploded")
        if sym == "DEAD":
            return pd.DataFrame()  # delisted: no bars
        return _ohlcv(FRONTIER)

    ctx = _ctx(
        tmp_path,
        panel_universe=universe,
        fetch_fn=fake_fetch,
        expected_session=FRONTIER,
        session_gap_fn=_cal_day_gap,
    )

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
        + summary["n_future"]
        + summary["n_delisted"]
        + summary["n_failed"]
        == summary["n_universe"]
    )


def test_refresh_dry_run_makes_no_fetch(tmp_path) -> None:
    called: list[str] = []

    def fake_fetch(sym, *, timeout_sec=None):
        called.append(sym)
        return _ohlcv(FRONTIER)

    ctx = _ctx(tmp_path, panel_universe=["A", "B"], fetch_fn=fake_fetch, dry_run=True)

    assert mod.RefreshFullUniverseOhlcvTask().run(ctx) is True
    assert called == []
    assert ctx.ohlcv_refresh_summary["n_universe"] == 2


def test_refresh_disabled_skips_fetch(tmp_path) -> None:
    called: list[str] = []

    def fake_fetch(sym, *, timeout_sec=None):
        called.append(sym)
        return _ohlcv(FRONTIER)

    ctx = _ctx(tmp_path, panel_universe=["A", "B"], fetch_fn=fake_fetch, refresh_ohlcv=False)

    assert mod.RefreshFullUniverseOhlcvTask().run(ctx) is True
    assert called == []


def test_refresh_missing_inventory_fails_closed(tmp_path) -> None:
    """A missing inventory is NOT a safe empty-universe noop — it is an
    unestablishable required training universe and must fail closed."""
    (tmp_path / "data").mkdir(parents=True)  # no inventory present
    ctx = _ctx(tmp_path)
    with pytest.raises(mod.InventoryUnavailableError, match="not found"):
        mod.RefreshFullUniverseOhlcvTask().run(ctx)


def test_refresh_corrupt_inventory_fails_closed(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "transformer_universe_inventory.json").write_text("{ this is not json")
    ctx = _ctx(tmp_path)
    with pytest.raises(mod.InventoryUnavailableError, match="invalid JSON"):
        mod.RefreshFullUniverseOhlcvTask().run(ctx)


def test_refresh_empty_active_universe_fails_closed(tmp_path) -> None:
    """An inventory whose tiers are empty (or fully delisted) yields no active
    universe → fail closed rather than 'refreshed 0 names successfully'."""
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "transformer_universe_inventory.json").write_text(
        json.dumps(
            {
                "kind": "transformer_universe_inventory",
                "tier_A_tickers": ["DEAD"],
                "tier_B_tickers": [],
                "delisted_tickers": ["DEAD"],
            }
        )
    )
    ctx = _ctx(tmp_path)
    with pytest.raises(mod.InventoryUnavailableError, match="EMPTY active universe"):
        mod.RefreshFullUniverseOhlcvTask().run(ctx)


def test_refresh_resolves_default_fetch_fn_when_not_injected(tmp_path, monkeypatch) -> None:
    """Runtime-wiring seam: when no fetch_fn is injected, the task resolves the
    real base-data primitive via ``_default_fetch_fn`` (patched here so no
    network import happens)."""
    calls: list[str] = []

    def fake_fetch(sym, *, timeout_sec=None):
        calls.append(sym)
        return _ohlcv(FRONTIER)

    monkeypatch.setattr(mod, "_default_fetch_fn", lambda: fake_fetch)
    ctx = _ctx(
        tmp_path,
        panel_universe=["A", "B", "C"],
        expected_session=FRONTIER,
        session_gap_fn=_cal_day_gap,
    )

    mod.RefreshFullUniverseOhlcvTask().run(ctx)

    assert set(calls) == {"A", "B", "C"}


# ─────────────────────────── universe provenance ───────────────────────────


def test_inventory_delisted_excluded_via_versioned_universe(tmp_path) -> None:
    """Delisted names are pruned via the *versioned* inventory (a versioned
    exclusion), NOT absorbed as tolerated stale failures."""
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "transformer_universe_inventory.json").write_text(
        json.dumps(
            {
                "kind": "transformer_universe_inventory",
                "generated_utc": "2026-06-30T00:00:00+00:00",
                "tier_A_tickers": ["AAPL", "MSFT", "OLDCO"],
                "tier_B_tickers": ["XYZ"],
                "inactive_tickers": ["OLDCO"],
            }
        )
    )
    ctx = _ctx(tmp_path)
    universe, prov = mod._resolve_panel_universe(ctx)
    assert universe == ["AAPL", "MSFT", "XYZ"]
    assert "OLDCO" not in universe
    assert prov["n_declared"] == 4
    assert prov["n_delisted_excluded"] == 1
    assert prov["n_universe"] == 3
    assert prov["fingerprint"].startswith("sha256:")


def test_explicit_empty_universe_fails_closed(tmp_path) -> None:
    ctx = _ctx(tmp_path, panel_universe=[])
    with pytest.raises(mod.InventoryUnavailableError, match="empty"):
        mod._resolve_panel_universe(ctx)


def test_non_inventory_object_fails_closed(tmp_path) -> None:
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "transformer_universe_inventory.json").write_text(json.dumps({"foo": "bar"}))
    ctx = _ctx(tmp_path)
    with pytest.raises(mod.InventoryUnavailableError, match="tier_A_tickers"):
        mod._resolve_panel_universe(ctx)


# ─────────────────────────── freshness guard ───────────────────────────────


def test_guard_quiet_when_bars_fresh_despite_fwd60d_panel_frontier(tmp_path, monkeypatch) -> None:
    """The guard reads RAW OHLCV bars, whose frontier is ~today. A panel built
    from them legitimately ends ~60 trading days earlier (fwd_60d clip) — that
    expected frontier must NOT be mistaken for input staleness, so with all raw
    bars fresh the guard stays silent."""
    universe = [f"T{i}" for i in range(20)]
    ctx = _guard_ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates={t: FRONTIER for t in universe},
        freshness_stale_after_days=10,
        freshness_max_stale_fraction=0.10,
        freshness_fail_on_stale=True,
    )
    posted: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: posted.append(a))

    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert posted == []
    assert ctx.freshness_report["n_stale"] == 0
    assert ctx.freshness_report["expected_session"] == FRONTIER.isoformat()
    assert ctx.freshness_report["inventory_fingerprint"].startswith("sha256:")


def test_guard_quiet_below_threshold(tmp_path, monkeypatch) -> None:
    universe = [f"T{i}" for i in range(20)]
    md = {t: FRONTIER for t in universe}
    md["T0"] = FROZEN  # 1/20 = 5% <= 10%
    ctx = _guard_ctx(
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
    fresh_tickers = [f"F{i}" for i in range(10)]  # watchlist-like, fresh
    frozen_tickers = [f"Z{i}" for i in range(10)]  # research, frozen (the May freeze)
    universe = fresh_tickers + frozen_tickers
    md = {t: FRONTIER for t in fresh_tickers}
    md.update({t: FROZEN for t in frozen_tickers})
    ctx = _guard_ctx(
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


def test_guard_blocks_globally_uniform_stale(tmp_path, monkeypatch) -> None:
    """The KEY Codex regression: if the WHOLE universe freezes on the same old
    date, ``max(known)`` would call everything fresh. Measuring vs the
    independently-derived expected session makes every name read stale → BLOCK.
    Even a generous 10% tolerance cannot mask a 100%-stale universe."""
    universe = [f"T{i}" for i in range(20)]
    md = {t: FROZEN for t in universe}  # uniform freeze; frontier == FROZEN
    ctx = _guard_ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates=md,
        expected_session=FRONTIER,  # independently derived, recent
        freshness_max_stale_fraction=0.10,
        freshness_fail_on_stale=True,
    )
    posted: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: posted.append(a))

    with pytest.raises(RuntimeError, match="panel tickers stale"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    assert len(posted) == 1
    assert ctx.freshness_report["n_stale"] == 20
    assert ctx.freshness_report["stale_fraction"] == 1.0
    # the frontier (max known) is the frozen date, proving we did NOT anchor to it
    assert ctx.freshness_report["as_of_frontier"] == FROZEN.isoformat()
    assert ctx.freshness_report["expected_session"] == FRONTIER.isoformat()


def test_guard_flags_future_dated_bars(tmp_path, monkeypatch) -> None:
    """A bar dated AFTER the expected session is a data-integrity anomaly; it is
    bucketed as future (counted stale), never as fresh."""
    future_date = dt.date(2026, 7, 20)
    universe = [f"T{i}" for i in range(10)]
    md = {t: FRONTIER for t in universe}
    md["T0"] = future_date
    md["T1"] = future_date
    ctx = _guard_ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates=md,
        expected_session=FRONTIER,
        freshness_max_stale_fraction=0.0,  # strict
        freshness_fail_on_stale=True,
    )
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)

    with pytest.raises(RuntimeError):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    assert ctx.freshness_report["n_future"] == 2
    assert ctx.freshness_report["n_stale"] == 2


def test_guard_proceeds_with_warning_when_fail_disabled(tmp_path, monkeypatch) -> None:
    universe = [f"T{i}" for i in range(20)]
    md = {t: FRONTIER for t in universe}
    for t in universe[:10]:
        md[t] = FROZEN
    ctx = _guard_ctx(
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
    universe = [f"T{i}" for i in range(10)]
    md = {t: FRONTIER for t in universe}
    for t in universe[:3]:
        md[t] = None  # no bars at all (never fetched / delisted with no cache)
    ctx = _guard_ctx(
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
    universe = ["AAA", "BBB", "CCC"]
    ctx = _guard_ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_date_fn=lambda t: FRONTIER,
        freshness_fail_on_stale=True,
    )
    posted: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: posted.append(a))

    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert posted == []
    assert ctx.freshness_report["expected_session"] == FRONTIER.isoformat()


def test_guard_fails_closed_when_no_dates_resolvable(tmp_path) -> None:
    ctx = _guard_ctx(
        tmp_path,
        panel_universe=["A", "B"],
        ohlcv_max_date_fn=lambda t: None,
    )
    # cannot prove freshness for ANY name → fail closed (was a soft skip)
    with pytest.raises(mod.FreshnessUnprovableError, match="no OHLCV max dates"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)


def test_guard_fails_closed_on_missing_inventory(tmp_path) -> None:
    (tmp_path / "data").mkdir(parents=True)  # no inventory
    ctx = mod.RetrainContext(
        repo_dir=tmp_path,
        xgb_artifact_out=tmp_path / "x.json",
        calibrator_out=tmp_path / "c.json",
        expected_session=FRONTIER,
        session_gap_fn=_cal_day_gap,
    )
    with pytest.raises(mod.InventoryUnavailableError):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)


def test_guard_fails_closed_no_readable_parquet(tmp_path) -> None:
    """No injected dates and no readable parquet on disk → the default disk
    reader returns None for every name → freshness unprovable → fail closed."""
    (tmp_path / "data" / "ohlcv").mkdir(parents=True)  # empty ohlcv dir, no parquet
    ctx = mod.RetrainContext(
        repo_dir=tmp_path,
        xgb_artifact_out=tmp_path / "x.json",
        calibrator_out=tmp_path / "c.json",
        panel_universe=["AAA", "BBB"],
        expected_session=FRONTIER,
        session_gap_fn=_cal_day_gap,
    )
    with pytest.raises(mod.FreshnessUnprovableError, match="no OHLCV max dates"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)


def test_guard_fails_closed_when_expected_session_unresolvable(tmp_path, monkeypatch) -> None:
    """If the expected market session cannot be derived, freshness is unprovable
    → fail closed rather than falling back to max(known)."""
    monkeypatch.setattr(mod, "_expected_last_completed_session", lambda ex, now: None)
    universe = ["A", "B"]
    ctx = _ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates={t: FRONTIER for t in universe},
        session_gap_fn=_cal_day_gap,
        now_fn=lambda: pd.Timestamp("2026-06-30 20:00", tz="America/New_York"),
    )
    with pytest.raises(mod.FreshnessUnprovableError, match="expected"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)


# ─────────────────────────── end to end ────────────────────────────────────


def test_refresh_then_guard_catches_partial_freeze_end_to_end(tmp_path, monkeypatch) -> None:
    """Refresh the whole universe, then the guard catches the research-ticker
    freeze that the watchlist-only scan silently passed."""
    watchlist = [f"W{i}" for i in range(8)]
    research = [f"R{i}" for i in range(8)]
    universe = watchlist + research

    def fake_fetch(sym, *, timeout_sec=None):
        # fresh where the live path already refreshes; frozen for the research
        # tail that has no refresh cadence upstream
        return _ohlcv(FRONTIER) if sym in watchlist else _ohlcv(FROZEN)

    ctx = _ctx(
        tmp_path,
        panel_universe=universe,
        fetch_fn=fake_fetch,
        expected_session=FRONTIER,
        session_gap_fn=_cal_day_gap,
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
    _ohlcv(FRONTIER).to_parquet(ohlcv_dir / "AAA" / "1d.parquet")

    assert mod._default_ohlcv_max_date(ohlcv_dir, "AAA") == FRONTIER
    assert mod._default_ohlcv_max_date(ohlcv_dir, "MISSING") is None


def test_default_max_stale_fraction_is_strict() -> None:
    """The tolerated-stale default is strict (fail-closed on any stale name).
    The old unjustified 10% default could hide ~29 frozen names."""
    assert mod.DEFAULT_FRESHNESS_MAX_STALE_FRACTION == 0.0
    ctx = mod.RetrainContext(
        repo_dir=Path("/tmp/_x"),
        xgb_artifact_out=Path("/tmp/_x/x.json"),
        calibrator_out=Path("/tmp/_x/c.json"),
    )
    assert ctx.freshness_max_stale_fraction == 0.0


def test_pipeline_includes_refresh_and_guard_first() -> None:
    tasks = [type(t).__name__ for t in mod.build_pipeline().jobs[0].tasks]
    assert tasks[:2] == ["RefreshFullUniverseOhlcvTask", "PanelUniverseFreshnessGuardTask"]


# ─────────────────── shared exchange calendar (holiday / half-day) ──────────
# These exercise the REAL NYSE calendar and are skipped where
# pandas_market_calendars is not installed (e.g. minimal CI).


def test_session_gap_uses_exchange_calendar_holidays() -> None:
    pytest.importorskip("pandas_market_calendars")
    # 2026-06-19 is Juneteenth (NYSE holiday). A plain business-day helper would
    # count it as a session; the exchange calendar must not.
    # (Thu 6/18, Fri 6/19 holiday, weekend, Mon 6/22) → 1 session gap, not 2.
    assert mod._default_session_gap("NYSE", dt.date(2026, 6, 18), dt.date(2026, 6, 22)) == 1
    # A clean week: sessions after Mon 6/22 through Mon 6/29 = 5.
    assert mod._default_session_gap("NYSE", dt.date(2026, 6, 22), dt.date(2026, 6, 29)) == 5
    assert mod._default_session_gap("NYSE", dt.date(2026, 6, 30), dt.date(2026, 6, 30)) == 0
    # 2026-07-03 is the observed Independence Day holiday (Jul 4 is a Saturday).
    assert mod._default_session_gap("NYSE", dt.date(2026, 7, 2), dt.date(2026, 7, 6)) == 1


def test_session_gap_counts_half_day_as_session() -> None:
    pytest.importorskip("pandas_market_calendars")
    # 2026-11-26 is Thanksgiving (holiday); 2026-11-27 is an early-close half-day
    # but is still an open session and must be counted.
    # sessions after Wed 11/25 through Mon 11/30 = {11/27 (half), 11/30} = 2.
    assert mod._default_session_gap("NYSE", dt.date(2026, 11, 25), dt.date(2026, 11, 30)) == 2


def test_expected_session_half_day_early_close_cutoff() -> None:
    pytest.importorskip("pandas_market_calendars")
    # 2026-11-27 is a half-day with a 13:00 ET early close.
    before = pd.Timestamp("2026-11-27 12:30", tz="America/New_York")
    after = pd.Timestamp("2026-11-27 13:30", tz="America/New_York")
    # Before the (early) close: the last COMPLETED session is Wed 11/25
    # (11/26 is the Thanksgiving holiday).
    assert mod._expected_last_completed_session("NYSE", before) == dt.date(2026, 11, 25)
    # After the early close: today's half-day session is complete.
    assert mod._expected_last_completed_session("NYSE", after) == dt.date(2026, 11, 27)


def test_expected_session_regular_close_cutoff() -> None:
    pytest.importorskip("pandas_market_calendars")
    # Regular session (Tue 2026-06-30, 16:00 ET close).
    before = pd.Timestamp("2026-06-30 15:00", tz="America/New_York")
    after = pd.Timestamp("2026-06-30 16:30", tz="America/New_York")
    assert mod._expected_last_completed_session("NYSE", before) == dt.date(2026, 6, 29)
    assert mod._expected_last_completed_session("NYSE", after) == dt.date(2026, 6, 30)
