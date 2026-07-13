"""Tests for the crypto Stage-0 battery workflow + CLI (D-C12).

Paper/shadow readiness work only — this workflow is structurally unable to
authorize live trading entries.

Coverage:
- Workflow: Task/Pipeline invocation path, run_id generation/propagation,
  context population, readiness record schema and persistence.
- CLI: argument parsing, delegation to workflow (CLI is a thin wrapper),
  exit-code handling.
- Safety: live-blocking before any broker object is created, missing
  dependency reported as FAIL, ERROR status fails closed.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from renquant_orchestrator.crypto_stage0_workflow import (
    BatteryReport,
    CryptoStage0Context,
    CryptoStage0Job,
    CryptoStage0Pipeline,
    PersistStage0ReadinessTask,
    RunBatteryTask,
    StepResult,
    ValidateStage0InputsTask,
    _report_to_jsonable,
    new_run_id,
    run_stage0_workflow,
)


def _fake_step(name, status, detail="", data=None, required=True):
    return StepResult(name=name, status=status, detail=detail, data=data or {}, required=required)


def _make_ctx(tmp_path, *, paper=True, dry_run=True, run_id=None):
    return CryptoStage0Context(
        run_id=run_id if run_id is not None else new_run_id(),
        output_dir=tmp_path / "out",
        paper=paper,
        dry_run=dry_run,
    )


# ── run_id generation ───────────────────────────────────────────────────────


class TestRunId:
    def test_new_run_id_is_valid_uuid4(self):
        rid = new_run_id()
        parsed = uuid.UUID(rid)
        assert parsed.version == 4

    def test_new_run_ids_are_unique(self):
        ids = {new_run_id() for _ in range(100)}
        assert len(ids) == 100


# ── ValidateStage0InputsTask ────────────────────────────────────────────────


class TestValidateStage0InputsTask:
    def test_missing_run_id_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path, run_id="")
        with pytest.raises(ValueError, match="run_id is required"):
            ValidateStage0InputsTask().run(ctx)

    def test_live_blocked_before_any_broker(self, tmp_path):
        ctx = _make_ctx(tmp_path, paper=False)
        result = ValidateStage0InputsTask().run(ctx)
        assert result is False
        assert ctx.report is not None
        assert ctx.report.steps[0].name == "safety"
        assert ctx.report.steps[0].status == "FAIL"
        assert ctx.report.all_passed is False

    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", False)
    def test_missing_dependency_reported_as_fail(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        result = ValidateStage0InputsTask().run(ctx)
        assert result is False
        assert ctx.report is not None
        assert ctx.report.steps[0].name == "dependency"
        assert ctx.report.steps[0].status == "FAIL"

    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    def test_valid_inputs_pass(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        result = ValidateStage0InputsTask().run(ctx)
        assert result is True
        assert ctx.stage_trace[-1]["stage"] == "validate_stage0_inputs"
        assert ctx.stage_trace[-1]["ok"] is True


# ── RunBatteryTask ──────────────────────────────────────────────────────────


class TestRunBatteryTask:
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_constructs_broker_and_delegates(self, mock_broker_cls, mock_run_battery, tmp_path):
        mock_broker = MagicMock()
        mock_broker_cls.return_value = mock_broker
        expected_report = BatteryReport(
            timestamp="2026-07-12T22:00:00+00:00",
            account_id="test-account",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("crypto_account_status", "PASS")],
        )
        mock_run_battery.return_value = expected_report

        ctx = _make_ctx(tmp_path)
        result = RunBatteryTask().run(ctx)

        assert result is True
        mock_broker_cls.assert_called_once_with(paper=True)
        mock_broker.connect.assert_called_once()
        mock_run_battery.assert_called_once_with(mock_broker, dry_run=True)
        assert ctx.report is expected_report
        assert ctx.stage_trace[-1]["stage"] == "run_battery"
        assert ctx.stage_trace[-1]["ok"] is True
        assert "elapsed_sec" in ctx.stage_trace[-1]


# ── PersistStage0ReadinessTask ──────────────────────────────────────────────


class TestPersistStage0ReadinessTask:
    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    def test_writes_readiness_record(self, _mock_commit, tmp_path):
        ctx = _make_ctx(tmp_path)
        ctx.report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("x", "PASS")],
        )

        result = PersistStage0ReadinessTask().run(ctx)

        assert result is True
        assert ctx.readiness_record["record_type"] == "crypto_stage0_readiness"
        assert ctx.readiness_record["run_id"] == ctx.run_id
        assert ctx.readiness_record["verdict"] == "PASS"

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    def test_readiness_record_schema(self, _mock_commit, tmp_path):
        ctx = _make_ctx(tmp_path, run_id="test-run-id-123")
        ctx.report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("x", "PASS")],
        )

        PersistStage0ReadinessTask().run(ctx)

        rec = ctx.readiness_record
        assert rec["record_type"] == "crypto_stage0_readiness"
        assert rec["schema_version"] == 1
        assert rec["run_id"] == "test-run-id-123"
        assert rec["run_type"] == "crypto_stage0_battery"
        assert rec["paper"] is True
        assert rec["dry_run"] is True
        assert rec["orchestrator_commit"] == "abc123"
        assert rec["verdict"] == "PASS"
        assert "timestamp" in rec
        assert "report_sha256" in rec
        assert len(rec["report_sha256"]) == 64
        assert "report" in rec
        assert "stage_trace" in rec

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    def test_readiness_file_written_to_output_dir(self, _mock_commit, tmp_path):
        ctx = _make_ctx(tmp_path)
        ctx.report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("x", "PASS")],
        )

        PersistStage0ReadinessTask().run(ctx)

        readiness_path = ctx.output_dir / "crypto_stage0_readiness.json"
        assert readiness_path.exists()
        content = json.loads(readiness_path.read_text(encoding="utf-8"))
        assert content["record_type"] == "crypto_stage0_readiness"
        assert content["run_id"] == ctx.run_id

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    def test_readiness_verdict_fail_on_required_failure(self, _mock_commit, tmp_path):
        ctx = _make_ctx(tmp_path)
        ctx.report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=False,
            steps=[
                _fake_step("ok_step", "PASS", required=True),
                _fake_step("bad_step", "FAIL", required=True),
            ],
        )

        PersistStage0ReadinessTask().run(ctx)

        assert ctx.readiness_record["verdict"] == "FAIL"

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    def test_readiness_sha256_is_deterministic(self, _mock_commit, tmp_path):
        steps = [_fake_step("x", "PASS")]

        ctx1 = _make_ctx(tmp_path, run_id="run-1")
        ctx1.report = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=True, steps=steps,
        )
        PersistStage0ReadinessTask().run(ctx1)

        ctx2 = _make_ctx(tmp_path, run_id="run-2")
        ctx2.report = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=True, steps=steps,
        )
        PersistStage0ReadinessTask().run(ctx2)

        # Same report content -> same report hash (different run_ids don't
        # affect the report hash, only the envelope-level run_id).
        assert ctx1.readiness_record["report_sha256"] == ctx2.readiness_record["report_sha256"]

    def test_missing_report_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        with pytest.raises(ValueError, match="report is required"):
            PersistStage0ReadinessTask().run(ctx)


# ── Pipeline integration ────────────────────────────────────────────────────


class TestPipelineIntegration:
    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_full_pipeline_produces_readiness_record(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path
    ):
        mock_broker_cls.return_value = MagicMock()
        mock_run_battery.return_value = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("x", "PASS")],
        )

        ctx = _make_ctx(tmp_path)
        pipeline = CryptoStage0Pipeline()
        result = pipeline.run(ctx)

        assert result.ok is True
        assert result.name == "crypto-stage0-readiness"
        assert ctx.report is not None
        assert ctx.report.all_passed is True
        assert ctx.readiness_record["record_type"] == "crypto_stage0_readiness"
        assert ctx.readiness_record["run_id"] == ctx.run_id

    def test_pipeline_short_circuits_on_live_blocked(self, tmp_path):
        ctx = _make_ctx(tmp_path, paper=False)
        pipeline = CryptoStage0Pipeline()
        result = pipeline.run(ctx)

        assert result.ok is True  # Pipeline itself completed without error
        assert ctx.report is not None
        assert ctx.report.all_passed is False
        # Readiness record should NOT be written (pipeline short-circuited).
        assert ctx.readiness_record == {}

    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", False)
    def test_pipeline_short_circuits_on_missing_dependency(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        pipeline = CryptoStage0Pipeline()
        pipeline.run(ctx)

        assert ctx.report is not None
        assert ctx.report.steps[0].name == "dependency"
        assert ctx.readiness_record == {}

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_run_id_propagates_through_pipeline(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path
    ):
        mock_broker_cls.return_value = MagicMock()
        mock_run_battery.return_value = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=True, steps=[_fake_step("x", "PASS")],
        )

        explicit_run_id = "explicit-run-id-for-test"
        ctx = _make_ctx(tmp_path, run_id=explicit_run_id)
        CryptoStage0Pipeline().run(ctx)

        assert ctx.run_id == explicit_run_id
        assert ctx.readiness_record["run_id"] == explicit_run_id


# ── run_stage0_workflow (public entry point) ─────────────────────────────────


class TestRunStage0Workflow:
    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_generates_run_id_if_not_provided(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path
    ):
        mock_broker_cls.return_value = MagicMock()
        mock_run_battery.return_value = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=True, steps=[_fake_step("x", "PASS")],
        )

        ctx = run_stage0_workflow(
            paper=True, dry_run=True, output_dir=tmp_path / "out",
        )

        # run_id should be a valid UUID.
        parsed = uuid.UUID(ctx.run_id)
        assert parsed.version == 4

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_uses_explicit_run_id(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path
    ):
        mock_broker_cls.return_value = MagicMock()
        mock_run_battery.return_value = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=True, steps=[_fake_step("x", "PASS")],
        )

        ctx = run_stage0_workflow(
            paper=True, dry_run=True, output_dir=tmp_path / "out",
            run_id="my-explicit-id",
        )

        assert ctx.run_id == "my-explicit-id"


# ── CLI (main) ──────────────────────────────────────────────────────────────


class TestMainExitCode:
    def test_paper_flag_required_by_argparse(self):
        from scripts.crypto_stage0_battery import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--dry-run"])
        assert exc_info.value.code != 0

    def test_non_dry_run_without_bundle_dir_exits_nonzero(self):
        from scripts.crypto_stage0_battery import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--paper"])
        assert exc_info.value.code != 0

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_all_passed_exits_zero(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path, capsys
    ):
        from scripts.crypto_stage0_battery import main

        mock_broker_cls.return_value = MagicMock()
        mock_run_battery.return_value = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=True, steps=[_fake_step("x", "PASS")],
        )
        rc = main(["--paper", "--dry-run", "--bundle-dir", str(tmp_path)])
        assert rc == 0

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_any_required_failure_exits_nonzero(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path, capsys
    ):
        from scripts.crypto_stage0_battery import main

        mock_broker_cls.return_value = MagicMock()
        mock_run_battery.return_value = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=True, steps=[_fake_step("x", "FAIL", required=True)],
        )
        rc = main(["--paper", "--dry-run", "--bundle-dir", str(tmp_path)])
        assert rc != 0

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_error_status_exits_nonzero(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path, capsys
    ):
        from scripts.crypto_stage0_battery import main

        mock_broker_cls.return_value = MagicMock()
        mock_run_battery.return_value = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=True, steps=[_fake_step("x", "ERROR", required=True)],
        )
        rc = main(["--paper", "--dry-run", "--bundle-dir", str(tmp_path)])
        assert rc != 0


class TestCliDelegation:
    """CLI is a thin wrapper -- it ONLY parses args and invokes the workflow."""

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_cli_persists_readiness_record(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path
    ):
        from scripts.crypto_stage0_battery import main

        mock_broker_cls.return_value = MagicMock()
        mock_run_battery.return_value = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=True, steps=[_fake_step("x", "PASS")],
        )
        bundle_dir = tmp_path / "bundles"
        rc = main(["--paper", "--dry-run", "--bundle-dir", str(bundle_dir)])
        assert rc == 0

        readiness_path = bundle_dir / "crypto_stage0_readiness.json"
        assert readiness_path.exists()
        content = json.loads(readiness_path.read_text(encoding="utf-8"))
        assert content["record_type"] == "crypto_stage0_readiness"
        assert content["schema_version"] == 1
        assert "run_id" in content
        # run_id should be a valid UUID (generated by the workflow).
        parsed = uuid.UUID(content["run_id"])
        assert parsed.version == 4

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_cli_json_output_serializable_with_enum_status(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path, capsys
    ):
        """Enum-like StepStatus objects serialize to plain strings in JSON output."""
        from scripts.crypto_stage0_battery import main

        mock_broker_cls.return_value = MagicMock()

        class _FakeStatus:
            # Mimics StepStatus(str, Enum): .value is the plain string.
            def __init__(self, value):
                self.value = value

        mock_run_battery.return_value = BatteryReport(
            timestamp="2026-07-12T22:00:00+00:00",
            account_id="test-account",
            environment="paper",
            dry_run=True,
            steps=[
                StepResult(
                    name="crypto_account_status",
                    status=_FakeStatus("PASS"),
                    detail="ok",
                    data={},
                    required=True,
                ),
            ],
        )

        # Run the CLI -- exit code depends on whether BatteryReport is the
        # real or fallback class (enum vs string comparison in all_passed),
        # but the JSON serialization of the status field is what this test
        # covers, not the exit code.
        main(["--paper", "--dry-run", "--bundle-dir", str(tmp_path)])
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["steps"][0]["status"] == "PASS"

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_non_dry_run_with_bundle_dir_succeeds(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path
    ):
        from scripts.crypto_stage0_battery import main

        mock_broker_cls.return_value = MagicMock()
        mock_run_battery.return_value = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=False, steps=[_fake_step("x", "PASS")],
        )
        bundle_dir = tmp_path / "bundles"
        rc = main(["--paper", "--bundle-dir", str(bundle_dir)])
        assert rc == 0

        readiness_path = bundle_dir / "crypto_stage0_readiness.json"
        assert readiness_path.exists()


# ── Fallback dataclass behavior ─────────────────────────────────────────────


class TestFallbackDataclasses:
    def test_battery_report_all_passed_only_checks_required(self):
        report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=False,
            steps=[
                _fake_step("required_ok", "PASS", required=True),
                _fake_step("optional_skip", "SKIP", required=False),
            ],
        )
        assert report.all_passed is True

    def test_battery_report_error_fails_closed(self):
        report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=False,
            steps=[_fake_step("x", "ERROR", required=True)],
        )
        assert report.all_passed is False
