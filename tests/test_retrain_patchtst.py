"""Tests for the orchestrator-owned weekly PatchTST retrain pipeline."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import subprocess

import pytest

from renquant_orchestrator import retrain_patchtst as mod


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


def test_module_imports_and_pipeline_shape() -> None:
    pipeline = mod.build_pipeline()
    assert pipeline.name == "weekly-patchtst-retrain"
    assert [type(job).__name__ for job in pipeline.jobs] == ["RetrainJob"]
    assert [type(task).__name__ for task in pipeline.jobs[0].tasks] == [
        "ResolveDataRootTask",
        "EnsureStagingDirTask",
        "TrainPatchtstScorerTask",
        "RefitCalibratorTask",
    ]


def test_parse_args_defaults_and_staged() -> None:
    args = mod.parse_args(["--repo-dir", "/tmp/_repo", "--staged", "--dry-run"])
    assert args.staged is True
    assert args.dry_run is True
    assert args.seed == mod.DEFAULT_SEED
    assert args.device == mod.DEFAULT_DEVICE
    # prod pt07 recipe: cross-stock attn on, sentiment features excluded.
    assert args.cross_stock_attn is True
    assert args.exclude_features == mod.DEFAULT_EXCLUDE_FEATURES


def test_retrain_pipeline_command_sequence(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    out_dir = repo / "backtesting" / "renquant_104" / "artifacts" / "patchtst_staging" / "wk"
    model = mod.model_path_for(out_dir, mod.DEFAULT_SEED)
    calibrator = mod.calibrator_path_for(model)
    today = dt.datetime.utcnow().strftime("%Y-%m-%d")
    seen: list[list[str]] = []

    def fake_run(cmd, cwd=None, env=None):
        seen.append(cmd)
        if "renquant_model_patchtst.hf_trainer" in cmd:
            model.parent.mkdir(parents=True, exist_ok=True)
            model.write_bytes(b"PT-CHECKPOINT-BYTES")
            sidecar = model.with_name(model.name + ".metadata.json")
            sidecar.write_text(json.dumps({
                "training_contract": {
                    "trained_date": today,
                    "effective_train_cutoff_date": "2024-04-09",
                    "lookahead_days": 60,
                }
            }))
        if "renquant_model_patchtst.fit_calibrator" in cmd:
            calibrator.parent.mkdir(parents=True, exist_ok=True)
            calibrator.write_text(json.dumps({"method": "platt", "version": 1}))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    ctx = mod.PatchtstRetrainContext(
        repo_dir=repo,
        output_dir=out_dir,
        train_cutoff="2024-06-01",
    )

    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    # Exactly the trainer + calibrator subprocesses (resolve/mkdir tasks don't run).
    assert len(seen) == 2
    train_cmd = next(c for c in seen if "renquant_model_patchtst.hf_trainer" in c)
    assert "--train-cutoff" in train_cmd
    assert train_cmd[train_cmd.index("--train-cutoff") + 1] == "2024-06-01"
    out_idx = train_cmd.index("--output-dir")
    assert train_cmd[out_idx + 1] == str(out_dir)
    assert "--cross-stock-attn" in train_cmd
    assert "--exclude-features" in train_cmd
    cal_cmd = next(c for c in seen if "renquant_model_patchtst.fit_calibrator" in c)
    assert cal_cmd[cal_cmd.index("--scorer-artifact") + 1] == str(model)
    assert cal_cmd[cal_cmd.index("--out") + 1] == str(calibrator)
    assert ctx.model_artifact == model
    assert ctx.calibrator_artifact == calibrator


def test_missing_scorer_fails_before_calibrator(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    out_dir = repo / "stage"

    def fake_run(cmd, cwd=None, env=None):
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    ctx = mod.PatchtstRetrainContext(repo_dir=repo, output_dir=out_dir)

    with pytest.raises(FileNotFoundError, match="PatchTST training did not produce"):
        mod.build_pipeline().run(ctx)


def test_stale_trained_date_fails(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    out_dir = repo / "stage"
    model = mod.model_path_for(out_dir, mod.DEFAULT_SEED)

    def fake_run(cmd, cwd=None, env=None):
        if "renquant_model_patchtst.hf_trainer" in cmd:
            model.parent.mkdir(parents=True, exist_ok=True)
            model.write_bytes(b"PT-CHECKPOINT-BYTES")
            sidecar = model.with_name(model.name + ".metadata.json")
            sidecar.write_text(json.dumps({
                "training_contract": {
                    "trained_date": "1999-01-01",
                    "effective_train_cutoff_date": "1998-01-01",
                }
            }))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    ctx = mod.PatchtstRetrainContext(repo_dir=repo, output_dir=out_dir)

    with pytest.raises(ValueError, match="trained_date"):
        mod.build_pipeline().run(ctx)


def test_dry_run_records_commands_without_training(tmp_path) -> None:
    repo = _repo(tmp_path)
    out_dir = repo / "stage"
    ctx = mod.PatchtstRetrainContext(repo_dir=repo, output_dir=out_dir, dry_run=True)

    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    # Two subprocess commands recorded, none executed.
    assert len(ctx.commands) == 2
    assert any("renquant_model_patchtst.hf_trainer" in c for c in ctx.commands)
    assert any("renquant_model_patchtst.fit_calibrator" in c for c in ctx.commands)
    # No artifacts materialized in dry-run.
    assert ctx.model_artifact is not None
    assert not ctx.model_artifact.exists()
    # Dry-run is side-effect-free: the staging dir is NOT created.
    assert not out_dir.exists()


def test_main_staged_uses_staging_dir_and_runs_pipeline(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    captured: list[mod.PatchtstRetrainContext] = []

    class FakePipeline:
        def run(self, ctx):
            captured.append(ctx)
            return None

    monkeypatch.setattr(mod, "build_pipeline", lambda: FakePipeline())

    assert mod.main(["--repo-dir", str(repo), "--staged", "--dry-run"]) == 0

    assert captured
    out = captured[0].output_dir
    # Staging dir lives under artifacts/patchtst_staging, NOT the prod artifact dir.
    assert "patchtst_staging" in str(out)
    assert "patchtst_shadow" not in str(out)


def test_main_refuses_prod_artifact_dir(tmp_path) -> None:
    repo = _repo(tmp_path)
    prod = repo / mod._PROD_MODEL_REL
    with pytest.raises(SystemExit, match="production PatchTST artifact dir"):
        mod.main([
            "--repo-dir", str(repo),
            "--output-dir", str(prod),
            "--dry-run",
        ])


def test_dry_run_command_carries_prod_recipe_flags(tmp_path) -> None:
    repo = _repo(tmp_path)
    ctx = mod.PatchtstRetrainContext(
        repo_dir=repo,
        output_dir=repo / "stage",
        dry_run=True,
    )
    mod.build_pipeline().run(ctx)
    train_cmd = next(c for c in ctx.commands if "renquant_model_patchtst.hf_trainer" in c)
    assert "--cross-stock-attn" in train_cmd
    excl_idx = train_cmd.index("--exclude-features")
    assert train_cmd[excl_idx + 1] == mod.DEFAULT_EXCLUDE_FEATURES


def test_pythonpath_includes_required_sibling_repos(monkeypatch, tmp_path) -> None:
    _clear_runtime_path_env(monkeypatch)
    repo = _repo(tmp_path)
    env = mod._subrepo_pythonpath(repo, env={})
    path = env["PYTHONPATH"]
    for name in (
        "renquant-orchestrator/src",
        "renquant-common/src",
        "renquant-base-data/src",
        "renquant-model/src",
        "renquant-pipeline/src",
        "renquant-backtesting/src",
    ):
        assert name in path
    assert env["RENQUANT_DATA_ROOT"] == str(repo)


def test_strict_subrepo_pythonpath_requires_existing_siblings(monkeypatch, tmp_path) -> None:
    _clear_runtime_path_env(monkeypatch)
    repo = _repo(tmp_path)

    with pytest.raises(FileNotFoundError, match="missing multirepo source paths"):
        mod._subrepo_pythonpath(repo, env={"RENQUANT_STRICT_SUBREPO_PATHS": "1"})


def test_validate_repo_dir_fails_loudly_for_non_umbrella_checkout(tmp_path) -> None:
    repo = tmp_path / "RenQuant"
    repo.mkdir()

    with pytest.raises(FileNotFoundError, match="data"):
        mod._validate_repo_dir(repo)
