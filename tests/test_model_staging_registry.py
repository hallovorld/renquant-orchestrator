"""Tests for the read-only rolling staging registry (#210)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from renquant_orchestrator.model_staging_registry import (
    CATEGORY_INFRA,
    CATEGORY_LEAKAGE,
    CATEGORY_NONE,
    CATEGORY_PLACEBO,
    CATEGORY_SUBSTANTIVE,
    CATEGORY_UNKNOWN,
    INFRA_FAILURE_CLASSES,
    INTEGRITY_FLOOR_KEYS,
    ModelStagingRegistry,
    StagingCandidate,
    classify_failure,
    passes_integrity_floor,
    selection_score,
)

AS_OF = date(2026, 6, 30)  # injected clock


def _payload(
    artifact_id: str,
    *,
    family: str = "panel",
    trained: str = "2026-06-28",
    cutoff: str = "2026-06-25",
    created: str | None = None,
    verdict: str = "fail",
    failure_class: str | None = "timeout",
    oos_sharpe: float = 0.5,
    spy_sharpe: float = 0.3,
    integrity_ok: bool = True,
) -> dict:
    if created is None:
        created = f"{trained}T12:00:00Z"
    integ = (
        {k: True for k in INTEGRITY_FLOOR_KEYS}
        if integrity_ok
        else {"loads": True}  # missing keys → fails the floor
    )
    return {
        "artifact_id": artifact_id,
        "model_family": family,
        "artifact_path": f"artifacts/{artifact_id}/model.pt",
        "artifact_created_at": created,
        "data_cutoff": cutoff,
        "trained_date": trained,
        "gate": {
            "verdict": verdict,
            "failure_class": failure_class,
            "observed_at": created,
        },
        "quality": {
            "oos_sharpe": oos_sharpe,
            "spy_sharpe": spy_sharpe,
            "genuine_ic": 0.03,
            "net_return": 0.01,
        },
        "integrity": integ,
    }


def _write(staging_dir: Path, artifact_id: str, **kw) -> Path:
    staging_dir.mkdir(parents=True, exist_ok=True)
    path = staging_dir / f"{artifact_id}.staging.json"
    path.write_text(json.dumps(_payload(artifact_id, **kw)), encoding="utf-8")
    return path


# ── scan ──────────────────────────────────────────────────────────────────
def test_scan_finds_all_sidecars(tmp_path):
    _write(tmp_path, "a", trained="2026-06-28")
    _write(tmp_path, "b", trained="2026-06-27")
    # a nested sidecar should also be found (rglob)
    _write(tmp_path / "sub", "c", trained="2026-06-26")
    # a non-sidecar json is ignored
    (tmp_path / "not_a_sidecar.json").write_text("{}", encoding="utf-8")

    reg = ModelStagingRegistry.scan(tmp_path)
    ids = {c.artifact_id for c in reg.valid()}
    assert ids == {"a", "b", "c"}


def test_scan_missing_dir_is_empty_not_error(tmp_path):
    reg = ModelStagingRegistry.scan(tmp_path / "does_not_exist")
    assert reg.candidates == []


def test_scan_family_filter(tmp_path):
    _write(tmp_path, "panel1", family="panel")
    _write(tmp_path, "tour1", family="tournament")
    reg = ModelStagingRegistry.scan(tmp_path, family="tournament")
    assert {c.artifact_id for c in reg.valid()} == {"tour1"}


def test_scan_is_read_only(tmp_path):
    _write(tmp_path, "a")
    _write(tmp_path, "b")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.staging.json")}
    ModelStagingRegistry.scan(tmp_path).within_last_days(10, as_of=AS_OF)
    after = {p: p.read_bytes() for p in tmp_path.rglob("*.staging.json")}
    assert before == after
    # no new files created by a scan
    assert set(before) == set(after)


# ── last-N-days query ───────────────────────────────────────────────────────
def test_within_last_days_filters_by_age_and_orders_newest_first(tmp_path):
    _write(tmp_path, "fresh", trained="2026-06-29")   # age 1
    _write(tmp_path, "mid", trained="2026-06-24")     # age 6
    _write(tmp_path, "edge", trained="2026-06-20")    # age 10 (inclusive)
    _write(tmp_path, "stale", trained="2026-06-15")   # age 15 > 10
    reg = ModelStagingRegistry.scan(tmp_path)

    recent = reg.within_last_days(10, as_of=AS_OF)
    assert [c.artifact_id for c in recent] == ["fresh", "mid", "edge"]


def test_beyond_window_returns_none(tmp_path):
    _write(tmp_path, "stale", trained="2026-06-15")  # age 15
    reg = ModelStagingRegistry.scan(tmp_path)
    assert reg.within_last_days(10, as_of=AS_OF) == []


def test_future_dated_candidate_excluded(tmp_path):
    _write(tmp_path, "future", trained="2026-07-05", created="2026-07-05T12:00:00Z")
    reg = ModelStagingRegistry.scan(tmp_path)
    assert reg.within_last_days(10, as_of=AS_OF) == []


def test_missing_availability_fails_closed(tmp_path):
    # No artifact_created_at / registry_available_at at all → not available (§5.0-i-a).
    staging = tmp_path
    staging.mkdir(parents=True, exist_ok=True)
    payload = _payload("noavail", trained="2026-06-29")
    payload.pop("artifact_created_at")
    (staging / "noavail.staging.json").write_text(json.dumps(payload), encoding="utf-8")
    reg = ModelStagingRegistry.scan(staging)

    assert reg.within_last_days(10, as_of=AS_OF, require_available=True) == []
    # but visible when availability is not required
    got = reg.within_last_days(10, as_of=AS_OF, require_available=False)
    assert [c.artifact_id for c in got] == ["noavail"]


def test_created_after_as_of_excluded_even_if_cutoff_old(tmp_path):
    # Registered July 5 against a June-25 cutoff: NOT available to a June-30 decision.
    _write(tmp_path, "backfilled", trained="2026-06-29",
           created="2026-07-05T09:00:00Z")
    reg = ModelStagingRegistry.scan(tmp_path)
    assert reg.within_last_days(10, as_of=AS_OF, require_available=True) == []


# ── failure classification (infra vs substance) ─────────────────────────────
@pytest.mark.parametrize(
    "raw,verdict,expected",
    [
        ("timeout", "fail", CATEGORY_INFRA),
        ("ParallelTimeoutError", "fail", CATEGORY_INFRA),
        ("config_path_not_found", "fail", CATEGORY_INFRA),
        ("artifact_not_found", "fail", CATEGORY_INFRA),
        # Codex r7: a recipe / fingerprint mismatch of ANY flavour is NOT
        # comparable to the prod contract → fail-closed (substantive), never infra.
        ("recipe_fingerprint_mismatch", "fail", CATEGORY_SUBSTANTIVE),
        ("recipe_mismatch", "fail", CATEGORY_SUBSTANTIVE),
        ("fingerprint_mismatch", "fail", CATEGORY_SUBSTANTIVE),
        ("sub_spy", "fail", CATEGORY_SUBSTANTIVE),
        ("delta_sharpe_negative", "fail", CATEGORY_SUBSTANTIVE),
        ("recipe_identity_mismatch", "fail", CATEGORY_SUBSTANTIVE),
        ("placebo_contamination", "fail", CATEGORY_PLACEBO),
        ("placebo_floor", "fail", CATEGORY_PLACEBO),  # conservative: placebo → fail closed
        ("leakage_detected", "fail", CATEGORY_LEAKAGE),
        ("some_new_weird_error", "fail", CATEGORY_UNKNOWN),
        (None, "fail", CATEGORY_UNKNOWN),   # unclassified failure
        (None, "pass", CATEGORY_NONE),
        ("", "pass", CATEGORY_NONE),
    ],
)
def test_classify_failure(raw, verdict, expected):
    assert classify_failure(raw, verdict) == expected


def test_infra_failure_classes_narrowed_to_mechanical_only():
    # Codex r7: the enumerated infra allowlist is timeout / config-path /
    # artifact-not-found ONLY. Recipe/fingerprint mismatches are a comparability
    # violation, not a mechanical rescue, and must never be in this set.
    assert INFRA_FAILURE_CLASSES == frozenset(
        {"timeout", "config_path", "artifact_not_found"}
    )
    assert "recipe_mismatch" not in INFRA_FAILURE_CLASSES
    assert "recipe_fingerprint_mismatch" not in INFRA_FAILURE_CLASSES


def test_candidate_carries_classified_category(tmp_path):
    _write(tmp_path, "s", verdict="fail", failure_class="sub_spy_no_edge")
    reg = ModelStagingRegistry.scan(tmp_path)
    cand = reg.valid()[0]
    assert cand.failure_category == CATEGORY_SUBSTANTIVE
    assert cand.raw_failure_class == "sub_spy_no_edge"


# ── integrity floor + selection score ───────────────────────────────────────
def test_integrity_floor():
    ok = {k: True for k in INTEGRITY_FLOOR_KEYS}
    assert passes_integrity_floor(ok) is True
    # one missing key → fails
    missing = dict(ok)
    missing.pop("recipe_loads")
    assert passes_integrity_floor(missing) is False
    # one falsey → fails
    falsey = dict(ok)
    falsey["not_degenerate"] = False
    assert passes_integrity_floor(falsey) is False
    assert passes_integrity_floor({}) is False
    assert passes_integrity_floor(None) is False


def test_selection_score_prefers_oos_sharpe_then_genuine_ic():
    assert selection_score({"oos_sharpe": 0.4, "genuine_ic": 0.03}) == 0.4
    assert selection_score({"genuine_ic": 0.03}) == 0.03
    assert selection_score({}) is None
    assert selection_score({"oos_sharpe": True}) is None  # bool is not a score


# ── malformed sidecars degrade, never crash ─────────────────────────────────
def test_malformed_sidecar_degrades_to_parse_error(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "bad.staging.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "arr.staging.json").write_text("[1,2,3]", encoding="utf-8")
    _write(tmp_path, "good", trained="2026-06-29")

    reg = ModelStagingRegistry.scan(tmp_path)
    assert {c.artifact_id for c in reg.valid()} == {"good"}
    broken = [c for c in reg.candidates if c.parse_error is not None]
    assert {c.artifact_id for c in broken} == {"bad.staging.json", "arr.staging.json"}
    # broken candidates never enter a window query
    assert [c.artifact_id for c in reg.within_last_days(10, as_of=AS_OF)] == ["good"]


def test_candidate_from_dict_defaults():
    cand = StagingCandidate.from_dict({}, "x.staging.json")
    assert cand.artifact_id == "x.staging.json"
    assert cand.model_family == "unknown"
    # no gate info at all → conservative: unknown (fail-closed), not a pass
    assert cand.failure_category == CATEGORY_UNKNOWN
    assert cand.recency_date() is None
    assert cand.age_days(AS_OF) is None
    assert cand.available_at is None
    assert cand.is_available_at(AS_OF) is False
