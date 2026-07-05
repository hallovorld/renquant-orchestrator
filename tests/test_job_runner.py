"""Tests for job_runner — scheduled-job dispatcher."""
from __future__ import annotations

from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from renquant_orchestrator.job_runner import (
    _MODULE_JOBS,
    _clean_args,
    _run_module_main,
    run_scheduled_job,
)


class TestCleanArgs:
    def test_strips_leading_separator(self):
        assert _clean_args(["--", "a", "b"]) == ["a", "b"]

    def test_passes_through_without_separator(self):
        assert _clean_args(["a", "b"]) == ["a", "b"]

    def test_none_returns_empty(self):
        assert _clean_args(None) == []

    def test_empty_returns_empty(self):
        assert _clean_args([]) == []

    def test_only_separator(self):
        assert _clean_args(["--"]) == []

    def test_separator_not_first_kept(self):
        assert _clean_args(["a", "--", "b"]) == ["a", "--", "b"]


class TestRunModuleMain:
    def test_calls_main_and_returns_rc(self):
        mod = ModuleType("fake")
        mod.main = MagicMock(return_value=42)
        with patch("renquant_orchestrator.job_runner.importlib.import_module", return_value=mod):
            assert _run_module_main("fake", ["--x"]) == 42
        mod.main.assert_called_once_with(["--x"])

    def test_none_return_coerced_to_zero(self):
        mod = ModuleType("fake")
        mod.main = MagicMock(return_value=None)
        with patch("renquant_orchestrator.job_runner.importlib.import_module", return_value=mod):
            assert _run_module_main("fake", []) == 0

    def test_raises_if_no_main(self):
        mod = ModuleType("fake")
        with patch("renquant_orchestrator.job_runner.importlib.import_module", return_value=mod):
            with pytest.raises(ValueError, match="has no main"):
                _run_module_main("fake", [])


class TestRunScheduledJob:
    def test_unknown_job_id_raises(self):
        with pytest.raises(ValueError, match="unknown scheduled job id"):
            run_scheduled_job("nonexistent_job_xyz")

    def test_daily_contract_fixture_dispatches_to_cli(self):
        with patch("renquant_orchestrator.job_runner.main", create=True) as mock_main:
            with patch.dict("renquant_orchestrator.job_runner.__builtins__", {}):
                from renquant_orchestrator import cli
                with patch.object(cli, "main", return_value=0) as cli_main:
                    with patch(
                        "renquant_orchestrator.job_runner.run_scheduled_job",
                        wraps=run_scheduled_job,
                    ):
                        pass
            # Simpler: just mock the import path
            with patch("renquant_orchestrator.cli.main", return_value=0) as cli_main:
                result = run_scheduled_job("daily_contract_fixture", ["--strategy-config", "s.yaml"])
            cli_main.assert_called_once_with(["daily-contract", "--strategy-config", "s.yaml"])
            assert result == 0

    def test_daily_live_runner_bridge_dispatches_to_cli(self):
        with patch("renquant_orchestrator.cli.main", return_value=0) as cli_main:
            result = run_scheduled_job("daily_live_runner_bridge", ["--repo-dir", "/tmp"])
        cli_main.assert_called_once_with(["daily-bridge", "--repo-dir", "/tmp"])
        assert result == 0

    def test_live_runner_bridge_dispatches_to_cli(self):
        with patch("renquant_orchestrator.cli.main", return_value=0) as cli_main:
            result = run_scheduled_job("live_runner_bridge")
        cli_main.assert_called_once_with(["live-bridge"])
        assert result == 0

    def test_module_job_dispatches_to_run_module_main(self):
        with patch(
            "renquant_orchestrator.job_runner._run_module_main", return_value=0
        ) as mock_run:
            result = run_scheduled_job("state_backup", ["--dry-run"])
        mock_run.assert_called_once_with(
            "renquant_orchestrator.state_backup", ["--dry-run"]
        )
        assert result == 0

    def test_module_job_with_separator(self):
        with patch(
            "renquant_orchestrator.job_runner._run_module_main", return_value=0
        ) as mock_run:
            run_scheduled_job("state_backup", ["--", "--dry-run"])
        mock_run.assert_called_once_with(
            "renquant_orchestrator.state_backup", ["--dry-run"]
        )

    def test_module_jobs_registry_is_nonempty(self):
        assert len(_MODULE_JOBS) > 20
