"""The self-contained GBDT driver trains a complete model from a data_dir.

Creates tiny synthetic parquets + stats, invokes train_gbdt.py (script mode, so it
bootstraps its own pin paths without the package __init__), and asserts a valid
version:3 artifact is written — proving the orchestrator trains the model entirely
through the subrepos with no umbrella code and no real data.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("xgboost")

ORCH_SRC = Path(__file__).resolve().parents[1] / "src"
DRIVER = ORCH_SRC / "renquant_orchestrator" / "train_gbdt.py"
FUND_COLS = ["earnings_yield", "book_to_price", "gross_profitability", "roe", "asset_growth"]


def _make_data_dir(tmp: Path, n_dates: int = 40, n_tickers: int = 10, seed: int = 4) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
    rows, fund = [], []
    for d in dates:
        for t in range(n_tickers):
            x = rng.normal(size=3)
            rows.append({"date": d, "ticker": f"T{t}", "a0": x[0], "a1": x[1], "a2": x[2],
                         "fwd_60d_excess": 0.6 * x[0] - 0.3 * x[1] + rng.normal(scale=0.5)})
            fund.append({"date": d, "ticker": f"T{t}", **{c: float(rng.normal()) for c in FUND_COLS}})
    pd.DataFrame(rows).to_parquet(tmp / "alpha158_291_fundamental_dataset.parquet")
    pd.DataFrame(fund).to_parquet(tmp / "sec_fundamentals_daily.parquet")
    (tmp / "alpha158_qlib_dataset.stats.json").write_text(json.dumps(
        {"feature_cols": ["a0", "a1", "a2"], "feature_means": [0.0, 0.0, 0.0],
         "feature_stds": [1.0, 1.0, 1.0]}))
    return tmp


def test_native_driver_trains_complete_artifact(tmp_path: Path) -> None:
    """Self-contained research mode: no umbrella, no sentiment gate, content fp."""
    data_dir = _make_data_dir(tmp_path / "data")
    out = tmp_path / "panel-ltr.json"
    r = subprocess.run(
        [sys.executable, str(DRIVER), "--data-dir", str(data_dir),
         "--output-path", str(out), "--num-boost-round", "20",
         "--cv-n-splits", "3", "--cv-embargo-days", "2",
         "--skip-sentiment-gate", "--strategy-config", "none"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"driver failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"
    assert out.exists(), "driver did not write the artifact"
    art = json.loads(out.read_text())
    assert art["kind"] == "panel_ltr_xgboost" and art["version"] == 3
    assert art["booster_raw_json"]
    assert art["config_fingerprint"].startswith("sha256:")
    assert art["feature_cols"] == ["a0", "a1", "a2"]
    assert art["oos_per_fold_ic"]
    assert art["metadata"]["inference_smoke_test"]["all_finite"] is True


def test_default_strategy_config_prefers_strategy_subrepo(monkeypatch, tmp_path: Path) -> None:
    from renquant_orchestrator import train_gbdt

    subrepo = tmp_path / "renquant-strategy-104" / "configs" / "strategy_config.json"
    legacy = tmp_path / "RenQuant" / "backtesting" / "renquant_104" / "strategy_config.json"
    subrepo.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    subrepo.write_text("{}")
    legacy.write_text("{}")
    monkeypatch.setattr(train_gbdt, "DEFAULT_STRATEGY_CONFIG", subrepo)
    monkeypatch.setattr(train_gbdt, "LEGACY_STRATEGY_CONFIG", legacy)

    assert train_gbdt._default_strategy_config() == subrepo

    subrepo.unlink()
    assert train_gbdt._default_strategy_config() == legacy


_UMBRELLA = Path(__file__).resolve().parents[2] / "RenQuant"
_REAL_DATA = _UMBRELLA / "data" / "alpha158_291_fundamental_dataset.parquet"
_SPY = _UMBRELLA / "data" / "ohlcv" / "SPY" / "1d.parquet"
_STRATEGY = _UMBRELLA / "backtesting" / "renquant_104" / "strategy_config.json"


@pytest.mark.skipif(not (_REAL_DATA.exists() and _SPY.exists() and _STRATEGY.exists()),
                    reason="production data/SPY/strategy config absent (skipped outside workstation)")
def test_production_path_artifact_passes_panel_contract(tmp_path: Path) -> None:
    """Production mode: real fingerprint + sentiment gate → the artifact must pass
    the renquant-artifacts panel contract (i.e. the runtime scorer can load it)."""
    sys.path.insert(0, str(_UMBRELLA.parent / "renquant-artifacts" / "src"))
    sys.path.insert(0, str(_UMBRELLA.parent / "renquant-common" / "src"))
    from renquant_artifacts import validate_panel_artifact_contract

    out = tmp_path / "walkforward_prod.json"
    r = subprocess.run(
        [sys.executable, str(DRIVER), "--train-cutoff", "2019-01-01",
         "--side-label", "ci", "--output-path", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"driver failed:\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}"
    art = json.loads(out.read_text())
    from renquant_orchestrator import train_gbdt

    expected_fp, _ = train_gbdt._production_fingerprint(
        train_gbdt._default_strategy_config(),
    )
    assert expected_fp is not None
    assert art["config_fingerprint"] == expected_fp, (
        "artifact fingerprint must match the current production strategy config"
    )
    assert art["sentiment_runtime_gate_contract"] == "trained_zeroing"
    result = validate_panel_artifact_contract(art, strict=True)
    assert result.ok, f"panel contract failed: {result.errors}"
