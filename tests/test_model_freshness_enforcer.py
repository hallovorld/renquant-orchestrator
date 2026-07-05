"""Tests for model freshness enforcement (read-only recommendation engine)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from renquant_orchestrator.model_freshness_enforcer import (
    ACTION_NONE,
    ACTION_PROMOTE_FRESHEST,
    ACTION_PROMOTE_PASSING,
    CandidateResult,
    EnforcementResult,
    _classify_gate_failure,
    enforce,
    main,
    scan_candidates,
)
from renquant_orchestrator.model_freshness_monitor import (
    PROD_FAST_POLICY,
)


NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


def _write_artifact(path: Path, *, cutoff: str, passed: bool | None = None,
                    failure_reason: str = "", trained_date: str = "2026-07-01",
                    lookahead_days: int | None = None) -> Path:
    """Write a minimal panel-ltr artifact JSON."""
    data = {
        "label_observation_cutoff": cutoff,
        "trained_date": trained_date,
    }
    if lookahead_days is not None:
        data["lookahead_days"] = lookahead_days
    if passed is not None:
        wf = {"passed": passed}
        if failure_reason:
            wf["failure_reason"] = failure_reason
        data["wf_gate_metadata"] = wf
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


# ─── Gate failure classification ──────────────────────────────────────


def test_classify_gate_none():
    passed, cls, _ = _classify_gate_failure(None)
    assert not passed
    assert cls == "no_gate"


def test_classify_gate_empty():
    passed, cls, _ = _classify_gate_failure({})
    assert not passed
    assert cls == "unknown"


def test_classify_gate_passed():
    passed, cls, _ = _classify_gate_failure({"passed": True})
    assert passed
    assert cls == "none"


def test_classify_gate_infra_timeout():
    passed, cls, _ = _classify_gate_failure({
        "passed": False,
        "failure_reason": "ParallelTimeoutError: 600s exceeded",
    })
    assert not passed
    assert cls == "infra"


def test_classify_gate_infra_path_not_found():
    passed, cls, _ = _classify_gate_failure({
        "passed": False,
        "failure_reason": "FileNotFoundError: panel-ltr.json artifact-not-found",
    })
    assert not passed
    assert cls == "infra"


def test_classify_gate_infra_kind_parity():
    passed, cls, _ = _classify_gate_failure({
        "passed": False,
        "failure_reason": "scorer-kind parity-mismatch: xgb vs hf_patchtst",
    })
    assert not passed
    assert cls == "infra"


def test_classify_gate_substance_sub_spy():
    passed, cls, _ = _classify_gate_failure({
        "passed": False,
        "failure_reason": "sub-SPY Sharpe: 0.35 vs 1.07",
    })
    assert not passed
    assert cls == "substance"


def test_classify_gate_substance_generic():
    passed, cls, _ = _classify_gate_failure({"passed": False})
    assert not passed
    assert cls == "substance"


def test_classify_gate_unknown_neither():
    passed, cls, _ = _classify_gate_failure({"something_else": 42})
    assert not passed
    assert cls == "unknown"


def test_classify_gate_infra_via_error_field():
    passed, cls, _ = _classify_gate_failure({
        "passed": False,
        "error": "ParallelTimeoutError in WF gate",
    })
    assert not passed
    assert cls == "infra"


# ─── Candidate scanning ──────────────────────────────────────────────


@pytest.fixture()
def artifact_dir(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    _write_artifact(
        staging / "panel-ltr.alpha158_fund.json",
        cutoff="2026-06-30", passed=True, lookahead_days=60,
    )
    _write_artifact(
        staging / "panel-ltr.v2.json",
        cutoff="2026-06-25", passed=False, failure_reason="ParallelTimeoutError",
        lookahead_days=60,
    )
    _write_artifact(
        staging / "panel-ltr.old.json",
        cutoff="2026-01-01", passed=True, lookahead_days=60,
        trained_date="2026-01-01",
    )
    # Fresh retrain (trained_date recent) whose fwd_60d label_observation_cutoff
    # is necessarily ~80-100d old by construction — must NOT be excluded by the
    # scan window (Codex round 2/3: window binds to trained_date, not cutoff).
    _write_artifact(
        staging / "panel-ltr.fresh_retrain_wide_horizon.json",
        cutoff="2026-04-10", passed=True, lookahead_days=60,
        trained_date="2026-07-03",
    )
    # Not a panel-ltr file
    _write_artifact(
        staging / "other-model.json",
        cutoff="2026-07-01", passed=True, lookahead_days=60,
    )
    # Staging file (excluded)
    _write_artifact(
        staging / "panel-ltr.staging.staging.json",
        cutoff="2026-07-01", passed=True, lookahead_days=60,
    )
    # Metadata sidecar (excluded)
    _write_artifact(
        staging / "panel-ltr.pt.metadata.json",
        cutoff="2026-07-01", passed=True, lookahead_days=60,
    )
    return tmp_path


def test_scan_candidates_finds_recent(artifact_dir):
    candidates = scan_candidates(
        [artifact_dir / "staging"], NOW, window_days=10,
    )
    names = [Path(c.path).name for c in candidates]
    assert "panel-ltr.alpha158_fund.json" in names
    assert "panel-ltr.v2.json" in names
    assert "panel-ltr.old.json" not in names
    assert not any("other-model" in n for n in names)
    assert not any(n.endswith(".staging.json") for n in names)
    assert not any(n.endswith(".metadata.json") for n in names)


def test_scan_candidates_window_binds_to_trained_date_not_cutoff_age(artifact_dir):
    """Codex round 2/3: a genuinely fresh retrain whose fwd_60d cutoff is ~85d
    old by construction must still be scanned — the window is production
    recency (trained_date), never the label-horizon-widened cutoff age."""
    candidates = scan_candidates(
        [artifact_dir / "staging"], NOW, window_days=10,
    )
    names = [Path(c.path).name for c in candidates]
    assert "panel-ltr.fresh_retrain_wide_horizon.json" in names
    fresh = next(c for c in candidates if Path(c.path).name == "panel-ltr.fresh_retrain_wide_horizon.json")
    assert fresh.age_days is not None and fresh.age_days > 10, (
        "fixture must actually exercise the wide-horizon case (cutoff age > window_days)"
    )


def test_scan_candidates_classifies_gates(artifact_dir):
    candidates = scan_candidates(
        [artifact_dir / "staging"], NOW, window_days=10,
    )
    passing = [c for c in candidates if c.gate_passed]
    infra = [c for c in candidates if c.failure_class == "infra"]
    assert len(passing) >= 1
    assert len(infra) >= 1


def test_scan_candidates_sorted_by_age(artifact_dir):
    candidates = scan_candidates(
        [artifact_dir / "staging"], NOW, window_days=10,
    )
    ages = [c.age_days for c in candidates if c.age_days is not None]
    assert ages == sorted(ages)


def test_scan_candidates_empty_dir(tmp_path):
    candidates = scan_candidates([tmp_path / "nonexistent"], NOW)
    assert candidates == []


def test_scan_candidates_deduplicates(artifact_dir):
    candidates = scan_candidates(
        [artifact_dir / "staging", artifact_dir / "staging"],
        NOW, window_days=10,
    )
    paths = [c.path for c in candidates]
    assert len(paths) == len(set(paths))


# ─── Enforcement logic ────────────────────────────────────────────────


@pytest.fixture()
def enforce_dirs(tmp_path):
    prod_dir = tmp_path / "prod"
    staging_dir = tmp_path / "staging"
    prod_dir.mkdir()
    staging_dir.mkdir()
    return tmp_path, prod_dir, staging_dir


def test_enforce_healthy_model(enforce_dirs):
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-06-30", lookahead_days=60,
    )
    result = enforce(prod, [staging_dir], NOW, breach_days=28)
    assert not result.stale
    assert result.action == ACTION_NONE
    assert "no enforcement needed" in result.detail


def test_enforce_breach_days_is_authoritative_over_default_policy(enforce_dirs):
    """``breach_days`` must actually drive tiering, not just the detail text.

    age=100d sits between the 14d-effective (14+82 lag=96d, BREACH) and
    28d-effective (28+82 lag=110d, HEALTHY) thresholds. Pre-fix, passing
    ``breach_days=14`` without also constructing a matching ``FreshnessPolicy``
    silently kept evaluating against the default ``PROD_FAST_POLICY`` (28d),
    so this artifact read HEALTHY even though the caller asked for a 14d ceiling.
    """
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-03-26", lookahead_days=60,
    )
    result_default_policy_14 = enforce(prod, [staging_dir], NOW, breach_days=14)
    assert result_default_policy_14.stale, (
        "breach_days=14 must be authoritative even with the default policy object"
    )

    result_28 = enforce(prod, [staging_dir], NOW, breach_days=28)
    assert not result_28.stale


def test_enforce_stale_with_passing_candidate(enforce_dirs):
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-03-01", lookahead_days=60,
    )
    _write_artifact(
        staging_dir / "panel-ltr.candidate.json",
        cutoff="2026-06-28", passed=True, lookahead_days=60,
    )
    result = enforce(prod, [staging_dir], NOW, breach_days=28)
    assert result.stale
    assert result.action == ACTION_PROMOTE_PASSING
    assert result.gate_passed
    assert result.failure_class == "none"
    assert "candidate" in result.recommended_path


def test_enforce_stale_with_infra_only_candidate(enforce_dirs):
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-03-01", lookahead_days=60,
    )
    _write_artifact(
        staging_dir / "panel-ltr.candidate.json",
        cutoff="2026-06-28", passed=False,
        failure_reason="ParallelTimeoutError", lookahead_days=60,
    )
    result = enforce(prod, [staging_dir], NOW, breach_days=28)
    assert result.stale
    assert result.action == ACTION_PROMOTE_FRESHEST
    assert not result.gate_passed
    assert result.failure_class == "infra"
    assert "Pillar 3 DEFERRED" in result.detail


def test_enforce_stale_with_substance_only_candidate(enforce_dirs):
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-03-01", lookahead_days=60,
    )
    _write_artifact(
        staging_dir / "panel-ltr.candidate.json",
        cutoff="2026-06-28", passed=False,
        failure_reason="sub-SPY Sharpe", lookahead_days=60,
    )
    result = enforce(prod, [staging_dir], NOW, breach_days=28)
    assert result.stale
    assert result.action == ACTION_NONE
    assert result.candidates_scanned == 1
    assert result.candidates_passing == 0
    assert "none gate-passing or infra-only" in result.detail


def test_enforce_stale_no_candidates(enforce_dirs):
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-03-01", lookahead_days=60,
    )
    result = enforce(prod, [staging_dir], NOW, breach_days=28)
    assert result.stale
    assert result.action == ACTION_NONE
    assert result.candidates_scanned == 0


def test_enforce_prefers_passing_over_infra(enforce_dirs):
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-03-01", lookahead_days=60,
    )
    _write_artifact(
        staging_dir / "panel-ltr.infra.json",
        cutoff="2026-07-01", passed=False,
        failure_reason="timeout", lookahead_days=60,
    )
    _write_artifact(
        staging_dir / "panel-ltr.passing.json",
        cutoff="2026-06-28", passed=True, lookahead_days=60,
    )
    result = enforce(prod, [staging_dir], NOW, breach_days=28)
    assert result.action == ACTION_PROMOTE_PASSING
    assert result.gate_passed
    assert "passing" in result.recommended_path


def test_enforce_missing_prod_panel(enforce_dirs):
    root, prod_dir, staging_dir = enforce_dirs
    missing = prod_dir / "panel-ltr.alpha158_fund.json"
    result = enforce(missing, [staging_dir], NOW)
    assert result.stale
    assert result.current_tier == "breach"


def test_enforce_unknown_cutoff_is_stale(enforce_dirs):
    root, prod_dir, staging_dir = enforce_dirs
    prod = prod_dir / "panel-ltr.alpha158_fund.json"
    prod.parent.mkdir(parents=True, exist_ok=True)
    prod.write_text(json.dumps({"trained_date": "2026-07-01"}))
    result = enforce(prod, [staging_dir], NOW)
    assert result.stale
    assert result.current_tier == "unknown"


# ─── Result serialization ────────────────────────────────────────────


def test_enforcement_result_as_dict():
    r = EnforcementResult(stale=True, action=ACTION_PROMOTE_PASSING)
    d = r.as_dict()
    assert d["stale"] is True
    assert d["action"] == ACTION_PROMOTE_PASSING
    assert "candidates_scanned" in d


def test_candidate_result_as_dict():
    from renquant_orchestrator.model_freshness_monitor import ArtifactFreshness
    c = CandidateResult(
        path="/foo/bar.json",
        freshness=ArtifactFreshness(label="test", path="/foo/bar.json"),
        gate_passed=True,
        failure_class="none",
    )
    d = c.as_dict()
    assert d["gate_passed"] is True
    assert d["path"] == "/foo/bar.json"


# ─── CLI ──────────────────────────────────────────────────────────────


def test_cli_json_output(enforce_dirs, capsys):
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-06-30", lookahead_days=60,
    )
    rc = main([
        "--as-of", "2026-07-04",
        "--prod-panel", str(prod),
        "--search-dir", str(staging_dir),
        "--json",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "action" in data
    assert data["stale"] is False


def test_cli_stale_json(enforce_dirs, capsys):
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-03-01", lookahead_days=60,
    )
    rc = main([
        "--as-of", "2026-07-04",
        "--prod-panel", str(prod),
        "--search-dir", str(staging_dir),
        "--json",
    ])
    assert rc == 2
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["stale"] is True
    assert data["action"] == ACTION_NONE


def test_cli_text_output(enforce_dirs, capsys):
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-06-30", lookahead_days=60,
    )
    rc = main([
        "--as-of", "2026-07-04",
        "--prod-panel", str(prod),
        "--search-dir", str(staging_dir),
    ])
    captured = capsys.readouterr()
    assert "Model freshness enforcement" in captured.out
    assert rc == 0


def test_cli_stale_with_candidate_exit_code(enforce_dirs):
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-03-01", lookahead_days=60,
    )
    _write_artifact(
        staging_dir / "panel-ltr.candidate.json",
        cutoff="2026-06-28", passed=True, lookahead_days=60,
    )
    rc = main([
        "--as-of", "2026-07-04",
        "--prod-panel", str(prod),
        "--search-dir", str(staging_dir),
        "--quiet",
    ])
    assert rc == 1


def test_cli_window_days(enforce_dirs, capsys):
    root, prod_dir, staging_dir = enforce_dirs
    prod = _write_artifact(
        prod_dir / "panel-ltr.alpha158_fund.json",
        cutoff="2026-03-01", lookahead_days=60,
    )
    _write_artifact(
        staging_dir / "panel-ltr.candidate.json",
        cutoff="2026-06-20", passed=True, lookahead_days=60,
        trained_date="2026-06-15",  # produced outside the 5d window
    )
    rc = main([
        "--as-of", "2026-07-04",
        "--prod-panel", str(prod),
        "--search-dir", str(staging_dir),
        "--window-days", "5",
        "--json",
    ])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["candidates_scanned"] == 0
