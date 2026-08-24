"""orch#1041 round 2: existence is not pin verification.

Every test here is a REFUSAL the scheduler's LIVE prerequisite depends on:
missing lock entry, wrong HEAD, dirty config, unreadable git state, missing
file — plus the measured original defect (an unrelated sibling must never
win). The resolver under test is the generalized #1037 implementation
(`rq105_pinned_common.py`), loaded from its file exactly as the shell wrapper
invokes it.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "rq105_pinned_common", ROOT / "ops" / "renquant105" / "rq105_pinned_common.py")
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _mk_pinned(tmp_path: Path, *, cfg_body='{"a": 1}\n') -> tuple[Path, str]:
    """A real git checkout at .subrepo_runtime/repos/renquant-strategy-104
    with configs/strategy_config.json committed, plus a matching lock."""
    rq = tmp_path / "RQ"
    co = rq / ".subrepo_runtime" / "repos" / "renquant-strategy-104"
    (co / "configs").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(co)], check=True)
    (co / "configs" / "strategy_config.json").write_text(cfg_body)
    _git(co, "add", "-A")
    _git(co, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "pin")
    head = _git(co, "rev-parse", "HEAD")
    (rq / "subrepos.lock.json").write_text(json.dumps(
        {"subrepos": [{"name": "renquant-strategy-104", "commit": head}]}))
    return rq, head


def test_a_clean_pinned_config_verifies_and_returns_its_path(tmp_path):
    rq, _ = _mk_pinned(tmp_path)
    got = mod.verify_pinned_file(str(rq), "renquant-strategy-104",
                                 "configs/strategy_config.json")
    assert got.endswith(".subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json")


def test_a_missing_lock_entry_refuses(tmp_path):
    rq, _ = _mk_pinned(tmp_path)
    (rq / "subrepos.lock.json").write_text(json.dumps({"subrepos": []}))
    with pytest.raises(mod.PinRefusal, match="no renquant-strategy-104 entry"):
        mod.verify_pinned_file(str(rq), "renquant-strategy-104",
                               "configs/strategy_config.json")


def test_a_wrong_HEAD_refuses(tmp_path):
    rq, _ = _mk_pinned(tmp_path)
    lock = json.loads((rq / "subrepos.lock.json").read_text())
    lock["subrepos"][0]["commit"] = "0" * 40
    (rq / "subrepos.lock.json").write_text(json.dumps(lock))
    with pytest.raises(mod.PinRefusal, match="a directory name is not a revision"):
        mod.verify_pinned_file(str(rq), "renquant-strategy-104",
                               "configs/strategy_config.json")


def test_a_DIRTY_config_refuses_even_at_the_right_HEAD(tmp_path):
    """The check codex asked for by name: existence and a correct HEAD are not
    enough — a hand-edited file in a pinned checkout is exactly as unreviewed
    as a sibling tree."""
    rq, _ = _mk_pinned(tmp_path)
    co = rq / ".subrepo_runtime" / "repos" / "renquant-strategy-104"
    (co / "configs" / "strategy_config.json").write_text('{"a": 999}\n')
    with pytest.raises(mod.PinRefusal, match="DIRTY relative to"):
        mod.verify_pinned_file(str(rq), "renquant-strategy-104",
                               "configs/strategy_config.json")


def test_unreadable_git_state_refuses(tmp_path):
    rq, _ = _mk_pinned(tmp_path)
    co = rq / ".subrepo_runtime" / "repos" / "renquant-strategy-104"
    subprocess.run(["rm", "-rf", str(co / ".git")], check=True)
    with pytest.raises(mod.PinRefusal):
        mod.verify_pinned_file(str(rq), "renquant-strategy-104",
                               "configs/strategy_config.json")


def test_a_missing_file_refuses(tmp_path):
    rq, _ = _mk_pinned(tmp_path)
    co = rq / ".subrepo_runtime" / "repos" / "renquant-strategy-104"
    (co / "configs" / "strategy_config.json").unlink()
    with pytest.raises(mod.PinRefusal, match="missing from the pinned"):
        mod.verify_pinned_file(str(rq), "renquant-strategy-104",
                               "configs/strategy_config.json")


def test_an_unrelated_sibling_must_never_win(tmp_path):
    """The measured original defect, restated against the resolver: a sibling
    checkout with a DIFFERENT config must not influence the result — the
    returned path and bytes are the pinned checkout's, full stop."""
    rq, _ = _mk_pinned(tmp_path, cfg_body='{"pinned": true}\n')
    sibling = tmp_path / "gh" / "renquant-strategy-104" / "configs"
    sibling.mkdir(parents=True)
    (sibling / "strategy_config.json").write_text('{"sibling": true}\n')
    got = mod.verify_pinned_file(str(rq), "renquant-strategy-104",
                                 "configs/strategy_config.json")
    assert ".subrepo_runtime" in got
    assert json.loads(Path(got).read_text()) == {"pinned": True}


def test_the_cli_verify_file_mode_round_trips(tmp_path):
    rq, _ = _mk_pinned(tmp_path)
    r = subprocess.run(
        ["python3", str(ROOT / "ops" / "renquant105" / "rq105_pinned_common.py"),
         "--rq-root", str(rq), "--subrepo", "renquant-strategy-104",
         "--verify-file", "configs/strategy_config.json"],
        capture_output=True, text=True)
    assert r.returncode == 0 and ".subrepo_runtime" in r.stdout.strip()


def test_the_cli_refuses_dirty_with_nonzero_exit(tmp_path):
    rq, _ = _mk_pinned(tmp_path)
    co = rq / ".subrepo_runtime" / "repos" / "renquant-strategy-104"
    (co / "configs" / "strategy_config.json").write_text("{}")
    r = subprocess.run(
        ["python3", str(ROOT / "ops" / "renquant105" / "rq105_pinned_common.py"),
         "--rq-root", str(rq), "--subrepo", "renquant-strategy-104",
         "--verify-file", "configs/strategy_config.json"],
        capture_output=True, text=True)
    assert r.returncode != 0 and "DIRTY" in r.stderr
