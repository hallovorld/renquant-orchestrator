"""D1 refactor tests — single-responsibility helpers of ``build_wf_manifest.py``.

Each helper has a dedicated test that asserts ONLY its own contract:
  * ``extract_cutoffs``       — manifest parsing + ISO-datetime trim
  * ``build_train_cmd``       — argv assembly under all flag combos
  * ``manifest_row``          — row schema
  * ``build_manifest_payload``— v2 payload composition

Pre-D1 the script was a 118-line monolith with one ``main()`` that was
untestable without spinning up subprocess. The refactor preserves CLI behaviour
byte-for-byte; this test pins each pure helper.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# `pip install -e` exposes the package; this is a defensive add for local runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from renquant_orchestrator import build_wf_manifest as bm  # noqa: E402


def test_extract_cutoffs_trims_iso_datetime(tmp_path):
    src = tmp_path / "manifest.json"
    src.write_text(json.dumps({
        "retrains": [
            {"cutoff_date": "2022-01-01T00:00:00"},
            {"cutoff_date": "2022-07-09T00:00:00"},
            {"cutoff_date": "2023-01-14"},
        ],
    }))
    out = bm.extract_cutoffs(src)
    assert out == ["2022-01-01", "2022-07-09", "2023-01-14"]


def test_extract_cutoffs_skips_rows_without_cutoff(tmp_path):
    src = tmp_path / "manifest.json"
    src.write_text(json.dumps({
        "retrains": [
            {"cutoff_date": "2022-01-01"},
            {"other_field": "x"},  # no cutoff_date → skipped
            {"cutoff_date": "2022-02-01"},
        ],
    }))
    out = bm.extract_cutoffs(src)
    assert out == ["2022-01-01", "2022-02-01"]


def test_extract_cutoffs_accepts_list_form(tmp_path):
    src = tmp_path / "manifest.json"
    src.write_text(json.dumps([
        {"cutoff_date": "2022-01-01"},
        {"cutoff_date": "2022-02-01"},
    ]))
    out = bm.extract_cutoffs(src)
    assert out == ["2022-01-01", "2022-02-01"]


def test_build_train_cmd_baseline():
    cmd = bm.build_train_cmd(
        cutoff="2022-01-01",
        out_path=Path("/tmp/out/panel-ltr.json"),
        side_label="wf_dropsenti_v3",
        cv_embargo_days=60,
        cv_n_splits=3,
        drop_sentiment=False,
        skip_cv=True,
    )
    assert cmd[0] == sys.executable
    assert "renquant_orchestrator.train_gbdt" in cmd
    assert "--train-cutoff" in cmd and "2022-01-01" in cmd
    assert "--side-label" in cmd and "wf_dropsenti_v3" in cmd
    assert "--cv-embargo-days" in cmd and "60" in cmd
    assert "--cv-n-splits" in cmd and "3" in cmd
    assert "--skip-cv" in cmd
    assert "--drop-sentiment" not in cmd
    assert "--data-dir" not in cmd
    assert "--strategy-config" not in cmd


def test_build_train_cmd_drop_sentiment_and_no_skip_cv():
    cmd = bm.build_train_cmd(
        cutoff="2022-01-01",
        out_path=Path("/tmp/out/x.json"),
        side_label="sl",
        cv_embargo_days=10,
        cv_n_splits=5,
        drop_sentiment=True,
        skip_cv=False,
        data_dir="/data/root",
        strategy_config="/cfg/strategy_config.json",
    )
    assert "--drop-sentiment" in cmd
    assert "--skip-cv" not in cmd
    assert "--cv-embargo-days" in cmd and "10" in cmd
    assert "--data-dir" in cmd and "/data/root" in cmd
    assert "--strategy-config" in cmd and "/cfg/strategy_config.json" in cmd


def test_default_strategy_config_prefers_strategy_subrepo(monkeypatch, tmp_path):
    strategy = tmp_path / "renquant-strategy-104" / "configs" / "strategy_config.json"
    legacy = tmp_path / "RenQuant" / "backtesting" / "renquant_104" / "strategy_config.json"
    strategy.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    strategy.write_text("{}", encoding="utf-8")
    legacy.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(bm, "DEFAULT_STRATEGY_CONFIG", strategy)
    monkeypatch.setattr(bm, "LEGACY_STRATEGY_CONFIG", legacy)

    assert bm.default_strategy_config() == str(strategy.resolve())


def test_training_env_sets_data_and_strategy_roots(tmp_path):
    env = bm.training_env(
        tmp_path / "RenQuant" / "data",
        "/cfg/strategy_config.json",
    )

    assert env["RENQUANT_DATA_ROOT"] == str(tmp_path / "RenQuant")
    assert env["RENQUANT_STRATEGY_CONFIG"] == "/cfg/strategy_config.json"


def test_manifest_row_shape():
    row = bm.manifest_row(artifact_uri=Path("/tmp/a/b/c.json"), cutoff="2024-01-02")
    assert set(row) == {"artifact_uri", "cutoff_date", "lookahead_days", "trained_date"}
    assert row["cutoff_date"] == "2024-01-02"
    assert row["lookahead_days"] == 60
    # trained_date is today's date in ISO form — at minimum, parseable
    import datetime
    datetime.date.fromisoformat(row["trained_date"])


def test_manifest_row_custom_lookahead():
    row = bm.manifest_row(artifact_uri=Path("/x.json"), cutoff="2024-01-02",
                          lookahead_days=30)
    assert row["lookahead_days"] == 30


def test_build_manifest_payload_includes_required_keys(tmp_path):
    src = tmp_path / "src.json"; src.write_text("{}")
    payload = bm.build_manifest_payload(
        rows=[{"artifact_uri": "/x", "cutoff_date": "2024-01-02",
               "lookahead_days": 60, "trained_date": "2026-05-30"}],
        source_manifest_path=src,
        options={"drop_sentiment": True, "cv_embargo_days": 60,
                 "cv_n_splits": 3, "skip_cv": True,
                 "data_dir": "/data", "strategy_config": "/cfg.json"},
        failed_cutoffs=[],
    )
    assert payload["schema_version"] == 2
    assert payload["built_by"] == "renquant_orchestrator.build_wf_manifest"
    assert payload["trainer"] == "renquant_orchestrator.train_gbdt"
    assert payload["options"]["drop_sentiment"] is True
    assert payload["failed_cutoffs"] == []
    assert len(payload["retrains"]) == 1
    # built_at should be parseable as ISO-8601 UTC
    assert payload["built_at"].endswith("Z")
