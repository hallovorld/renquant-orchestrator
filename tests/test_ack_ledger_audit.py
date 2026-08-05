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


def _ack(acked_at, clears="renquant-orchestrator#1 is merged", reason="r",
         check="default"):
    # The default clears_when carries a QUALIFIED ref so a fixture ledger is clean
    # under the machine-checkability finding too. A repo#N token feeds no date into
    # ack_expiry, so fixture expiries are untouched.
    #
    # orch#733: a clears_check is now MANDATORY, so the fixture default declares an
    # honest kind=manual — deterministic on every host (no launchctl subprocess) and
    # clean under the mandatory-clause finding. Undeclared fixtures must opt in with
    # check=None: that state is a finding, not a neutral default.
    row = {"acked_at": acked_at, "clears_when": clears, "reason": reason}
    if check == "default":
        check = {"kind": "manual", "why": "fixture — not machine-evaluable"}
    if check is not None:
        row["clears_check"] = check
    return row


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
    # 10 as of 2026-08-01 (was 12): the #622 AC4 prune removed the two rows whose
    # jobs now exit 0 (daily104, weekly-retrain-patchtst — measured via launchctl),
    # and re-stamped shadow-ab-daily with its DIAGNOSED failure (fail-closed
    # PRECHECK on run-checkout pin drift; clears at the #747 item-5 pin sync).
    # 9 after the 2026-08-03 GOAL-1 refresh (goal1/ack-ledger-refresh): the
    # 07-31-expired cohort was RE-AFFIRMED with fresh diagnoses (retrain-panel104
    # carries the two-era table pointer + the renquant-backtesting#101 decision
    # surface; weekly-wf-promote likewise; meta-label's bare "task #75" became
    # renquant-orchestrator#771), and rq104-liveness was RETIRED — its state was
    # EXPIRED_CONDITION_MET: the next scheduled firing it waited on passed.
    # 5 after the 2026-08-04 RFC#210 promotion CLEARED retrain-panel104 +
    # weekly-wf-promote: both rows' clears_when named "an RFC#210 freshness-
    # fallback promotion lands" and the 11:31 PT manual promote stamped
    # promotion_basis=freshness_fallback_rfc210 into the ACTIVE artifact —
    # the named event, measured, not an expiry.
    assert R["n_acks"] == 5
    # SIX of ten. `com.renquant.rq105-batch-scores-export` was re-stamped
    # on 2026-07-31 by a32f397c ("the batch-export ack described a failure that is no
    # longer the failure"), so it is live until 2026-08-14; shadow-ab-daily is live
    # by the 2026-08-01 re-stamp. The count moved because the LEDGER moved, not
    # because the audit changed — a re-stamp is exactly the event this audit is
    # for. Named rather than counted, so the next re-stamp is visible here.
    # 5 after the 2026-08-02 conditional-retrain104 re-stamp: its 07-31 VIX-anomaly
    # run TESTED the clearing condition (chain FAILED in 5s — same root as the
    # weekly-wf-promote row), and the re-stamp records that measurement, making the
    # row live again instead of an expired row with an obsolete May-era reason.
    # 0 at this as-of after the refresh: every row's clock now starts 2026-08-01..03
    # and every explicit expiry sits inside the 14-day backstop (the first attempt
    # staggered 08-18..20 and the MEASUREMENT showed the acked_at+14 backstop
    # capping them all at 08-17 — expiries beyond the backstop are dead letters).
    assert R["n_expired"] == 0
    live = [r["job"] for r in R["rows"] if not r.get("expired")]
    assert len(live) == 5, live  # 2026-08-04: 105 pair + RFC#210 promotion pair cleared
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
    #
    # orch#733 is the SECOND such migration: it adds `clears_check` to every row, so
    # once its commit lands, ALL TEN rows read stale — including the 07-31/08-01
    # cohort this pin previously listed as fresh. Same reasoning as #641: the acked_at
    # stamps stay honest (adding a predicate is not a re-review), the audit correctly
    # reports every row edited after its stamp, and the pinnable fact is again the
    # PROPERTY: every row is stale and none is dropped.
    stale = {j: v for j, v in lags.items() if v is not None and v > 0}
    fresh = {j: v for j, v in lags.items() if v == 0}

    # 2026-08-05: the two stale rows were RE-REVIEWED and re-stamped, so the live
    # ledger now has none. That is the goal — but it meant this control, which
    # demanded a live stale row, could only pass while the ledger was defective.
    # A positive control bound to today's defects retires itself the moment the
    # defect is fixed; the anti-vacuity check is now SYNTHETIC and always
    # available, and the live assertion is that every stale row (if any) is
    # reported.
    for job, lag in stale.items():
        assert any(job in f and "expiry clock" in f for f in R["findings"]), (job, lag)

    # After the 2026-08-03 GOAL-1 refresh the FRESH set is the re-affirmed cohort
    # (acked_at re-stamped the day each row was actually re-reviewed with a new
    # diagnosis — a real re-review, unlike the #641/#733 field migrations) plus
    # the 2026-08-02 conditional-retrain104 re-stamp.
    # retrain-panel104 + weekly-wf-promote left the ledger 2026-08-04 (their
    # clears_when event — an RFC#210 fallback promotion — happened and was
    # measured in the ACTIVE artifact's promotion_basis stamp).
    assert fresh == {"com.renquant.conditional-retrain104": 0,
                     "com.renquant.monthly-meta-label-retrain": 0,
                     "com.renquant.rq104-degradation-sentinel": 0,
                     "com.renquant.rq105-batch-scores-export": 0,
                     "com.renquant.shadow-ab-daily": 0}, fresh
    assert set(stale) | set(fresh) == set(lags), "a row was silently dropped"


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
    """Measured 2026-08-01 after the #622 AC4 prune: fires on 0 today AND on
    2026-08-04 — the 2026-07-20 cohort that would have crossed the threshold then
    is gone (two rows removed as cleared, shadow-ab-daily re-stamped with its
    diagnosis). A forecast FROM a measurement, not a prediction."""
    def n(day):
        return len([f for f in A.audit(day)["findings"] if "longer than the" in f])

    assert n(dt.date(2026, 8, 1)) == 0
    assert n(dt.date(2026, 8, 4)) == 0
    # 0 after the 2026-08-03 refresh (was 5): every row re-stamped 08-01..03 and
    # every explicit expiry fires AT or BEFORE the age backstop would — the expiry
    # findings (measured ramp: 1 @08-12, 2 @08-13, 6 @08-15, 9 @08-17) arrive
    # before any age finding can, which is the staggered-reminder design.
    assert n(dt.date(2026, 8, 15)) == 0


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
    # 10 after the #622 AC4 prune; shadow-ab-daily's re-stamp is bucket ['ref']
    # (binds to orch#747 item 5) — one more checkable row than the survey counted.
    assert len(by) == 5  # 2026-08-04: 105 pair + RFC#210 promotion pair cleared
    assert by["com.renquant.shadow-ab-daily"] == [A.BUCKET_REF]
    narrative = {j for j, b in by.items()
                 if not any(x in (A.BUCKET_DATE, A.BUCKET_REF, A.BUCKET_ARTIFACT)
                            for x in b)}
    # 2 after the 2026-08-03 refresh (was 6): retrain-panel104 + weekly-wf-promote
    # now bind to renquant-backtesting#101, meta-label to renquant-orchestrator#771
    # (all bucket ref), and rq104-liveness was retired. The two remaining narrative
    # rows are the genuinely unbindable ones: an anomaly-gated chain and a
    # self-referential detection job.
    assert narrative == {
        "com.renquant.conditional-retrain104",
        "com.renquant.rq104-degradation-sentinel",
    }, narrative
    # rq105-batch-scores-export legitimately contains BOTH a qualified ref and a later
    # bare "#73" — the bucket records it, the finding's REF-guard keeps it quiet. The
    # unresolvable-as-written set is bare WITHOUT any qualified ref:
    # [] after the refresh: the meta-label row's bare "task #75" became the
    # qualified renquant-orchestrator#771 (the ack-audit finding that forced it).
    assert [j for j, b in by.items()
            if A.BUCKET_BARE_REF in b and A.BUCKET_REF not in b] == []
    # PIN MOVED 6 -> 0 by orch#733, and the finding itself was RETIRED: the prose lint
    # ("no machine-bindable fragment") is upgraded into the mandatory `clears_check`
    # clause, and all ten live rows now declare one (six launchctl_exit_zero, four
    # kind=manual with a why) — so neither the old finding nor its replacement fires.
    # The narrative-set pin above is unchanged: the PROSE of those six rows still has
    # no bindable fragment; what changed is that a structured predicate now governs.
    assert sum(1 for f in R["findings"] if "no machine-bindable fragment" in f) == 0
    assert sum(1 for f in R["findings"] if "no clears_check declared" in f) == 0
    assert sum(1 for f in R["findings"] if "bare #NN" in f) == 0


# ------------------------------------------------------- clears_check (orch#733) ----
#
# `ack_expiry` reads DATES out of an ack; nothing read its CONDITION — so "the fix
# landed" and "the fix never shipped" both surfaced as the same word, "expired".
# `clears_check` is the structured predicate the audit can evaluate, and the states
# below are the distinction #733 asks for. Dispatch is FAIL-CLOSED: the enumerated
# kinds are the allow-list and the default branch is a FINDING, per the repo's
# standing rule that an enumerated allow-list leaves a fail-open default.

def _lc_row(job, scope=None):
    d = {"kind": "launchctl_exit_zero", "job": job}
    if scope is not None:
        d["scope"] = scope
    return d


# launchctl list's 3-column shape: <pid> <status> <label>
FAKE_LAUNCHCTL = ("123\t0\tcom.t.ok\n"
                  "-\t1\tcom.t.bad\n"
                  "-\t-\tcom.t.neverran\n")


def test_launchctl_exit_zero_met_iff_the_status_is_zero():
    """Codex on PR #752: a MET verdict is scope-qualified. An omitted scope
    defaults to "clause" — the WEAKER claim — so the authoritative CONDITION_MET
    needs an explicit scope="full" declaration."""
    clause = A.evaluate_clears_check(_lc_row("com.t.ok"), FAKE_LAUNCHCTL)
    assert clause["condition"] == A.CONDITION_CLAUSE_MET
    assert clause["finding"] is None
    assert "NOT evaluated" in clause["detail"]  # says so out loud
    full = A.evaluate_clears_check(_lc_row("com.t.ok", scope="full"),
                                   FAKE_LAUNCHCTL)
    assert full["condition"] == A.CONDITION_MET and full["finding"] is None
    unmet = A.evaluate_clears_check(_lc_row("com.t.bad"), FAKE_LAUNCHCTL)
    assert unmet["condition"] == A.CONDITION_UNMET
    assert "last exit 1" in unmet["detail"]


def test_a_never_ran_job_and_an_unloaded_job_are_UNMET_not_met():
    """'-' in the status column and an absent label both mean launchctl does NOT
    show last exit 0 — the condition as stated. Neither is 'could not check':
    launchctl answered; the answer just is not 0."""
    never = A.evaluate_clears_check(_lc_row("com.t.neverran"), FAKE_LAUNCHCTL)
    absent = A.evaluate_clears_check(_lc_row("com.t.ghost"), FAKE_LAUNCHCTL)
    assert never["condition"] == A.CONDITION_UNMET
    assert absent["condition"] == A.CONDITION_UNMET
    assert "not in launchctl list" in absent["detail"]


def test_launchctl_UNAVAILABLE_is_UNEVALUABLE_a_distinct_state_not_a_verdict():
    """On a linux CI runner launchctl does not exist. 'unmet' there would turn an
    environment property into a false problem; 'met' would be the fail-open
    default this module exists to refuse. So it is neither — and no finding,
    because the check itself is well-formed."""
    r = A.evaluate_clears_check(_lc_row("com.t.ok"), None)
    assert r["condition"] == A.CONDITION_UNEVALUABLE
    assert r["finding"] is None
    assert r["condition"] not in (A.CONDITION_MET, A.CONDITION_UNMET)


def test_path_exists_is_met_iff_the_path_exists(tmp_path):
    there = tmp_path / "artifact.json"
    there.write_text("{}")
    clause = A.evaluate_clears_check({"kind": "path_exists", "path": str(there)})
    full = A.evaluate_clears_check({"kind": "path_exists", "path": str(there),
                                    "scope": "full"})
    gone = A.evaluate_clears_check({"kind": "path_exists",
                                    "path": str(tmp_path / "nope")})
    assert clause["condition"] == A.CONDITION_CLAUSE_MET  # default scope=clause
    assert full["condition"] == A.CONDITION_MET
    assert gone["condition"] == A.CONDITION_UNMET


def test_unmet_is_unmet_under_EITHER_scope():
    """UNMET is deliberately not scope-qualified: one failed clause already
    falsifies the whole conjunction, so that direction is sound as stated —
    which is also why EXPIRED_CONDITION_UNMET keeps its problem grade from a
    clause-scoped check."""
    for scope in (None, "clause", "full"):
        r = A.evaluate_clears_check(_lc_row("com.t.bad", scope=scope),
                                    FAKE_LAUNCHCTL)
        assert r["condition"] == A.CONDITION_UNMET, scope


def test_an_unknown_scope_is_a_FINDING_never_a_silent_pass():
    """The scope set is closed and fails closed exactly like the kind set."""
    r = A.evaluate_clears_check(_lc_row("com.t.ok", scope="total"),
                                FAKE_LAUNCHCTL)
    assert r["condition"] == A.CONDITION_UNEVALUABLE
    assert r["finding"] and "unknown clears_check scope" in r["finding"]
    assert r["condition"] not in (A.CONDITION_MET, A.CONDITION_CLAUSE_MET)


def test_manual_reports_MANUAL_and_is_never_a_missing_check_finding():
    r = A.evaluate_clears_check({"kind": "manual", "why": "open-ended WF-gate pass"})
    assert r["condition"] == A.CONDITION_MANUAL
    assert r["finding"] is None
    assert "open-ended WF-gate pass" in r["detail"]


def test_manual_WITHOUT_a_why_is_a_finding_not_an_honest_declaration():
    """kind=manual is a design statement; without its justification it is an
    undeclared check in disguise, and fail-closed applies."""
    r = A.evaluate_clears_check({"kind": "manual"})
    assert r["condition"] == A.CONDITION_UNEVALUABLE
    assert r["finding"] and "no `why`" in r["finding"]


def test_an_UNKNOWN_kind_is_a_FINDING_never_a_silent_pass():
    """The fail-closed default itself. A new kind somebody invents — or a typo of
    a known one — must land in the default branch AS A FINDING."""
    r = A.evaluate_clears_check({"kind": "github_pr_merged", "repo": "x", "pr": 73})
    assert r["condition"] == A.CONDITION_UNEVALUABLE
    assert r["finding"] and "unknown clears_check kind" in r["finding"]
    assert r["condition"] not in (A.CONDITION_MET, A.CONDITION_UNMET)


@pytest.mark.parametrize("bad", [
    "a string", 7, ["launchctl_exit_zero"],                 # not an object
    {"job": "com.t.ok"},                                    # no kind at all
    {"kind": "launchctl_exit_zero"},                        # kind without its field
    {"kind": "path_exists"},
])
def test_every_malformed_shape_is_a_finding(bad):
    r = A.evaluate_clears_check(bad, FAKE_LAUNCHCTL)
    assert r["finding"], bad
    assert r["condition"] == A.CONDITION_UNEVALUABLE, bad


def test_no_clears_check_at_all_is_UNDECLARED_its_own_condition():
    r = A.evaluate_clears_check(None)
    assert r["condition"] == A.CONDITION_UNDECLARED
    assert r["finding"] is None  # the audit emits the mandatory-clause finding


# ------------------------------- the condition x expiry matrix, end to end ----
def test_the_condition_x_expiry_matrix_on_synthetic_rows(tmp_path):
    """Every cell #733 names — plus the CLAUSE_MET pair codex asked for on
    PR #752 — produced by one audit run with an injected launchctl snapshot.
    Today = 2026-07-25: rows acked 07-01 are expired (07-01 + 14d = 07-15),
    rows acked 07-20 are not (08-03)."""
    ledger = {
        "met.live": _ack("2026-07-20", check=_lc_row("com.t.ok", scope="full")),
        "met.dead": _ack("2026-07-01", check=_lc_row("com.t.ok", scope="full")),
        "clause.live": _ack("2026-07-20", check=_lc_row("com.t.ok")),
        "clause.dead": _ack("2026-07-01", check=_lc_row("com.t.ok")),
        "unmet.live": _ack("2026-07-20", check=_lc_row("com.t.bad")),
        "unmet.dead": _ack("2026-07-01", check=_lc_row("com.t.bad")),
        "manual.dead": _ack("2026-07-01"),
        "undeclared.live": _ack("2026-07-20", check=None),
    }
    root = _repo(tmp_path, [(ledger, "2026-07-20")])
    R = A.audit(dt.date(2026, 7, 25), str(root / A.LEDGER_REL), str(root),
                launchctl_text=FAKE_LAUNCHCTL)
    states = {r["job"]: r["state"] for r in R["rows"]}
    assert states == {
        "met.live": A.STATE_MET_UNEXPIRED,
        "met.dead": A.STATE_EXPIRED_CONDITION_MET,
        "clause.live": A.STATE_CLAUSE_MET,
        "clause.dead": A.STATE_EXPIRED_CLAUSE_MET,
        "unmet.live": A.STATE_UNMET_UNEXPIRED,
        "unmet.dead": A.STATE_EXPIRED_CONDITION_UNMET,
        "manual.dead": A.STATE_MANUAL_EXPIRED,
        "undeclared.live": A.STATE_UNDECLARED_UNEXPIRED,
    }, states

    # Exactly ONE problem-grade condition finding, and it names the one row whose
    # expiry means "the fix never shipped" — #733's core point.
    unmet_findings = [f for f in R["findings"] if "condition UNMET" in f]
    assert len(unmet_findings) == 1 and "unmet.dead" in unmet_findings[0]

    # The MET and CLAUSE_MET states are info-grade: visible as states, never
    # findings. A met condition alarming would train readers to ignore the one
    # alarm that matters. (Prefix match, because "met.live" is a substring of
    # "unmet.live"; restricted to condition findings, because the fixture's
    # 07-01 rows also carry an honest stamp-lag finding not under test here.)
    assert not [f for f in R["findings"]
                if f.startswith(("met.live:", "met.dead:",
                                 "clause.live:", "clause.dead:"))
                and "condition" in f]

    # The undeclared row gets the mandatory-clause finding — the #733 upgrade of
    # the old narrative-only clears_when lint.
    mand = [f for f in R["findings"] if "no clears_check declared" in f]
    assert len(mand) == 1 and "undeclared.live" in mand[0]


def test_a_met_clause_under_a_conjunction_NEVER_reports_CONDITION_MET(tmp_path):
    """The regression codex asked for on PR #752, on a synthetic mirror of the
    live 1-of-3 row (rq105-batch-scores-export: merged AND pinned AND one clean
    session, checked by a single launchctl exit). The met clause must surface as
    CLAUSE_MET — and must NEVER surface under the authoritative name, in either
    expiry column: a misleading verdict under a stronger name was the finding."""
    row = _ack("2026-07-20",
               clears="repo-x#73 merged AND pinned AND one clean session",
               check=_lc_row("com.t.ok"))          # scope omitted -> "clause"
    root = _repo(tmp_path, [({"j": row}, "2026-07-20")])
    for today, want in ((dt.date(2026, 7, 25), A.STATE_CLAUSE_MET),
                        (dt.date(2026, 8, 20), A.STATE_EXPIRED_CLAUSE_MET)):
        R = A.audit(today, str(root / A.LEDGER_REL), str(root),
                    launchctl_text=FAKE_LAUNCHCTL)
        r = R["rows"][0]
        assert r["condition"] == A.CONDITION_CLAUSE_MET, r
        assert r["condition"] != A.CONDITION_MET
        assert r["state"] == want, r
        assert r["state"] not in (A.STATE_MET_UNEXPIRED,
                                  A.STATE_EXPIRED_CONDITION_MET), r
        assert "NOT evaluated" in r["condition_detail"]


def test_an_expired_row_with_UNEVALUABLE_condition_does_not_claim_unmet(tmp_path):
    """Expired + could-not-check must not read as 'the fix never shipped' — that
    claim needs an actual verdict. The state stays distinct instead."""
    root = _repo(tmp_path, [
        ({"j": _ack("2026-07-01", check=_lc_row("com.t.ok"))}, "2026-07-01")])
    R = A.audit(dt.date(2026, 7, 25), str(root / A.LEDGER_REL), str(root),
                launchctl_text=None)
    assert R["rows"][0]["state"] == A.STATE_EXPIRED_CONDITION_UNEVALUABLE
    assert not [f for f in R["findings"] if "condition UNMET" in f]


def test_an_unknown_kind_reaches_the_findings_with_the_job_name(tmp_path):
    root = _repo(tmp_path, [
        ({"j": _ack("2026-07-20", check={"kind": "wishful_thinking"})},
         "2026-07-20")])
    R = A.audit(dt.date(2026, 7, 25), str(root / A.LEDGER_REL), str(root))
    bad = [f for f in R["findings"] if "unknown clears_check kind" in f]
    assert len(bad) == 1 and bad[0].startswith("j: ")


def test_a_row_with_a_declared_check_is_not_flagged_for_narrative_prose(tmp_path):
    """The upgrade must not double-charge: a narrative-only clears_when WITH a
    declared clears_check is exactly the honest end state (prose for humans, a
    predicate for the machine) and produces no mandatory-clause finding."""
    root = _repo(tmp_path, [
        ({"j": _ack("2026-07-20", clears="next VIX-anomaly trigger runs clean",
                    check=_lc_row("com.t.ok"))}, "2026-07-20")])
    R = A.audit(dt.date(2026, 7, 25), str(root / A.LEDGER_REL), str(root),
                launchctl_text=FAKE_LAUNCHCTL)
    assert not [f for f in R["findings"] if "clears_check" in f]
    assert not [f for f in R["findings"] if "no machine-bindable fragment" in f]


# --------------------------- the live ledger's clears_check, measured today ----
def test_the_live_ledgers_clears_check_states_are_measured_not_asserted():
    """The #733 population pin, in two layers.

    The KINDS are ledger content — deterministic everywhere, pinned exactly: six
    launchctl_exit_zero rows and four kind=manual rows whose conditions are
    open-ended by design (WF-gate passes, the #75 redesign, the sentinel's
    self-referential exit 1).

    The SCOPES are ledger content too — the reviewed judgment of whether each
    row's exit-0 observation IS its whole clears_when ("full": VIX-trigger-runs-
    clean, next-liveness-firing) or ONE clause of a wider condition ("clause":
    the 1-of-3 batch-export row, the pin-sync-AND-PRECHECK shadow-ab row, the
    two rq105 rows whose clears_when names upstream deploys). Pinned exactly,
    with the codex #752 invariant: a clause-scoped row can NEVER reach the
    authoritative CONDITION_MET, on any host, whatever launchctl says.

    The launchctl VERDICTS are read from THIS host's launchd, so they are NOT
    hard-pinned: on the run machine they were measured 2026-08-02 as
    met={rq104-liveness (scope full)}, clause_met={rq105-batch-scores-export
    (scope clause — its OTHER two clauses, pinned + clean session, are exactly
    what #733 measured as unmet)}, unmet={conditional-retrain104 (exit 1),
    shadow-ab-daily (3)}  (105 pair cleared 2026-08-04)
    [VERIFIED — launchctl list, 2026-08-02], but a linux CI runner has no
    launchctl (every launchctl row reads UNEVALUABLE — the designed distinct
    state) and any job rerun moves a verdict on a schedule nobody controls. A
    literal here would measure the operator's disk. What IS pinned: the verdict
    vocabulary, the scope-to-verdict invariants, that unavailability is
    all-or-nothing within one run, and the state = condition x expiry parity
    on every live row."""
    R = A.audit(dt.date(2026, 8, 2))
    kinds = {r["job"]: r["check_kind"] for r in R["rows"]}
    assert kinds == {
        "com.renquant.conditional-retrain104": A.CHECK_LAUNCHCTL,
        "com.renquant.monthly-meta-label-retrain": A.CHECK_MANUAL,
        "com.renquant.rq104-degradation-sentinel": A.CHECK_MANUAL,
        "com.renquant.rq105-batch-scores-export": A.CHECK_LAUNCHCTL,
        "com.renquant.shadow-ab-daily": A.CHECK_LAUNCHCTL,
    }, kinds

    scopes = {r["job"]: r["check_scope"] for r in R["rows"]}
    assert scopes == {
        "com.renquant.conditional-retrain104": A.SCOPE_FULL,
        "com.renquant.monthly-meta-label-retrain": None,
        "com.renquant.rq104-degradation-sentinel": None,
        "com.renquant.rq105-batch-scores-export": A.SCOPE_CLAUSE,
        "com.renquant.shadow-ab-daily": A.SCOPE_CLAUSE,
    }, scopes

    conds = {r["job"]: r["condition"] for r in R["rows"]}
    for job, kind in kinds.items():
        if kind == A.CHECK_MANUAL:
            assert conds[job] == A.CONDITION_MANUAL, job
        elif scopes[job] == A.SCOPE_CLAUSE:
            # the codex #752 invariant, host-independent: clause-scoped rows can
            # reach clause_met at best, NEVER the authoritative met
            assert conds[job] in (A.CONDITION_CLAUSE_MET, A.CONDITION_UNMET,
                                  A.CONDITION_UNEVALUABLE), (job, conds[job])
            assert conds[job] != A.CONDITION_MET, job
        else:
            assert conds[job] in (A.CONDITION_MET, A.CONDITION_UNMET,
                                  A.CONDITION_UNEVALUABLE), (job, conds[job])
            assert conds[job] != A.CONDITION_CLAUSE_MET, job

    # One launchctl snapshot serves the whole run, so unavailability cannot be
    # per-row: either every launchctl verdict is UNEVALUABLE or none is.
    lc = {conds[j] for j, k in kinds.items() if k == A.CHECK_LAUNCHCTL}
    assert lc == {A.CONDITION_UNEVALUABLE} or A.CONDITION_UNEVALUABLE not in lc, lc

    # state = condition x expiry, verified cell by cell on the live rows
    for r in R["rows"]:
        assert r["state"] == A.combine_state(r["condition"], r["expired"]), r

    # All ten rows declare — the mandatory-clause finding set is EMPTY, and no
    # row's check is malformed (fail-closed would make that loud).
    assert not [f for f in R["findings"] if "no clears_check declared" in f]
    assert not [f for f in R["findings"] if "unknown clears_check kind" in f]
    for r in R["rows"]:
        assert r["condition_finding"] is None, r


def test_the_ANTI_VACUITY_control_is_SYNTHETIC_not_bound_to_a_live_defect(tmp_path):
    """A stale row must still be DETECTED — proven on a repo built for it.

    Until 2026-08-05 this property was pinned by requiring the LIVE ledger to
    contain a stale row. That control could only pass while the ledger was
    defective: fixing the two mis-stamped rows retired the very evidence that
    the audit can see staleness at all. A positive control that dies when the
    thing it guards is repaired is not a control — so it is synthetic here, and
    available forever.
    """
    root = _repo(tmp_path / "stale", [
        ({"j": _ack("2026-07-01")}, "2026-07-01"),
        # the row is EDITED later without its stamp moving: exactly the lag the
        # audit exists to report.
        ({"j": _ack("2026-07-01", reason="re-diagnosed, stamp not moved")},
         "2026-07-20"),
    ])
    R = A.audit(dt.date(2026, 7, 25), str(root / A.LEDGER_REL), str(root))
    row = R["rows"][0]
    assert row["stamp_lag_days"] == 19, row
    assert any("expiry clock" in f for f in R["findings"]), R["findings"]
