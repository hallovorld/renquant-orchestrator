"""Tests for the software-stop registry-file contract (READ side only).

PR #481 round 3 (Codex CHANGES_REQUESTED, 2026-07-11): the pager wrapper's
``RENQUANT_STOPS_PAGER_DATA_ROOT`` still names the deprecated umbrella in
production; this module defines the neutral-runtime-root convention (an
exact mirror of ``deployment_manifest.deploy_state_root``) and a fail-closed
envelope validator, so "consume the neutral contract" is concrete and
testable BEFORE the actual writer migration (out of scope for this repo)
lands. See ``doc/progress/2026-07-11-stops-liveness-pager-package.md``
("BLOCKING FOLLOW-UP") for what remains.
"""
from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.software_stops_registry_contract import (
    REGISTRY_ENVELOPE_KIND,
    REGISTRY_ENVELOPE_SCHEMA_VERSION,
    VERDICT_INVALID,
    VERDICT_MISSING,
    VERDICT_UNVERSIONED,
    VERDICT_VALID,
    classify_data_root,
    classify_registry_file,
    describe_data_root,
    registry_envelope_problems,
    runtime_state_root,
    software_stops_registry_path,
    software_stops_registry_root,
)

# --- neutral runtime-state root (mirrors test_state_root_env_override) --------------


def test_runtime_state_root_default_is_sibling_of_deploy_root() -> None:
    assert runtime_state_root() == Path("~/.renquant/runtime").expanduser()


def test_runtime_state_root_env_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RENQUANT_RUNTIME_STATE_ROOT", str(tmp_path / "root"))
    assert runtime_state_root() == tmp_path / "root"
    monkeypatch.delenv("RENQUANT_RUNTIME_STATE_ROOT")
    assert runtime_state_root() == Path("~/.renquant/runtime").expanduser()


def test_runtime_state_root_explicit_override_wins_over_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RENQUANT_RUNTIME_STATE_ROOT", str(tmp_path / "env-root"))
    assert runtime_state_root(tmp_path / "explicit") == tmp_path / "explicit"


def test_software_stops_registry_path_layout(tmp_path: Path) -> None:
    root = software_stops_registry_root(tmp_path)
    assert root == tmp_path / "software-stops"
    assert software_stops_registry_path(tmp_path, broker="alpaca") == root / "alpaca.json"


# --- data-root classifier ------------------------------------------------------------


def test_classify_data_root_neutral_when_under_runtime_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    data_root = runtime_root / "software-stops"
    data_root.mkdir(parents=True)
    verdict = classify_data_root(data_root, runtime_root=runtime_root)
    assert verdict.neutral is True
    assert "NEUTRAL" in verdict.message


def test_classify_data_root_neutral_when_equal_to_runtime_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    verdict = classify_data_root(runtime_root, runtime_root=runtime_root)
    assert verdict.neutral is True


def test_classify_data_root_legacy_for_umbrella_path(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    umbrella_like = tmp_path / "RenQuant"
    umbrella_like.mkdir()
    verdict = classify_data_root(umbrella_like, runtime_root=runtime_root)
    assert verdict.neutral is False
    assert "LEGACY/UNVERSIONED" in verdict.message
    assert "R-PIN writer migration not yet landed" in verdict.message


def test_classify_data_root_legacy_for_actual_production_value(tmp_path: Path) -> None:
    """A non-neutral path (e.g. the deprecated umbrella) must classify
    LEGACY against any neutral root."""
    runtime_root = tmp_path / "runtime"
    verdict = classify_data_root(
        "/Users/renhao/git/github/RenQuant", runtime_root=runtime_root
    )
    assert verdict.neutral is False


def test_describe_data_root_matches_classify(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    assert describe_data_root(tmp_path / "elsewhere", runtime_root=runtime_root) == (
        classify_data_root(tmp_path / "elsewhere", runtime_root=runtime_root).message
    )


# --- envelope contract (versioning marker; never the writer's business schema) -------


def test_registry_envelope_problems_valid_payload() -> None:
    payload = {
        "schema_version": REGISTRY_ENVELOPE_SCHEMA_VERSION,
        "kind": REGISTRY_ENVELOPE_KIND,
    }
    assert registry_envelope_problems(payload) == []


def test_registry_envelope_problems_wrong_schema_version() -> None:
    payload = {"schema_version": 99, "kind": REGISTRY_ENVELOPE_KIND}
    problems = registry_envelope_problems(payload)
    assert any("schema_version" in p for p in problems)


def test_registry_envelope_problems_wrong_kind() -> None:
    payload = {"schema_version": REGISTRY_ENVELOPE_SCHEMA_VERSION, "kind": "something-else"}
    problems = registry_envelope_problems(payload)
    assert any("kind" in p for p in problems)


def test_registry_envelope_problems_non_dict() -> None:
    assert registry_envelope_problems([1, 2, 3]) == ["registry file must be a JSON object"]


# --- classify_registry_file (fail-closed read side) -----------------------------------


def test_classify_registry_file_missing(tmp_path: Path) -> None:
    verdict = classify_registry_file(tmp_path / "does-not-exist.json")
    assert verdict.status == VERDICT_MISSING


def test_classify_registry_file_not_json(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text("not json{{{", encoding="utf-8")
    verdict = classify_registry_file(path)
    assert verdict.status == VERDICT_INVALID


def test_classify_registry_file_unversioned_legacy_shape(tmp_path: Path) -> None:
    """Today's actual registry files (whatever renquant_pipeline.software_stops
    writes) carry no envelope at all — this is the correct, expected,
    fail-closed verdict for every file written before the writer migration."""
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"AAPL": {"stop_price": 190.0, "armed_at": "2026-07-01T00:00:00Z"}}),
        encoding="utf-8",
    )
    verdict = classify_registry_file(path)
    assert verdict.status == VERDICT_UNVERSIONED


def test_classify_registry_file_wrong_schema_version_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"schema_version": 2, "kind": REGISTRY_ENVELOPE_KIND}), encoding="utf-8")
    verdict = classify_registry_file(path)
    assert verdict.status == VERDICT_INVALID


def test_classify_registry_file_valid_envelope(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": REGISTRY_ENVELOPE_SCHEMA_VERSION,
                "kind": REGISTRY_ENVELOPE_KIND,
                "positions": {},
            }
        ),
        encoding="utf-8",
    )
    verdict = classify_registry_file(path)
    assert verdict.status == VERDICT_VALID
