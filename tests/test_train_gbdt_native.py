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
    data_dir = _make_data_dir(tmp_path / "data")
    out = tmp_path / "panel-ltr.json"
    r = subprocess.run(
        [sys.executable, str(DRIVER), "--data-dir", str(data_dir),
         "--output-path", str(out), "--num-boost-round", "20",
         "--cv-n-splits", "3", "--cv-embargo-days", "2"],
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
