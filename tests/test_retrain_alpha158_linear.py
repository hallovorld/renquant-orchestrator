"""Tests for the orchestrator-owned alpha158 linear retrain pipeline."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import subprocess

import pytest

from renquant_orchestrator import retrain_alpha158_linear as mod
from renquant_orchestrator import retrain_common


_RUNTIME_PATH_ENVS = (
    "RENQUANT_SUBREPO_ROOT",
    "RENQUANT_ASSEMBLY_DIR",
    "RENQUANT_SUBREPO_ENV",
)


def _clear_runtime_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _RUNTIME_PATH_ENVS:
        monkeypatch.delenv(name, raising=False)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "RenQuant"
    (repo / "data").mkdir(parents=True)
    return repo


def test_pipeline_shape_is_single_job_with_ordered_tasks() -> None:
    pipeline = mod.build_pipeline()
    assert pipeline.name == "daily-alpha158-linear-retrain"
    assert [type(job).__name__ for job in pipeline.jobs] == ["RetrainLinearJob"]
    assert [type(task).__name__ for task in pipeline.jobs[0].tasks] == [
        "BuildAlpha158PanelTask",
        "TrainLinearScorerTask",
        "RefitLinearCalibratorTask",
    ]


def test_retrain_linear_command_sequence(monkeypatch, tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    scorer = repo / "artifacts" / "panel-ltr.alpha158_linear.staging.json"
    calibrator = repo / "artifacts" / "panel-rank-calibration.alpha158_linear.staging.json"
    seen: list[list[str]] = []

    def fake_run(cmd, cwd=None, env=None):
        seen.append(cmd)
        if "renquant_model_alpha158_linear.trainer" in cmd:
            scorer.parent.mkdir(parents=True, exist_ok=True)
            scorer.write_text(
                json.dumps({
                    "kind": "panel_linear",
                    "feature_cols": ["alpha0", "alpha1"],
                    "trained_date": dt.date.today().isoformat(),
                }),
                encoding="utf-8",
            )
        if "renquant_model_alpha158_linear.calibrator" in cmd:
            calibrator.parent.mkdir(parents=True, exist_ok=True)
            calibrator.write_text(json.dumps({"kind": "global_panel_calibration"}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(retrain_common.subprocess, "run", fake_run)
    ctx = mod.RetrainLinearContext(repo_dir=repo, scorer_out=scorer, calibrator_out=calibrator)

    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    assert len(seen) == 3
    assert "renquant_base_data.alpha158_qlib_panel" in seen[0]
    assert ["--data-dir", str(repo / "data")] == seen[0][3:5]
    assert "renquant_model_alpha158_linear.trainer" in seen[1]
    assert ["--dataset", str(repo / "data" / "alpha158_qlib_dataset.parquet")] == seen[1][3:5]
    assert ["--output", str(scorer)] == seen[1][-2:]
    assert "renquant_model_alpha158_linear.calibrator" in seen[2]
    assert ["--data-dir", str(repo / "data")] == seen[2][3:5]
    assert "--scorer-artifact" in seen[2]
    assert str(scorer) in seen[2]
    assert str(calibrator) in seen[2]


def test_skip_features_omits_panel_rebuild(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    ctx = mod.RetrainLinearContext(
        repo_dir=repo,
        scorer_out=repo / "s.json",
        calibrator_out=repo / "c.json",
        rebuild_features=False,
        dry_run=True,
    )

    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    assert len(ctx.commands) == 2
    assert "renquant_model_alpha158_linear.trainer" in ctx.commands[0]
    assert "renquant_model_alpha158_linear.calibrator" in ctx.commands[1]


def test_main_staged_defaults_to_candidate_artifact_paths(monkeypatch, tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    captured: list[mod.RetrainLinearContext] = []

    class FakePipeline:
        def run(self, ctx):
            captured.append(ctx)
            return None

    monkeypatch.setattr(mod, "build_pipeline", lambda: FakePipeline())

    assert mod.main(["--repo-dir", str(repo), "--staged", "--skip-features", "--dry-run"]) == 0

    assert captured
    assert captured[0].rebuild_features is False
    assert captured[0].scorer_out == (
        repo / "backtesting" / "renquant_104" / "artifacts" / "panel-ltr.alpha158_linear.staging.json"
    )
    assert captured[0].calibrator_out == (
        repo / "backtesting" / "renquant_104" / "artifacts" / "panel-rank-calibration.alpha158_linear.staging.json"
    )


def test_pythonpath_uses_runtime_assembly_dir_env(monkeypatch, tmp_path: Path) -> None:
    _clear_runtime_path_env(monkeypatch)
    repo = _repo(tmp_path)
    assembly = tmp_path / "runtime-assembly"
    (assembly / "repos").mkdir(parents=True)
    monkeypatch.setenv("RENQUANT_ASSEMBLY_DIR", str(assembly))

    env = retrain_common.subrepo_pythonpath(repo, env={})

    entries = env["PYTHONPATH"].split(os.pathsep)
    assert entries[0] == str(assembly / "repos" / "renquant-orchestrator" / "src")
    assert entries[4] == str(assembly / "repos" / "renquant-model" / "src")
    assert str(repo.parent / "renquant-model" / "src") not in entries


def test_missing_scorer_fails_before_calibrator(monkeypatch, tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    scorer = repo / "missing.json"
    calibrator = repo / "calibration.json"

    def fake_run(cmd, cwd=None, env=None):
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(retrain_common.subprocess, "run", fake_run)
    ctx = mod.RetrainLinearContext(repo_dir=repo, scorer_out=scorer, calibrator_out=calibrator)

    with pytest.raises(FileNotFoundError, match="alpha158 linear training did not produce"):
        mod.build_pipeline().run(ctx)


def test_validate_repo_dir_requires_data_dir(tmp_path: Path) -> None:
    repo = tmp_path / "RenQuant"
    repo.mkdir()

    with pytest.raises(FileNotFoundError, match="data"):
        retrain_common.validate_repo_dir(repo)
