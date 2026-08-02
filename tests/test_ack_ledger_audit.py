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


def _ack(acked_at, clears="renquant-orchestrator#1 is merged", reason="r"):
    # The default clears_when carries a QUALIFIED ref so a fixture ledger is clean
    # under the machine-checkability finding too. A repo#N token feeds no date into
    # ack_expiry, so fixture expiries are untouched. Narrative-only fixtures must opt
    # in explicitly — that state is now a finding, not a neutral default.
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


def test_a_stamp_AHEAD_of_its_edit_is_flagged_as_CHRONOLOGY_CORRUPTION(tmp_path):
    """A stamp dated after its introducing commit. NOT a re-stamp detector — see
    `test_a_re_review_and_an_unreviewed_re_stamp_are_INDISTINGUISHABLE`."""
    root = _repo(tmp_path, [({"j": _ack("2026-07-20")}, "2026-07-05")])
    R = A.audit(dt.date(2026, 7, 21), str(root / A.LEDGER_REL), str(root))
    assert R["rows"][0]["stamp_lag_days"] == -15
    assert any("chronology is corrupt" in f for f in R["findings"])


def test_an_unreadable_acked_at_is_a_finding_not_a_pass(tmp_path):
    root = _repo(tmp_path, [({"j": {"acked_at": "soon", "reason": "r",
                                    "clears_when": "orch#7 is merged"}}, "2026-07-05")])
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
    # 12 as of 2026-08-01: the two rq105 exit-1 acks (shadow-serving structurally
    # unrunnable; liveness = the detector honestly firing on it) joined the ledger.
    assert R["n_acks"] == 12
    # NINE of ten, not ten. `com.renquant.rq105-batch-scores-export` was re-stamped
    # on 2026-07-31 by a32f397c ("the batch-export ack described a failure that is no
    # longer the failure"), so it is live until 2026-08-14. The count moved because
    # the LEDGER moved, not because the audit changed — asserting ten would pin a
    # ledger that no longer exists, and a re-stamp is exactly the event this audit is
    # for. Named rather than counted, so the next re-stamp is visible here.
    assert R["n_expired"] == 9
    live = [r["job"] for r in R["rows"] if not r.get("expired")]
    assert live == ["com.renquant.rq105-batch-scores-export",
                    "com.renquant.rq105-liveness",
                    "com.renquant.rq105-shadow-serving"], live
    assert R["ack_max_age_days"] == 14
    lags = {r["job"]: r["stamp_lag_days"] for r in R["rows"]}

    # The DAY COUNT is not pinned, and my first fix to this test pinned it anyway.
    #
    # `stamp_lag_days = last_edited - acked_at`, and `last_edited` comes from GIT
    # HISTORY. It therefore differs between this branch (13) and CI, which tests the
    # merge with main and sees a later ledger commit (14) — same code, same ledger
    # contents, different answer. Any literal here is a value that moves whenever
    # anyone touches the ledger, on a schedule nobody controls.
    #
    # ...and the SET of stale rows is not pinnable either, which orch#641 proved by
    # landing. It added `acked_exit_codes` to every row, so every row's VALUE changed
    # today while every `acked_at` still says 2026-07-17 — and `last_edit_dates` is
    # value-based per key, so the stale count went from 1 to 9 in one merge.
    #
    # The audit is RIGHT about all nine. What it cannot see is that the edit was a
    # SCHEMA MIGRATION rather than a re-diagnosis — which is this PR's own established
    # limit (see `test_a_re_review_and_an_unreviewed_re_stamp_are_INDISTINGUISHABLE`),
    # now demonstrated at ledger scale instead of on one row.
    #
    # And restamping the nine to today would be the WRONG repair: adding a field is not
    # a re-review, so a fresh `acked_at` would assert a review that never happened. The
    # stale lag is the honest state, so what is pinned here is the PROPERTY.
    stale = {j: v for j, v in lags.items() if v is not None and v > 0}
    fresh = {j: v for j, v in lags.items() if v == 0}

    assert stale, "no row is stale — the audit has nothing to detect, so it proves nothing"
    for job, lag in stale.items():
        assert any(job in f and "expiry clock" in f for f in R["findings"]), (job, lag)

    # The one row genuinely re-stamped on 2026-07-31 must NOT read as stale, or the
    # signal is just "the file was touched" and carries no information about a row.
    assert list(fresh) == ["com.renquant.rq105-batch-scores-export",
                           "com.renquant.rq105-liveness",
                           "com.renquant.rq105-shadow-serving"], fresh
    assert set(stale) | set(fresh) == set(lags), "a row was silently dropped"
    assert set(stale).isdisjoint(fresh)


# ---------------- the limit of this evidence, pinned so it is not re-claimed ----
def test_a_re_review_and_an_unreviewed_re_stamp_are_INDISTINGUISHABLE(tmp_path):
    """Codex BLOCKER on #654, verified empirically before accepting.

    An earlier version of this audit reported a negative lag as *"an ack re-stamped
    without a re-review"*. It cannot be: both human actions write today's `acked_at`
    in today's commit, so both yield lag 0 and identical findings. The claim named an
    event the mechanism cannot see — the guards-that-validate-the-wrong-object shape,
    committed inside the audit built to catch it.

    This test exists so the claim cannot be re-added without failing.
    """
    reviewed = _repo(tmp_path / "reviewed", [
        ({"j": _ack("2026-07-01")}, "2026-07-01"),
        ({"j": _ack("2026-07-20", reason="re-reviewed properly")}, "2026-07-20"),
    ])
    restamped = _repo(tmp_path / "restamped", [
        ({"j": _ack("2026-07-01")}, "2026-07-01"),
        ({"j": _ack("2026-07-20")}, "2026-07-20"),
    ])
    out = []
    for root in (reviewed, restamped):
        R = A.audit(dt.date(2026, 7, 25), str(root / A.LEDGER_REL), str(root))
        r = R["rows"][0]
        out.append((r["stamp_lag_days"], len(R["findings"])))
    assert out[0] == out[1] == (0, 0), out


# ------------- "expired" vs "expired for longer than an ack may live" --------
def test_a_LONG_expired_ack_is_its_own_finding(tmp_path):
    """An ack that lapsed yesterday means the reminder just fired, as designed.
    One that lapsed longer ago than ACK_MAX_AGE_DAYS means a FULL REVIEW CYCLE
    passed with nobody lifting or renewing it — the alarm returning unheeded, which
    is the state the ledger exists to prevent."""
    sent = A._load_sentinel()
    root = _repo(tmp_path, [({"j": _ack("2026-07-01")}, "2026-07-01")])
    expiry = dt.date(2026, 7, 1) + dt.timedelta(days=sent.ACK_MAX_AGE_DAYS)
    just = A.audit(expiry + dt.timedelta(days=1), str(root / A.LEDGER_REL), str(root))
    long_ = A.audit(expiry + dt.timedelta(days=sent.ACK_MAX_AGE_DAYS + 1),
                    str(root / A.LEDGER_REL), str(root))
    assert not [f for f in just["findings"] if "longer than the" in f]
    assert [f for f in long_["findings"] if "longer than the" in f]


def test_the_threshold_is_the_ledgers_OWN_cadence_not_a_magic_number(tmp_path):
    """If it were a literal, nobody could re-derive it. It is ACK_MAX_AGE_DAYS."""
    src = open(MOD_PATH, encoding="utf-8").read()
    assert "sent.ACK_MAX_AGE_DAYS" in src.split("LONG-EXPIRED")[1][:900]
    sent = A._load_sentinel()
    root = _repo(tmp_path, [({"j": _ack("2026-07-01")}, "2026-07-01")])
    expiry = dt.date(2026, 7, 1) + dt.timedelta(days=sent.ACK_MAX_AGE_DAYS)
    # exactly at the threshold: NOT yet a finding; one day past: a finding
    at = A.audit(expiry + dt.timedelta(days=sent.ACK_MAX_AGE_DAYS),
                 str(root / A.LEDGER_REL), str(root))
    past = A.audit(expiry + dt.timedelta(days=sent.ACK_MAX_AGE_DAYS + 1),
                   str(root / A.LEDGER_REL), str(root))
    assert not [f for f in at["findings"] if "longer than the" in f]
    assert [f for f in past["findings"] if "longer than the" in f]


def test_the_live_ledger_today_and_when_it_will_fire():
    """Measured 2026-08-01: fires on 0 today; the 2026-07-20 cohort crosses the
    threshold on 2026-08-04. A forecast FROM a measurement, not a prediction."""
    def n(day):
        return len([f for f in A.audit(day)["findings"] if "longer than the" in f])

    assert n(dt.date(2026, 8, 1)) == 0
    assert n(dt.date(2026, 8, 4)) == 3
    assert n(dt.date(2026, 8, 15)) == 9


# ---------------------------------------------------------------- clears_when ----
#
# Surveyed 2026-08-01 (orch#733): only 4 of 10 live acks carried ANY fragment a checker
# could bind to, and 6 of the 9 expired rows expired purely via the acked_at backstop —
# their clears_when never participated. The classifier makes narrative-only clearing
# conditions a FINDING instead of an invisible default.

def test_a_date_is_machine_checkable():
    c = A.classify_clears_when("next NYSE session's 13:55 wrapper run (2026-07-20)")
    assert A.BUCKET_DATE in c["buckets"] and c["has_machine_bindable_fragment"]


def test_a_repo_qualified_ref_and_a_keyval_are_machine_checkable():
    c = A.classify_clears_when(
        "renquant-strategy-104#73 (wash_sale_min_material_npv = 1.00) is merged")
    assert A.BUCKET_REF in c["buckets"]
    assert A.BUCKET_ARTIFACT in c["buckets"]
    assert A.BUCKET_BARE_REF not in c["buckets"], \
        "a QUALIFIED ref must not also count as a bare one"


def test_a_bare_ref_is_flagged_and_NOT_counted_as_checkable():
    c = A.classify_clears_when("job redesigned — task #75")
    assert A.BUCKET_BARE_REF in c["buckets"]
    assert not c["has_machine_bindable_fragment"], \
        "an unresolvable #NN must not count as a bindable fragment"


def test_narrative_only_is_empty_and_not_checkable():
    c = A.classify_clears_when("next VIX-anomaly trigger runs the gated chain clean")
    assert c["buckets"] == [] and not c["has_machine_bindable_fragment"]


def test_a_path_token_counts_as_artifact():
    c = A.classify_clears_when("restore logs/rq105/shadow_serving.log first")
    assert A.BUCKET_ARTIFACT in c["buckets"]


def test_date_detection_stays_in_parity_with_the_sentinels_extractor():
    """The classifier's DATE bucket and ack_expiry's clears_when date extraction must
    agree on every live row, or the audit would call a row narrative-only while the
    sentinel is quietly deriving an expiry from it."""
    sent = A._load_sentinel()
    iso = getattr(sent, "_ISO_DATE", None)
    assert iso is not None, "sentinel no longer exposes _ISO_DATE — re-pin this parity"
    acks = sent.load_acks()
    assert acks, "live ledger unreadable — parity test has no subject"
    for name, ack in acks.items():
        cw = str(ack.get("clears_when") or "")
        mine = A.BUCKET_DATE in A.classify_clears_when(cw)["buckets"]
        theirs = bool(iso.search(cw))
        assert mine == theirs, (name, cw)


def test_the_live_ledgers_checkability_is_measured_not_asserted():
    """Pins the surveyed state so the doc cannot rot: 6 narrative-only rows (counting
    the bare-#75 row, whose ref is unresolvable), 1 bare-ref row. A ledger edit that
    adds a checkable clause SHOULD move these — update the pin with it."""
    R = A.audit(dt.date(2026, 8, 1))
    by = {r["job"]: r["clears_when_buckets"] for r in R["rows"]}
    assert len(by) == 12
    narrative = {j for j, b in by.items()
                 if not any(x in (A.BUCKET_DATE, A.BUCKET_REF, A.BUCKET_ARTIFACT)
                            for x in b)}
    assert narrative == {
        "com.renquant.conditional-retrain104",
        "com.renquant.monthly-meta-label-retrain",
        "com.renquant.retrain-panel104",
        "com.renquant.rq104-degradation-sentinel",
        "com.renquant.rq104-liveness",
        "com.renquant.weekly-wf-promote",
    }, narrative
    # rq105-batch-scores-export legitimately contains BOTH a qualified ref and a later
    # bare "#73" — the bucket records it, the finding's REF-guard keeps it quiet. The
    # unresolvable-as-written set is bare WITHOUT any qualified ref:
    assert [j for j, b in by.items()
            if A.BUCKET_BARE_REF in b and A.BUCKET_REF not in b] == \
        ["com.renquant.monthly-meta-label-retrain"]
    assert sum(1 for f in R["findings"] if "no machine-bindable fragment" in f) == 6
    assert sum(1 for f in R["findings"] if "bare #NN" in f) == 1
