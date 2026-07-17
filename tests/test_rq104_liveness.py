"""Tests for ops/renquant104/rq104_liveness_check.py and ops/liveness_common.py."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant104"))


class TestLivenessCommon:
    def test_is_session_day_weekend(self):
        import datetime as dt
        from liveness_common import is_session_day

        with patch("liveness_common.session_calendar") as mock_cal:
            mock_cal.return_value.session_bounds.return_value = None
            assert is_session_day(dt.date(2026, 7, 4)) is False

    def test_is_session_day_weekday(self):
        import datetime as dt
        from liveness_common import is_session_day

        with patch("liveness_common.session_calendar") as mock_cal:
            mock_cal.return_value.session_bounds.return_value = ("09:30", "16:00")
            assert is_session_day(dt.date(2026, 7, 6)) is True

    def test_is_session_day_calendar_failure_fails_closed(self):
        import datetime as dt
        from liveness_common import is_session_day

        with patch("liveness_common.session_calendar") as mock_cal:
            mock_cal.return_value.session_bounds.side_effect = RuntimeError("broken")
            assert is_session_day(dt.date(2026, 7, 6)) is True

    def test_alert_missing_notify_does_not_crash(self, capsys):
        from liveness_common import alert

        with patch.dict("sys.modules", {"renquant_common.notify": None}):
            with patch("builtins.__import__", side_effect=ImportError("no module")):
                alert("test title", "test body")
        err = capsys.readouterr().err
        assert "unavailable" in err
        assert "test title" in err
        assert "test body" in err


class TestRq104Liveness:
    def test_non_session_day_skips(self, tmp_path):
        from rq104_liveness_check import main

        with patch("rq104_liveness_check.is_session_day", return_value=False):
            rc = main(["--as-of", "2026-07-04"])
        assert rc == 0

    def test_missing_logs_detected(self, tmp_path):
        from rq104_liveness_check import main

        with (
            patch("rq104_liveness_check.is_session_day", return_value=True),
            patch("rq104_liveness_check.LOG_DIR", str(tmp_path)),
            patch("rq104_liveness_check.alert") as mock_alert,
        ):
            rc = main(["--as-of", "2026-07-06"])
        assert rc == 1
        mock_alert.assert_called_once()
        alert_body = mock_alert.call_args[0][1]
        # risk_budget is a MONTHLY job (launchd Day=1); on a non-run day a
        # missing wrapper log is NOT a problem (2026-07-16 false alarm).
        assert "risk_budget" not in alert_body
        assert "scorer_identity" in alert_body

    def test_monthly_wrapper_checked_only_on_run_day(self, tmp_path):
        from rq104_liveness_check import main

        # Day 1: risk_budget log missing -> alarm names it.
        (tmp_path / "scorer_identity_2026-07-01.log").write_text(
            "=== ok ===\nscorer_identity_check: OK\n"
        )
        with (
            patch("rq104_liveness_check.is_session_day", return_value=True),
            patch("rq104_liveness_check.LOG_DIR", str(tmp_path)),
            patch("rq104_liveness_check.alert") as mock_alert,
        ):
            rc = main(["--as-of", "2026-07-01"])
        assert rc == 1
        assert "risk_budget" in mock_alert.call_args[0][1]

    def test_all_logs_present_ok(self, tmp_path):
        from rq104_liveness_check import main

        (tmp_path / "risk_budget_2026-07-06.log").write_text("=== ok ===\n")
        log = tmp_path / "scorer_identity_2026-07-06.log"
        log.write_text("=== ok ===\nscorer_identity_check: OK\n")

        with (
            patch("rq104_liveness_check.is_session_day", return_value=True),
            patch("rq104_liveness_check.LOG_DIR", str(tmp_path)),
            patch("rq104_liveness_check.alert") as mock_alert,
        ):
            rc = main(["--as-of", "2026-07-06"])
        assert rc == 0
        mock_alert.assert_not_called()

    def test_fallback_verdict_recognized_without_explicit_marker(self, tmp_path):
        """Isolates the fallback path from the wrapper-log zero-byte check:
        both logs are non-empty, and the scorer_identity log carries only the
        plain 'identity ok' style success line, never the explicit
        'scorer_identity_check:' marker. Must resolve OK on its own -- this
        is the case the case-sensitivity bug (`"identity OK" not in
        text.lower()`, which can never match) made permanently unreachable.
        """
        from rq104_liveness_check import main

        (tmp_path / "risk_budget_2026-07-06.log").write_text("=== ok ===\n")
        (tmp_path / "scorer_identity_2026-07-06.log").write_text("=== ok ===\nidentity OK\n")

        with (
            patch("rq104_liveness_check.is_session_day", return_value=True),
            patch("rq104_liveness_check.LOG_DIR", str(tmp_path)),
            patch("rq104_liveness_check.alert") as mock_alert,
        ):
            rc = main(["--as-of", "2026-07-06"])
        assert rc == 0
        mock_alert.assert_not_called()

    def test_empty_log_detected(self, tmp_path):
        from rq104_liveness_check import main

        # zero-byte DAILY wrapper log (risk_budget is monthly, not checked
        # on 07-06; the zero-byte path is covered via scorer_identity)
        (tmp_path / "scorer_identity_2026-07-06.log").write_text("")

        with (
            patch("rq104_liveness_check.is_session_day", return_value=True),
            patch("rq104_liveness_check.LOG_DIR", str(tmp_path)),
            patch("rq104_liveness_check.alert") as mock_alert,
        ):
            rc = main(["--as-of", "2026-07-06"])
        assert rc == 1
        alert_body = mock_alert.call_args[0][1]
        assert "zero-byte" in alert_body

    def test_scorer_identity_no_verdict_detected(self, tmp_path):
        from rq104_liveness_check import main

        (tmp_path / "risk_budget_2026-07-06.log").write_text("=== ok ===\n")
        (tmp_path / "scorer_identity_2026-07-06.log").write_text("=== crashed ===\nTraceback...\n")

        with (
            patch("rq104_liveness_check.is_session_day", return_value=True),
            patch("rq104_liveness_check.LOG_DIR", str(tmp_path)),
            patch("rq104_liveness_check.alert") as mock_alert,
        ):
            rc = main(["--as-of", "2026-07-06"])
        assert rc == 1
        alert_body = mock_alert.call_args[0][1]
        assert "no verdict" in alert_body
