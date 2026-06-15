"""Tests for ``artifact_resolver`` (#108 S1) — the single resolution authority.

Hermetic: every case builds its own tmp layout, so the suite never depends on
the live ``/Users/renhao`` artifact tree.

Pins:
- absolute ref used as-is (source="absolute")
- relative ref: strategy_dir tried first, repo_root fallback
- relative ref present in BOTH -> strategy_dir wins (the incident-#2 invariant)
- missing ref -> FileNotFoundError listing every path tried (fail-closed)
- sha256 matches hashlib over the bytes; streaming hash holds for >1 MiB
- short_sha is the 16-hex manifest/fingerprint form
- verify_sha=False skips hashing
- ArtifactResolver class shares one resolution order across calls
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from renquant_orchestrator.artifact_resolver import (
    ArtifactResolver,
    ResolvedArtifact,
    resolve_artifact,
)


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    """A (strategy_dir, repo_root) pair where strategy_dir is nested in repo_root,
    mirroring RenQuant/backtesting/renquant_104 under RenQuant/."""
    repo_root = tmp_path / "RenQuant"
    strategy_dir = repo_root / "backtesting" / "renquant_104"
    strategy_dir.mkdir(parents=True)
    return strategy_dir, repo_root


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_absolute_ref_used_as_is(layout):
    strategy_dir, repo_root = layout
    art = _write(strategy_dir / "abs.json", b"{}")
    res = resolve_artifact(str(art), strategy_dir=strategy_dir, repo_root=repo_root)
    assert res.path == art.resolve()
    assert res.source == "absolute"
    assert res.ref == str(art)


def test_relative_ref_resolves_strategy_dir(layout):
    strategy_dir, repo_root = layout
    _write(strategy_dir / "artifacts" / "panel-ltr.json", b"strat")
    res = resolve_artifact("artifacts/panel-ltr.json",
                           strategy_dir=strategy_dir, repo_root=repo_root)
    assert res.source == "strategy_dir"
    assert res.path == (strategy_dir / "artifacts" / "panel-ltr.json").resolve()


def test_relative_ref_falls_back_to_repo_root(layout):
    strategy_dir, repo_root = layout
    _write(repo_root / "artifacts" / "model.pt", b"root")
    res = resolve_artifact("artifacts/model.pt",
                           strategy_dir=strategy_dir, repo_root=repo_root)
    assert res.source == "repo_root"
    assert res.path == (repo_root / "artifacts" / "model.pt").resolve()


def test_strategy_dir_wins_when_present_in_both(layout):
    """The incident-#2 invariant: a ref present in both roots ALWAYS resolves
    strategy_dir-first, so primary and shadow can never diverge."""
    strategy_dir, repo_root = layout
    rel = "artifacts/panel-ltr.alpha158_fund.json"
    _write(strategy_dir / rel, b"the-live-one")
    _write(repo_root / rel, b"the-stale-one")
    res = resolve_artifact(rel, strategy_dir=strategy_dir, repo_root=repo_root)
    assert res.source == "strategy_dir"
    assert res.path.read_bytes() == b"the-live-one"


def test_missing_ref_fails_closed_listing_tried(layout):
    strategy_dir, repo_root = layout
    with pytest.raises(FileNotFoundError) as exc:
        resolve_artifact("artifacts/nope.json",
                         strategy_dir=strategy_dir, repo_root=repo_root)
    msg = str(exc.value)
    assert "fail-closed" in msg
    # both candidate paths are reported
    assert str((strategy_dir / "artifacts" / "nope.json").resolve()) in msg
    assert str((repo_root / "artifacts" / "nope.json").resolve()) in msg


def test_sha256_matches_hashlib(layout):
    strategy_dir, repo_root = layout
    content = b"deterministic-bytes-123"
    _write(strategy_dir / "a.json", content)
    res = resolve_artifact("a.json", strategy_dir=strategy_dir, repo_root=repo_root)
    assert res.sha256 == hashlib.sha256(content).hexdigest()
    assert len(res.sha256) == 64
    assert res.short_sha == res.sha256[:16]


def test_streaming_hash_holds_over_multichunk_file(layout):
    """>1 MiB exercises the streaming read loop, not a single read()."""
    strategy_dir, repo_root = layout
    content = b"x" * (3 * (1 << 20) + 7)  # 3 MiB + change
    _write(strategy_dir / "big.pt", content)
    res = resolve_artifact("big.pt", strategy_dir=strategy_dir, repo_root=repo_root)
    assert res.sha256 == hashlib.sha256(content).hexdigest()


def test_verify_sha_false_skips_hashing(layout):
    strategy_dir, repo_root = layout
    _write(strategy_dir / "a.json", b"whatever")
    res = resolve_artifact("a.json", strategy_dir=strategy_dir, repo_root=repo_root,
                           verify_sha=False)
    assert res.sha256 == ""
    assert res.short_sha == ""
    assert res.path.exists()


def test_resolver_class_shares_resolution_order(layout):
    strategy_dir, repo_root = layout
    rel = "artifacts/shared.json"
    _write(strategy_dir / rel, b"strat")
    _write(repo_root / rel, b"root")
    r = ArtifactResolver(strategy_dir=strategy_dir, repo_root=repo_root)
    first = r.resolve(rel)
    second = r.resolve(rel)
    assert first.source == second.source == "strategy_dir"
    assert isinstance(first, ResolvedArtifact)


def test_resolver_class_resolves_distinct_refs(layout):
    strategy_dir, repo_root = layout
    _write(strategy_dir / "primary.pt", b"p")
    _write(repo_root / "shadow.pt", b"s")
    r = ArtifactResolver(strategy_dir=strategy_dir, repo_root=repo_root)
    assert r.resolve("primary.pt").source == "strategy_dir"
    assert r.resolve("shadow.pt").source == "repo_root"
