"""Tests for the deterministic data-dependency contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator.cloud.data_contract import (
    ContractCheck,
    ContractReport,
    verify_staged,
    verify_remote,
)


@pytest.fixture
def staged_dirs(tmp_path: Path) -> dict:
    """Create a minimal valid staging layout."""
    bundle = tmp_path / "bundle"
    ohlcv = tmp_path / "ohlcv"
    data = tmp_path / "data"

    # Code entry points
    for rel in (
        "kernel/panel_pipeline/job_panel_scoring.py",
        "sim/runner.py",
        "scripts/run_concentration_cap_sweep.py",
    ):
        p = bundle / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# stub")

    # Subrepo packages
    for repo in (
        "renquant-common", "renquant-pipeline", "renquant-model",
        "renquant-execution", "renquant-strategy-104", "renquant-backtesting",
    ):
        p = bundle / "subrepos" / repo / "src"
        p.mkdir(parents=True, exist_ok=True)
        (p / "__init__.py").write_text("")

    # WF manifest + artifacts
    manifest_dir = bundle / "kernel" / "artifacts" / "sim"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "retrains": [
            {
                "artifact_uri": "artifacts/models/model_v1.pkl",
                "calibrator_uri": "artifacts/calibrators/cal_v1.pkl",
            }
        ]
    }
    (manifest_dir / "walkforward_manifest_v2_20260602.json").write_text(
        json.dumps(manifest)
    )
    for uri in ("artifacts/models/model_v1.pkl", "artifacts/calibrators/cal_v1.pkl"):
        p = bundle / "kernel" / uri
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"stub")

    # Fundamentals
    data.mkdir(parents=True, exist_ok=True)
    (data / "sec_fundamentals_daily.parquet").write_bytes(b"stub")
    (data / "alpha158_291_fundamental_dataset.parquet").write_bytes(b"stub")

    # OHLCV
    for sym in ("SPY", "AAPL", "XLK"):
        d = ohlcv / sym
        d.mkdir(parents=True, exist_ok=True)
        (d / "1d.parquet").write_bytes(b"stub")

    return {
        "bundle_dir": bundle,
        "ohlcv_staging": ohlcv,
        "data_staging": data,
        "base_config": {
            "watchlist": ["AAPL"],
            "sector_etf_map": {"Technology": "XLK"},
            "benchmark": "SPY",
        },
        "manifest_path": "artifacts/sim/walkforward_manifest_v2_20260602.json",
    }


def test_verify_staged_all_present(staged_dirs: dict) -> None:
    report = verify_staged(**staged_dirs)
    assert report.passed
    assert len(report.failed) == 0
    assert len(report.checks) > 0


def test_verify_staged_missing_fundamentals(staged_dirs: dict) -> None:
    (staged_dirs["data_staging"] / "sec_fundamentals_daily.parquet").unlink()
    report = verify_staged(**staged_dirs)
    assert not report.passed
    failed_names = [c.name for c in report.failed]
    assert "fundamentals:sec_fundamentals_daily.parquet" in failed_names


def test_verify_staged_missing_ohlcv_symbol(staged_dirs: dict) -> None:
    import shutil
    shutil.rmtree(staged_dirs["ohlcv_staging"] / "AAPL")
    report = verify_staged(**staged_dirs)
    assert not report.passed
    failed_names = [c.name for c in report.failed]
    assert "ohlcv:AAPL" in failed_names


def test_verify_staged_missing_code_entry(staged_dirs: dict) -> None:
    (staged_dirs["bundle_dir"] / "sim" / "runner.py").unlink()
    report = verify_staged(**staged_dirs)
    assert not report.passed
    failed_names = [c.name for c in report.failed]
    assert "bundle:backtest runner" in failed_names


def test_verify_staged_missing_wf_artifact(staged_dirs: dict) -> None:
    (staged_dirs["bundle_dir"] / "kernel" / "artifacts" / "models" / "model_v1.pkl").unlink()
    report = verify_staged(**staged_dirs)
    assert not report.passed
    failed_names = [c.name for c in report.failed]
    assert any("artifact_uri" in n for n in failed_names)


def test_verify_staged_missing_subrepo(staged_dirs: dict) -> None:
    import shutil
    shutil.rmtree(staged_dirs["bundle_dir"] / "subrepos" / "renquant-pipeline")
    report = verify_staged(**staged_dirs)
    assert not report.passed
    failed_names = [c.name for c in report.failed]
    assert "subrepo:renquant-pipeline" in failed_names


def test_verify_remote_code_and_subrepos(tmp_path: Path) -> None:
    """Remote contract verifies code entries and subrepo packages from app_root."""
    app_root = str(tmp_path / "app")

    for rel in (
        "kernel/panel_pipeline/job_panel_scoring.py",
        "sim/runner.py",
        "scripts/run_concentration_cap_sweep.py",
    ):
        p = tmp_path / "app" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# stub")

    for repo in (
        "renquant-common", "renquant-pipeline", "renquant-model",
        "renquant-execution", "renquant-strategy-104", "renquant-backtesting",
    ):
        p = tmp_path / "app" / "subrepos" / repo / "src"
        p.mkdir(parents=True, exist_ok=True)

    # WF manifest
    wf_dir = tmp_path / "app" / "kernel" / "artifacts" / "sim"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "walkforward_manifest_v2_20260602.json").write_text("{}")

    report = verify_remote(app_root=app_root)
    code_checks = [c for c in report.checks if c.name.startswith("code:")]
    subrepo_checks = [c for c in report.checks if c.name.startswith("subrepo:")]
    assert all(c.exists for c in code_checks), [c for c in code_checks if not c.exists]
    assert all(c.exists for c in subrepo_checks), [c for c in subrepo_checks if not c.exists]


def test_verify_remote_missing_code(tmp_path: Path) -> None:
    """Remote contract fails when a code entry point is missing."""
    app_root = str(tmp_path / "app")
    (tmp_path / "app").mkdir()

    report = verify_remote(app_root=app_root)
    code_checks = [c for c in report.checks if c.name.startswith("code:")]
    assert not all(c.exists for c in code_checks)
    assert not report.passed


def test_contract_report_summary() -> None:
    report = ContractReport(
        passed=False,
        checks=[
            ContractCheck(name="a", required=True, path="/x", exists=True),
            ContractCheck(name="b", required=True, path="/y", exists=False, detail="missing"),
            ContractCheck(name="c", required=False, path="/z", exists=False),
        ],
    )
    assert len(report.failed) == 1
    assert report.failed[0].name == "b"
    summary = report.summary()
    assert "[PASS]" in summary
    assert "[FAIL]" in summary
    assert "[WARN]" in summary
