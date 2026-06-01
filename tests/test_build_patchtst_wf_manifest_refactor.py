"""D2 refactor tests — single-responsibility helpers of ``build_patchtst_wf_manifest.py``.

Each helper has a dedicated test:
  * ``extract_cutoffs``       — manifest parsing + cadence subsampling + first/last preservation
  * ``build_train_cmd``       — hf_trainer argv assembly under all flag combos
  * ``resolve_data_root``     — env-var + parent-walk fallback path resolution
  * ``manifest_row``          — row schema
  * ``build_manifest_payload``— v2 payload composition
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from renquant_orchestrator import build_patchtst_wf_manifest as bm  # noqa: E402


def _write_model_sidecar(path: Path, *, effective_cutoff: str = "2024-01-01") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")
    path.with_name(path.name + ".metadata.json").write_text(json.dumps({
        "training_contract": {
            "trained_date": "2026-06-01",
            "effective_train_cutoff_date": effective_cutoff,
            "lookahead_days": 60,
        }
    }))


def test_extract_cutoffs_no_cadence(tmp_path):
    src = tmp_path / "m.json"
    src.write_text(json.dumps({"retrains": [
        {"cutoff_date": "2022-01-01"}, {"cutoff_date": "2022-02-01"},
        {"cutoff_date": "2022-03-01"},
    ]}))
    assert bm.extract_cutoffs(src, None) == ["2022-01-01", "2022-02-01", "2022-03-01"]
    assert bm.extract_cutoffs(src, 0) == ["2022-01-01", "2022-02-01", "2022-03-01"]


def test_extract_cutoffs_cadence_subsamples_and_preserves_endpoints(tmp_path):
    src = tmp_path / "m.json"
    # weekly cadence over 1 year (~52 cutoffs)
    cutoffs = []
    d = datetime.date(2022, 1, 1)
    for _ in range(52):
        cutoffs.append({"cutoff_date": d.isoformat()})
        d += datetime.timedelta(days=7)
    last_date = d - datetime.timedelta(days=7)
    src.write_text(json.dumps({"retrains": cutoffs}))
    selected = bm.extract_cutoffs(src, 180)  # semi-annual
    # Sparser than the 52 weekly entries
    assert 2 <= len(selected) <= 5
    # Always keeps the first and last cutoff
    assert selected[0] == "2022-01-01"
    assert selected[-1] == last_date.isoformat()
    # Spacing ≥ cadence_days between adjacent (except possibly first/last pair)
    for i in range(len(selected) - 1):
        d1 = datetime.date.fromisoformat(selected[i])
        d2 = datetime.date.fromisoformat(selected[i + 1])
        # Allow last-pair below cadence (last is force-included)
        if i < len(selected) - 2:
            assert (d2 - d1).days >= 180


def test_build_train_cmd_baseline_includes_tuned():
    cmd = bm.build_train_cmd(
        cutoff="2024-01-02",
        out_path=Path("/tmp/out"),
        epochs=4,
        device="mps",
        seed=42,
        cross_stock_attn=False,
        film_regime_cond=False,
        exclude_features=None,
        strategy_config=None,
    )
    assert cmd[0] == sys.executable
    assert "renquant_model_patchtst.hf_trainer" in cmd
    assert "--cut" in cmd and "all" in cmd
    assert "--train-cutoff" in cmd and "2024-01-02" in cmd
    assert "--epochs" in cmd and "4" in cmd
    assert "--device" in cmd and "mps" in cmd
    assert "--seed" in cmd and "42" in cmd
    assert "--label" in cmd and bm.DEFAULT_LABEL in cmd
    # tuned baseline applied
    assert "--lr" in cmd and "1e-4" in cmd
    assert "--weight-decay" in cmd and "0.3" in cmd
    assert "--seq-len" in cmd and "24" in cmd
    assert "--early-stopping-patience" in cmd and "2" in cmd
    assert "--save-model" in cmd
    assert "--output-dir" in cmd and "/tmp/out" in cmd
    # flags absent when disabled
    assert "--cross-stock-attn" not in cmd
    assert "--film-regime-cond" not in cmd
    assert "--exclude-features" not in cmd
    assert "--strategy-config" not in cmd
    assert "--dataset" not in cmd
    assert "--spy-path" not in cmd


def test_build_train_cmd_with_flags():
    cmd = bm.build_train_cmd(
        cutoff="2024-01-02",
        out_path=Path("/tmp/out"),
        epochs=8,
        device="cpu",
        seed=44,
        cross_stock_attn=True,
        film_regime_cond=True,
        exclude_features="mean_sentiment,n_articles_log",
        strategy_config="strategy_config.shadow.json",
        dataset_path="/data/transformer.parquet",
        spy_path="/data/SPY.parquet",
    )
    assert "--cross-stock-attn" in cmd
    assert "--film-regime-cond" in cmd
    assert "--exclude-features" in cmd and "mean_sentiment,n_articles_log" in cmd
    assert "--strategy-config" in cmd and "strategy_config.shadow.json" in cmd
    assert "--dataset" in cmd and "/data/transformer.parquet" in cmd
    assert "--spy-path" in cmd and "/data/SPY.parquet" in cmd


def test_build_calibrator_cmd_uses_model_repo_entrypoint():
    cmd = bm.build_calibrator_cmd(
        scorer_artifact=Path("/tmp/model.pt"),
        out_path=Path("/tmp/calibration.json"),
        panel_path="/data/panel.parquet",
        raw_label_panel_path="/data/raw.parquet",
        label="fwd_60d_excess",
        data_end="2024-04-01",
        batch_size=512,
        method="platt",
        min_rows=1000,
    )
    assert "renquant_model_patchtst.fit_calibrator" in cmd
    assert "--scorer-artifact" in cmd and "/tmp/model.pt" in cmd
    assert "--panel" in cmd and "/data/panel.parquet" in cmd
    assert "--raw-label-panel" in cmd and "/data/raw.parquet" in cmd
    assert "--data-end" in cmd and "2024-04-01" in cmd


def test_data_end_for_cutoff_subtracts_label_lookahead_business_days():
    assert bm.data_end_for_cutoff("2024-04-01", "fwd_60d_excess") == "2024-01-08"


def test_resolve_data_root_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RENQUANT_DATA_ROOT", str(tmp_path))
    out = bm.resolve_data_root()
    assert out == tmp_path.resolve()


def test_resolve_data_root_no_env_no_data_returns_none(monkeypatch):
    monkeypatch.delenv("RENQUANT_STRATEGY_DIR", raising=False)
    monkeypatch.delenv("RENQUANT_DATA_ROOT", raising=False)
    monkeypatch.setattr(bm, "DEFAULT_DATA_ROOT", Path("/definitely/missing"))
    # The walk-parents fallback finds nothing in any reasonable test env
    out = bm.resolve_data_root()
    # Either None or a real umbrella path (if test is run from inside umbrella)
    assert out is None or (out / bm.DEFAULT_DATASET_REL).exists()


def test_default_strategy_config_prefers_strategy_subrepo(monkeypatch, tmp_path):
    strategy = tmp_path / "renquant-strategy-104" / "configs" / "strategy_config.json"
    legacy = tmp_path / "RenQuant" / "backtesting" / "renquant_104" / "strategy_config.json"
    strategy.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    strategy.write_text("{}", encoding="utf-8")
    legacy.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("RENQUANT_STRATEGY_CONFIG", raising=False)
    monkeypatch.setattr(bm, "DEFAULT_STRATEGY_CONFIG", strategy)
    monkeypatch.setattr(bm, "LEGACY_STRATEGY_CONFIG", legacy)

    assert bm.default_strategy_config() == str(strategy.resolve())


def test_manifest_row_shape(tmp_path):
    artifact = tmp_path / "hf_patchtst_all_seed42_model.pt"
    calibrator = tmp_path / "hf_patchtst-calibration.json"
    calibrator.write_text("{}")
    _write_model_sidecar(artifact, effective_cutoff="2024-01-02")
    row = bm.manifest_row(artifact=artifact, cutoff="2024-01-02", calibrator=calibrator)
    assert set(row) == {
        "artifact_uri",
        "calibrator_uri",
        "cutoff_date",
        "effective_train_cutoff_date",
        "lookahead_days",
        "trained_date",
    }
    assert row["lookahead_days"] == 60


def test_build_manifest_payload_includes_required_keys(tmp_path):
    src = tmp_path / "src.json"; src.write_text("{}")
    payload = bm.build_manifest_payload(
        rows=[{"artifact_uri": "/x.pt", "cutoff_date": "2024-01-02",
               "lookahead_days": 60, "trained_date": "2026-05-30"}],
        source_manifest_path=src,
        options={"cadence_days": 180, "epochs": 4, "device": "mps", "seed": 42,
                 "cross_stock_attn": True, "film_regime_cond": False,
                 "exclude_features": None, "strategy_config": None},
        failed_cutoffs=["2024-04-01"],
    )
    assert payload["schema_version"] == 2
    assert payload["built_by"] == "renquant_orchestrator.build_patchtst_wf_manifest"
    assert payload["trainer"] == "renquant_model_patchtst.hf_trainer"
    assert payload["failed_cutoffs"] == ["2024-04-01"]
    assert payload["options"]["cadence_days"] == 180
    assert payload["built_at"].endswith("Z")
