"""Tests for ops/renquant104/dawn_funnel_analyze.py (GOAL-5 AC5, D2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops" / "renquant104"))
from dawn_funnel_analyze import analyze  # noqa: E402

HEALTHY = """
[multirepo] routed 54 kernel modules to renquant-pipeline
preflight ✓ P-WF-GATE [HARD] buys admitted under a governed operator authorization
LoadGlobalCalibrationTask: loaded pooled (pool_IC=0.1149)
ApplyGlobalCalibrationTask: calibrated 5/5 candidates, 4/4 holdings
ntfy sent: [READONLY]RENQUANT-104 [full] SHADOW-DECISION | no trade
runner rc=0 (analyzer owns the verdict)
"""


class TestAnalyze:
    def test_healthy_funnel_is_clean(self):
        assert analyze(HEALTHY) == []

    def test_calibrator_contract_fail_detected(self):
        log = HEALTHY + "\nValueError: LoadGlobalCalibrationTask contract fail: fingerprint mismatch\n"
        assert any("contract failure" in p for p in analyze(log))

    def test_config_mismatch_detected(self):
        log = HEALTHY + "\nPanel scoring contract failed (panel_scorer_config_mismatch).\n"
        assert any("config-consistency" in p for p in analyze(log))

    def test_import_gap_524_class_detected(self):
        log = HEALTHY + (
            "\nModuleNotFoundError: No module named "
            "'renquant_pipeline.kernel.meta_label.task_meta_label_veto'\n"
        )
        assert any("#524 class" in p for p in analyze(log))

    def test_pin_drift_detected(self):
        log = HEALTHY + "\n[multirepo] subrepo pin drift:\n  - renquant-pipeline: HEAD x != lock y\n"
        assert any("pins drifted" in p for p in analyze(log))

    def test_traceback_detected_even_with_decision_line(self):
        log = HEALTHY + "\nTraceback (most recent call last):\n  ...\n"
        assert any("unhandled exception" in p for p in analyze(log))

    def test_missing_decision_line_detected(self):
        log = "[multirepo] routed modules\nprepare_inference_panel_frames: progress 10/145\n"
        assert any("never reached a decision" in p for p in analyze(log))
