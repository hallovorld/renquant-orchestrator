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


# --- codex on #653: two fail-open cases -------------------------------------------
# (1) `rev-list pin..origin/main` returns a number for DIVERGENT pins too, so the
#     count alone hides a non-fast-forward state. Ancestry must be PROVED first.
# (2) `scan` dropped lock entries missing name/commit, shrinking the denominator
#     while still reporting success.

def _diverged_repo(tmp_path: Path, name: str) -> tuple[Path, str]:
    """A pin on a branch that origin/main does not contain."""
    d = tmp_path / name
    d.mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", "-C", str(d), *a], capture_output=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t"); run("config", "user.name", "t")
    (d / "f.txt").write_text("base"); run("add", "."); run("commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    # a side commit that main will never contain
    run("checkout", "-q", "-b", "side")
    (d / "f.txt").write_text("side"); run("add", "."); run("commit", "-qm", "side")
    pin = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    run("checkout", "-q", "main")
    (d / "g.txt").write_text("main"); run("add", "."); run("commit", "-qm", "main2")
    run("update-ref", "refs/remotes/origin/main", "refs/heads/main")
    run("remote", "add", "origin", str(d))
    return d, pin


def test_a_DIVERGED_pin_is_not_reported_as_a_behind_count(tmp_path):
    """THE DEFECT. `rev-list A..B` is defined for divergent pairs and returns a
    number; taking it as 'behind' silently hides the non-fast-forward state."""
    _, pin = _diverged_repo(tmp_path, "sub-div")
    r = pl.measure("sub-div", pin, tmp_path)
    assert r["status"] == pl.STATUS_DIVERGED, r
    assert r["behind"] is None, "a divergent pin has no behind count"
    assert "NOT an ancestor" in r["detail"]


def test_an_ancestor_pin_is_still_MEASURED(tmp_path):
    """Anti-vacuity for the ancestry proof: if nothing qualified, every real pin
    would report DIVERGED and the tool would measure nothing."""
    d, first = _repo(tmp_path, "sub-anc", n_commits=3)
    assert pl.measure("sub-anc", first, tmp_path)["status"] == pl.STATUS_MEASURED


@pytest.mark.parametrize("entry,missing", [
    ({"commit": "abc123"}, "name"),
    ({"name": "sub-x"}, "commit"),
    ({"name": "", "commit": "abc"}, "name"),
    ({"name": "sub-x", "commit": ""}, "commit"),
])
def test_a_malformed_lock_entry_is_a_ROW_not_a_silent_drop(tmp_path, entry, missing):
    """THE DENOMINATOR. Dropping these shrinks the population being checked while
    the run still reports success — the same shape the tool exists to expose."""
    lock = tmp_path / "l.json"
    lock.write_text(json.dumps({"subrepos": [entry]}))
    res = pl.scan(lock, tmp_path)
    assert res["lock_entries"] == 1
    assert res["malformed"] == 1
    assert res["rows"][0]["status"] == pl.STATUS_MALFORMED
    assert missing in res["rows"][0]["detail"]


def test_the_denominator_is_the_LOCK_length_not_the_measurable_subset(tmp_path):
    d, first = _repo(tmp_path, "sub-ok", n_commits=2)
    lock = tmp_path / "l.json"
    lock.write_text(json.dumps({"subrepos": [
        {"name": "sub-ok", "commit": first},
        {"name": "sub-bad"},
    ]}))
    res = pl.scan(lock, tmp_path)
    assert res["lock_entries"] == 2 and res["measured"] == 1 and res["malformed"] == 1


def test_the_cli_exits_nonzero_on_a_malformed_entry_alone(tmp_path):
    lock = tmp_path / "l.json"
    lock.write_text(json.dumps({"subrepos": [{"name": "only-name"}]}))
    assert pl.main(["--lock", str(lock), "--github", str(tmp_path),
                    "--max-lag", "9999"]) == pl.EXIT_LAG
