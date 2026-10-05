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


EMPTY_REGISTRY = {"kind": "retrain_universe_exclusions", "schema_version": 1, "exclusions": []}


def _registry_file(tmp_path: Path, entries: list | None = None, **top) -> Path:
    """Write a registry under tmp_path (default: valid and EMPTY); ``top``
    overrides top-level keys (used to break the schema on purpose)."""
    payload = dict(EMPTY_REGISTRY)
    payload["exclusions"] = list(entries or [])
    payload.update(top)
    path = tmp_path / "retrain_universe_exclusions.json"
    path.write_text(json.dumps(payload))
    return path


def _ctx(tmp_path: Path, **kw) -> mod.RetrainContext:
    # Deterministic defaults so no guard test measures the operator's disk:
    # an EXPLICITLY EMPTY served watchlist (else the guard would read the live
    # pinned strategy config) and an EMPTY exclusion registry under tmp_path
    # (else the committed registry — which really does list IAC and AVB —
    # would prune names these tests declare). The registry tests below write
    # their own entries; the committed file has its own test.
    kw.setdefault("served_watchlist", [])
    if "exclusion_registry_path" not in kw:  # not setdefault: never clobber a caller's file
        kw["exclusion_registry_path"] = _registry_file(tmp_path)
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


def test_exclude_tickers_cli_prunes_from_universe(tmp_path) -> None:
    """--exclude-tickers supplements the inventory's delisted list so a
    newly-delisted ticker can be excluded without updating the inventory."""
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "transformer_universe_inventory.json").write_text(
        json.dumps(
            {
                "kind": "transformer_universe_inventory",
                "generated_utc": "2026-06-30T00:00:00+00:00",
                "tier_A_tickers": ["AAPL", "IAC", "MSFT"],
                "tier_B_tickers": ["XYZ"],
            }
        )
    )
    ctx = _ctx(tmp_path, exclude_tickers={"IAC"})
    universe, prov = mod._resolve_panel_universe(ctx)
    assert "IAC" not in universe
    assert universe == ["AAPL", "MSFT", "XYZ"]
    assert prov["n_cli_excluded"] == 1
    assert prov["cli_excluded"] == ["IAC"]
    assert prov["n_universe"] == 3


def test_exclude_tickers_stacks_with_inventory_delisted(tmp_path) -> None:
    """CLI excludes and inventory delisted tickers both apply."""
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "transformer_universe_inventory.json").write_text(
        json.dumps(
            {
                "kind": "transformer_universe_inventory",
                "generated_utc": "2026-06-30T00:00:00+00:00",
                "tier_A_tickers": ["AAPL", "IAC", "MSFT", "OLDCO"],
                "tier_B_tickers": [],
                "delisted_tickers": ["OLDCO"],
            }
        )
    )
    ctx = _ctx(tmp_path, exclude_tickers={"IAC"})
    universe, prov = mod._resolve_panel_universe(ctx)
    assert universe == ["AAPL", "MSFT"]
    assert prov["n_cli_excluded"] == 1
    assert prov["n_delisted_excluded"] == 1


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


def test_exclude_tickers_unblocks_freshness_guard(tmp_path, monkeypatch) -> None:
    """A single stale ticker (e.g. IAC delisted) with strict 0.0 tolerance
    blocks the entire retrain. --exclude-tickers removes it from the universe
    so the guard passes."""
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "transformer_universe_inventory.json").write_text(
        json.dumps(
            {
                "kind": "transformer_universe_inventory",
                "generated_utc": "2026-06-30T00:00:00+00:00",
                "tier_A_tickers": ["AAPL", "IAC", "MSFT"],
                "tier_B_tickers": [],
            }
        )
    )
    md = {"AAPL": FRONTIER, "MSFT": FRONTIER, "IAC": FROZEN}
    posted: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: posted.append(a))

    # Without exclude: IAC is stale, 1/3 > 0.0 → FAIL
    ctx_fail = _guard_ctx(
        tmp_path,
        ohlcv_max_dates=md,
        freshness_max_stale_fraction=0.0,
        freshness_fail_on_stale=True,
    )
    with pytest.raises(RuntimeError, match="panel tickers stale"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx_fail)

    # With exclude: IAC pruned from universe, 0/2 stale → PASS
    ctx_pass = _guard_ctx(
        tmp_path,
        exclude_tickers={"IAC"},
        ohlcv_max_dates=md,
        freshness_max_stale_fraction=0.0,
        freshness_fail_on_stale=True,
    )
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx_pass) is True
    assert ctx_pass.freshness_report["n_stale"] == 0
    assert "IAC" not in ctx_pass.freshness_report.get("stale_names", {})


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


# ───────────── per-name lag tolerance (Codex #217 policy blocker) ───────────
# The tolerated fraction cannot see a PER-NAME lag: the old default of 10
# sessions let every active ticker sit ~two weeks stale with n_bad=0. The
# default is now a single session (a narrowly-justified operational lag).


def test_default_stale_after_days_is_one_session(tmp_path) -> None:
    assert mod.DEFAULT_FRESHNESS_STALE_AFTER_DAYS == 1
    ctx = _ctx(tmp_path)
    assert ctx.freshness_stale_after_days == 1


def test_guard_blocks_uniform_multi_session_lag_by_default(tmp_path, monkeypatch) -> None:
    """A whole universe five sessions behind the expected session BLOCKS under
    the default 1-session tolerance — the old 10-session default silently passed
    the exact two-week per-name mismatch Codex flagged."""
    universe = [f"T{i}" for i in range(20)]
    lag_date = FRONTIER - dt.timedelta(days=5)  # 5-session gap in the proxy
    ctx = _guard_ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates={t: lag_date for t in universe},
        # default freshness_stale_after_days (1) + strict fraction (0.0)
    )
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="panel tickers stale"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    assert ctx.freshness_report["n_stale"] == 20
    assert ctx.freshness_report["stale_after_days"] == 1


def test_guard_tolerates_exactly_one_session_lag(tmp_path, monkeypatch) -> None:
    """One session behind is within the operational allowance; two sessions is
    stale (default tolerance = 1)."""
    universe = ["A", "B", "C"]
    md = {
        "A": FRONTIER,  # 0 sessions
        "B": FRONTIER - dt.timedelta(days=1),  # 1 session → tolerated
        "C": FRONTIER - dt.timedelta(days=2),  # 2 sessions → stale
    }
    ctx = _guard_ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates=md,
        freshness_max_stale_fraction=0.5,  # 1/3 <= 0.5 → does not raise
        freshness_fail_on_stale=False,
    )
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert ctx.freshness_report["n_stale"] == 1
    assert set(ctx.freshness_report["stale_names"]) == {"C"}


# ─────────── run-bundle persistence: affected names + overrides ─────────────


def test_freshness_report_persists_affected_names_and_overrides(tmp_path, monkeypatch) -> None:
    """The run bundle records the FULL affected-name lists (stale / missing /
    future — not just the worst 10) and any deliberate override of the
    fail-closed defaults (Codex #217: 'persist any override and affected names
    in the run bundle')."""
    universe = [f"T{i}" for i in range(6)]
    md = {t: FRONTIER for t in universe}
    md["T0"] = FROZEN  # stale
    md["T1"] = None  # missing
    md["T2"] = dt.date(2026, 7, 20)  # future-dated
    ctx = _guard_ctx(
        tmp_path,
        panel_universe=universe,
        ohlcv_max_dates=md,
        freshness_stale_after_days=3,  # override (non-default)
        freshness_max_stale_fraction=0.9,  # override → keeps it from raising
        freshness_fail_on_stale=False,  # override
    )
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    rep = ctx.freshness_report
    assert set(rep["stale_names"]) == {"T0"}
    assert rep["missing_names"] == ["T1"]
    assert set(rep["future_names"]) == {"T2"}
    ov = rep["overrides"]
    assert ov["stale_after_days"] == {"value": 3, "default": 1}
    assert ov["max_stale_fraction"]["value"] == 0.9
    assert ov["fail_on_stale"] == {"value": False, "default": True}
    assert ov["expected_session_pinned"] == FRONTIER.isoformat()


def test_freshness_report_affected_names_persist_on_fail_closed(tmp_path, monkeypatch) -> None:
    """Even when the guard RAISES (fail-closed block), the report — with the
    affected names — is persisted BEFORE the raise so the run bundle keeps the
    exact names to chase."""
    universe = [f"T{i}" for i in range(4)]
    md = {t: FROZEN for t in universe}
    ctx = _guard_ctx(tmp_path, panel_universe=universe, ohlcv_max_dates=md)  # strict defaults
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: None)
    with pytest.raises(RuntimeError):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    assert set(ctx.freshness_report["stale_names"]) == set(universe)
    # strict defaults → no override recorded except the pinned reference session
    # and the tmp exclusion registry `_ctx` pins (a non-default path IS an override)
    assert set(ctx.freshness_report["overrides"]) == {
        "expected_session_pinned",
        "exclusion_registry_path",
    }


# ─────────── CLI / integration: expected-session / as-of injection ──────────
# main() must expose the reference-session injection so historical replay does
# NOT depend on the wall clock (Codex #217).


def _main_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "RenQuant"
    (repo / "data").mkdir(parents=True)
    return repo


def test_cli_parses_expected_session(tmp_path) -> None:
    args = mod.parse_args(["--repo-dir", str(tmp_path), "--expected-session", "2026-06-30"])
    assert args.expected_session == dt.date(2026, 6, 30)
    assert args.as_of is None


def test_cli_parses_as_of_bare_date_and_timestamp() -> None:
    bare = mod.parse_args(["--as-of", "2026-06-30"])
    # a bare date means that day's end-of-session, not midnight
    assert bare.as_of == dt.datetime(2026, 6, 30, 23, 59, 59)
    ts = mod.parse_args(["--as-of", "2026-06-30T15:00:00"])
    assert ts.as_of == dt.datetime(2026, 6, 30, 15, 0, 0)


def test_cli_rejects_bad_expected_session() -> None:
    with pytest.raises(SystemExit):
        mod.parse_args(["--expected-session", "not-a-date"])
    with pytest.raises(SystemExit):
        mod.parse_args(["--as-of", "nonsense"])


def test_main_injects_expected_session_into_context(tmp_path, monkeypatch) -> None:
    repo = _main_repo(tmp_path)
    captured: list[mod.RetrainContext] = []

    class FakePipeline:
        def run(self, ctx):
            captured.append(ctx)
            return None

    monkeypatch.setattr(mod, "build_pipeline", lambda: FakePipeline())
    assert mod.main(
        ["--repo-dir", str(repo), "--dry-run", "--expected-session", "2026-06-29"]
    ) == 0
    assert captured[0].expected_session == dt.date(2026, 6, 29)
    assert captured[0].now_fn is None


def test_main_as_of_injects_now_fn(tmp_path, monkeypatch) -> None:
    repo = _main_repo(tmp_path)
    captured: list[mod.RetrainContext] = []

    class FakePipeline:
        def run(self, ctx):
            captured.append(ctx)
            return None

    monkeypatch.setattr(mod, "build_pipeline", lambda: FakePipeline())
    assert mod.main(
        ["--repo-dir", str(repo), "--dry-run", "--as-of", "2026-06-30T16:30:00"]
    ) == 0
    ctx = captured[0]
    assert ctx.expected_session is None
    assert ctx.now_fn is not None
    assert ctx.now_fn() == dt.datetime(2026, 6, 30, 16, 30, 0)


def test_expected_session_priority_over_as_of(tmp_path) -> None:
    """When both are set, the explicit expected_session wins (no clock/calendar
    dependency at all)."""
    ctx = _ctx(
        tmp_path,
        panel_universe=["A"],
        expected_session=dt.date(2026, 6, 25),
        now_fn=lambda: dt.datetime(2026, 6, 30, 16, 30, 0),
    )
    assert mod._resolve_expected_session(ctx) == dt.date(2026, 6, 25)


def test_as_of_now_fn_resolves_session_via_real_calendar(tmp_path) -> None:
    """The as-of clock resolves the expected session through the real NYSE
    calendar — deterministic historical replay, independent of the wall clock."""
    pytest.importorskip("pandas_market_calendars")
    # 2026-06-30 16:30 ET is after the regular close → that session is complete.
    ctx = _ctx(
        tmp_path,
        panel_universe=["A"],
        now_fn=lambda: dt.datetime(2026, 6, 30, 16, 30, 0),
    )
    assert mod._resolve_expected_session(ctx) == dt.date(2026, 6, 30)
    # Before the close, the prior session is the last completed one.
    ctx_before = _ctx(
        tmp_path,
        panel_universe=["A"],
        now_fn=lambda: dt.datetime(2026, 6, 30, 15, 0, 0),
    )
    assert mod._resolve_expected_session(ctx_before) == dt.date(2026, 6, 29)


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


# ──────────── reviewed universe-exclusion registry (AVB / IAC pattern) ───────
#
# 2026-08-29/30: the weekly promote FAILED "PANEL-FREEZE 1/293 stale" on AVB
# (Equity Residential merger closed 2026-08-17, last bar 2026-08-24), still in
# tier_A of an inventory that ships NO delisted_tickers channel — the IAC
# pattern from July. Review REJECTED a "stale AND not served ⇒ presumed
# delisted" heuristic: a single-name outage, a symbol transition or an
# ingestion gap satisfies it, and pruning a name only from the freshness
# accounting leaves its stale rows in the panel. Exclusions are therefore
# EXPLICIT and REVIEWED (config/retrain_universe_exclusions.json), applied to
# the universe AND to the inventory the panel build reads; everything else
# stays strict and the veto says exactly what to do.

SERVED = ["AAPL", "MSFT", "NVDA"]
SEC_AVB = "https://www.sec.gov/Archives/edgar/data/0000915912/000110465926097833/tm2623381d1_8k.htm"
AVB_ENTRY = {
    "ticker": "AVB",
    "reason": "merged",
    "effective_date": "2026-08-17",
    "evidence_url": SEC_AVB,
    "added_by_pr": "hallovorld/renquant-orchestrator#1096",
}
IAC_ENTRY = {
    "ticker": "IAC",
    "reason": "data_outage_confirmed",
    "effective_date": "2026-05-12",
    "evidence_url": "https://github.com/hallovorld/RenQuant/blob/main/doc/progress/2026-07-17-retrain-exclude-iac.md",
    "added_by_pr": "hallovorld/renquant-orchestrator#1096",
}
EFFECTIVE_INVENTORY = Path("logs") / "daily_retrain_alpha158_fund" / "effective_universe_inventory.json"


def _inventory(tmp_path: Path, tier_a: list[str], tier_b: list[str] = (), **extra) -> Path:
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    path = data / "transformer_universe_inventory.json"
    payload = {
        "kind": "transformer_universe_inventory",
        "generated_utc": "2026-06-30T00:00:00+00:00",
        "tier_A_tickers": list(tier_a),
        "tier_B_tickers": list(tier_b),
        "tier_counts": {"A": len(tier_a), "B": len(tier_b)},
        **extra,
    }
    path.write_text(json.dumps(payload))
    return path


def _posted(monkeypatch) -> list:
    posted: list = []
    monkeypatch.setattr(mod, "post_ntfy", lambda *a, **k: posted.append(a))
    return posted


def _strict(tmp_path: Path, md: dict, **kw) -> mod.RetrainContext:
    kw.setdefault("served_watchlist", SERVED)
    kw.setdefault("freshness_max_stale_fraction", 0.0)  # the production strict rule
    kw.setdefault("freshness_fail_on_stale", True)
    return _guard_ctx(tmp_path, ohlcv_max_dates=md, **kw)


# ── registry parsing / validation ─────────────────────────────────────────────


def test_registry_valid_entries_parse(tmp_path) -> None:
    reg = _registry_file(tmp_path, [AVB_ENTRY, {**IAC_ENTRY, "notes": "vendor: no price data"}])
    registry, prov = mod.load_exclusion_registry(reg)
    assert sorted(registry) == ["AVB", "IAC"]
    avb = registry["AVB"]
    assert avb.reason == "merged"
    assert avb.effective_date == dt.date(2026, 8, 17)
    assert avb.evidence_url == SEC_AVB
    assert avb.as_record() == {
        "reason": "merged",
        "effective_date": "2026-08-17",
        "evidence_url": SEC_AVB,
        "added_by_pr": "hallovorld/renquant-orchestrator#1096",
    }
    assert registry["IAC"].as_record()["notes"] == "vendor: no price data"
    assert prov == {
        "path": str(reg),
        "n": 2,
        "schema_version": 1,
        "fingerprint": prov["fingerprint"],
    }
    assert prov["fingerprint"].startswith("sha256:")


def test_registry_empty_is_valid_and_ticker_is_uppercased(tmp_path) -> None:
    registry, prov = mod.load_exclusion_registry(_registry_file(tmp_path))
    assert registry == {} and prov["n"] == 0
    registry, _ = mod.load_exclusion_registry(
        _registry_file(tmp_path, [{**AVB_ENTRY, "ticker": " avb "}])
    )
    assert list(registry) == ["AVB"]


def test_registry_unknown_reason_rejected(tmp_path) -> None:
    reg = _registry_file(tmp_path, [{**AVB_ENTRY, "reason": "spun_off"}])
    with pytest.raises(mod.ExclusionRegistryError, match="reason 'spun_off' is not one of"):
        mod.load_exclusion_registry(reg)


def test_registry_missing_or_bad_evidence_rejected(tmp_path) -> None:
    no_evidence = {k: v for k, v in AVB_ENTRY.items() if k != "evidence_url"}
    with pytest.raises(mod.ExclusionRegistryError, match=r"missing required key\(s\) \['evidence_url'\]"):
        mod.load_exclusion_registry(_registry_file(tmp_path, [no_evidence]))
    with pytest.raises(mod.ExclusionRegistryError, match="'evidence_url' must be a non-empty string"):
        mod.load_exclusion_registry(_registry_file(tmp_path, [{**AVB_ENTRY, "evidence_url": "  "}]))
    with pytest.raises(mod.ExclusionRegistryError, match=r"evidence_url must be an http\(s\) URL"):
        mod.load_exclusion_registry(
            _registry_file(tmp_path, [{**AVB_ENTRY, "evidence_url": "doc/progress/x.md"}])
        )


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda e: {**e, "effective_date": "2026/08/17"}, "is not an ISO date"),
        (lambda e: {**e, "ticker": "av b"}, "is not a symbol"),
        (lambda e: {**e, "added_by_pr": ""}, "'added_by_pr' must be a non-empty string"),
        (lambda e: {**e, "sessions_stale": 4}, r"unknown key\(s\) \['sessions_stale'\]"),
        (lambda e: {**e, "notes": 7}, "'notes' must be a non-empty string"),
        (lambda e: "AVB", "entry must be a JSON object"),
    ],
)
def test_registry_entry_schema_violations_rejected(tmp_path, mutate, match) -> None:
    with pytest.raises(mod.ExclusionRegistryError, match=match):
        mod.load_exclusion_registry(_registry_file(tmp_path, [mutate(AVB_ENTRY)]))


def test_registry_duplicate_ticker_rejected(tmp_path) -> None:
    reg = _registry_file(tmp_path, [AVB_ENTRY, {**AVB_ENTRY, "reason": "delisted"}])
    with pytest.raises(mod.ExclusionRegistryError, match="duplicate ticker AVB"):
        mod.load_exclusion_registry(reg)


@pytest.mark.parametrize(
    "top, match",
    [
        ({"kind": "something_else"}, "kind='something_else'"),
        ({"schema_version": 2}, "schema_version=2"),
        ({"exclusions": {"AVB": AVB_ENTRY}}, "'exclusions' must be a list"),
    ],
)
def test_registry_top_level_violations_rejected(tmp_path, top, match) -> None:
    with pytest.raises(mod.ExclusionRegistryError, match=match):
        mod.load_exclusion_registry(_registry_file(tmp_path, [], **top))


def test_registry_missing_or_corrupt_file_fails_closed(tmp_path) -> None:
    with pytest.raises(mod.ExclusionRegistryError, match="unreadable"):
        mod.load_exclusion_registry(tmp_path / "absent.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(mod.ExclusionRegistryError, match="invalid JSON"):
        mod.load_exclusion_registry(bad)
    bad.write_text("[]")
    with pytest.raises(mod.ExclusionRegistryError, match="must be a JSON object"):
        mod.load_exclusion_registry(bad)


def test_committed_registry_is_valid_and_lists_iac_and_avb() -> None:
    """The registry shipped in THIS repo is the production default: it must
    parse under the strict schema and carry the two reviewed entries."""
    expected = Path(mod.__file__).resolve().parents[2] / "config" / "retrain_universe_exclusions.json"
    assert mod.DEFAULT_EXCLUSION_REGISTRY_PATH == expected
    registry, prov = mod.load_exclusion_registry(mod.DEFAULT_EXCLUSION_REGISTRY_PATH)
    assert {"IAC", "AVB"} <= set(registry)
    assert registry["AVB"].reason == "merged"
    assert registry["AVB"].effective_date == dt.date(2026, 8, 17)
    assert registry["AVB"].evidence_url == SEC_AVB
    assert registry["IAC"].effective_date == dt.date(2026, 5, 12)
    assert registry["IAC"].reason in mod.EXCLUSION_REASONS
    assert all(x.added_by_pr for x in registry.values())
    assert prov["n"] == len(registry)


# ── AVB in the registry → out of the universe, the panel build AND freshness ──


def test_registry_entry_leaves_universe_panel_build_and_freshness(tmp_path, monkeypatch) -> None:
    """AVB (4 sessions behind, in the registry) is removed from the resolved
    universe, never counted stale, absent from the EFFECTIVE inventory handed
    to the panel build (both tier lists), listed with its reason in the report
    and the effective inventory — and the run PROCEEDS with no alert."""
    _inventory(tmp_path, ["AAPL", "AVB", "MSFT"], ["XYZ"])
    md = {"AAPL": FRONTIER, "MSFT": FRONTIER, "XYZ": FRONTIER, "AVB": FRONTIER - dt.timedelta(days=4)}
    ctx = _strict(tmp_path, md, exclusion_registry_path=_registry_file(tmp_path, [AVB_ENTRY]))
    posted = _posted(monkeypatch)

    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert posted == []

    prov = ctx.panel_universe_provenance
    assert prov["n_universe"] == 3 and prov["n_declared"] == 4
    assert prov["registry_excluded"] == {"AVB": AVB_ENTRY_RECORD}
    assert prov["exclusion_registry"]["n"] == 1
    rep = ctx.freshness_report
    assert rep["n_stale"] == 0 and rep["stale_names"] == {} and rep["n_universe"] == 3
    assert rep["excluded_names"] == ["AVB"] and rep["n_excluded"] == 1
    assert rep["registry_excluded"]["AVB"]["reason"] == "merged"
    assert rep["registry_excluded"]["AVB"]["evidence_url"] == SEC_AVB
    # the effective inventory the panel build consumes
    eff = tmp_path / EFFECTIVE_INVENTORY
    assert Path(rep["effective_inventory"]["path"]) == eff == ctx.effective_inventory_path
    assert rep["effective_inventory"]["n_universe"] == 3
    on_disk = json.loads(eff.read_text())
    assert on_disk["tier_A_tickers"] == ["AAPL", "MSFT"]
    assert on_disk["tier_B_tickers"] == ["XYZ"]
    assert on_disk["delisted_tickers"] == ["AVB"]
    assert on_disk["effective_universe"]["registry_excluded"]["AVB"]["reason"] == "merged"
    assert on_disk["effective_universe"]["source"] == str(tmp_path / "data" / "transformer_universe_inventory.json")
    # every other inventory key is preserved verbatim
    assert on_disk["kind"] == "transformer_universe_inventory"
    assert on_disk["generated_utc"] == "2026-06-30T00:00:00+00:00"
    assert on_disk["tier_counts"] == {"A": 3, "B": 1}
    assert not list(eff.parent.glob("*.incoming"))
    # the panel build is handed that file, not the raw inventory
    ctx.dry_run = True  # record the command instead of spawning base-data
    assert mod.BuildAlpha158PanelTask().run(ctx) is True
    cmd = ctx.commands[-1]
    assert "renquant_base_data.alpha158_qlib_panel" in cmd
    assert cmd[-4:] == ["--data-dir", str(tmp_path / "data"), "--inventory", str(eff)]


AVB_ENTRY_RECORD = {k: v for k, v in AVB_ENTRY.items() if k != "ticker"}


def test_panel_build_refuses_a_real_run_without_the_effective_inventory(tmp_path) -> None:
    """Never fall back to the raw inventory (it would re-admit every excluded
    name). A dry-run previews the plain command."""
    ctx = _ctx(tmp_path)
    with pytest.raises(RuntimeError, match="panel build refused"):
        mod.BuildAlpha158PanelTask().run(ctx)
    assert ctx.commands == []
    ctx = _ctx(tmp_path, dry_run=True)
    assert mod.BuildAlpha158PanelTask().run(ctx) is True
    assert "--inventory" not in ctx.commands[-1]


def test_registry_entry_is_not_refreshed_either(tmp_path) -> None:
    _inventory(tmp_path, ["AAPL", "AVB", "MSFT"])
    calls: list[str] = []

    def fake_fetch(sym, *, timeout_sec=None):
        calls.append(sym)
        return _ohlcv(FRONTIER)

    ctx = _ctx(
        tmp_path,
        fetch_fn=fake_fetch,
        expected_session=FRONTIER,
        session_gap_fn=_cal_day_gap,
        exclusion_registry_path=_registry_file(tmp_path, [AVB_ENTRY]),
    )
    assert mod.RefreshFullUniverseOhlcvTask().run(ctx) is True
    assert sorted(calls) == ["AAPL", "MSFT"]
    assert ctx.ohlcv_refresh_summary["n_universe"] == 2


# ── a stale name NOT in the registry still vetoes, and says what to do ────────


def test_stale_name_not_in_registry_vetoes_with_actionable_message(tmp_path, monkeypatch) -> None:
    _inventory(tmp_path, ["AAPL", "AVB", "MSFT"])
    last_bar = FRONTIER - dt.timedelta(days=4)
    md = {"AAPL": FRONTIER, "MSFT": FRONTIER, "AVB": last_bar}
    ctx = _strict(tmp_path, md)  # empty registry
    posted = _posted(monkeypatch)

    with pytest.raises(RuntimeError) as excinfo:
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    msg = str(excinfo.value)
    assert "1/3 panel tickers stale" in msg
    assert f"AVB(-4s, last {last_bar.isoformat()})" in msg  # ticker, lag, last bar
    assert "add a REVIEWED entry to config/retrain_universe_exclusions.json" in msg
    assert str(ctx.exclusion_registry_path) in msg
    assert "otherwise fix ingestion" in msg
    assert "never skipped silently" in msg
    # the informational alert names the registry, then the veto alert
    assert [t for t, *_ in posted] == [
        "RenQuant retrain STALE-NON-WATCHLIST",
        "RenQuant retrain PANEL-FREEZE",
    ]
    info = posted[0][1]
    assert "1 stale panel ticker(s) not in the served watchlist of 3" in info
    assert f"AVB(-4s, last {last_bar.isoformat()})" in info
    assert "NOT excluded" in info
    assert "config/retrain_universe_exclusions.json" in info
    rep = ctx.freshness_report
    assert rep["stale_names"] == {"AVB": 4}
    assert rep["stale_detail"] == {"AVB": {"lag_sessions": 4, "last_bar": last_bar.isoformat()}}
    assert rep["stale_not_served"] == rep["stale_detail"]
    assert rep["served_watchlist"] == {"source": "explicit", "status": "ok", "n": 3}
    assert rep["excluded_names"] == [] and rep["registry_excluded"] == {}
    assert "config/retrain_universe_exclusions.json" in rep["remedy"]
    on_disk = json.loads(
        (tmp_path / "logs" / "daily_retrain_alpha158_fund" / "freshness_report.latest.json").read_text()
    )
    assert on_disk["stale_not_served"] == rep["stale_not_served"]


def test_stale_served_name_vetoes_without_the_non_watchlist_alert(tmp_path, monkeypatch) -> None:
    _inventory(tmp_path, ["AAPL", "MSFT"])
    md = {"AAPL": FRONTIER - dt.timedelta(days=10), "MSFT": FRONTIER}
    ctx = _strict(tmp_path, md)
    posted = _posted(monkeypatch)
    with pytest.raises(RuntimeError, match="panel tickers stale"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    assert [t for t, *_ in posted] == ["RenQuant retrain PANEL-FREEZE"]
    assert ctx.freshness_report["stale_not_served"] == {}
    assert ctx.freshness_report["stale_names"] == {"AAPL": 10}


def test_unavailable_served_watchlist_skips_the_label_but_still_vetoes(tmp_path, monkeypatch) -> None:
    """Labels only: with no served set "non-watchlist" is undefined, so the
    informational alert is skipped (a WARNING says why) — the verdict is the
    strict rule regardless and the veto carries the remedy."""
    _inventory(tmp_path, ["AAPL", "AVB"])
    md = {"AAPL": FRONTIER, "AVB": FRONTIER - dt.timedelta(days=4)}
    ctx = _strict(tmp_path, md, served_watchlist=None, strategy_config_path=tmp_path / "absent.json")
    posted = _posted(monkeypatch)
    with pytest.raises(RuntimeError, match="fix ingestion"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    assert [t for t, *_ in posted] == ["RenQuant retrain PANEL-FREEZE"]
    rep = ctx.freshness_report
    assert rep["served_watchlist"]["status"] == "unavailable"
    assert rep["stale_not_served"] == {}
    assert rep["stale_names"] == {"AVB": 4}


def test_served_watchlist_read_from_strategy_config(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text(json.dumps({"watchlist": ["aapl", " avb "]}))
    _inventory(tmp_path, ["AAPL", "AVB", "ZZZ"])
    md = {"AAPL": FRONTIER, "AVB": FRONTIER - dt.timedelta(days=4), "ZZZ": FRONTIER - dt.timedelta(days=4)}
    ctx = _strict(tmp_path, md, served_watchlist=None, strategy_config_path=cfg)
    _posted(monkeypatch)
    with pytest.raises(RuntimeError, match="panel tickers stale"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    rep = ctx.freshness_report
    assert rep["served_watchlist"] == {"source": str(cfg), "status": "ok", "n": 2}
    assert sorted(rep["stale_names"]) == ["AVB", "ZZZ"]
    assert sorted(rep["stale_not_served"]) == ["ZZZ"]  # AVB is served here → not labelled


# ── IAC keeps working; registry ∪ --exclude-tickers; explicit universe ───────


def test_iac_and_avb_excluded_via_the_committed_registry_without_the_cli_bridge(
    tmp_path, monkeypatch
) -> None:
    """With the umbrella's --exclude-tickers IAC bridge gone, the committed
    registry alone keeps IAC (frozen since 2026-05-12) and AVB out."""
    _inventory(tmp_path, ["AAPL", "AVB", "IAC", "MSFT"])
    md = {"AAPL": FRONTIER, "MSFT": FRONTIER, "IAC": FROZEN, "AVB": FRONTIER - dt.timedelta(days=4)}
    ctx = _strict(tmp_path, md, exclusion_registry_path=mod.DEFAULT_EXCLUSION_REGISTRY_PATH)
    posted = _posted(monkeypatch)
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert posted == []
    rep = ctx.freshness_report
    assert rep["excluded_names"] == ["AVB", "IAC"]
    assert sorted(rep["registry_excluded"]) == ["AVB", "IAC"]
    assert rep["cli_excluded"] == []
    assert rep["n_universe"] == 2 and rep["n_stale"] == 0
    assert "exclusion_registry_path" not in rep["overrides"]  # the default is not an override
    on_disk = json.loads(ctx.effective_inventory_path.read_text())
    assert on_disk["tier_A_tickers"] == ["AAPL", "MSFT"]
    assert on_disk["delisted_tickers"] == ["AVB", "IAC"]


def test_registry_and_exclude_tickers_union(tmp_path, monkeypatch) -> None:
    """The CLI bridge and the registry UNION: each source is reported on its
    own, a name in both is excluded once, and the effective inventory carries
    the union in delisted_tickers."""
    _inventory(tmp_path, ["AAPL", "AVB", "IAC", "MSFT", "ZZZ"], delisted_tickers=["OLD"])
    md = {"AAPL": FRONTIER, "MSFT": FRONTIER, "IAC": FROZEN, "AVB": FROZEN, "ZZZ": FROZEN}
    ctx = _strict(
        tmp_path,
        md,
        exclude_tickers={"IAC", "ZZZ", "AVB"},
        exclusion_registry_path=_registry_file(tmp_path, [AVB_ENTRY]),
    )
    _posted(monkeypatch)
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    prov = ctx.panel_universe_provenance
    assert prov["cli_excluded"] == ["AVB", "IAC", "ZZZ"] and prov["n_cli_excluded"] == 3
    assert sorted(prov["registry_excluded"]) == ["AVB"] and prov["n_registry_excluded"] == 1
    assert prov["inventory_delisted_excluded"] == []  # OLD is not a declared name
    assert prov["n_universe"] == 2
    rep = ctx.freshness_report
    assert rep["excluded_names"] == ["AVB", "IAC", "ZZZ"]
    on_disk = json.loads(ctx.effective_inventory_path.read_text())
    assert on_disk["tier_A_tickers"] == ["AAPL", "MSFT"]
    assert on_disk["delisted_tickers"] == ["AVB", "IAC", "OLD", "ZZZ"]  # inventory key preserved


def test_inventory_delisted_key_flows_into_the_effective_inventory(tmp_path, monkeypatch) -> None:
    _inventory(tmp_path, ["AAPL", "OLD"], delisted_tickers=["OLD"])
    ctx = _strict(tmp_path, {"AAPL": FRONTIER, "OLD": FROZEN})
    _posted(monkeypatch)
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    prov = ctx.panel_universe_provenance
    assert prov["inventory_delisted_excluded"] == ["OLD"] and prov["n_delisted_excluded"] == 1
    assert ctx.freshness_report["excluded_names"] == ["OLD"]
    on_disk = json.loads(ctx.effective_inventory_path.read_text())
    assert on_disk["tier_A_tickers"] == ["AAPL"] and on_disk["delisted_tickers"] == ["OLD"]


def test_registry_applies_to_an_explicit_panel_universe(tmp_path, monkeypatch) -> None:
    md = {"AAPL": FRONTIER, "AVB": FROZEN}
    ctx = _strict(
        tmp_path,
        md,
        panel_universe=["AAPL", "AVB"],
        exclusion_registry_path=_registry_file(tmp_path, [AVB_ENTRY]),
    )
    _posted(monkeypatch)
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    prov = ctx.panel_universe_provenance
    assert prov["source"] == "explicit" and prov["n_declared"] == 2 and prov["n_universe"] == 1
    assert sorted(prov["registry_excluded"]) == ["AVB"]
    on_disk = json.loads(ctx.effective_inventory_path.read_text())
    assert on_disk["tier_A_tickers"] == ["AAPL"] and on_disk["tier_B_tickers"] == []
    assert on_disk["delisted_tickers"] == ["AVB"]
    assert on_disk["effective_universe"]["source"] == "explicit"
    # every explicit name excluded → empty universe → fail closed
    ctx = _strict(tmp_path, md, panel_universe=["AVB"], exclusion_registry_path=ctx.exclusion_registry_path)
    with pytest.raises(mod.InventoryUnavailableError, match="EMPTY after the reviewed exclusion registry"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)


def test_invalid_registry_fails_closed_in_guard_and_refresh(tmp_path) -> None:
    _inventory(tmp_path, ["AAPL"])
    bad = _registry_file(tmp_path, [{**AVB_ENTRY, "reason": "gone"}])
    ctx = _strict(tmp_path, {"AAPL": FRONTIER}, exclusion_registry_path=bad)
    with pytest.raises(mod.ExclusionRegistryError, match="reason 'gone'"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    assert ctx.effective_inventory_path is None
    ctx = _ctx(
        tmp_path,
        fetch_fn=lambda sym, *, timeout_sec=None: _ohlcv(FRONTIER),
        expected_session=FRONTIER,
        session_gap_fn=_cal_day_gap,
        exclusion_registry_path=tmp_path / "absent.json",
    )
    with pytest.raises(mod.ExclusionRegistryError, match="unreadable"):
        mod.RefreshFullUniverseOhlcvTask().run(ctx)


# ── persisted report + overrides + CLI ───────────────────────────────────────


def test_freshness_report_is_persisted_dated_and_latest(tmp_path, monkeypatch) -> None:
    """The report is written to a dated file + a latest copy under the retrain
    log dir (default), next to the effective inventory, so the next run / the
    drift scan can read the stale and excluded sets without parsing a log."""
    _inventory(tmp_path, ["AAPL", "AVB"])
    md = {"AAPL": FRONTIER, "AVB": FRONTIER - dt.timedelta(days=4)}
    ctx = _strict(tmp_path, md, exclusion_registry_path=_registry_file(tmp_path, [AVB_ENTRY]))
    _posted(monkeypatch)
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    log_dir = tmp_path / "logs" / "daily_retrain_alpha158_fund"
    latest = log_dir / "freshness_report.latest.json"
    dated = log_dir / f"freshness_report.{FRONTIER.isoformat()}.json"
    assert ctx.freshness_report["persisted_to"] == {"dated": str(dated), "latest": str(latest)}
    for path in (latest, dated):
        on_disk = json.loads(path.read_text())
        assert on_disk["excluded_names"] == ["AVB"]
        assert on_disk["registry_excluded"]["AVB"]["reason"] == "merged"
        assert on_disk["expected_session"] == FRONTIER.isoformat()
        assert on_disk["effective_inventory"]["path"] == str(log_dir / "effective_universe_inventory.json")
    assert not list(log_dir.glob("*.incoming"))  # atomic replace left no temp


def test_freshness_report_out_override_json_and_directory(tmp_path, monkeypatch) -> None:
    _inventory(tmp_path, ["AAPL"])
    _posted(monkeypatch)
    # a .json path is the 'latest' file, siblings next to it
    ctx = _strict(tmp_path, {"AAPL": FRONTIER}, freshness_report_out=tmp_path / "out" / "fr.json")
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert (tmp_path / "out" / "fr.json").exists()
    assert (tmp_path / "out" / f"freshness_report.{FRONTIER.isoformat()}.json").exists()
    assert ctx.effective_inventory_path == tmp_path / "out" / "effective_universe_inventory.json"
    # a directory holds the default names
    ctx = _strict(tmp_path, {"AAPL": FRONTIER}, freshness_report_out=tmp_path / "outdir")
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert (tmp_path / "outdir" / "freshness_report.latest.json").exists()
    assert (tmp_path / "outdir" / "effective_universe_inventory.json").exists()


def test_report_is_persisted_even_when_the_guard_vetoes(tmp_path, monkeypatch) -> None:
    _inventory(tmp_path, ["AAPL", "MSFT"])
    md = {"AAPL": FRONTIER - dt.timedelta(days=10), "MSFT": FRONTIER}  # served AND stale → veto
    ctx = _strict(tmp_path, md)
    _posted(monkeypatch)
    with pytest.raises(RuntimeError, match="panel tickers stale"):
        mod.PanelUniverseFreshnessGuardTask().run(ctx)
    on_disk = json.loads(
        (tmp_path / "logs" / "daily_retrain_alpha158_fund" / "freshness_report.latest.json").read_text()
    )
    assert on_disk["stale_names"] == {"AAPL": 10}
    assert "fix ingestion" in on_disk["remedy"]


def test_non_default_registry_path_is_recorded_as_an_override(tmp_path, monkeypatch) -> None:
    _inventory(tmp_path, ["AAPL"])
    _posted(monkeypatch)
    ctx = _strict(tmp_path, {"AAPL": FRONTIER})  # _ctx pins a tmp registry
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    ov = ctx.freshness_report["overrides"]["exclusion_registry_path"]
    assert ov == {"value": str(ctx.exclusion_registry_path), "default": str(mod.DEFAULT_EXCLUSION_REGISTRY_PATH)}
    ctx = _strict(tmp_path, {"AAPL": FRONTIER}, exclusion_registry_path=None)
    assert mod.PanelUniverseFreshnessGuardTask().run(ctx) is True
    assert "exclusion_registry_path" not in ctx.freshness_report["overrides"]
    assert ctx.freshness_report["exclusion_registry"]["path"] == str(mod.DEFAULT_EXCLUSION_REGISTRY_PATH)


def test_cli_exclusion_registry_flag_and_presumed_delisted_flags_removed() -> None:
    args = mod.parse_args(["--repo-dir", "/tmp/_test_repo", "--dry-run"])
    assert args.exclusion_registry is None
    assert args.freshness_report_out is None
    args = mod.parse_args(
        ["--repo-dir", "/tmp/_test_repo", "--exclusion-registry", "/tmp/reg.json",
         "--freshness-report-out", "/tmp/fr", "--exclude-tickers", "IAC"]
    )
    assert args.exclusion_registry == Path("/tmp/reg.json")
    assert args.freshness_report_out == Path("/tmp/fr")
    assert args.exclude_tickers == "IAC"
    for flag in (
        ["--presumed-delisted-after-sessions", "5"],
        ["--presumed-delisted-max-fraction", "0.01"],
        ["--served-watchlist-file", "/tmp/wl.json"],
    ):
        with pytest.raises(SystemExit):
            mod.parse_args(["--repo-dir", "/tmp/_test_repo", *flag])
