"""GOAL-1 #622 — a shadow feed that never lived must not look like one nobody ran.

`run_shadow_serving.sh` has three early exits. Two of them returned 1 **without
writing a dated log** while the third wrote one. Measured 2026-07-31:

  * newest dated log `shadow_serving_2026-07-13.log`, job scheduled Mon-Fri 13:45;
  * `feature_snapshot_*.json`: produced since S3-P3 by build_feature_snapshot.sh
    when a valid served matrix exists; REFUSED (fail-closed) otherwise
    (the wrapper's own comment says so), so the second early exit is taken on every
    run that gets that far;
  * `batch_scores_*.json` present through 2026-07-29, so the first guard passes.

So the job runs, deterministically takes the skip exit, and leaves nothing on
disk. The only surviving signal was a `launchctl` exit code that launchd retains
until the NEXT run — which is exactly how a fixed failure keeps re-alarming and a
never-wired one looks identical to a broken one.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRAPPER = os.path.join(ROOT, "ops", "renquant105", "run_shadow_serving.sh")


def _run(tmp_path, *, scores: bool, snapshot: bool, producer_rc: int | None = None):
    """Drive the real wrapper. ``producer_rc`` stubs the snapshot producer so a
    test can choose which half of its exit contract fires: 3 is the expected
    provenance refusal (calm skip), anything else nonzero is the producer
    BREAKING (page + distinct exit). Without the stub the real producer runs and
    exits 127 in a bare tmp root — which is a BREAKAGE, not a refusal, so the
    earlier version of these tests was asserting refusal semantics against a
    breakage scenario (orch#1033)."""
    rq = tmp_path / "RQ"
    (rq / "data" / "rq105").mkdir(parents=True)
    (rq / "logs" / "rq105").mkdir(parents=True)
    (rq / "scripts").mkdir(parents=True)
    (rq / "scripts" / "notify.sh").write_text("rq_notify() { :; }\n")
    import datetime as dt

    ts = dt.date.today().isoformat()
    if scores:
        (rq / "data" / "rq105" / f"batch_scores_{ts}.json").write_text("{}")
        (rq / "data" / "rq105" / f"batch_scores_{ts}.meta.json").write_text("{}")
    if snapshot:
        (rq / "data" / "rq105" / f"feature_snapshot_{ts}.json").write_text("{}")
    env = dict(os.environ, RQ_ROOT=str(rq))
    if producer_rc is not None:
        # Shadow the real producer next to the wrapper, since the wrapper calls
        # it via "$(dirname "$0")/build_feature_snapshot.sh".
        stub_dir = tmp_path / "ops"
        stub_dir.mkdir(parents=True, exist_ok=True)
        (stub_dir / "run_shadow_serving.sh").write_text(
            pathlib.Path(WRAPPER).read_text())
        (stub_dir / "build_feature_snapshot.sh").write_text(
            f"#!/bin/bash\nexit {producer_rc}\n")
        (stub_dir / "build_feature_snapshot.sh").chmod(0o755)
        wrapper = str(stub_dir / "run_shadow_serving.sh")
    else:
        wrapper = WRAPPER
    proc = subprocess.run(["/bin/bash", wrapper], env=env,
                          capture_output=True, text=True)
    log = rq / "logs" / "rq105" / f"shadow_serving_{ts}.log"
    return proc.returncode, (log.read_text() if log.exists() else None)


def test_the_upstream_skip_now_leaves_a_dated_line(tmp_path):
    rc, log = _run(tmp_path, scores=False, snapshot=False)
    assert rc == 1                                  # upstream failure stays 1
    assert log is not None, "no dated log written — the defect"
    assert "SKIP upstream" in log


def test_a_producer_refusal_leaves_a_line_AND_the_distinct_exit_code(tmp_path):
    """A REFUSAL (rc=3) is the producer working: calm skip, no page, exit 4."""
    rc, log = _run(tmp_path, scores=True, snapshot=False, producer_rc=3)
    assert rc == 4                                  # EXIT_NOT_WIRED, not 1
    assert log is not None
    assert "SKIP producer-refused" in log
    assert "orch#1032" in log
    assert "SKIP not-wired" not in log, "the pre-S3-P3 message must be gone"
    assert "producer-broken" not in log, "a refusal must not be called breakage"


def test_a_producer_BREAKAGE_is_not_reported_as_a_refusal(tmp_path):
    """The distinction #1032 created and this wrapper must not flatten: any
    nonzero that is NOT 3 is our bug — distinct evidence, distinct exit, and it
    pages. Exiting the calm skip code here is what let a broken producer read as
    'no input today' (codex, orch#1033)."""
    rc, log = _run(tmp_path, scores=True, snapshot=False, producer_rc=1)
    assert rc == 5, "a broken producer must not exit the skippable code"
    assert log is not None
    assert "FAIL producer-broken (rc=1)" in log
    assert "producer-refused" not in log, "breakage must not be labelled a refusal"


def test_rc0_without_a_snapshot_is_breakage_not_a_refusal(tmp_path):
    """exit 0 means "snapshot written". If it is missing anyway the producer
    FALSELY REPORTED SUCCESS — our bug, and the loudest kind, because nothing
    else in the chain will notice. Merging it into the refusal branch left a
    lying producer completely silent (codex, orch#1033)."""
    rc, log = _run(tmp_path, scores=True, snapshot=False, producer_rc=0)
    assert rc == 5, "a producer that lies about success must not take the calm skip"
    assert log is not None
    assert "FAIL producer-lied (rc=0)" in log
    assert "producer-refused" not in log, "false success must not be called a refusal"


def test_an_unexpected_producer_code_is_also_breakage(tmp_path):
    """127 (script missing) is the case the earlier tests accidentally ran."""
    rc, log = _run(tmp_path, scores=True, snapshot=False, producer_rc=127)
    assert rc == 5
    assert "FAIL producer-broken (rc=127)" in log


def test_the_two_skips_are_distinguishable_from_each_other(tmp_path):
    """Otherwise one log line would answer 'something skipped' and nothing more."""
    rc_a, log_a = _run(tmp_path / "a", scores=False, snapshot=False)
    # producer_rc=3 so this is the REFUSAL skip. Without the stub the producer
    # exits 127, which is breakage and now takes a different exit — the two
    # things this test compares must both be skips.
    rc_b, log_b = _run(tmp_path / "b", scores=True, snapshot=False, producer_rc=3)
    assert rc_a != rc_b
    # compare the MESSAGE, not a positional token: field [1] is "SKIP" in both and
    # the discriminator is field [2]. Indexing by position made the test assert
    # 'SKIP' != 'SKIP' -- my error, not the wrapper's.
    msg = lambda t: t.split(" ", 1)[1].strip()
    assert msg(log_a) != msg(log_b)
    assert "upstream" in msg(log_a) and "producer-refused" in msg(log_b)


def test_every_line_is_timestamped(tmp_path):
    """A log line without its own timestamp cannot be attributed to a run --
    the append-only attribution trap this repo keeps paying for."""
    _, log = _run(tmp_path, scores=True, snapshot=False)
    for line in log.splitlines():
        assert line[:4].isdigit() and line[4] == "-", line
        assert line.rstrip().endswith(")") or "SKIP" in line


def test_the_wrapper_still_parses():
    assert subprocess.run(["/bin/bash", "-n", WRAPPER]).returncode == 0


def test_with_a_valid_served_matrix_the_wrapper_PRODUCES_its_own_snapshot(tmp_path):
    """The S3-P3 point: the gap between 'matrix persisted daily' and 'snapshot
    available to serving' closes inside the wrapper, with no human step."""
    import datetime as dt
    import json as _json

    import pandas as pd

    rq = tmp_path / "RQ"
    (rq / "data" / "rq105").mkdir(parents=True)
    (rq / "logs" / "rq105").mkdir(parents=True)
    (rq / "scripts").mkdir(parents=True)
    (rq / "scripts" / "notify.sh").write_text("rq_notify() { :; }\n")
    ts = dt.date.today().isoformat()
    (rq / "data" / "rq105" / f"batch_scores_{ts}.json").write_text("{}")
    (rq / "data" / "rq105" / f"batch_scores_{ts}.meta.json").write_text("{}")
    prior = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    sm = rq / "backtesting" / "renquant_104" / "logs" / "served_matrix" / prior
    sm.mkdir(parents=True)
    pd.DataFrame({"ticker": ["APH"], "BETA10": [0.5]}).to_parquet(sm / "alpaca__r1.parquet")
    (sm / "alpaca__r1.json").write_text(_json.dumps({
        "schema_version": "served-matrix-1", "lane": "alpaca",
        "as_of_date": prior, "run_id": "r1", "feature_cols": ["BETA10"]}))

    env = dict(os.environ, RQ_ROOT=str(rq), RQ105_PYTHON=sys.executable)
    subprocess.run(["/bin/bash", WRAPPER], env=env,
                   capture_output=True, text=True, timeout=300)
    snap = rq / "data" / "rq105" / f"feature_snapshot_{ts}.json"
    assert snap.is_file(), "the wrapper must have produced its own snapshot"
    payload = _json.loads(snap.read_text())
    assert payload["feature_cutoff"] == prior
    assert payload["features"]["APH"]["BETA10"] == 0.5
    log = (rq / "logs" / "rq105" / f"shadow_serving_{ts}.log")
    if log.exists():
        assert "producer-refused" not in log.read_text()


# ---------------------------------------------------------------------------
# orch#1053: pinned-pipeline loader-code identity — the wrapper must verify the
# renquant-pipeline checkout (lock + HEAD==pin + clean tree) BEFORE it joins
# PYTHONPATH, and refuse before any serving. These drive the REAL wrapper
# against a hermetic fake RQ_ROOT holding real git checkouts.
# ---------------------------------------------------------------------------
def _git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True,
        env=dict(os.environ,
                 GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                 GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))


def _mk_pinned_repo(root, name, files, *, lock_matches=True, dirty=False):
    """A real git checkout under .subrepo_runtime/repos/<name>; returns the
    commit the LOCK should record (HEAD when lock_matches, else a bogus sha)."""
    repo = root / ".subrepo_runtime" / "repos" / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "pinned")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        (repo / "src" / "drifted.py").write_text("# hand edit\n")
    return head if lock_matches else "0" * 40


def _run_pinned(tmp_path, *, pipeline_lock_matches=True, pipeline_dirty=False):
    """Fake root where common + strategy-104 pins VERIFY and the pipeline pin is
    controlled by the test. Scores/meta/snapshot exist so the wrapper reaches
    the code-identity gates; .venv/bin/python symlinks the system python."""
    import datetime as dt
    import json as _json
    import shutil

    rq = tmp_path / "RQ"
    for d in ("data/rq105", "logs/rq105", "scripts"):
        (rq / d).mkdir(parents=True)
    (rq / "scripts" / "notify.sh").write_text("rq_notify() { :; }\n")
    venv_bin = rq / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    os.symlink(shutil.which("python3"), venv_bin / "python")
    ts = dt.date.today().isoformat()
    for rel in (f"batch_scores_{ts}.json", f"batch_scores_{ts}.meta.json",
                f"feature_snapshot_{ts}.json"):
        (rq / "data" / "rq105" / rel).write_text("{}")

    locks = []
    locks.append(("renquant-common", _mk_pinned_repo(
        rq, "renquant-common", {"src/renquant_common/__init__.py": ""})))
    locks.append(("renquant-strategy-104", _mk_pinned_repo(
        rq, "renquant-strategy-104",
        {"configs/strategy_config.json": "{}", "src/keep.py": ""})))
    locks.append(("renquant-pipeline", _mk_pinned_repo(
        rq, "renquant-pipeline", {"src/renquant_pipeline/__init__.py": ""},
        lock_matches=pipeline_lock_matches, dirty=pipeline_dirty)))
    (rq / "subrepos.lock.json").write_text(_json.dumps(
        {"subrepos": [{"name": n, "commit": c} for n, c in locks]}))

    proc = subprocess.run(["/bin/bash", WRAPPER], env=dict(os.environ, RQ_ROOT=str(rq)),
                          capture_output=True, text=True)
    log = rq / "logs" / "rq105" / f"shadow_serving_{ts}.log"
    return proc.returncode, (log.read_text() if log.exists() else "")


def test_a_pipeline_HEAD_mismatch_refuses_before_serving(tmp_path):
    """[codex on orch#1053] drifted loader code must not import: lock pins a
    different revision than the checkout HEAD → visible refusal, exit 1, and
    the run never reaches bundle verification (nothing served)."""
    rc, log = _run_pinned(tmp_path, pipeline_lock_matches=False)
    assert rc == 1
    assert "pinned renquant-pipeline verification refused" in log
    assert "directory name is not a revision" in log
    assert "bundle verification" not in log, "must refuse BEFORE serving steps"


def test_a_DIRTY_pipeline_tree_refuses_even_at_the_right_HEAD(tmp_path):
    """HEAD==pin is not enough: a hand-edited pinned checkout is unreviewed
    code. The clean-tree prong must refuse it."""
    rc, log = _run_pinned(tmp_path, pipeline_lock_matches=True, pipeline_dirty=True)
    assert rc == 1
    assert "pinned renquant-pipeline verification refused" in log
    assert "DIRTY" in log


def test_verified_pins_pass_the_code_identity_gates(tmp_path):
    """Control: with all three pins verifying, the wrapper proceeds PAST both
    code-identity gates and fails later at bundle verification (the fake
    bundle is empty) — proving the gates pass-through rather than fail-open."""
    rc, log = _run_pinned(tmp_path)
    assert "pinned renquant-pipeline verification refused" not in log
    assert "pinned strategy-config verification refused" not in log
    assert rc != 0, "the empty fake bundle cannot verify — but only AFTER the gates"
