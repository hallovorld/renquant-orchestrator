"""Tests for retrain_common — shared retrain infrastructure."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import pytest

from renquant_orchestrator.retrain_common import (
    SUBREPO_NAMES,
    read_json_object,
    resolve_path,
    run_subprocess,
    staging_path,
    subrepo_pythonpath,
    subrepo_srcs,
    validate_repo_dir,
)


@dataclass
class _FakeCtx:
    repo_dir: Path
    dry_run: bool = True
    commands: list[list[str]] = field(default_factory=list)


class TestSubrepoSrcs:
    def test_returns_src_path_for_each_subrepo(self, tmp_path):
        with patch(
            "renquant_orchestrator.retrain_common.resolve_subrepo_root",
            return_value=tmp_path,
        ):
            srcs = subrepo_srcs(tmp_path)
        assert len(srcs) == len(SUBREPO_NAMES)
        for src, name in zip(srcs, SUBREPO_NAMES):
            assert src == tmp_path / name / "src"

    def test_all_nine_subrepos_present(self):
        assert len(SUBREPO_NAMES) == 9
        assert "renquant-orchestrator" in SUBREPO_NAMES
        assert "renquant-pipeline" in SUBREPO_NAMES


class TestSubrepoPythonpath:
    def test_sets_pythonpath_with_subrepo_srcs(self, tmp_path):
        with patch(
            "renquant_orchestrator.retrain_common.resolve_subrepo_root",
            return_value=tmp_path,
        ):
            result = subrepo_pythonpath(tmp_path, env={})
        pp = result["PYTHONPATH"]
        for name in SUBREPO_NAMES:
            assert str(tmp_path / name / "src") in pp

    def test_sets_default_env_vars(self, tmp_path):
        with patch(
            "renquant_orchestrator.retrain_common.resolve_subrepo_root",
            return_value=tmp_path,
        ):
            result = subrepo_pythonpath(tmp_path, env={})
        assert result["RENQUANT_REPO_ROOT"] == str(tmp_path)
        assert result["RENQUANT_DATA_ROOT"] == str(tmp_path)
        assert result["RENQUANT_STRATEGY_DIR"] == str(
            tmp_path / "backtesting" / "renquant_104"
        )

    def test_does_not_override_existing_env_vars(self, tmp_path):
        with patch(
            "renquant_orchestrator.retrain_common.resolve_subrepo_root",
            return_value=tmp_path,
        ):
            result = subrepo_pythonpath(
                tmp_path, env={"RENQUANT_REPO_ROOT": "/custom"}
            )
        assert result["RENQUANT_REPO_ROOT"] == "/custom"

    def test_strategy_config_sets_env_var(self, tmp_path):
        with patch(
            "renquant_orchestrator.retrain_common.resolve_subrepo_root",
            return_value=tmp_path,
        ):
            result = subrepo_pythonpath(
                tmp_path, env={}, strategy_config="/path/to/config.yaml"
            )
        assert result["RENQUANT_STRATEGY_CONFIG"] == "/path/to/config.yaml"

    def test_strategy_config_none_does_not_set(self, tmp_path):
        with patch(
            "renquant_orchestrator.retrain_common.resolve_subrepo_root",
            return_value=tmp_path,
        ):
            result = subrepo_pythonpath(tmp_path, env={})
        assert "RENQUANT_STRATEGY_CONFIG" not in result

    def test_strict_paths_with_missing_dirs_raises(self, tmp_path):
        with patch(
            "renquant_orchestrator.retrain_common.resolve_subrepo_root",
            return_value=tmp_path,
        ):
            with pytest.raises(FileNotFoundError, match="missing multirepo"):
                subrepo_pythonpath(
                    tmp_path,
                    env={"RENQUANT_STRICT_SUBREPO_PATHS": "1"},
                )

    def test_preserves_existing_pythonpath(self, tmp_path):
        with patch(
            "renquant_orchestrator.retrain_common.resolve_subrepo_root",
            return_value=tmp_path,
        ):
            result = subrepo_pythonpath(
                tmp_path, env={"PYTHONPATH": "/existing/path"}
            )
        assert result["PYTHONPATH"].endswith("/existing/path")


class TestRunSubprocess:
    def test_dry_run_records_command(self, tmp_path):
        ctx = _FakeCtx(repo_dir=tmp_path, dry_run=True)
        run_subprocess(ctx, ["echo", "hello"])
        assert ctx.commands == [["echo", "hello"]]

    def test_dry_run_does_not_execute(self, tmp_path):
        ctx = _FakeCtx(repo_dir=tmp_path, dry_run=True)
        run_subprocess(ctx, ["false"])
        assert len(ctx.commands) == 1


class TestReadJsonObject:
    def test_valid_json_object(self, tmp_path):
        path = tmp_path / "data.json"
        path.write_text('{"key": "value"}')
        result = read_json_object(path, "test")
        assert result == {"key": "value"}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="did not produce"):
            read_json_object(tmp_path / "missing.json", "test")

    def test_too_small_file_raises(self, tmp_path):
        path = tmp_path / "tiny.json"
        path.write_text("{}")
        with pytest.raises(ValueError, match="too small"):
            read_json_object(path, "test")

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json at all")
        with pytest.raises(ValueError, match="invalid JSON"):
            read_json_object(path, "test")

    def test_json_array_raises(self, tmp_path):
        path = tmp_path / "arr.json"
        path.write_text('[1, 2, 3]')
        with pytest.raises(ValueError, match="must be a JSON object"):
            read_json_object(path, "test")

    def test_nested_object(self, tmp_path):
        path = tmp_path / "nested.json"
        payload = {"a": {"b": [1, 2]}, "c": True}
        path.write_text(json.dumps(payload))
        assert read_json_object(path, "test") == payload


class TestResolvePath:
    def test_absolute_path_unchanged(self):
        result = resolve_path(Path("/repo"), "/abs/path")
        assert result == Path("/abs/path")

    def test_relative_path_joined(self):
        result = resolve_path(Path("/repo"), "data/file.json")
        assert result == Path("/repo/data/file.json")


class TestStagingPath:
    def test_adds_staging_suffix(self):
        result = staging_path(Path("/repo/data/model.json"))
        assert result == Path("/repo/data/model.staging.json")

    def test_replaces_existing_suffix(self):
        result = staging_path(Path("/repo/data/output.parquet"))
        assert result == Path("/repo/data/output.staging.json")


class TestValidateRepoDir:
    def test_passes_with_required_dirs(self, tmp_path):
        (tmp_path / "data").mkdir()
        validate_repo_dir(tmp_path)

    def test_raises_with_missing_default_required(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="missing"):
            validate_repo_dir(tmp_path)

    def test_custom_required_list(self, tmp_path):
        (tmp_path / "models").mkdir()
        validate_repo_dir(tmp_path, required=[Path("models")])

    def test_custom_required_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="configs"):
            validate_repo_dir(tmp_path, required=[Path("configs")])
