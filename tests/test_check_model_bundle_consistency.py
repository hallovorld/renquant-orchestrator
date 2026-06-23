"""Unit tests for the pre-deploy model-bundle consistency check.

Uses a synthetic bundle + injected fingerprint functions, so it runs without the
strategy venv. Proves the check catches each of the four contracts that fired
one-by-one in production on 2026-06-23.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_model_bundle_consistency.py"
_spec = importlib.util.spec_from_file_location("bundlecheck", _SCRIPT)
bundlecheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bundlecheck)

LIVE_FP = "sha256:LIVE"
SCORER_FP = "sha256:SCORER"
WATCHLIST = ["AAPL", "MSFT", "NVDA"]


def _write_bundle(tmp_path: Path, *, art_fp=LIVE_FP, art_wl=WATCHLIST,
                  cal_fp=SCORER_FP, wf_passed=True, wf_complete=True) -> Path:
    sd = tmp_path / "backtesting" / "renquant_104"
    (sd / "artifacts" / "prod").mkdir(parents=True, exist_ok=True)
    wf = {}
    if wf_passed is not None:
        wf = {"passed": wf_passed, "operator_authorized_override": True}
        if wf_complete:
            wf.update({"wf_3cut_sharpe_mean": 0.7, "spy_sharpe_mean": 1.08,
                       "strategy_minus_spy_sharpe_mean": -0.38, "n_cuts_beat_spy_sharpe": 1})
    art = {"kind": "panel_ltr_xgboost", "config_fingerprint": art_fp,
           "config_fingerprint_fields": {"watchlist": art_wl},
           "metadata": ({"wf_gate_metadata": wf} if wf else {})}
    (sd / "artifacts" / "prod" / "panel-ltr.alpha158_fund.json").write_text(json.dumps(art))
    cal = {"metadata": {"scorer_model_content_fingerprint": cal_fp}}
    (sd / "artifacts" / "prod" / "panel-rank-calibration.json").write_text(json.dumps(cal))
    cfg = {"watchlist": WATCHLIST,
           "ranking": {"panel_scoring": {
               "kind": "xgb",
               "artifact_path": "artifacts/prod/panel-ltr.alpha158_fund.json",
               "global_calibration": {"enabled": True,
                                      "artifact_path": "artifacts/prod/panel-rank-calibration.json"}}}}
    cfg_path = tmp_path / "strategy_config.json"
    cfg_path.write_text(json.dumps(cfg))
    return cfg_path


def _run(tmp_path: Path, **kw) -> dict:
    cfg_path = _write_bundle(tmp_path, **kw)
    sd = tmp_path / "backtesting" / "renquant_104"
    return bundlecheck.check_bundle(
        cfg_path, sd,
        fingerprint_config=lambda c: LIVE_FP,
        model_content_sha256=lambda a: SCORER_FP,
    )


def _verdict(res, contract):
    return next(c["pass"] for c in res["checks"] if c["contract"] == contract)


def test_consistent_bundle_is_deploy_ready(tmp_path):
    res = _run(tmp_path)
    assert res["deploy_ready"] is True
    assert all(c["pass"] for c in res["checks"])


def test_config_fingerprint_mismatch_fails(tmp_path):
    res = _run(tmp_path, art_fp="sha256:STALE")
    assert res["deploy_ready"] is False
    assert _verdict(res, "config_fingerprint") is False


def test_watchlist_mismatch_fails(tmp_path):
    res = _run(tmp_path, art_wl=["AAPL", "MSFT"])  # trained on fewer names
    assert res["deploy_ready"] is False
    assert _verdict(res, "watchlist") is False


def test_calibrator_scorer_mismatch_fails(tmp_path):
    res = _run(tmp_path, cal_fp="sha256:OTHER_SCORER")
    assert res["deploy_ready"] is False
    assert _verdict(res, "calibrator_scorer_match") is False


def test_wf_metadata_absent_fails(tmp_path):
    res = _run(tmp_path, wf_passed=None)
    assert res["deploy_ready"] is False
    assert _verdict(res, "wf_gate_metadata") is False


def test_wf_metadata_passed_false_fails(tmp_path):
    res = _run(tmp_path, wf_passed=False)
    assert res["deploy_ready"] is False
    assert _verdict(res, "wf_gate_metadata") is False


def test_wf_metadata_missing_numerics_fails(tmp_path):
    res = _run(tmp_path, wf_complete=False)
    assert res["deploy_ready"] is False
    assert _verdict(res, "wf_gate_metadata") is False
