"""Tests for the software-stop registry-file contract (LOCATION side only).

PR #481 round 3 (Codex CHANGES_REQUESTED, 2026-07-11): the pager wrapper's
``RENQUANT_STOPS_PAGER_DATA_ROOT`` still names the deprecated umbrella in
production; this module defines the neutral-runtime-root convention (an
exact mirror of ``deployment_manifest.deploy_state_root``), so "consume the
neutral contract" is concrete and testable BEFORE the actual writer
migration (out of scope for this repo) lands.

Round 5 correction (Codex CHANGES_REQUESTED, 2026-07-12T04:32:57Z): the
round-3 revision also invented a versioned "envelope" content schema
(``schema_version``/``kind``, ``classify_registry_file``) that this repo
does not own and that never matched what the real writer
(``renquant_pipeline.software_stops``) produces. That machinery — and its
tests — has been removed. Registry CONTENT validity is now delegated to
``renquant_execution.software_stops_liveness`` (backed by
``renquant_pipeline.software_stops``'s real schema); see
``scripts/install_stops_pager.sh`` for the fail-closed pre-install guard
that now calls it. This module keeps only the LOCATION convention (the
neutral runtime-state root) and the NEUTRAL-vs-LEGACY path classifier.
See ``doc/progress/2026-07-11-stops-liveness-pager-package.md`` for the
full round history.
"""
from __future__ import annotations

from pathlib import Path

from renquant_orchestrator.software_stops_registry_contract import (
    classify_data_root,
    describe_data_root,
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
