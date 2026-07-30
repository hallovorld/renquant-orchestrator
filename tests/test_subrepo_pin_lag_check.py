"""Two surfaces, two baselines — and the weaker one reads like the stronger.

`run_surface_drift_check` compares the runtime subrepo checkouts against
`subrepos.lock.json`'s pin ("does runtime match what we pinned") and, four lines
later, compares `orchestrator-run` against its fetched `origin/main` ("is it
current"). A pin frozen for months passes the first check clean forever.

Measured 2026-07-30, after a day in which four merged fixes reached the run path
zero times: 617 commits behind in total, renquant-model 240, orchestrator 213.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_S = importlib.util.spec_from_file_location(
    "pl", REPO / "ops" / "subrepo_pin_lag_check.py")
pl = importlib.util.module_from_spec(_S)
sys.modules["pl"] = pl
_S.loader.exec_module(pl)


def _repo(tmp_path: Path, name: str, n_commits: int = 3) -> tuple[Path, str]:
    d = tmp_path / name
    d.mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", "-C", str(d), *a], capture_output=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t"); run("config", "user.name", "t")
    first = None
    for i in range(n_commits):
        (d / "f.txt").write_text(str(i))
        run("add", "."); run("commit", "-qm", f"c{i}")
        if i == 0:
            first = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                                   capture_output=True, text=True).stdout.strip()
    run("update-ref", "refs/remotes/origin/main", "HEAD")
    run("remote", "add", "origin", str(d))
    return d, first


def test_the_lag_count_is_the_real_distance(tmp_path):
    d, first = _repo(tmp_path, "sub-b", n_commits=4)
    r = pl.measure("sub-b", first, tmp_path)
    assert r["status"] == pl.STATUS_MEASURED
    assert r["behind"] == 3, r


def test_a_pin_AT_origin_main_is_zero(tmp_path):
    """Anti-vacuity: if everything reported a lag the number would carry nothing."""
    d, _ = _repo(tmp_path, "sub-c", n_commits=2)
    head = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    r = pl.measure("sub-c", head, tmp_path)
    assert r["status"] == pl.STATUS_MEASURED and r["behind"] == 0


def test_a_missing_dev_checkout_is_UNMEASURABLE_not_zero(tmp_path):
    """A lag nobody could compute is not a lag of zero — that conflation is how a
    fail-open guard reports green."""
    r = pl.measure("ghost", "deadbeef", tmp_path)
    assert r["status"] == pl.STATUS_NO_CHECKOUT and r["behind"] is None


def test_a_pin_not_present_in_the_repo_is_UNMEASURABLE(tmp_path):
    _repo(tmp_path, "sub-d", n_commits=2)
    r = pl.measure("sub-d", "0" * 40, tmp_path)
    assert r["status"] == pl.STATUS_UNKNOWN_PIN and r["behind"] is None


def test_unmeasurable_rows_are_counted_separately(tmp_path):
    d, first = _repo(tmp_path, "sub-e", n_commits=3)
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"subrepos": [
        {"name": "sub-e", "commit": first},
        {"name": "ghost", "commit": "deadbeef"},
    ]}))
    res = pl.scan(lock, tmp_path)
    assert res["measured"] == 1 and res["unmeasurable"] == 1
    assert res["total_behind"] == 2


def test_an_empty_lock_is_an_ERROR_not_a_clean_pass(tmp_path):
    """A lock listing nothing would make every assertion above vacuous."""
    lock = tmp_path / "empty.json"
    lock.write_text(json.dumps({"subrepos": []}))
    with pytest.raises(ValueError):
        pl.scan(lock, tmp_path)


def test_the_cli_exits_nonzero_on_an_unmeasurable_row(tmp_path, capsys):
    lock = tmp_path / "l.json"
    lock.write_text(json.dumps({"subrepos": [{"name": "ghost", "commit": "dead"}]}))
    rc = pl.main(["--lock", str(lock), "--github", str(tmp_path), "--max-lag", "9999"])
    assert rc == pl.EXIT_LAG, "an unmeasurable pin must not exit clean"
