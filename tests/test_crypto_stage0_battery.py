"""Tests for the crypto Stage-0 paper battery CLI/orchestration (D-C12).

2026-07-12 ownership split: all broker-facing step checks, safety gates
(paper-only enforcement, fail-closed environment verification, the
required/optional step policy), and their aggregation into a
``BatteryReport`` live in renquant-execution
(``renquant_execution.crypto_stage0_checks.run_full_battery``,
renquant-execution#34) — see ``scripts/crypto_stage0_battery.py``'s module
docstring and ``doc/progress/2026-07-12-crypto-stage0-battery.md`` for why.
This file covers only what stays here: CLI argument parsing, --paper
live-blocking before any broker object is created, delegation to
``run_full_battery`` with a connected broker, JSON report serialization
(including ``StepStatus`` enum -> plain string), run bundle persistence
(report + orchestrator identity + content hash), and exit-code handling —
never real (or even alpaca-typed) broker calls. ``run_full_battery`` and
``AlpacaBroker`` are both monkeypatched at the module-qualified name, so
this suite needs no ``alpaca-py`` install at all (grep the file: it never
references ``alpaca``).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from scripts.crypto_stage0_battery import (
    BUNDLE_CONTRACT_VERSION,
    BatteryReport,
    StepResult,
    build_run_bundle,
    main,
    run_battery,
)


def _fake_step(name, status, detail="", data=None, required=True):
    return StepResult(name=name, status=status, detail=detail, data=data or {}, required=required)


# ── run_battery ──────────────────────────────────────────────────────────────


class TestRunBattery:
    def test_live_blocked_before_any_broker_created(self):
        with patch("scripts.crypto_stage0_battery.AlpacaBroker") as mock_broker_cls:
            report = run_battery(paper=False, dry_run=True)
        assert report.steps[0].name == "safety"
        assert report.steps[0].status == "FAIL"
        assert report.all_passed is False
        mock_broker_cls.assert_not_called()

    @patch("scripts.crypto_stage0_battery._HAS_CHECKS", False)
    def test_missing_dependency_reported_as_fail(self):
        report = run_battery(paper=True, dry_run=True)
        assert report.steps[0].name == "dependency"
        assert report.steps[0].status == "FAIL"

    @patch("scripts.crypto_stage0_battery._HAS_CHECKS", True)
    @patch("scripts.crypto_stage0_battery.run_full_battery")
    @patch("scripts.crypto_stage0_battery.AlpacaBroker")
    def test_paper_constructs_and_connects_broker_then_delegates(
        self, mock_broker_cls, mock_run_full_battery
    ):
        mock_broker = MagicMock()
        mock_broker_cls.return_value = mock_broker
        expected_report = BatteryReport(
            timestamp="2026-07-12T22:00:00+00:00",
            account_id="test-account-123",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("crypto_account_status", "PASS")],
        )
        mock_run_full_battery.return_value = expected_report

        report = run_battery(paper=True, dry_run=True)

        mock_broker_cls.assert_called_once_with(paper=True)
        mock_broker.connect.assert_called_once_with()
        mock_run_full_battery.assert_called_once_with(mock_broker, dry_run=True)
        assert report is expected_report

    @patch("scripts.crypto_stage0_battery._HAS_CHECKS", True)
    @patch("scripts.crypto_stage0_battery.run_full_battery")
    @patch("scripts.crypto_stage0_battery.AlpacaBroker")
    def test_summary_json_serializable_including_enum_status(
        self, mock_broker_cls, mock_run_full_battery
    ):
        mock_broker_cls.return_value = MagicMock()

        class _FakeStatus:
            # Mimics StepStatus(str, Enum): .value is the plain string.
            def __init__(self, value):
                self.value = value

        mock_run_full_battery.return_value = BatteryReport(
            timestamp="2026-07-12T22:00:00+00:00",
            account_id="test-account-123",
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

        report = run_battery(paper=True, dry_run=True)
        from scripts.crypto_stage0_battery import _report_to_jsonable

        summary = _report_to_jsonable(report)
        out = json.dumps(summary, default=str)
        parsed = json.loads(out)
        assert parsed["environment"] == "paper"
        assert parsed["steps"][0]["status"] == "PASS"


# ── main() exit codes ────────────────────────────────────────────────────────


class TestMainExitCode:
    def test_live_without_paper_flag_exits_nonzero(self, capsys):
        # --paper is argparse-required, so omitting it is a parse-time
        # SystemExit (code 2), not a run_battery-level FAIL — argparse
        # itself makes the flag mandatory; run_battery's own paper=False
        # branch is defense-in-depth for direct/programmatic callers.
        import pytest

        with pytest.raises(SystemExit) as exc_info:
            main(["--dry-run"])
        assert exc_info.value.code != 0

    @patch("scripts.crypto_stage0_battery._HAS_CHECKS", True)
    @patch("scripts.crypto_stage0_battery.run_full_battery")
    @patch("scripts.crypto_stage0_battery.AlpacaBroker")
    def test_all_passed_exits_zero(self, mock_broker_cls, mock_run_full_battery, capsys):
        mock_broker_cls.return_value = MagicMock()
        report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("x", "PASS")],
        )
        mock_run_full_battery.return_value = report
        rc = main(["--paper", "--dry-run"])
        assert rc == 0

    @patch("scripts.crypto_stage0_battery._HAS_CHECKS", True)
    @patch("scripts.crypto_stage0_battery.run_full_battery")
    @patch("scripts.crypto_stage0_battery.AlpacaBroker")
    def test_any_required_failure_exits_nonzero(self, mock_broker_cls, mock_run_full_battery, capsys):
        mock_broker_cls.return_value = MagicMock()
        report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("x", "FAIL", required=True)],
        )
        mock_run_full_battery.return_value = report
        rc = main(["--paper", "--dry-run"])
        assert rc != 0

    @patch("scripts.crypto_stage0_battery._HAS_CHECKS", True)
    @patch("scripts.crypto_stage0_battery.run_full_battery")
    @patch("scripts.crypto_stage0_battery.AlpacaBroker")
    def test_error_only_battery_exits_nonzero(self, mock_broker_cls, mock_run_full_battery, capsys):
        """Codex review finding 1: ERROR status must fail closed (exit != 0)."""
        mock_broker_cls.return_value = MagicMock()
        report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("x", "ERROR", required=True)],
        )
        mock_run_full_battery.return_value = report
        rc = main(["--paper", "--dry-run"])
        assert rc != 0


# ── BatteryReport / StepResult fallback dataclasses ─────────────────────────


class TestFallbackDataclasses:
    def test_battery_report_all_passed_property_exists(self):
        report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=False,
            steps=[_fake_step("a", "PASS")],
        )
        # Real BatteryReport.all_passed only considers required steps; this
        # just checks the attribute is reachable through this module's import.
        assert hasattr(report, "all_passed")


# ── run bundle ─────────────────────────────────────────────────────────────────


class TestRunBundle:
    @patch("scripts.crypto_stage0_battery._orchestrator_commit", return_value="abc123def456")
    def test_bundle_envelope_structure(self, _mock_commit):
        report = BatteryReport(
            timestamp="2026-07-12T22:00:00+00:00",
            account_id="test-account",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("crypto_account_status", "PASS")],
        )
        bundle = build_run_bundle(report)

        assert bundle["bundle_contract_version"] == BUNDLE_CONTRACT_VERSION
        assert bundle["orchestrator_commit"] == "abc123def456"
        assert "bundle_timestamp" in bundle
        assert bundle["verdict"] == "PASS"
        assert "report_sha256" in bundle
        assert len(bundle["report_sha256"]) == 64  # SHA-256 hex digest
        assert bundle["report"]["environment"] == "paper"
        assert bundle["report"]["all_passed"] is True

    @patch("scripts.crypto_stage0_battery._orchestrator_commit", return_value="abc123def456")
    def test_bundle_verdict_fail_on_required_failure(self, _mock_commit):
        report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=False,
            steps=[
                _fake_step("ok_step", "PASS", required=True),
                _fake_step("bad_step", "FAIL", required=True),
            ],
        )
        bundle = build_run_bundle(report)
        assert bundle["verdict"] == "FAIL"

    @patch("scripts.crypto_stage0_battery._orchestrator_commit", return_value="abc123def456")
    def test_bundle_verdict_pass_when_only_optional_fails(self, _mock_commit):
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
        bundle = build_run_bundle(report)
        assert bundle["verdict"] == "PASS"

    @patch("scripts.crypto_stage0_battery._orchestrator_commit", return_value="abc123def456")
    def test_bundle_report_sha256_is_deterministic(self, _mock_commit):
        report = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("x", "PASS")],
        )
        bundle1 = build_run_bundle(report)
        bundle2 = build_run_bundle(report)
        # Same report content -> same hash (deterministic canonical serialization).
        assert bundle1["report_sha256"] == bundle2["report_sha256"]

    @patch("scripts.crypto_stage0_battery._orchestrator_commit", return_value="abc123def456")
    def test_bundle_report_sha256_changes_on_content_change(self, _mock_commit):
        report_a = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("x", "PASS")],
        )
        report_b = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("x", "FAIL")],
        )
        sha_a = build_run_bundle(report_a)["report_sha256"]
        sha_b = build_run_bundle(report_b)["report_sha256"]
        assert sha_a != sha_b

    @patch("scripts.crypto_stage0_battery._HAS_CHECKS", True)
    @patch("scripts.crypto_stage0_battery.run_full_battery")
    @patch("scripts.crypto_stage0_battery.AlpacaBroker")
    @patch("scripts.crypto_stage0_battery._orchestrator_commit", return_value="abc123")
    def test_bundle_dir_persists_bundle_file(
        self, _mock_commit, mock_broker_cls, mock_run_full_battery, tmp_path
    ):
        mock_broker_cls.return_value = MagicMock()
        mock_run_full_battery.return_value = BatteryReport(
            timestamp="t",
            account_id="a",
            environment="paper",
            dry_run=True,
            steps=[_fake_step("x", "PASS")],
        )
        bundle_dir = tmp_path / "bundles"
        rc = main(["--paper", "--dry-run", "--bundle-dir", str(bundle_dir)])
        assert rc == 0

        # A bundle file should have been created in the directory.
        bundle_files = list(bundle_dir.glob("crypto_stage0_bundle_*.json"))
        assert len(bundle_files) == 1

        bundle = json.loads(bundle_files[0].read_text(encoding="utf-8"))
        assert bundle["bundle_contract_version"] == BUNDLE_CONTRACT_VERSION
        assert bundle["orchestrator_commit"] == "abc123"
        assert bundle["verdict"] == "PASS"
        assert "report_sha256" in bundle
        assert bundle["report"]["all_passed"] is True
