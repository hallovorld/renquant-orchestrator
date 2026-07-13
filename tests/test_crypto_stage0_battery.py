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

    def test_non_uuid_run_id_raises(self, tmp_path):
        ctx = _make_ctx(tmp_path, run_id="not-a-uuid")
        with pytest.raises(ValueError, match="run_id must be a valid UUID"):
            ValidateStage0InputsTask().run(ctx)

    def test_live_blocked_before_any_broker(self, tmp_path):
        ctx = _make_ctx(tmp_path, paper=False)
        result = ValidateStage0InputsTask().run(ctx)
        # Short-circuits the Job (False): the pipeline stops, and
        # run_stage0_workflow handles persistence as a fallback.
        assert result is False
        assert ctx.report is not None
        assert ctx.report.steps[0].name == "safety"
        assert ctx.report.steps[0].status == "FAIL"
        assert ctx.report.all_passed is False
        assert ctx.workflow_ok is False

    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", False)
    def test_missing_dependency_reported_as_fail(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        result = ValidateStage0InputsTask().run(ctx)
        assert result is False
        assert ctx.report is not None
        assert ctx.report.steps[0].name == "dependency"
        assert ctx.report.steps[0].status == "FAIL"
        assert ctx.workflow_ok is False

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
        # Broker must always be disconnected after use.
        mock_broker.disconnect.assert_called_once()

    def test_skips_broker_when_report_already_set(self, tmp_path):
        """ValidateStage0InputsTask already populated ctx.report (a block) --
        RunBatteryTask must not construct or touch a broker at all."""
        ctx = _make_ctx(tmp_path)
        pre_existing_report = BatteryReport(
            timestamp="t", account_id="", environment="LIVE-BLOCKED",
            dry_run=True, steps=[_fake_step("safety", "FAIL")],
        )
        ctx.report = pre_existing_report

        with patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker") as mock_broker_cls:
            result = RunBatteryTask().run(ctx)

        assert result is True
        mock_broker_cls.assert_not_called()
        assert ctx.report is pre_existing_report

    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_disconnect_called_even_when_battery_raises(
        self, mock_broker_cls, mock_run_battery, tmp_path
    ):
        mock_broker = MagicMock()
        mock_broker_cls.return_value = mock_broker
        mock_run_battery.side_effect = RuntimeError("simulated probe failure")

        ctx = _make_ctx(tmp_path)
        result = RunBatteryTask().run(ctx)

        assert result is True
        mock_broker.connect.assert_called_once()
        mock_broker.disconnect.assert_called_once()
        assert ctx.report is not None
        assert ctx.report.all_passed is False
        assert ctx.report.steps[0].status == "ERROR"
        assert "simulated probe failure" in ctx.report.steps[0].detail
        assert ctx.stage_trace[-1]["verdict"] == "ERROR"
        assert ctx.stage_trace[-1]["ok"] is False

    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_disconnect_called_even_when_connect_raises(self, mock_broker_cls, tmp_path):
        mock_broker = MagicMock()
        mock_broker.connect.side_effect = ConnectionError("no credentials")
        mock_broker_cls.return_value = mock_broker

        ctx = _make_ctx(tmp_path)
        result = RunBatteryTask().run(ctx)

        assert result is True
        mock_broker.disconnect.assert_called_once()
        assert ctx.report is not None
        assert ctx.report.all_passed is False
        assert ctx.report.steps[0].status == "ERROR"

    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_constructor_exception_produces_error_report(self, mock_broker_cls, tmp_path):
        """If AlpacaBroker(...) itself raises, the task must still return
        normally with an ERROR report so PersistStage0ReadinessTask can run."""
        mock_broker_cls.side_effect = RuntimeError("missing credentials file")

        ctx = _make_ctx(tmp_path)
        result = RunBatteryTask().run(ctx)

        assert result is True
        assert ctx.report is not None
        assert ctx.report.all_passed is False
        assert ctx.report.steps[0].status == "ERROR"
        assert "missing credentials file" in ctx.report.steps[0].detail

    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_disconnect_failure_after_successful_battery(
        self, mock_broker_cls, mock_run_battery, tmp_path
    ):
        """Successful battery + disconnect() raises -> report gets an ERROR
        step appended, all_passed becomes False, task returns normally."""
        mock_broker = MagicMock()
        mock_broker_cls.return_value = mock_broker
        mock_broker.disconnect.side_effect = OSError("socket already closed")
        mock_run_battery.return_value = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=True, steps=[_fake_step("crypto_account_status", "PASS")],
        )

        ctx = _make_ctx(tmp_path)
        result = RunBatteryTask().run(ctx)

        assert result is True
        assert ctx.report is not None
        # The disconnect error is appended as a required ERROR step.
        disconnect_steps = [s for s in ctx.report.steps if s.name == "broker_disconnect"]
        assert len(disconnect_steps) == 1
        assert disconnect_steps[0].status == "ERROR"
        assert "socket already closed" in disconnect_steps[0].detail
        # The overall verdict must now be FAIL because the ERROR step is required.
        assert ctx.report.all_passed is False

    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_disconnect_failure_after_battery_exception(
        self, mock_broker_cls, mock_run_battery, tmp_path
    ):
        """Battery raises + disconnect() raises -> report captures BOTH errors,
        all_passed is False, task returns normally."""
        mock_broker = MagicMock()
        mock_broker_cls.return_value = mock_broker
        mock_run_battery.side_effect = RuntimeError("probe order failed")
        mock_broker.disconnect.side_effect = OSError("socket already closed")

        ctx = _make_ctx(tmp_path)
        result = RunBatteryTask().run(ctx)

        assert result is True
        assert ctx.report is not None
        assert ctx.report.all_passed is False
        # Primary error is the battery exception.
        assert ctx.report.steps[0].name == "run_battery"
        assert ctx.report.steps[0].status == "ERROR"
        assert "probe order failed" in ctx.report.steps[0].detail
        # Disconnect error is appended as a separate step.
        assert ctx.report.steps[1].name == "broker_disconnect"
        assert ctx.report.steps[1].status == "ERROR"
        assert "socket already closed" in ctx.report.steps[1].detail


# ── Disconnect-failure end-to-end (pipeline + CLI) ──────────────────────────


class TestDisconnectFailureEndToEnd:
    """Verify that disconnect failures do NOT prevent readiness record
    persistence -- the whole reason for the fix."""

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_successful_battery_disconnect_fail_persists_fail_record(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path
    ):
        """Successful battery + disconnect() raises -> persisted FAIL record
        with disconnect error detail, nonzero CLI exit."""
        from scripts.crypto_stage0_battery import main

        mock_broker = MagicMock()
        mock_broker_cls.return_value = mock_broker
        mock_broker.disconnect.side_effect = OSError("socket already closed")
        mock_run_battery.return_value = BatteryReport(
            timestamp="t", account_id="a", environment="paper",
            dry_run=True, steps=[_fake_step("crypto_account_status", "PASS")],
        )

        bundle_dir = tmp_path / "bundles"
        rc = main(["--paper", "--dry-run", "--bundle-dir", str(bundle_dir)])

        # CLI exit must be nonzero because the disconnect error taints the verdict.
        assert rc != 0
        # Exactly one readiness record must be persisted.
        readiness_path = bundle_dir / "crypto_stage0_readiness.json"
        assert readiness_path.exists()
        content = json.loads(readiness_path.read_text(encoding="utf-8"))
        assert content["record_type"] == "crypto_stage0_readiness"
        assert content["verdict"] == "FAIL"
        # The disconnect error must be visible in the persisted report.
        disconnect_steps = [
            s for s in content["report"]["steps"] if s["name"] == "broker_disconnect"
        ]
        assert len(disconnect_steps) == 1
        assert disconnect_steps[0]["status"] == "ERROR"
        assert "socket already closed" in disconnect_steps[0]["detail"]

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_battery_exception_disconnect_fail_persists_fail_record(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path
    ):
        """Battery exception + disconnect() raises -> persisted FAIL record
        with both errors, nonzero CLI exit."""
        from scripts.crypto_stage0_battery import main

        mock_broker = MagicMock()
        mock_broker_cls.return_value = mock_broker
        mock_run_battery.side_effect = RuntimeError("probe order failed")
        mock_broker.disconnect.side_effect = OSError("socket already closed")

        bundle_dir = tmp_path / "bundles"
        rc = main(["--paper", "--dry-run", "--bundle-dir", str(bundle_dir)])

        # CLI exit must be nonzero.
        assert rc != 0
        # Exactly one readiness record must be persisted.
        readiness_path = bundle_dir / "crypto_stage0_readiness.json"
        assert readiness_path.exists()
        content = json.loads(readiness_path.read_text(encoding="utf-8"))
        assert content["record_type"] == "crypto_stage0_readiness"
        assert content["verdict"] == "FAIL"
        # Both errors must be visible in the persisted report.
        step_names = [s["name"] for s in content["report"]["steps"]]
        assert "run_battery" in step_names
        assert "broker_disconnect" in step_names
        battery_step = next(s for s in content["report"]["steps"] if s["name"] == "run_battery")
        assert "probe order failed" in battery_step["detail"]
        disconnect_step = next(
            s for s in content["report"]["steps"] if s["name"] == "broker_disconnect"
        )
        assert "socket already closed" in disconnect_step["detail"]


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
        assert ctx.workflow_ok is True
        assert ctx.readiness_record["record_type"] == "crypto_stage0_readiness"
        assert ctx.readiness_record["run_id"] == ctx.run_id
        assert ctx.readiness_record["verdict"] == "PASS"

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    def test_readiness_record_schema(self, _mock_commit, tmp_path):
        ctx = _make_ctx(tmp_path, run_id="12345678-1234-4abc-8def-123456789abc")
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
        assert rec["run_id"] == "12345678-1234-4abc-8def-123456789abc"
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

        assert ctx.workflow_ok is False
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
        assert ctx.workflow_ok is True
        assert ctx.readiness_record["record_type"] == "crypto_stage0_readiness"
        assert ctx.readiness_record["run_id"] == ctx.run_id

    def test_pipeline_blocked_on_live_fails_closed(self, tmp_path):
        """A safety-gate block must produce a fail-closed pipeline result.

        When ValidateStage0InputsTask returns False, the pipeline stops
        early and result.ok is False (overridden by CryptoStage0Pipeline).
        Readiness record persistence is handled by run_stage0_workflow as
        a post-pipeline fallback (tested in TestRunStage0Workflow).
        """
        ctx = _make_ctx(tmp_path, paper=False)
        pipeline = CryptoStage0Pipeline()
        result = pipeline.run(ctx)

        assert result.ok is False
        assert result.name == "crypto-stage0-readiness"
        assert ctx.report is not None
        assert ctx.report.all_passed is False
        assert ctx.workflow_ok is False

    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", False)
    def test_pipeline_blocked_on_missing_dependency_fails_closed(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        pipeline = CryptoStage0Pipeline()
        result = pipeline.run(ctx)

        assert result.ok is False
        assert ctx.report is not None
        assert ctx.report.steps[0].name == "dependency"
        assert ctx.workflow_ok is False

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_pipeline_battery_exception_fails_closed(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path
    ):
        """A battery exception must produce result.ok=False (fail-closed)
        and persist an ERROR readiness record via the pipeline itself
        (RunBatteryTask catches the exception and PersistStage0ReadinessTask
        still runs)."""
        mock_broker = MagicMock()
        mock_broker_cls.return_value = mock_broker
        mock_run_battery.side_effect = RuntimeError("simulated failure")

        ctx = _make_ctx(tmp_path)
        pipeline = CryptoStage0Pipeline()
        result = pipeline.run(ctx)

        assert result.ok is False
        assert ctx.workflow_ok is False
        assert ctx.report.steps[0].status == "ERROR"
        assert ctx.readiness_record["verdict"] == "FAIL"
        mock_broker.disconnect.assert_called_once()

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

        explicit_run_id = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
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

        explicit_id = "deadbeef-dead-4ead-beef-deadbeefcafe"
        ctx = run_stage0_workflow(
            paper=True, dry_run=True, output_dir=tmp_path / "out",
            run_id=explicit_id,
        )

        assert ctx.run_id == explicit_id

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    def test_live_blocked_persists_fail_readiness_record(self, _mock_commit, tmp_path):
        """run_stage0_workflow must persist a FAIL readiness record even
        when the pipeline stops early due to a safety-gate block."""
        ctx = run_stage0_workflow(
            paper=False, dry_run=True, output_dir=tmp_path / "out",
        )

        assert ctx.workflow_ok is False
        assert ctx.readiness_record != {}
        assert ctx.readiness_record["verdict"] == "FAIL"
        assert ctx.readiness_record["run_id"] == ctx.run_id
        # File must be written to disk.
        readiness_path = ctx.output_dir / "crypto_stage0_readiness.json"
        assert readiness_path.exists()
        content = json.loads(readiness_path.read_text(encoding="utf-8"))
        assert content["verdict"] == "FAIL"

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", False)
    def test_missing_dependency_persists_fail_readiness_record(self, _mock_commit, tmp_path):
        """Missing execution dependency must persist a FAIL readiness record."""
        ctx = run_stage0_workflow(
            paper=True, dry_run=True, output_dir=tmp_path / "out",
        )

        assert ctx.workflow_ok is False
        assert ctx.readiness_record != {}
        assert ctx.readiness_record["verdict"] == "FAIL"
        assert ctx.report.steps[0].name == "dependency"

    @patch("renquant_orchestrator.crypto_stage0_workflow._orchestrator_commit", return_value="abc123")
    @patch("renquant_orchestrator.crypto_stage0_workflow._HAS_CHECKS", True)
    @patch("renquant_orchestrator.crypto_stage0_workflow.run_full_battery")
    @patch("renquant_orchestrator.crypto_stage0_workflow.AlpacaBroker")
    def test_battery_exception_persists_error_readiness_record(
        self, mock_broker_cls, mock_run_battery, _mock_commit, tmp_path
    ):
        """A battery exception must produce a persisted ERROR readiness record."""
        mock_broker = MagicMock()
        mock_broker_cls.return_value = mock_broker
        mock_run_battery.side_effect = RuntimeError("broker exploded")

        ctx = run_stage0_workflow(
            paper=True, dry_run=True, output_dir=tmp_path / "out",
        )

        assert ctx.workflow_ok is False
        assert ctx.readiness_record != {}
        assert ctx.readiness_record["verdict"] == "FAIL"
        assert ctx.report.steps[0].status == "ERROR"
        assert "broker exploded" in ctx.report.steps[0].detail
        mock_broker.disconnect.assert_called_once()


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
