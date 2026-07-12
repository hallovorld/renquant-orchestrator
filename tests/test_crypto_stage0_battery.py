"""Tests for the crypto Stage-0 paper battery CLI/orchestration (D-C12).

2026-07-12 ownership split: the 7 broker-facing step checks (and their
own unit tests) moved to renquant-execution
(``renquant_execution.crypto_stage0_checks``, renquant-execution#32) —
see ``scripts/crypto_stage0_battery.py``'s module docstring and
``doc/progress/2026-07-12-crypto-stage0-battery.md`` for why. This file
covers only what stays here: CLI argument parsing, --paper live-blocking,
report aggregation, and JSON serialization — never real (or even
alpaca-typed) broker calls. Every step-check function this module calls
is monkeypatched with a fake at the module-qualified name, mirroring this
file's own pre-existing ``_get_trading_client`` patch pattern (now
``get_trading_client``) — so this suite needs no ``alpaca-py`` install at
all (grep the file: it never references ``alpaca``).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from scripts.crypto_stage0_battery import (
    BatteryReport,
    StepResult,
    run_battery,
)


def _fake_step(name, status, detail="", data=None):
    return StepResult(name, status, detail, data or {})


# ── run_battery ──────────────────────────────────────────────────────────────


class TestRunBattery:
    def test_live_blocked(self):
        report = run_battery(paper=False, dry_run=True)
        assert report.failed > 0
        assert report.steps[0].name == "safety"

    @patch("scripts.crypto_stage0_battery.step_data_parity")
    @patch("scripts.crypto_stage0_battery.step_buying_power")
    @patch("scripts.crypto_stage0_battery.step_fee_from_fill")
    @patch("scripts.crypto_stage0_battery.step_stop_limit_acceptance")
    @patch("scripts.crypto_stage0_battery.step_order_acceptance")
    @patch("scripts.crypto_stage0_battery.step_pair_snapshot")
    @patch("scripts.crypto_stage0_battery.step_crypto_status")
    @patch("scripts.crypto_stage0_battery.get_trading_client")
    def test_dry_run_completes(
        self,
        mock_client_fn,
        mock_crypto_status,
        mock_pair_snapshot,
        mock_order_acceptance,
        mock_stop_limit,
        mock_fee_from_fill,
        mock_buying_power,
        mock_data_parity,
    ):
        mock_client_fn.return_value = MagicMock()
        mock_crypto_status.return_value = _fake_step(
            "crypto_status", "PASS", "crypto_status=ACTIVE",
            {"account_id": "test-account-123"},
        )
        mock_pair_snapshot.return_value = _fake_step(
            "pair_snapshot", "PASS", "2 tradable crypto pairs",
        )
        mock_order_acceptance.return_value = _fake_step(
            "order_acceptance", "SKIP", "Skipped in dry-run mode (no orders placed)",
        )
        mock_stop_limit.return_value = _fake_step(
            "stop_limit_acceptance", "SKIP", "Skipped in dry-run mode",
        )
        mock_fee_from_fill.return_value = _fake_step(
            "fee_from_fill", "SKIP", "Skipped in dry-run mode",
        )
        mock_buying_power.return_value = _fake_step(
            "buying_power", "PASS", "cash=10000.00, crypto_bp=10000.00",
        )
        mock_data_parity.return_value = _fake_step(
            "data_parity", "SKIP", "Skipped in dry-run mode",
        )

        report = run_battery(paper=True, dry_run=True)
        assert report.environment == "paper"
        assert report.dry_run is True
        assert len(report.steps) == 7
        assert report.account_id == "test-account-123"
        assert report.steps[0].status == "PASS"  # crypto_status
        assert report.steps[1].status == "PASS"  # pair_snapshot
        assert report.steps[2].status == "SKIP"  # order_acceptance (dry)
        assert report.steps[3].status == "SKIP"  # stop_limit (dry)
        assert report.steps[4].status == "SKIP"  # fee_from_fill (dry)
        assert report.steps[5].status == "PASS"  # buying_power
        assert report.steps[6].status == "SKIP"  # data_parity (dry)
        mock_order_acceptance.assert_called_once_with(mock_client_fn.return_value, dry_run=True)
        mock_stop_limit.assert_called_once_with(mock_client_fn.return_value, dry_run=True)
        mock_fee_from_fill.assert_called_once_with(mock_client_fn.return_value, dry_run=True)
        mock_data_parity.assert_called_once_with(dry_run=True)

    @patch("scripts.crypto_stage0_battery.step_data_parity")
    @patch("scripts.crypto_stage0_battery.step_buying_power")
    @patch("scripts.crypto_stage0_battery.step_fee_from_fill")
    @patch("scripts.crypto_stage0_battery.step_stop_limit_acceptance")
    @patch("scripts.crypto_stage0_battery.step_order_acceptance")
    @patch("scripts.crypto_stage0_battery.step_pair_snapshot")
    @patch("scripts.crypto_stage0_battery.step_crypto_status")
    @patch("scripts.crypto_stage0_battery.get_trading_client")
    def test_summary_json_serializable(
        self,
        mock_client_fn,
        mock_crypto_status,
        mock_pair_snapshot,
        mock_order_acceptance,
        mock_stop_limit,
        mock_fee_from_fill,
        mock_buying_power,
        mock_data_parity,
    ):
        mock_client_fn.return_value = MagicMock()
        mock_crypto_status.return_value = _fake_step(
            "crypto_status", "PASS", "crypto_status=ACTIVE",
            {"account_id": "test-account-123"},
        )
        mock_pair_snapshot.return_value = _fake_step("pair_snapshot", "PASS")
        mock_order_acceptance.return_value = _fake_step("order_acceptance", "SKIP")
        mock_stop_limit.return_value = _fake_step("stop_limit_acceptance", "SKIP")
        mock_fee_from_fill.return_value = _fake_step("fee_from_fill", "SKIP")
        mock_buying_power.return_value = _fake_step("buying_power", "PASS")
        mock_data_parity.return_value = _fake_step("data_parity", "SKIP")

        report = run_battery(paper=True, dry_run=True)
        out = json.dumps(report.summary(), default=str)
        parsed = json.loads(out)
        assert parsed["environment"] == "paper"
        assert isinstance(parsed["steps"], list)
        assert len(parsed["steps"]) == 7


# ── BatteryReport ────────────────────────────────────────────────────────────


class TestBatteryReport:
    def test_counts(self):
        report = BatteryReport(steps=[
            StepResult("a", "PASS"),
            StepResult("b", "FAIL"),
            StepResult("c", "SKIP"),
            StepResult("d", "PASS"),
        ])
        assert report.passed == 2
        assert report.failed == 1
        summary = report.summary()
        assert summary["total"] == 4
        assert summary["skipped"] == 1
