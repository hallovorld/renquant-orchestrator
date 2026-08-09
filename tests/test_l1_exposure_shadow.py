"""L1 exposure-shadow logger: pure math + append-only + fail-closed contracts.

All tests use tmp dirs and synthetic data; nothing touches RenQuant or a
real DB.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from renquant_orchestrator import l1_exposure_shadow as l1


# --- pure helpers -------------------------------------------------------------


def test_regime_multiplier_matches_the_frozen_form():
    assert l1.regime_multiplier("BULL_CALM", 0.9) == 1.0
    assert l1.regime_multiplier("BEAR", 1.0) == pytest.approx(0.5)
    assert l1.regime_multiplier("BEAR", 0.5) == pytest.approx(0.75)
    assert l1.regime_multiplier("BULL_VOLATILE", 1.0) == pytest.approx(0.75)
    # absent/garbage confidence degrades to no reduction, never to negative g
    assert l1.regime_multiplier("BEAR", None) == 1.0
    assert l1.regime_multiplier("BEAR", float("nan")) == 1.0
    assert l1.regime_multiplier(None, 0.9) == 1.0


def test_target_exposure_clips_both_ends():
    # low vol -> uncapped raw target above 1 -> clipped to E_MAX
    assert l1.target_exposure(0.05, 1.0) == l1.E_MAX
    # high vol + bear shrink -> floor
    assert l1.target_exposure(2.0, 0.5) == l1.E_MIN
    # interior point: 0.15/0.20 * 0.8 = 0.6
    assert l1.target_exposure(0.20, 0.8) == pytest.approx(0.6)
    with pytest.raises(ValueError):
        l1.target_exposure(0.0, 1.0)
    with pytest.raises(ValueError):
        l1.target_exposure(float("nan"), 1.0)


def test_build_row_carries_components_and_gap():
    snap = {"run_date": "2026-08-08", "regime": "BEAR", "confidence": 0.8,
            "cash": 8000.0, "portfolio_value": 10000.0}
    row = l1.build_row(snapshot=snap, sigma_hat=0.25, asof=date(2026, 8, 8),
                       vol_input_cutoff=date(2026, 8, 8),
                       vol_input_last_date=date(2026, 8, 7))
    assert row["schema"] == l1.SCHEMA
    assert row["g"] == pytest.approx(1 - 0.5 * 0.8)
    assert row["achieved_exposure"] == pytest.approx(0.2)
    # target = clip(0.15/0.25 * 0.6, 0.3, 1.0) = 0.36
    assert row["target_exposure"] == pytest.approx(0.36)
    assert row["gap"] == pytest.approx(0.16)
    # components allow recomputation under ANY sigma*: sigma_hat and g present
    assert row["sigma_hat"] == 0.25 and "params" in row
    # the temporal-integrity metadata is persisted, so the row is auditable
    assert row["vol_input_cutoff"] == "2026-08-08"
    assert row["vol_input_last_date"] == "2026-08-07"


def test_append_row_is_append_only_per_date(tmp_path):
    row = {"schema": l1.SCHEMA, "asof": "2026-08-08", "target_exposure": 0.5}
    out = l1.append_row(tmp_path, dict(row))
    assert out.exists()
    with pytest.raises(RuntimeError, match="append-only"):
        l1.append_row(tmp_path, dict(row))
    l1.append_row(tmp_path, {**row, "asof": "2026-08-09"})  # next date fine
    assert len(out.read_text().splitlines()) == 2


# --- CLI fail-closed ----------------------------------------------------------


def _mk_db(path: Path, run_date: str) -> None:
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE live_state_snapshots (run_date TEXT, regime TEXT,"
                    " confidence REAL, cash REAL, portfolio_value REAL)")
        con.execute("INSERT INTO live_state_snapshots VALUES (?,?,?,?,?)",
                    (run_date, "BULL_CALM", 0.6, 5000.0, 10000.0))


def test_cli_refuses_a_stale_snapshot(tmp_path, capsys):
    db = tmp_path / "runs.db"
    _mk_db(db, "2020-01-01")  # long past
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"sector_map": {"AAPL": "giant_tech"}}))
    rc = l1.main(["--repo-root", str(tmp_path), "--db", str(db),
                  "--sector-map-config", str(cfg),
                  "--ohlcv-root", str(tmp_path / "ohlcv"),
                  "--log-dir", str(tmp_path / "logs")])
    assert rc == 1
    assert "REFUSED-STALE-SNAPSHOT" in capsys.readouterr().out
    assert not (tmp_path / "logs").exists()  # nothing written on refusal


def test_cli_refuses_a_thin_universe(tmp_path, capsys):
    db = tmp_path / "runs.db"
    _mk_db(db, date.today().isoformat())
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"sector_map": {"AAPL": "giant_tech"}}))
    (tmp_path / "ohlcv").mkdir()  # empty: zero names resolvable
    rc = l1.main(["--repo-root", str(tmp_path), "--db", str(db),
                  "--sector-map-config", str(cfg),
                  "--ohlcv-root", str(tmp_path / "ohlcv"),
                  "--log-dir", str(tmp_path / "logs")])
    assert rc == 1
    out = capsys.readouterr().out
    assert "REFUSED" in out and "thin universe" in out
    assert not (tmp_path / "logs").exists()


# --- temporal integrity (codex on orch#920) -----------------------------------
#
# AUDIT REGRESSION GUARD: a row logged against a day-t snapshot must be a pure
# function of OHLCV sessions STRICTLY BEFORE t. A delayed run, a same-day
# partial bar, or a later OHLCV refresh must not be able to change what the
# row says for that snapshot date.


def _synthetic_closes(tickers, dates):
    """Full per-ticker OHLCV frames; deterministic, seeded per ticker."""
    import numpy as np
    import pandas as pd

    frames = {}
    for i, t in enumerate(tickers):
        rng = np.random.default_rng(1000 + i)
        rets = rng.normal(0.0, 0.01, len(dates))
        close = pd.Series(100.0 * np.cumprod(1.0 + rets),
                          index=pd.DatetimeIndex(dates), name="close")
        frames[t] = pd.DataFrame({"close": close, "dividend": 0.0})
    return frames


def _write_ohlcv(root, frames):
    for t, df in frames.items():
        d = root / t
        d.mkdir(parents=True, exist_ok=True)
        df.to_parquet(d / "1d.parquet")


def test_vol_input_stops_strictly_before_the_cutoff(tmp_path):
    import pandas as pd

    tickers = ["AA", "BB", "CC"]
    dates = pd.bdate_range("2026-06-01", periods=40)
    cutoff = dates[30].date()
    frames = _synthetic_closes(tickers, dates)

    # completed history only: sessions strictly before the snapshot date
    _write_ohlcv(tmp_path, {t: df.iloc[:30] for t, df in frames.items()})
    base = l1.universe_ew_returns(tmp_path, tickers, cutoff=cutoff, min_names=3)
    assert base.index.max() < pd.Timestamp(cutoff)
    sigma_base = l1.ewma_vol_annualized(base)

    # the tree then gains a bar ON the cutoff day (partial) plus later sessions
    _write_ohlcv(tmp_path, frames)
    after = l1.universe_ew_returns(tmp_path, tickers, cutoff=cutoff, min_names=3)
    pd.testing.assert_series_equal(after, base)
    assert l1.ewma_vol_annualized(after) == sigma_base

    # a cutoff with no completed session before it fails closed, never invents
    with pytest.raises(RuntimeError, match="no completed sessions"):
        l1.universe_ew_returns(tmp_path, tickers, cutoff=dates[0].date(),
                               min_names=3)


def test_future_ohlcv_cannot_change_the_row_for_a_fixed_snapshot_date(tmp_path):
    """End-to-end: same snapshot, OHLCV tree mutated afterwards -> same row."""
    import pandas as pd

    today = date.today()
    tickers = [f"T{i:02d}" for i in range(32)]  # above the 30-name floor
    completed = pd.bdate_range(end=pd.Timestamp(today) - pd.Timedelta(days=1),
                               periods=34)
    extended = completed.append(pd.DatetimeIndex(
        [pd.Timestamp(today), pd.Timestamp(today) + pd.Timedelta(days=1)]))
    frames = _synthetic_closes(tickers, extended)

    db = tmp_path / "runs.db"
    _mk_db(db, today.isoformat())
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"sector_map": {t: "tech" for t in tickers}}))

    def run(ohlcv_dir, log_dir, per_ticker_frames):
        _write_ohlcv(tmp_path / ohlcv_dir, per_ticker_frames)
        rc = l1.main(["--repo-root", str(tmp_path), "--db", str(db),
                      "--sector-map-config", str(cfg),
                      "--ohlcv-root", str(tmp_path / ohlcv_dir),
                      "--log-dir", str(tmp_path / log_dir)])
        assert rc == 0
        line = (tmp_path / log_dir / "l1_exposure_shadow.jsonl").read_text()
        return json.loads(line.splitlines()[-1])

    # run 1: only completed sessions exist on disk
    row1 = run("ohlcv_a", "logs_a",
               {t: df.iloc[:34] for t, df in frames.items()})
    # run 2: the tree now also holds a same-day partial bar + a future bar
    row2 = run("ohlcv_b", "logs_b", frames)

    for key in ("sigma_hat", "target_exposure", "gap",
                "vol_input_cutoff", "vol_input_last_date"):
        assert row1[key] == row2[key], key
    assert row1["vol_input_cutoff"] == today.isoformat()
    assert row1["vol_input_last_date"] == completed[-1].date().isoformat()
