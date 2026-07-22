"""Tests for ops/renquant104/dawn_preflight_attest.py (GOAL-5 AC5; PR #565).

The dawn shell guard must fail closed unless live.runner --preflight attests a
clean no-write/no-notify probe that reached a decision. These pin that the
verifier accepts ONLY a positive attestation and flags every failure class.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops" / "renquant104"))
from dawn_preflight_attest import main, verify  # noqa: E402

# The exact line live.runner emits for a clean probe (json.dumps of the guard
# payload) — kept in lockstep with live/runner.py::_emit_preflight_attestation.
_CLEAN_PAYLOAD = {
    "persisted": False, "notified": False, "promoted": False,
    "ordered": False, "reached_decision": True,
}
CLEAN_LINE = "preflight_attestation: " + json.dumps(_CLEAN_PAYLOAD)

HEALTHY = f"""
[multirepo] routed 54 kernel modules to renquant-pipeline
RENQUANT-104 [full (preflight)] PREFLIGHT-DECISION reached — no orders, no state persisted, no ntfy
{CLEAN_LINE}
runner rc=0 (attestation + analyzer own the verdict)
"""


class TestVerify:
    def test_clean_attestation_passes(self):
        assert verify(HEALTHY) == []

    def test_missing_attestation_fails_closed(self):
        log = "[multirepo] routed modules\nsome funnel output\n"
        problems = verify(log)
        assert problems and "no preflight_attestation" in problems[0]

    def test_notified_true_flagged(self):
        payload = dict(_CLEAN_PAYLOAD, notified=True)
        log = "preflight_attestation: " + json.dumps(payload)
        assert any("'notified'" in p for p in verify(log))

    def test_persisted_true_flagged(self):
        payload = dict(_CLEAN_PAYLOAD, persisted=True)
        log = "preflight_attestation: " + json.dumps(payload)
        assert any("'persisted'" in p for p in verify(log))

    def test_ordered_true_flagged(self):
        payload = dict(_CLEAN_PAYLOAD, ordered=True)
        log = "preflight_attestation: " + json.dumps(payload)
        assert any("'ordered'" in p for p in verify(log))

    def test_reached_decision_false_flagged(self):
        payload = dict(_CLEAN_PAYLOAD, reached_decision=False)
        log = "preflight_attestation: " + json.dumps(payload)
        assert any("'reached_decision'" in p for p in verify(log))

    def test_malformed_json_flagged(self):
        log = "preflight_attestation: {not json}\n"
        assert any("not valid JSON" in p for p in verify(log))

    def test_last_attestation_line_wins(self):
        # A stray earlier line must not mask a terminal failure (or vice versa).
        bad = dict(_CLEAN_PAYLOAD, persisted=True)
        log = (
            "preflight_attestation: " + json.dumps(_CLEAN_PAYLOAD) + "\n"
            "preflight_attestation: " + json.dumps(bad) + "\n"
        )
        assert any("'persisted'" in p for p in verify(log))


class TestMain:
    def test_main_clean_returns_zero(self, tmp_path):
        log = tmp_path / "dawn.log"
        log.write_text(HEALTHY)
        assert main(["--log", str(log), "--no-alert"]) == 0

    def test_main_dirty_returns_one(self, tmp_path):
        log = tmp_path / "dawn.log"
        payload = dict(_CLEAN_PAYLOAD, notified=True)
        log.write_text("preflight_attestation: " + json.dumps(payload))
        assert main(["--log", str(log), "--no-alert"]) == 1

    def test_main_missing_log_returns_one(self, tmp_path):
        assert main(["--log", str(tmp_path / "nope.log"), "--no-alert"]) == 1
