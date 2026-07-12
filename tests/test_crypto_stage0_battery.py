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
(including ``StepStatus`` enum -> plain string), and exit-code handling —
never real (or even alpaca-typed) broker calls. ``run_full_battery`` and
``AlpacaBroker`` are both monkeypatched at the module-qualified name, so
this suite needs no ``alpaca-py`` install at all (grep the file: it never
references ``alpaca``).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from scripts.crypto_stage0_battery import (
    BatteryReport,
    StepResult,
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
