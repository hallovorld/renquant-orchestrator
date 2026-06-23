"""Unit tests for model_bundle: stamp -> verify, and atomic reversible promote.

Synthetic bundle + injected fingerprint authorities, so the suite runs without the
strategy venv (same convention as tests/test_check_model_bundle_consistency.py).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator import model_bundle as mb

LIVE_FP = "sha256:LIVE"
SCORER_FP = "sha256:SCORER"
WATCHLIST = ["AAPL", "MSFT", "NVDA"]
FP = lambda c: LIVE_FP  # noqa: E731
MC = lambda a: SCORER_FP  # noqa: E731


def _wf(complete=True):
    wf = {"passed": True, "operator_authorized_override": True}
    if complete:
        wf.update({"wf_3cut_sharpe_mean": 0.7, "spy_sharpe_mean": 1.08,
                   "strategy_minus_spy_sharpe_mean": -0.38, "n_cuts_beat_spy_sharpe": 1})
    return wf


def _bundle(tmp_path: Path, *, wf_complete=True, consistent=False):
    """Write a synthetic strategy dir + config. If not `consistent`, the scorer/calibrator
    carry WRONG fingerprints/watchlist so the #172 check fails until stamped."""
    sd = tmp_path / "backtesting" / "renquant_104"
    prod = sd / "artifacts" / "prod"
    prod.mkdir(parents=True, exist_ok=True)
    scorer = {
        "kind": "panel_ltr_xgboost",
        "config_fingerprint": LIVE_FP if consistent else "sha256:STALE",
        "config_fingerprint_fields": {"watchlist": WATCHLIST if consistent else ["AAPL"]},
        "metadata": {"wf_gate_metadata": _wf(wf_complete)} if wf_complete is not None else {},
    }
    (prod / "panel-ltr.alpha158_fund.json").write_text(json.dumps(scorer))
    cal = {"metadata": {"scorer_model_content_fingerprint": SCORER_FP if consistent else "sha256:OTHER"}}
    (prod / "panel-rank-calibration.json").write_text(json.dumps(cal))
    config = {"watchlist": WATCHLIST, "ranking": {"panel_scoring": {
        "kind": "xgb",
        "artifact_path": "artifacts/prod/panel-ltr.alpha158_fund.json",
        "global_calibration": {"enabled": True,
                               "artifact_path": "artifacts/prod/panel-rank-calibration.json"}}}}
    cfg_path = tmp_path / "strategy_config.json"
    cfg_path.write_text(json.dumps(config))
    return cfg_path, sd, prod


def _lock(tmp_path: Path, commit="aaaa111") -> Path:
    lock = {"schema_version": 1, "subrepos": [
        {"name": "renquant-common", "commit": "ffff000"},
        {"name": "renquant-strategy-104", "commit": commit},
    ]}
    p = tmp_path / "subrepos.lock.json"
    p.write_text(json.dumps(lock, indent=2))
    return p


# ── stamp -> verify ──────────────────────────────────────────────────────────

def test_stamp_makes_inconsistent_bundle_deploy_ready(tmp_path):
    cfg, sd, prod = _bundle(tmp_path, consistent=False)
    pre = mb.verify_bundle(cfg, sd, fingerprint_config=FP, model_content_sha256=MC)
    assert pre["deploy_ready"] is False  # starts broken

    mb.stamp_bundle(prod / "panel-ltr.alpha158_fund.json",
                    prod / "panel-rank-calibration.json", cfg,
                    out_dir=prod, fingerprint_config=FP, model_content_sha256=MC)

    post = mb.verify_bundle(cfg, sd, fingerprint_config=FP, model_content_sha256=MC)
    assert post["deploy_ready"] is True
    assert all(c["pass"] for c in post["checks"])


def test_stamp_refuses_without_wf_metadata(tmp_path):
    cfg, sd, prod = _bundle(tmp_path, wf_complete=False, consistent=False)
    with pytest.raises(mb.BundleError):
        mb.stamp_bundle(prod / "panel-ltr.alpha158_fund.json",
                        prod / "panel-rank-calibration.json", cfg,
                        out_dir=prod, fingerprint_config=FP, model_content_sha256=MC)


def test_stamp_refuses_when_wf_metadata_absent(tmp_path):
    cfg, sd, prod = _bundle(tmp_path, wf_complete=None, consistent=False)
    with pytest.raises(mb.BundleError):
        mb.stamp_bundle(prod / "panel-ltr.alpha158_fund.json",
                        prod / "panel-rank-calibration.json", cfg,
                        out_dir=prod, fingerprint_config=FP, model_content_sha256=MC)


# ── atomic pin swap + rollback ───────────────────────────────────────────────

def test_atomic_set_pin_and_rollback_roundtrip(tmp_path):
    lock = _lock(tmp_path, commit="OLD")
    rb = mb.atomic_set_pin(lock, "renquant-strategy-104", "NEW")
    after = json.loads(lock.read_text())
    assert mb._find_subrepo(after, "renquant-strategy-104")["commit"] == "NEW"
    # other repos untouched
    assert mb._find_subrepo(after, "renquant-common")["commit"] == "ffff000"

    restored = mb.rollback_pin(rb)
    assert restored == "OLD"
    assert mb._find_subrepo(json.loads(lock.read_text()), "renquant-strategy-104")["commit"] == "OLD"


def test_atomic_set_pin_rejects_noop_and_missing(tmp_path):
    lock = _lock(tmp_path, commit="SAME")
    with pytest.raises(mb.BundleError):
        mb.atomic_set_pin(lock, "renquant-strategy-104", "SAME")
    with pytest.raises(mb.BundleError):
        mb.atomic_set_pin(lock, "no-such-repo", "X")


# ── promote (verified, reversible) ───────────────────────────────────────────

def test_promote_refuses_inconsistent_bundle(tmp_path):
    cfg, sd, _ = _bundle(tmp_path, consistent=False)
    lock = _lock(tmp_path, commit="OLD")
    res = mb.promote(cfg, sd, lock, "renquant-strategy-104", "NEW",
                     dry_run=False, fingerprint_config=FP, model_content_sha256=MC)
    assert res["promoted"] is False and "deploy_ready" in res["reason"]
    assert mb._find_subrepo(json.loads(lock.read_text()), "renquant-strategy-104")["commit"] == "OLD"


def test_promote_dry_run_does_not_touch_lock(tmp_path):
    cfg, sd, _ = _bundle(tmp_path, consistent=True)
    lock = _lock(tmp_path, commit="OLD")
    res = mb.promote(cfg, sd, lock, "renquant-strategy-104", "NEW",
                     dry_run=True, fingerprint_config=FP, model_content_sha256=MC)
    assert res["promoted"] is False and res["dry_run"] is True
    assert mb._find_subrepo(json.loads(lock.read_text()), "renquant-strategy-104")["commit"] == "OLD"


def test_promote_real_swaps_pin_and_is_reversible(tmp_path):
    cfg, sd, _ = _bundle(tmp_path, consistent=True)
    lock = _lock(tmp_path, commit="OLD")
    res = mb.promote(cfg, sd, lock, "renquant-strategy-104", "NEW",
                     dry_run=False, fingerprint_config=FP, model_content_sha256=MC)
    assert res["promoted"] is True
    assert mb._find_subrepo(json.loads(lock.read_text()), "renquant-strategy-104")["commit"] == "NEW"
    assert mb.rollback_pin(res["rollback_path"]) == "OLD"
    assert mb._find_subrepo(json.loads(lock.read_text()), "renquant-strategy-104")["commit"] == "OLD"
