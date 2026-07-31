"""GOAL-1 #622 — a shadow feed that never lived must not look like one nobody ran.

`run_shadow_serving.sh` has three early exits. Two of them returned 1 **without
writing a dated log** while the third wrote one. Measured 2026-07-31:

  * newest dated log `shadow_serving_2026-07-13.log`, job scheduled Mon-Fri 13:45;
  * `feature_snapshot_*.json` files in `data/rq105/`: **zero** — no producer exists
    (the wrapper's own comment says so), so the second early exit is taken on every
    run that gets that far;
  * `batch_scores_*.json` present through 2026-07-29, so the first guard passes.

So the job runs, deterministically takes the not-wired exit, and leaves nothing on
disk. The only surviving signal was a `launchctl` exit code that launchd retains
until the NEXT run — which is exactly how a fixed failure keeps re-alarming and a
never-wired one looks identical to a broken one.
"""

from __future__ import annotations

import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRAPPER = os.path.join(ROOT, "ops", "renquant105", "run_shadow_serving.sh")


def _run(tmp_path, *, scores: bool, snapshot: bool):
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
    proc = subprocess.run(["/bin/bash", WRAPPER], env=env,
                          capture_output=True, text=True)
    log = rq / "logs" / "rq105" / f"shadow_serving_{ts}.log"
    return proc.returncode, (log.read_text() if log.exists() else None)


def test_the_upstream_skip_now_leaves_a_dated_line(tmp_path):
    rc, log = _run(tmp_path, scores=False, snapshot=False)
    assert rc == 1                                  # upstream failure stays 1
    assert log is not None, "no dated log written — the defect"
    assert "SKIP upstream" in log


def test_the_not_wired_skip_leaves_a_line_AND_a_distinct_exit_code(tmp_path):
    """A job that CANNOT succeed today is not a job that FAILED today."""
    rc, log = _run(tmp_path, scores=True, snapshot=False)
    assert rc == 4                                  # EXIT_NOT_WIRED, not 1
    assert log is not None
    assert "SKIP not-wired" in log
    assert "#221" in log


def test_the_two_skips_are_distinguishable_from_each_other(tmp_path):
    """Otherwise one log line would answer 'something skipped' and nothing more."""
    rc_a, log_a = _run(tmp_path / "a", scores=False, snapshot=False)
    rc_b, log_b = _run(tmp_path / "b", scores=True, snapshot=False)
    assert rc_a != rc_b
    # compare the MESSAGE, not a positional token: field [1] is "SKIP" in both and
    # the discriminator is field [2]. Indexing by position made the test assert
    # 'SKIP' != 'SKIP' -- my error, not the wrapper's.
    msg = lambda t: t.split(" ", 1)[1].strip()
    assert msg(log_a) != msg(log_b)
    assert "upstream" in msg(log_a) and "not-wired" in msg(log_b)


def test_every_line_is_timestamped(tmp_path):
    """A log line without its own timestamp cannot be attributed to a run --
    the append-only attribution trap this repo keeps paying for."""
    _, log = _run(tmp_path, scores=True, snapshot=False)
    for line in log.splitlines():
        assert line[:4].isdigit() and line[4] == "-", line
        assert line.rstrip().endswith(("#221)", ")")) or "SKIP" in line


def test_the_wrapper_still_parses():
    assert subprocess.run(["/bin/bash", "-n", WRAPPER]).returncode == 0
