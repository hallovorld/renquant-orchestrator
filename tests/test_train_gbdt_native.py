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


def _make_data_dir(tmp: Path, n_dates: int = 40, n_tickers: int = 10, seed: int = 4,
                   label_complete_dates: int | None = None) -> Path:
    """Write a tiny synthetic data_dir.

    ``label_complete_dates=k`` leaves the label NULL on every date after the
    k-th, i.e. the panel's last LABEL-COMPLETE date is ``dates[k - 1]`` while
    its last FEATURE date stays ``dates[-1]`` — the real shape of a serving
    panel, and the shape that makes the two candidate answers differ.
    """
    tmp.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
    rows, fund = [], []
    for i, d in enumerate(dates):
        labeled = label_complete_dates is None or i < label_complete_dates
        for t in range(n_tickers):
            x = rng.normal(size=3)
            label = 0.6 * x[0] - 0.3 * x[1] + rng.normal(scale=0.5)
            rows.append({"date": d, "ticker": f"T{t}", "a0": x[0], "a1": x[1], "a2": x[2],
                         "fwd_60d_excess": label if labeled else None})
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


def _run_driver(*args: str) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, str(DRIVER), *args], capture_output=True, text=True)
    assert r.returncode == 0, f"driver failed:\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}"
    return r


# ---------------------------------------------------------------------------
# The WF-gate training cutoff (``effective_train_cutoff_date``)
# ---------------------------------------------------------------------------

def test_stamped_cutoff_is_the_last_label_complete_date(tmp_path: Path) -> None:
    """Full-panel retrain (no --train-cutoff): the stamp is the DATA's last
    label-complete date — not the panel's last feature date, not the wall clock.

    Without it the WF gate refuses the artifact outright ("trained_date is
    wall-clock metadata and cannot prove OOS label separation").
    """
    n_dates, n_tickers, complete = 40, 6, 25
    data_dir = _make_data_dir(tmp_path / "data", n_dates=n_dates, n_tickers=n_tickers,
                              label_complete_dates=complete)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
    expected = dates[complete - 1].date().isoformat()
    assert expected != dates[-1].date().isoformat()

    out = tmp_path / "panel-ltr.json"
    _run_driver("--data-dir", str(data_dir), "--output-path", str(out),
                "--num-boost-round", "10", "--skip-cv",
                "--skip-sentiment-gate", "--strategy-config", "none")
    art = json.loads(out.read_text())

    assert art["effective_train_cutoff_date"] == expected
    contract = art["metadata"]["training_contract"]
    assert contract["last_label_complete_date"] == expected
    assert contract["effective_train_cutoff_date"] == expected
    assert contract["effective_train_cutoff_source"] == "derived_last_label_complete_date"
    assert contract["label_col"] == "fwd_60d_excess"
    assert contract["lookahead_days"] == 60
    assert contract["n_rows"] == complete * n_tickers
    assert contract["dataset"].endswith("alpha158_291_fundamental_dataset.parquet")
    # The gate reads the cutoff off the payload ROOT — prove it is reachable there.
    assert _wf_gate_cutoff(art) == pd.Timestamp(expected)


def test_wf_fold_stamp_stays_consistent_with_train_cutoff(tmp_path: Path) -> None:
    """--train-cutoff path: renquant-model's (cutoff - embargo) stamp is KEPT and
    the derived last label-complete date is recorded alongside it, strictly
    inside it — the two can never disagree silently."""
    data_dir = _make_data_dir(tmp_path / "data", n_dates=200, n_tickers=5)
    out = tmp_path / "walkforward" / "fold.json"
    cutoff = "2020-09-01"
    _run_driver("--data-dir", str(data_dir), "--output-path", str(out),
                "--train-cutoff", cutoff, "--side-label", "ci",
                "--num-boost-round", "10", "--skip-cv",
                "--skip-sentiment-gate", "--strategy-config", "none")
    art = json.loads(out.read_text())

    stamped = art["effective_train_cutoff_date"]
    # Unchanged fold semantics: cutoff - lookahead business days.
    assert pd.Timestamp(stamped) == pd.Timestamp(cutoff) - pd.offsets.BDay(60)
    contract = art["metadata"]["training_contract"]
    assert contract["effective_train_cutoff_source"] == "train_cutoff_minus_embargo"
    assert contract["train_cutoff_date"] == cutoff
    assert contract["effective_train_cutoff_date"] == stamped
    assert (pd.Timestamp(contract["last_label_complete_date"])
            < pd.Timestamp(stamped)), "a fold must not train on labels past its cutoff"


def test_stamp_is_metadata_only_booster_byte_identical(tmp_path: Path) -> None:
    """The load-bearing test: stamping must not change training.

    Baseline = renquant-model's own stamp-free ``build_training_pipeline()``,
    which IS the path main() ran before this change, on the same inputs. The
    booster bytes, the fitted normalization AND the v1 model-content
    fingerprint must all be identical; only metadata may differ.
    """
    from renquant_model_gbdt import GbdtTrainingContext, build_training_pipeline
    from renquant_model_gbdt.panel_trainer import DEFAULT_LABEL, PANEL_LTR_PARAMS

    data_dir = _make_data_dir(tmp_path / "data", n_dates=60, n_tickers=8,
                              label_complete_dates=45)
    baseline_out = tmp_path / "baseline.json"
    ctx = GbdtTrainingContext(
        label=DEFAULT_LABEL, params=dict(PANEL_LTR_PARAMS), num_boost_round=15,
        skip_cv=True, data_dir=str(data_dir), output_path=str(baseline_out),
        train_run_id="fixed", training_notes="identity-baseline",
    )
    assert build_training_pipeline().run(ctx).ok
    baseline = json.loads(baseline_out.read_text())
    # Pre-change behaviour: the full-panel path stamped no cutoff at all.
    assert "effective_train_cutoff_date" not in baseline

    stamped_out = tmp_path / "stamped.json"
    _run_driver("--data-dir", str(data_dir), "--output-path", str(stamped_out),
                "--num-boost-round", "15", "--skip-cv",
                "--skip-sentiment-gate", "--strategy-config", "none")
    stamped = json.loads(stamped_out.read_text())

    assert stamped["booster_raw_json"] == baseline["booster_raw_json"]
    assert stamped["feature_means"] == baseline["feature_means"]
    assert stamped["feature_stds"] == baseline["feature_stds"]
    assert stamped["panel_shape"] == baseline["panel_shape"]
    assert stamped["training_train_ic"] == baseline["training_train_ic"]
    # Both stamp a self-describing content hash (--strategy-config none): equal
    # hashes prove every field this change adds is fingerprint-OPERATIONAL.
    assert stamped["config_fingerprint"] == baseline["config_fingerprint"]
    # …and the new metadata really is there (so the assertions above are not
    # comparing two identical no-op runs).
    assert stamped["effective_train_cutoff_date"]
    assert stamped["metadata"]["training_contract"]["last_label_complete_date"]
    assert stamped["metadata"]["inference_smoke_test"]["all_finite"] is True


def _wf_gate_cutoff(artifact: dict):
    """The WF gate's own resolver, when renquant-backtesting is importable."""
    runner = pytest.importorskip("renquant_backtesting.wf_gate.runner")
    return runner._effective_artifact_cutoff(artifact)


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
