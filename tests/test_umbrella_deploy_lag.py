"""Behavioural tests for umbrella deploy-lag detection.

The bug this guards: on 2026-07-29 the live umbrella tree sat 9 commits behind
origin/main, so a merged `--panel` flag was absent from the tree that actually
runs, while `check_umbrella_branch` passed clean the entire time because the
BRANCH NAME was right. A test that greps for the string "behind" would also
have passed on a check that never compares anything, so these drive the real
function against real on-disk ref layouts.
"""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parent.parent / "ops"

SHA_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SHA_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _load(rq_root: Path):
    spec = importlib.util.spec_from_file_location(
        "run_surface_drift_check", OPS / "run_surface_drift_check.py")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, str(OPS))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(OPS))
    mod.RQ = str(rq_root)
    return mod


def _fake_tree(tmp_path: Path, live: str | None, fetched: str | None,
               *, packed: bool = False, age_days: float = 0.0) -> Path:
    root = tmp_path / "umbrella"
    git = root / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "refs" / "remotes" / "origin").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    if packed:
        lines = ["# pack-refs with: peeled fully-peeled sorted "]
        if live:
            lines.append(f"{live} refs/heads/main")
        if fetched:
            lines.append(f"{fetched} refs/remotes/origin/main")
        (git / "packed-refs").write_text("\n".join(lines) + "\n")
    else:
        if live:
            (git / "refs" / "heads" / "main").write_text(live + "\n")
        if fetched:
            (git / "refs" / "remotes" / "origin" / "main").write_text(fetched + "\n")
    stamp = time.time() - age_days * 86400.0
    fh = git / "FETCH_HEAD"
    fh.write_text(f"{fetched or SHA_A}\t\tbranch 'main' of github\n")
    import os
    os.utime(fh, (stamp, stamp))
    return root


def test_in_sync_reports_no_problem(tmp_path):
    mod = _load(_fake_tree(tmp_path, SHA_A, SHA_A))
    problems, infos = mod.check_umbrella_deploy_lag()
    assert problems == []
    assert any("deploy lag: none" in i for i in infos)


def test_behind_is_detected_and_names_both_shas(tmp_path):
    """The exact 2026-07-29 condition: on main, but not AT origin/main."""
    mod = _load(_fake_tree(tmp_path, SHA_A, SHA_B))
    problems, _ = mod.check_umbrella_deploy_lag()
    assert len(problems) == 1
    assert SHA_A[:8] in problems[0] and SHA_B[:8] in problems[0]
    assert "DARK" in problems[0]


def test_the_branch_name_check_alone_would_have_missed_it(tmp_path):
    """Regression guard on the actual gap: branch-name-clean + drifted sha."""
    root = _fake_tree(tmp_path, SHA_A, SHA_B)
    mod = _load(root)
    assert mod.check_umbrella_branch() == []          # old check: clean
    problems, _ = mod.check_umbrella_deploy_lag()
    assert problems                                    # new check: catches it


def test_packed_refs_are_resolved(tmp_path):
    """A freshly-gc'd repo has no loose refs at all."""
    mod = _load(_fake_tree(tmp_path, SHA_A, SHA_B, packed=True))
    assert mod._resolve_ref(mod.RQ, "refs/heads/main") == SHA_A
    assert mod._resolve_ref(mod.RQ, "refs/remotes/origin/main") == SHA_B
    problems, _ = mod.check_umbrella_deploy_lag()
    assert problems and SHA_B[:8] in problems[0]


def test_missing_remote_ref_is_reported_not_crashed(tmp_path):
    mod = _load(_fake_tree(tmp_path, SHA_A, None))
    problems, _ = mod.check_umbrella_deploy_lag()
    assert len(problems) == 1
    assert "unmeasurable" in problems[0]
    assert "does not write" in problems[0]


def test_missing_local_ref_is_reported_not_crashed(tmp_path):
    mod = _load(_fake_tree(tmp_path, None, SHA_B))
    problems, _ = mod.check_umbrella_deploy_lag()
    assert len(problems) == 1 and "unmeasurable" in problems[0]


def test_stale_fetch_is_flagged_even_when_shas_match(tmp_path):
    """In-sync against a month-old fetch is not evidence of being in sync."""
    mod = _load(_fake_tree(tmp_path, SHA_A, SHA_A, age_days=30.0))
    problems, _ = mod.check_umbrella_deploy_lag()
    assert len(problems) == 1
    assert "stale remote" in problems[0]


def test_fresh_fetch_is_not_flagged(tmp_path):
    mod = _load(_fake_tree(tmp_path, SHA_A, SHA_A, age_days=1.0))
    problems, _ = mod.check_umbrella_deploy_lag()
    assert problems == []


def test_never_invokes_git_in_the_live_tree(tmp_path, monkeypatch):
    """The design property, enforced: this scan reads git metadata as FILES.
    A sub-agent's `git reset --hard` in the shared live checkout is why."""
    mod = _load(_fake_tree(tmp_path, SHA_A, SHA_B))

    def boom(*a, **k):
        raise AssertionError(f"deploy-lag check invoked a subprocess: {a!r}")

    monkeypatch.setattr(mod.subprocess, "run", boom)
    monkeypatch.setattr(mod.subprocess, "check_output", boom, raising=False)
    problems, _ = mod.check_umbrella_deploy_lag()
    assert problems


def test_now_is_injectable_so_the_test_is_not_clock_dependent(tmp_path):
    root = _fake_tree(tmp_path, SHA_A, SHA_A, age_days=0.0)
    mod = _load(root)
    future = time.time() + 40 * 86400.0
    problems, _ = mod.check_umbrella_deploy_lag(now=future)
    assert any("stale remote" in p for p in problems)
