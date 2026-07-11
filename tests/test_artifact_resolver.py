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


# --- manifest-declared artifact store (store-addressed refs) ----------------
#
# 2026-07-10 shadow-ab first-session precheck abort: prod configs author
# artifact refs as umbrella-layout parent walks ("../../artifacts/<...>");
# a pinned checkout has no such geometry. The run manifest declares the
# store explicitly and the resolver honours it FIRST for store-addressed
# refs — no symlink shims, no umbrella reconstruction (Codex on #464).


def test_store_relative_ref_contract():
    from renquant_orchestrator.artifact_resolver import store_relative_ref

    assert store_relative_ref("../../artifacts/x/y.pt") == Path("x/y.pt")
    assert store_relative_ref("artifacts/x.json") == Path("x.json")
    # interior ".." disqualifies (fail-safe to the geometric contract)
    assert store_relative_ref("../../artifacts/../x.pt") is None
    # non-store refs and the bare store itself are not store-addressed
    assert store_relative_ref("configs/x.json") is None
    assert store_relative_ref("../../artifacts") is None
    # absolute refs never store-address
    assert store_relative_ref("/abs/artifacts/x.pt") is None


def test_store_addressed_ref_resolves_from_declared_store(layout, tmp_path):
    strategy_dir, repo_root = layout
    store = tmp_path / "declared-store"
    _write(store / "patchtst/seed_44/model.pt", b"blob")
    res = resolve_artifact(
        "../../artifacts/patchtst/seed_44/model.pt",
        strategy_dir=strategy_dir,
        repo_root=repo_root,
        artifact_store=store,
    )
    assert res.source == "artifact_store"
    assert res.path == (store / "patchtst/seed_44/model.pt").resolve()
    assert res.sha256


def test_pinned_checkout_layout_needs_no_umbrella_geometry(tmp_path):
    # Integration shape: the strategy checkout lives under a runtime repos/
    # dir (NOT two levels below an artifact store) — exactly the layout the
    # first real session ran in. Resolution succeeds through the declared
    # store alone.
    pinned = tmp_path / "runtime" / "repos" / "renquant-strategy-104"
    (pinned / "configs").mkdir(parents=True)
    store = tmp_path / "elsewhere" / "artifact-store"
    _write(store / "panel/model.pt", b"pinned-blob")
    res = resolve_artifact(
        "../../artifacts/panel/model.pt",
        strategy_dir=pinned,
        repo_root=tmp_path / "runtime",
        artifact_store=store,
    )
    assert res.source == "artifact_store"
    assert res.path.read_bytes() == b"pinned-blob"


def test_declared_store_wins_over_geometric_accident(layout):
    strategy_dir, repo_root = layout
    # both the declared store AND the geometric walk exist with DIFFERENT
    # bytes — the explicit contract must win deterministically.
    store = repo_root / "declared"
    _write(store / "m.pt", b"declared")
    _write(strategy_dir / "../../artifacts/m.pt", b"geometric")
    res = resolve_artifact(
        "../../artifacts/m.pt",
        strategy_dir=strategy_dir,
        repo_root=repo_root,
        artifact_store=store,
    )
    assert res.source == "artifact_store"
    assert res.path.read_bytes() == b"declared"


def test_no_store_behaviour_is_unchanged(layout):
    strategy_dir, repo_root = layout
    _write(strategy_dir / "artifacts/m.pt", b"x")
    res = resolve_artifact(
        "artifacts/m.pt", strategy_dir=strategy_dir, repo_root=repo_root,
    )
    assert res.source == "strategy_dir"


def test_store_addressed_miss_never_falls_back_to_geometry(layout, tmp_path):
    # r4 (Codex on #464 r3): once a ref is store-addressed and a store is
    # declared, resolution happens ONLY inside that store — a miss raises
    # even when a geometric candidate exists (a recreated umbrella path must
    # never be silently consumed).
    strategy_dir, repo_root = layout
    empty_store = tmp_path / "empty-store"
    empty_store.mkdir()
    _write(strategy_dir / "artifacts/m.pt", b"geo")
    with pytest.raises(FileNotFoundError) as exc:
        resolve_artifact(
            "artifacts/m.pt",
            strategy_dir=strategy_dir,
            repo_root=repo_root,
            artifact_store=empty_store,
        )
    assert str(empty_store / "m.pt") in str(exc.value)
    # and the geometric candidate is NOT among the tried paths
    assert str(strategy_dir / "artifacts/m.pt") not in str(exc.value)


def test_artifact_symlink_escaping_the_store_fails_closed(layout, tmp_path):
    # r4 resolve-and-contain: a committed symlink below the store may not
    # smuggle resolution outside the verified checkout.
    strategy_dir, repo_root = layout
    store = tmp_path / "store"
    store.mkdir()
    outside = tmp_path / "outside"
    _write(outside / "evil.pt", b"external")
    (store / "m.pt").symlink_to(outside / "evil.pt")
    with pytest.raises(FileNotFoundError, match="escapes the declared artifact store"):
        resolve_artifact(
            "../../artifacts/m.pt",
            strategy_dir=strategy_dir,
            repo_root=repo_root,
            artifact_store=store,
        )


def test_symlink_inside_the_store_is_allowed(layout, tmp_path):
    strategy_dir, repo_root = layout
    store = tmp_path / "store"
    _write(store / "real/m.pt", b"internal")
    (store / "alias.pt").symlink_to(store / "real/m.pt")
    res = resolve_artifact(
        "artifacts/alias.pt",
        strategy_dir=strategy_dir,
        repo_root=repo_root,
        artifact_store=store,
    )
    assert res.source == "artifact_store"
    assert res.path == (store / "real/m.pt").resolve()


def test_non_store_ref_ignores_declared_store(layout, tmp_path):
    strategy_dir, repo_root = layout
    store = tmp_path / "store"
    _write(store / "x.json", b"wrong")
    _write(strategy_dir / "configs/x.json", b"right")
    res = resolve_artifact(
        "configs/x.json",
        strategy_dir=strategy_dir,
        repo_root=repo_root,
        artifact_store=store,
    )
    assert res.source == "strategy_dir"
    assert res.path.read_bytes() == b"right"


def test_resolver_class_carries_artifact_store(layout, tmp_path):
    strategy_dir, repo_root = layout
    store = tmp_path / "store"
    _write(store / "m.pt", b"s")
    r = ArtifactResolver(
        strategy_dir=strategy_dir, repo_root=repo_root, artifact_store=store,
    )
    assert r.resolve("../../artifacts/m.pt").source == "artifact_store"
