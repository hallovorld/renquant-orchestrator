"""Tests for the orchestrator-owned weekly alpha158+fund retrain pipeline."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import subprocess

import pytest

from renquant_orchestrator import retrain_alpha158_fund as mod


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "RenQuant"
    (repo / "data").mkdir(parents=True)
    return repo


def test_pipeline_shape_is_single_job_with_ordered_tasks(tmp_path) -> None:
    pipeline = mod.build_pipeline()
    assert pipeline.name == "weekly-alpha158-fund-retrain"
    assert [type(job).__name__ for job in pipeline.jobs] == ["RetrainJob"]
    assert [type(task).__name__ for task in pipeline.jobs[0].tasks] == [
        "BuildAlpha158PanelTask",
        "MergeFundFeaturesTask",
        "TrainGbdtScorerTask",
        "RefitCalibratorTask",
    ]


def test_retrain_pipeline_command_sequence(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    scorer = repo / "artifacts" / "panel-ltr.staging.json"
    calibrator = repo / "artifacts" / "panel-rank-calibration.staging.json"
    seen: list[list[str]] = []

    def fake_run(cmd, cwd=None, env=None):
        seen.append(cmd)
        if "renquant_orchestrator.train_gbdt" in cmd:
            scorer.parent.mkdir(parents=True, exist_ok=True)
            scorer.write_text(json.dumps({
                "config_fingerprint": "sha256:test",
                "trained_date": dt.datetime.utcnow().strftime("%Y-%m-%d"),
            }))
        if "renquant_model_gbdt.fit_calibrator_alpha158_fund" in cmd:
            calibrator.parent.mkdir(parents=True, exist_ok=True)
            calibrator.write_text(json.dumps({"method": "isotonic"}))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    strategy_config = repo / "strategy_config.json"
    strategy_config.write_text("{}")
    ctx = mod.RetrainContext(
        repo_dir=repo,
        xgb_artifact_out=scorer,
        calibrator_out=calibrator,
        strategy_config_path=strategy_config,
    )

    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    assert len(seen) == 4
    assert "renquant_base_data.alpha158_qlib_panel" in seen[0]
    assert ["--data-dir", str(repo / "data")] == seen[0][3:5]
    assert "renquant_base_data.alpha158_fund_panel" in seen[1]
    assert ["--data-dir", str(repo / "data")] == seen[1][3:5]
    assert "--truncate-to-sec-max" in seen[1]
    assert "renquant_orchestrator.train_gbdt" in seen[2]
    assert ["--strategy-config", str(strategy_config)] == seen[2][5:7]
    out_idx = seen[2].index("--output-path")
    assert seen[2][out_idx:out_idx + 2] == ["--output-path", str(scorer)]
    assert "--drop-sentiment" in seen[2]
    assert "renquant_model_gbdt.fit_calibrator_alpha158_fund" in seen[3]
    assert ["--data-dir", str(repo / "data")] == seen[3][3:5]
    assert "--scorer-artifact" in seen[3]
    assert str(scorer) in seen[3]
    assert str(calibrator) in seen[3]


def test_missing_scorer_fails_before_calibrator(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    scorer = repo / "artifacts" / "panel-ltr.staging.json"
    calibrator = repo / "artifacts" / "panel-rank-calibration.staging.json"

    def fake_run(_cmd, cwd=None, env=None):
        return subprocess.CompletedProcess(_cmd, 0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    ctx = mod.RetrainContext(repo_dir=repo, xgb_artifact_out=scorer, calibrator_out=calibrator)

    with pytest.raises(FileNotFoundError, match="GBDT training did not produce"):
        mod.build_pipeline().run(ctx)


def test_invalid_scorer_content_fails_before_calibrator(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    scorer = repo / "artifacts" / "panel-ltr.staging.json"
    calibrator = repo / "artifacts" / "panel-rank-calibration.staging.json"

    def fake_run(cmd, cwd=None, env=None):
        if "renquant_orchestrator.train_gbdt" in cmd:
            scorer.parent.mkdir(parents=True, exist_ok=True)
            scorer.write_text(json.dumps({"trained_date": dt.datetime.utcnow().strftime("%Y-%m-%d")}))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    ctx = mod.RetrainContext(repo_dir=repo, xgb_artifact_out=scorer, calibrator_out=calibrator)

    with pytest.raises(ValueError, match="missing config_fingerprint"):
        mod.build_pipeline().run(ctx)


def test_dry_run_records_commands_without_artifacts(tmp_path) -> None:
    repo = _repo(tmp_path)
    scorer = repo / "artifacts" / "panel-ltr.staging.json"
    calibrator = repo / "artifacts" / "panel-rank-calibration.staging.json"
    ctx = mod.RetrainContext(
        repo_dir=repo,
        xgb_artifact_out=scorer,
        calibrator_out=calibrator,
        dry_run=True,
    )

    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    assert len(ctx.commands) == 4
    assert not scorer.exists()
    assert not calibrator.exists()


def test_main_staged_defaults_to_candidate_artifact_paths(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    captured: list[mod.RetrainContext] = []

    class FakePipeline:
        def run(self, ctx):
            captured.append(ctx)
            return None

    monkeypatch.setattr(mod, "build_pipeline", lambda: FakePipeline())

    assert mod.main(["--repo-dir", str(repo), "--staged", "--dry-run"]) == 0

    assert captured
    assert captured[0].xgb_artifact_out == (
        repo / "backtesting" / "renquant_104" / "artifacts" / "prod" / "panel-ltr.alpha158_fund.staging.json"
    )
    assert captured[0].calibrator_out == (
        repo / "backtesting" / "renquant_104" / "artifacts" / "prod" / "panel-rank-calibration.staging.json"
    )


def test_pythonpath_includes_required_sibling_repos(tmp_path) -> None:
    repo = _repo(tmp_path)
    env = mod._subrepo_pythonpath(repo, env={})
    path = env["PYTHONPATH"]
    for name in (
        "renquant-orchestrator/src",
        "renquant-common/src",
        "renquant-base-data/src",
        "renquant-artifacts/src",
        "renquant-model/src",
        "renquant-pipeline/src",
        "renquant-execution/src",
        "renquant-strategy-104/src",
        "renquant-backtesting/src",
    ):
        assert name in path
    assert env["RENQUANT_DATA_ROOT"] == str(repo)
    assert env["RENQUANT_STRATEGY_CONFIG"]


def test_strict_subrepo_pythonpath_requires_existing_siblings(tmp_path) -> None:
    repo = _repo(tmp_path)

    with pytest.raises(FileNotFoundError, match="missing multirepo source paths"):
        mod._subrepo_pythonpath(repo, env={"RENQUANT_STRICT_SUBREPO_PATHS": "1"})


def test_validate_repo_dir_fails_loudly_for_non_umbrella_checkout(tmp_path) -> None:
    repo = tmp_path / "RenQuant"
    repo.mkdir()

    with pytest.raises(FileNotFoundError, match="data"):
        mod._validate_repo_dir(repo)
