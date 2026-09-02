"""A4-T1 governance — orchestrator consumption tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator import a4t1_governance as G

RUN_ID = "20260831T141820Z"
DIGEST = "760912ec122fa6e02628077df8b35e58145209ea3b6b395bd670d8ead9e4af1e"


def _gov(tmp_path: Path) -> Path:
    gov = tmp_path / "governance"
    gov.mkdir()
    return gov


def test_consume_creates_marker_and_returns_proof(tmp_path):
    gov = _gov(tmp_path)
    staging = tmp_path / "staging.json"
    staging.write_text("{}", encoding="utf-8")
    proof = G.consume(RUN_ID, DIGEST, staging, governance_dir=gov)
    assert proof["run_id"] == RUN_ID
    assert proof["artifact_digest"] == DIGEST
    assert proof["consumed_by"] == "renquant-orchestrator"
    assert "consumed_at" in proof
    marker = gov / f"a4t1_{RUN_ID}.consumed"
    assert marker.exists()
    stored = json.loads(marker.read_text())
    assert stored == proof


def test_consume_replay_raises_file_exists(tmp_path):
    gov = _gov(tmp_path)
    staging = tmp_path / "staging.json"
    staging.write_text("{}", encoding="utf-8")
    G.consume(RUN_ID, DIGEST, staging, governance_dir=gov)
    with pytest.raises(FileExistsError):
        G.consume(RUN_ID, DIGEST, staging, governance_dir=gov)


def test_consume_no_governance_dir_raises(tmp_path):
    staging = tmp_path / "staging.json"
    staging.write_text("{}", encoding="utf-8")
    missing = tmp_path / "nonexistent"
    with pytest.raises(FileNotFoundError, match="governance directory"):
        G.consume(RUN_ID, DIGEST, staging, governance_dir=missing)


def test_is_consumed_false_before_true_after(tmp_path):
    gov = _gov(tmp_path)
    staging = tmp_path / "staging.json"
    staging.write_text("{}", encoding="utf-8")
    assert not G.is_consumed(RUN_ID, governance_dir=gov)
    G.consume(RUN_ID, DIGEST, staging, governance_dir=gov)
    assert G.is_consumed(RUN_ID, governance_dir=gov)


def test_corrupt_marker_is_consumed(tmp_path):
    """A corrupt marker is still considered consumed (fail-closed)."""
    gov = _gov(tmp_path)
    marker = gov / f"a4t1_{RUN_ID}.consumed"
    marker.write_text("CORRUPT", encoding="utf-8")
    assert G.is_consumed(RUN_ID, governance_dir=gov)


def test_cross_directory_replay_blocked(tmp_path):
    """Two staging paths share one governance dir — second consume is blocked."""
    gov = _gov(tmp_path)
    dir1 = tmp_path / "dir1"
    dir1.mkdir()
    dir2 = tmp_path / "dir2"
    dir2.mkdir()
    staging1 = dir1 / "staging.json"
    staging1.write_text("{}", encoding="utf-8")
    staging2 = dir2 / "staging.json"
    staging2.write_text("{}", encoding="utf-8")
    G.consume(RUN_ID, DIGEST, staging1, governance_dir=gov)
    with pytest.raises(FileExistsError):
        G.consume(RUN_ID, DIGEST, staging2, governance_dir=gov)


def test_different_run_ids_independent(tmp_path):
    gov = _gov(tmp_path)
    staging = tmp_path / "staging.json"
    staging.write_text("{}", encoding="utf-8")
    G.consume("20260901T120000Z", DIGEST, staging, governance_dir=gov)
    assert not G.is_consumed(RUN_ID, governance_dir=gov)
    G.consume(RUN_ID, DIGEST, staging, governance_dir=gov)
    assert G.is_consumed(RUN_ID, governance_dir=gov)
