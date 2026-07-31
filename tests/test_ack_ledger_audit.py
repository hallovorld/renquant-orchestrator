"""Tests for the ack-ledger audit.

The load-bearing tests are the controls:

  * a **clean** ledger must produce NO findings — otherwise a tool that flags
    everything would pass every positive test and be useless;
  * expiry must come from the **sentinel's own** `ack_expiry`, not a copy — a twin
    would agree on the day it was written and diverge silently afterwards;
  * a stamp **ahead** of its edit (the silent direction) must be flagged too, not
    only the noisy direction that happens to be what the live ledger has today.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_PATH = os.path.join(ROOT, "ops", "renquant104", "ack_ledger_audit.py")


def _load():
    spec = importlib.util.spec_from_file_location("ack_ledger_audit", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


A = _load()


def _git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _repo(tmp_path, history):
    """Build a throwaway repo whose ledger evolves through `history`."""
    root = tmp_path / "repo"
    (root / "ops" / "renquant104").mkdir(parents=True)
    _git(root.parent, "init", "-q", str(root))
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    rel = A.LEDGER_REL
    for i, (content, date) in enumerate(history):
        (root / rel).write_text(json.dumps(content, indent=2))
        _git(root, "add", rel)
        env = dict(os.environ, GIT_AUTHOR_DATE=f"{date}T12:00:00",
                   GIT_COMMITTER_DATE=f"{date}T12:00:00")
        r = subprocess.run(["git", "commit", "-q", "-m", f"c{i}"],
                           cwd=root, capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
    return root


def _ack(acked_at, clears="some condition", reason="r"):
    return {"acked_at": acked_at, "clears_when": clears, "reason": reason}


# ------------------------------------------------------- last_edit_dates ----
def test_last_edit_date_is_when_the_value_was_introduced(tmp_path):
    root = _repo(tmp_path, [
        ({"j": _ack("2026-07-01")}, "2026-07-01"),
        ({"j": _ack("2026-07-01", reason="rewritten")}, "2026-07-10"),
        ({"j": _ack("2026-07-01", reason="rewritten"), "k": _ack("2026-07-20")},
         "2026-07-20"),
    ])
    d = A.last_edit_dates(str(root), A.LEDGER_REL)
    assert d["j"] == dt.date(2026, 7, 10)     # not 07-01, not 07-20
    assert d["k"] == dt.date(2026, 7, 20)


def test_an_unchanged_entry_dates_to_its_first_commit(tmp_path):
    root = _repo(tmp_path, [
        ({"j": _ack("2026-07-01")}, "2026-07-01"),
        ({"j": _ack("2026-07-01"), "k": _ack("2026-07-05")}, "2026-07-05"),
    ])
    assert A.last_edit_dates(str(root), A.LEDGER_REL)["j"] == dt.date(2026, 7, 1)


def test_last_edit_dates_refuses_a_file_with_no_history(tmp_path):
    root = tmp_path / "empty"
    (root / "ops" / "renquant104").mkdir(parents=True)
    _git(root.parent, "init", "-q", str(root))
    with pytest.raises(RuntimeError):
        A.last_edit_dates(str(root), A.LEDGER_REL)


# --------------------------------------------------------------- CONTROLS ---
def test_a_clean_ledger_produces_no_findings(tmp_path):
    """Anti-vacuity. Without this, a tool that flags everything passes every
    positive test below and tells the reader nothing."""
    root = _repo(tmp_path, [({"j": _ack("2026-07-20")}, "2026-07-20")])
    R = A.audit(dt.date(2026, 7, 25), str(root / A.LEDGER_REL), str(root))
    assert R["findings"] == [], R["findings"]
    assert R["n_expired"] == 0
    assert R["rows"][0]["stamp_lag_days"] == 0


def test_expiry_comes_from_the_sentinel_not_a_copy():
    """If this module ever grows its own ACK_MAX_AGE_DAYS the rule can drift."""
    src = open(MOD_PATH, encoding="utf-8").read()
    assert "ACK_MAX_AGE_DAYS =" not in src
    assert "def ack_expiry" not in src
    sent = A._load_sentinel()
    assert isinstance(sent.ACK_MAX_AGE_DAYS, int)
    assert callable(sent.ack_expiry)


def test_uses_the_sentinels_expiry_rule_including_the_boundary(tmp_path):
    """`expiry <= today` is the sentinel's rule: expiry day itself is EXPIRED."""
    root = _repo(tmp_path, [({"j": _ack("2026-07-01")}, "2026-07-01")])
    sent = A._load_sentinel()
    exp = dt.date(2026, 7, 1) + dt.timedelta(days=sent.ACK_MAX_AGE_DAYS)
    on = A.audit(exp, str(root / A.LEDGER_REL), str(root))
    before = A.audit(exp - dt.timedelta(days=1), str(root / A.LEDGER_REL), str(root))
    assert on["rows"][0]["expired"] is True
    assert before["rows"][0]["expired"] is False


# --------------------------------------------------------------- findings ---
def test_a_stamp_older_than_its_edit_is_flagged_as_the_noisy_direction(tmp_path):
    root = _repo(tmp_path, [
        ({"j": _ack("2026-07-01")}, "2026-07-01"),
        ({"j": _ack("2026-07-01", reason="re-dispositioned")}, "2026-07-14"),
    ])
    R = A.audit(dt.date(2026, 7, 15), str(root / A.LEDGER_REL), str(root))
    assert R["rows"][0]["stamp_lag_days"] == 13
    assert any("expiry fires early" in f for f in R["findings"])


def test_a_stamp_AHEAD_of_its_edit_is_flagged_as_the_silent_direction(tmp_path):
    """Re-stamping without re-reviewing buys silence. It must not pass quietly."""
    root = _repo(tmp_path, [({"j": _ack("2026-07-20")}, "2026-07-05")])
    R = A.audit(dt.date(2026, 7, 21), str(root / A.LEDGER_REL), str(root))
    assert R["rows"][0]["stamp_lag_days"] == -15
    assert any("suppresses 15d longer than earned" in f for f in R["findings"])


def test_an_unreadable_acked_at_is_a_finding_not_a_pass(tmp_path):
    root = _repo(tmp_path, [({"j": {"acked_at": "soon", "reason": "r",
                                    "clears_when": "c"}}, "2026-07-05")])
    R = A.audit(dt.date(2026, 7, 6), str(root / A.LEDGER_REL), str(root))
    assert any("cannot be checked at all" in f for f in R["findings"])


def test_an_expiry_cliff_is_reported(tmp_path):
    root = _repo(tmp_path, [
        ({"a": _ack("2026-07-01"), "b": _ack("2026-07-01"),
          "c": _ack("2026-07-01")}, "2026-07-01"),
    ])
    R = A.audit(dt.date(2026, 7, 10), str(root / A.LEDGER_REL), str(root))
    cliff = [f for f in R["findings"] if "expiry cliff" in f]
    assert len(cliff) == 1 and "3 acks expire together" in cliff[0]


def test_staggered_acks_are_not_a_cliff(tmp_path):
    """The mirror of the test above — otherwise 'cliff' means 'more than one ack'."""
    root = _repo(tmp_path, [
        ({"a": _ack("2026-07-01"), "b": _ack("2026-07-02"),
          "c": _ack("2026-07-03")}, "2026-07-03"),
    ])
    R = A.audit(dt.date(2026, 7, 10), str(root / A.LEDGER_REL), str(root))
    assert not [f for f in R["findings"] if "expiry cliff" in f]


# ---------------------------------------------------- root resolution ------
def test_root_is_resolved_from_the_ledger_not_the_cwd(tmp_path):
    """Dating one repo's acks against another repo's commits must be REFUSED."""
    root = _repo(tmp_path, [({"j": _ack("2026-07-01")}, "2026-07-01")])
    assert A.resolve_root(str(root / A.LEDGER_REL)) == str(root.resolve())


def test_a_ledger_at_the_wrong_path_is_refused_not_reported_as_a_finding(tmp_path):
    root = _repo(tmp_path, [({"j": _ack("2026-07-01")}, "2026-07-01")])
    stray = root / "elsewhere.json"
    stray.write_text(json.dumps({"j": _ack("2026-07-01")}))
    _git(root, "add", "elsewhere.json")
    subprocess.run(["git", "commit", "-q", "-m", "stray"], cwd=root,
                   capture_output=True, text=True)
    with pytest.raises(RuntimeError, match="refusing"):
        A.resolve_root(str(stray))


def test_a_missing_ledger_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="does not exist"):
        A.resolve_root(str(tmp_path / "nope.json"))


# ------------------------------------------------------------------- CLI ----
def test_cli_exits_nonzero_on_findings_and_zero_on_a_clean_ledger(tmp_path):
    dirty = _repo(tmp_path / "d", [
        ({"a": _ack("2026-07-01"), "b": _ack("2026-07-01")}, "2026-07-01")])
    clean = _repo(tmp_path / "c", [({"a": _ack("2026-07-20")}, "2026-07-20")])
    for root, expected in ((dirty, A.EXIT_FINDINGS), (clean, A.EXIT_OK)):
        r = subprocess.run(
            [sys.executable, MOD_PATH, "--today", "2026-07-25",
             "--ledger", str(root / A.LEDGER_REL)],
            cwd=str(root), capture_output=True, text=True)
        assert r.returncode == expected, (root, r.returncode, r.stdout)


def test_cli_reports_a_harness_failure_distinctly(tmp_path):
    """A tool that cannot run must not be indistinguishable from a clean run."""
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    r = subprocess.run([sys.executable, MOD_PATH, "--today", "2026-07-25"],
                       cwd=str(outside), capture_output=True, text=True,
                       env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path)))
    assert r.returncode in (A.EXIT_HARNESS, A.EXIT_FINDINGS)
    if r.returncode == A.EXIT_HARNESS:
        assert "HARNESS FAILURE" in r.stderr


# ------------------------------------------------- the live ledger, today ---
def test_the_live_ledger_is_measured_not_asserted():
    """Pins what this branch's progress doc claims, so the doc cannot rot."""
    R = A.audit(dt.date(2026, 7, 31))
    assert R["n_acks"] == 10
    # NINE of ten, not ten. `com.renquant.rq105-batch-scores-export` was re-stamped
    # on 2026-07-31 by a32f397c ("the batch-export ack described a failure that is no
    # longer the failure"), so it is live until 2026-08-14. The count moved because
    # the LEDGER moved, not because the audit changed — asserting ten would pin a
    # ledger that no longer exists, and a re-stamp is exactly the event this audit is
    # for. Named rather than counted, so the next re-stamp is visible here.
    assert R["n_expired"] == 9
    live = [r["job"] for r in R["rows"] if not r.get("expired")]
    assert live == ["com.renquant.rq105-batch-scores-export"], live
    assert R["ack_max_age_days"] == 14
    lags = {r["job"]: r["stamp_lag_days"] for r in R["rows"]}
    assert lags["com.renquant.rq104-degradation-sentinel"] == 13
