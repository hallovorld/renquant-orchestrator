"""Silent-refusal sentinel (GOAL-5 AC5).

The incident these pin: a weekly job that exits 0 every run while declining
to promote anything. Liveness says healthy, the served artifact ages to 622
days, and nothing alarms.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant104"))
import rq104_silent_refusal_sentinel as S  # noqa: E402

AS_OF = dt.date(2026, 7, 28)
REFUSED = "promote: refused — NOT FRESH (expected on a stale panel; old pin kept)\n"
ACTED = "promote: promoted candidate 2026-04-27 -> served pin\n"
CRASHED = "Traceback (most recent call last):\nValueError: boom\n"


def _job(tmp_path, runs: dict[str, str]) -> S.WatchedJob:
    d = tmp_path / "joblogs"
    d.mkdir(exist_ok=True)
    for day, text in runs.items():
        (d / f"{day}.log").write_text(text, encoding="utf-8")
    return S.WatchedJob(name="test-job", log_dir=str(d),
                        refusal_re=r"promote:\s*refused",
                        action_re=r"promote:\s*(promoted|advanced|applied)")


def test_three_consecutive_refusals_alarm(tmp_path):
    job = _job(tmp_path, {"2026-07-11": REFUSED, "2026-07-18": REFUSED,
                          "2026-07-25": REFUSED})
    msg = S.check(job, as_of=AS_OF)
    assert msg is not None
    assert "3 consecutive" in msg and "2026-07-25:refused" in msg


def test_two_refusals_stay_silent(tmp_path):
    # one legitimately stale week is the gate working, not an incident
    job = _job(tmp_path, {"2026-07-18": REFUSED, "2026-07-25": REFUSED})
    assert S.check(job, as_of=AS_OF) is None


def test_a_promotion_breaks_the_streak(tmp_path):
    job = _job(tmp_path, {"2026-07-04": REFUSED, "2026-07-11": REFUSED,
                          "2026-07-18": ACTED, "2026-07-25": REFUSED})
    assert S.check(job, as_of=AS_OF) is None


def test_action_wins_within_one_run(tmp_path):
    # refused one candidate, promoted another: that run ACTED
    job = _job(tmp_path, {"2026-07-11": REFUSED, "2026-07-18": REFUSED,
                          "2026-07-25": REFUSED + ACTED})
    assert S.check(job, as_of=AS_OF) is None


def test_crashed_runs_count_toward_the_streak(tmp_path):
    # The REAL 2026-07-28 shape: refused / failed / failed / refused. A
    # refusals-only rule scores this as a streak of 2 and stays silent while
    # the served model ages for months.
    job = _job(tmp_path, {"2026-07-03": REFUSED, "2026-07-11": CRASHED,
                          "2026-07-18": CRASHED, "2026-07-25": REFUSED})
    msg = S.check(job, as_of=AS_OF)
    assert msg is not None
    assert "4 consecutive" in msg and "2 of them CRASHED" in msg
    assert "2026-07-11:crashed" in msg
    assert "reported FAIL" not in msg  # crashes are crashes, not gate verdicts


def test_undecided_gap_does_not_masquerade_as_consecutive(tmp_path):
    # newest=undecided (empty log), then refused, failed, refused: the
    # streak still counts (fail toward alarming) but must NOT claim these
    # 3 runs are "consecutive" when an unclassifiable run sits at the top.
    job = _job(tmp_path, {"2026-07-04": REFUSED, "2026-07-11": CRASHED,
                          "2026-07-18": REFUSED, "2026-07-25": ""})
    msg = S.check(job, as_of=AS_OF)
    assert msg is not None
    assert "3 consecutive" not in msg
    assert "unclassifiable" in msg and "2026-07-25" in msg
    assert "2026-07-18:refused" in msg and "2026-07-11:crashed" in msg


def test_undecided_gap_between_two_older_runs_is_still_reported(tmp_path):
    # gap in the MIDDLE, not just at the top: 07-25 refused, 07-18
    # undecided, 07-11 failed, 07-04 refused. Still a streak of 3 real
    # non-actions, but not temporally consecutive.
    job = _job(tmp_path, {"2026-07-04": REFUSED, "2026-07-11": CRASHED,
                          "2026-07-18": "", "2026-07-25": REFUSED})
    msg = S.check(job, as_of=AS_OF)
    assert msg is not None
    assert "consecutive" not in msg
    assert "2026-07-18" in msg  # the skipped date is named


def test_a_crash_marker_NEXT_TO_a_verdict_is_evidence_not_a_crash(tmp_path):
    """REVERSED 2026-08-18 (D2), and the reversal is the fix.

    The rule this replaces — "a crash marker outranks a refusal" — was written
    for the retired patchtst lane's 07-03 run (CorpusRefreshError + `promote:
    refused` + rc=0). Applied to the WF-gate lanes it is simply wrong: the WF
    gate DELIBERATELY logs caught tracebacks as sanity evidence and then
    decides, so 14 of 14 weekly runs that had printed a terminal verdict were
    being reported as CRASHED (13 of them straight after "WF gate REJECTED
    staged model — production unchanged.").

    A crash is a claim about what the run never got to do. It has to rest on
    the ABSENCE of a decision. Nothing about the alarm's loudness changes —
    both outcomes count in the streak — only its truthfulness.
    """
    job = _job(tmp_path, {})
    assert S.classify_run(CRASHED + REFUSED, job) == "refused"


def test_corpus_refresh_error_is_recognised_without_a_traceback(tmp_path):
    job = _job(tmp_path, {})
    assert S.classify_run("CorpusRefreshError: sidecar rejected\n", job) == "crashed"


def test_appended_stdout_log_is_ignored(tmp_path):
    # stdout.log accumulates across runs; one old refusal in it must not pin
    # the streak forever
    job = _job(tmp_path, {"2026-07-25": REFUSED})
    (Path(job.log_dir) / "stdout.log").write_text(REFUSED * 9, encoding="utf-8")
    assert S.check(job, as_of=AS_OF) is None


def test_stale_logs_beyond_the_age_window_are_ignored(tmp_path, monkeypatch):
    # a job that stopped running is the liveness checker's problem, not ours
    monkeypatch.setattr(S, "MAX_LOG_AGE_DAYS", 30)
    job = _job(tmp_path, {"2026-01-10": REFUSED, "2026-01-17": REFUSED,
                          "2026-01-24": REFUSED})
    assert S.check(job, as_of=AS_OF) is None


def test_missing_log_dir_is_silent(tmp_path):
    job = S.WatchedJob(name="absent", log_dir=str(tmp_path / "nope"),
                       refusal_re=r"x", action_re=r"y")
    assert S.check(job, as_of=AS_OF) is None


def test_main_exit_codes_and_dry_run(tmp_path, monkeypatch, capsys):
    job = _job(tmp_path, {"2026-07-11": REFUSED, "2026-07-18": REFUSED,
                          "2026-07-25": REFUSED})
    monkeypatch.setattr(S, "WATCHED", (job,))
    sent: list = []
    monkeypatch.setattr(S, "alert", lambda t, b, **kw: sent.append((t, b)))
    assert S.main(["--as-of", "2026-07-28", "--dry-run"]) == 1
    assert sent == []                      # dry-run sends nothing
    assert S.main(["--as-of", "2026-07-28"]) == 1
    assert len(sent) == 1 and "SILENT REFUSAL" in sent[0][0]


def test_the_founding_lane_is_retired_and_the_registry_lives_on():
    """2026-08-02: the founding job (weekly-retrain-patchtst) was booted out
    under the operator's Grant B (decision orch#741; bootout verified). A
    watch on a job that can never write another log is eternal noise or
    eternal false-quiet — the lane is retired; the registry must NOT be
    empty (the doctrine outlives its founding incident)."""
    names = {j.name for j in S.WATCHED}
    assert "weekly-retrain-patchtst" not in names
    assert len(names) >= 3, "the registry must keep covering the living jobs"


@pytest.mark.parametrize("text,expected", [
    (REFUSED, "refused"),
    (ACTED, "acted"),
    (CRASHED, "crashed"),
    ("", "undecided"),
])
def test_classify_run(text, expected, tmp_path):
    job = _job(tmp_path, {})
    assert S.classify_run(text, job) == expected


# ------------------------------------------------- 2026-08-01 registry expansion ----
#
# Three promotion-adjacent jobs joined WATCHED after the #724 completeness pass. The
# patterns below are pinned to the REAL lines they were read from — refusals off dated
# logs, actions off the wrapper scripts' emitters (no success has ever occurred in any
# log window, which is precisely why these jobs need watching).

def _watched(name):
    return next(j for j in S.WATCHED if j.name == name)


def test_weekly_wf_promote_patterns_classify_the_real_lines():
    j = _watched("weekly-wf-promote")
    import re
    assert re.search(j.refusal_re,
                     "WF gate REJECTED staged model — production unchanged.")
    assert re.search(j.action_re,
                     "=== weekly_wf_promote PASSED at Sat Aug  1 — gate summary ===")
    assert re.search(j.failure_re, "Promote FAILED — production may still be on prior")


def test_conditional_retrain_has_no_refusal_vocabulary_and_real_failure_lines():
    j = _watched("conditional-retrain104")
    import re
    assert j.refusal_re is None
    assert re.search(j.failure_re,
                     "=== Gated WF promote chain FAILED (anomaly_vix_5pct) at Fri — rc=1 ===")
    # RenQuant#603/#604 (orch#1052): the wrapper names the POSITIVELY
    # established outcome. Both completed decisions are actions; a refusal by
    # the gate is the gate working, not silence.
    assert re.search(j.action_re,
                     "=== Gated WF promote chain PROMOTED (anomaly_vix_5pct) at Fri — passed ===")
    assert re.search(j.action_re,
                     "=== Gated WF promote chain RAN, NOTHING PROMOTED (anomaly_vix_5pct) at Fri — refused ===")
    # the wrapper's own contract-drift report is a FAILURE to establish, never
    # an action and never silence
    assert re.search(j.failure_re,
                     "=== Gated WF promote chain OUTCOME UNVERIFIED (anomaly_vix_5pct) at Fri ===")
    # the RETIRED exit-code-derived line must no longer classify as action —
    # an old log replayed through the new patterns must not read as a decision
    assert not re.search(j.action_re,
                         "=== Gated WF promote chain complete (anomaly_vix_5pct) at ===")
    # the healthy idle line must classify as NEITHER refusal nor action nor failure
    idle = "anomaly-triggers: No anomaly triggers fired; no retrain needed"
    assert not re.search(j.action_re, idle)
    assert not re.search(j.failure_re, idle)


def test_retrain_panel_patterns_classify_the_real_lines():
    j = _watched("retrain-panel104")
    import re
    assert j.refusal_re is None
    assert re.search(j.failure_re,
                     "=== retrain_panel delegated weekly_wf_promote FAILED at Sun — rc=1 ===")
    assert re.search(j.action_re,
                     "=== retrain_panel delegated weekly_wf_promote PROMOTED at Sun — passed ===")
    assert re.search(j.action_re,
                     "=== retrain_panel delegated weekly_wf_promote RAN, NOTHING PROMOTED at Sun — refused ===")
    assert re.search(j.failure_re,
                     "=== retrain_panel delegated weekly_wf_promote OUTCOME UNVERIFIED at Sun ===")
    # retired exit-code-derived line: must NOT classify as action (orch#1052)
    assert not re.search(j.action_re,
                         "=== retrain_panel delegated weekly_wf_promote PASS at Sun ===")
    assert not re.search(j.failure_re, "weekly_wf_promote already ran today")


def test_a_delegated_fail_is_never_glossed_as_crashed(tmp_path):
    """The first scheduled finding's defect (2026-08-03 diagnosis): the alarm
    said "11 of them CRASHED" about retrain-panel104 when 9 of the 11 were the
    wrapper's honest `delegated weekly_wf_promote FAIL` echo — the WF gate's
    own verdict, not a crash. Zero of the 6 quoted Sunday failures was a
    crash. The alarm must attribute each class as what it saw."""
    d = tmp_path / "joblogs"
    d.mkdir()
    fail = "=== retrain_panel delegated weekly_wf_promote FAIL at Sun ===\n"
    for day in ("2026-07-11", "2026-07-18"):
        (d / f"{day}.log").write_text(fail, encoding="utf-8")
    (d / "2026-07-25.log").write_text(CRASHED, encoding="utf-8")
    j = _watched("retrain-panel104")
    job = S.WatchedJob(name=j.name, log_dir=str(d), refusal_re=j.refusal_re,
                       action_re=j.action_re, failure_re=j.failure_re)
    msg = S.check(job, as_of=AS_OF)
    assert msg is not None
    assert "2 of them reported FAIL" in msg and "not a crash" in msg
    assert "1 of them CRASHED" in msg
    assert "2026-07-11:failed" in msg and "2026-07-25:crashed" in msg


def test_a_none_refusal_job_never_classifies_a_run_as_refused():
    """A job with no refusal vocabulary must classify a decision-less run as a SKIP,
    never as refused — exercised through the REAL classifier."""
    j = _watched("conditional-retrain104")
    out = S.classify_run("the job looked around and did nothing today", j)
    assert out != "refused", out

def test_weekly_wf_promote_left_the_unwatchable_registry():
    assert "weekly-wf-promote" not in S.UNWATCHABLE_LANES
    assert any(j.name == "weekly-wf-promote" for j in S.WATCHED)


@pytest.mark.parametrize("script,pattern", [
    ("scripts/weekly_wf_promote.sh", "weekly_wf_promote PASSED"),
    ("scripts/conditional_retrain_104.sh", "Gated WF promote chain PROMOTED"),
    ("scripts/retrain_panel.sh", "delegated weekly_wf_promote PROMOTED"),
])
def test_action_patterns_are_pinned_to_their_emitter_sources(script, pattern):
    """The doctrine amendment's enforcement: an action pattern read off source instead
    of history must MATCH that source, so a reworded emitter breaks here rather than
    silently blinding the watch. Skips LOUDLY where the umbrella is absent (CI)."""
    src = Path("/Users/renhao/git/github/RenQuant") / script
    if not src.exists():
        pytest.skip(f"{src} absent on this machine — emitter pin not verifiable here")
    # [orch#1052] the pattern must sit on an EMIT line, not merely in the file:
    # the previous pin ("delegated weekly_wf_promote PASS") stayed green for a
    # day because a COMMENT quoted the retired wording — a check satisfiable by
    # commentary validates the wrong object.
    emit_lines = [
        ln for ln in src.read_text(errors="ignore").splitlines()
        if ln.lstrip().startswith(("echo", "printf", "notify"))
    ]
    assert any(pattern in ln for ln in emit_lines), (
        f"{script} no longer emits '{pattern}' on any echo/printf/notify line — "
        f"the watch for it is now blind; update the pattern from the CURRENT "
        f"emitter, do not delete this test")


# ----------------------------------------------- emitter contract (CI-enforced) ----
#
# [codex on orch#738]: source-derived patterns proven only by a skip-in-CI local test
# leave the production classifications resting on a developer-local contract. The
# contract now lives IN THIS REPO as a versioned fixture; these tests run everywhere.

import json as _json
import re as _re

_CONTRACT = _json.loads(
    (Path(__file__).resolve().parent.parent / "ops" / "renquant104" /
     "emitter_contract.json").read_text())


def _render(template: str) -> str:
    """A plausible rendering of a shell echo template: every substitution collapses
    to a placeholder. The regexes under contract must match on the INVARIANT text, so
    the placeholder's content must not matter — that is what these tests prove."""
    out = _re.sub(r"\$\([^)]*\)", "PLACEHOLDER", template)
    out = _re.sub(r"\$\{?[A-Za-z_][A-Za-z_0-9]*\}?", "PLACEHOLDER", out)
    return out


def test_every_contract_line_is_matched_by_the_corresponding_pattern():
    """CI-enforced binding: regex <-> contract. Breaking either side fails here,
    on every machine, umbrella or not."""
    kinds = {"action": "action_re", "refusal": "refusal_re", "failure": "failure_re"}
    for row in _CONTRACT["lines"]:
        lane = _watched(row["job"])
        pattern = getattr(lane, kinds[row["kind"]])
        assert pattern is not None, (row["job"], row["kind"])
        rendered = _render(row["template"])
        assert _re.search(pattern, rendered), (
            f"{row['job']}/{row['kind']}: pattern {pattern!r} no longer matches the "
            f"contracted emitter line {rendered!r} — fix the pattern or version the "
            f"contract, never ignore this")


def test_every_source_derived_watched_pattern_is_under_contract():
    """Anti-vacuity for the contract itself: each of the three source-derived lanes
    must have its action line contracted — a lane added without a contract row would
    otherwise reintroduce the developer-local dependency reviewed away in #738."""
    contracted = {(r["job"], r["kind"]) for r in _CONTRACT["lines"]}
    for name in ("weekly-wf-promote", "conditional-retrain104", "retrain-panel104"):
        assert (name, "action") in contracted, name


def test_contract_lines_marked_observed_cite_a_real_log_shape():
    for row in _CONTRACT["lines"]:
        o = row["observed_in_logs"]
        assert o is False or (isinstance(o, str) and o.startswith("logs/")), row


def test_local_wrapper_still_emits_the_contracted_lines():
    """Drift detector — the LOCAL half. Skips loudly off-machine; on the dev box it
    catches a cross-repo wording change the day it lands, instead of the day an
    incident stays open on `undecided` classifications."""
    root = Path("/Users/renhao/git/github/RenQuant")
    if not root.exists():
        pytest.skip("umbrella absent — local drift check not verifiable here; the "
                    "CI-enforced contract tests above still ran")
    for row in _CONTRACT["lines"]:
        script = root / row["source"].rsplit(":", 1)[0]
        if not script.exists():
            pytest.skip(f"{script} absent — cannot verify drift here")
        text = script.read_text(errors="ignore")
        assert row["template"] in text, (
            f"{row['source']} no longer emits the contracted line verbatim — the "
            f"wrapper wording drifted; re-capture the contract AND re-verify the "
            f"patterns before trusting this lane's classifications")
        # [codex on orch#785] SOURCE-LOCATION assertion: the template must sit
        # at the RECORDED line, not merely somewhere in the file — a stale
        # line citation survives the presence check and rots silently.
        line_no = int(row["source"].rsplit(":", 1)[1])
        lines = text.splitlines()
        assert line_no <= len(lines) and row["template"].split("$")[0].strip('"= ') in lines[line_no - 1], (
            f"{row['source']}: the contracted template is not at the recorded "
            f"line (found elsewhere or moved) — re-capture line numbers")


# ═════════════════ 2026-08-18: four MEASURED classification defects ═════════
#
# Every fixture below is REAL LOG BYTES copied out of
# /Users/renhao/git/github/RenQuant/logs/, so these tests fail against the
# reality that produced them rather than against a story about it. The three
# `*_synth_from_emitter.log` files are the exception and are labelled as such:
# no delegator has EVER claimed success in any log window, which is precisely
# why D1 went unnoticed — those three are rendered from the contracted emitter
# templates and `test_the_synthesised_fixtures_render_the_CONTRACTED_emitters`
# pins them to the contract so they cannot drift into fiction.

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "silent_refusal"


def _fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _lane(name: str, log_dir, **over) -> S.WatchedJob:
    """A registered lane re-pointed at a temp log dir, patterns untouched."""
    j = _watched(name)
    fields = dict(name=j.name, log_dir=str(log_dir), refusal_re=j.refusal_re,
                  action_re=j.action_re, failure_re=j.failure_re,
                  abort_re=j.abort_re, corroborator=j.corroborator)
    fields.update(over)
    return S.WatchedJob(**fields)


# ── D2: a caught traceback is evidence, not a crash ─────────────────────────

def test_D2_a_traceback_before_a_verdict_is_REFUSED_not_CRASHED():
    """logs/weekly_wf_promote/2026-06-22.log: three caught tracebacks logged
    as WF-gate sanity evidence, then "WF gate REJECTED staged model —
    production unchanged." Before the fix this and 13 sibling runs were
    reported CRASHED — 14 of 14 runs that had reached a terminal verdict."""
    out = S.classify_run(_fx("weekly_traceback_then_reject.log"),
                         _watched("weekly-wf-promote"))
    assert out == "refused", out


def test_D2_the_fixture_really_does_contain_the_crash_marker():
    """Anti-vacuity: the test above proves nothing if the excerpt lost its
    traceback in the copy. The OLD rule must demonstrably fire on it."""
    text = _fx("weekly_traceback_then_reject.log")
    assert re.search(r"Traceback \(most recent call last\)", text)
    assert re.search(_watched("weekly-wf-promote").crash_re, text, re.M)


# ── D3: signal death is a crash, and it was invisible ───────────────────────

def test_D3_a_SIGSEGV_is_a_crash_even_though_the_wrapper_echoed_FAILED():
    """logs/weekly_wf_promote/2026-06-06.log, verbatim: SIGSEGV in the
    pre-flight smoke test, then "Smoke test FAILED — aborting weekly promote
    (no train)." It matches neither `Traceback` nor `^\\w*Error:`, so the one
    genuine hard crash in the whole corpus read as an ordinary `failed`.

    The wrapper's echo is an ABORT (it never got to Step 3), so it must not
    suppress the crash verdict the way a real decision would."""
    text = _fx("weekly_sigsegv_smoke_abort.log")
    assert "Segmentation fault: 11" in text
    assert not re.search(r"Traceback|^\w*Error:", text, re.M), (
        "the point of this fixture is that it carries NO python-level marker")
    assert S.classify_run(text, _watched("weekly-wf-promote")) == "crashed"


def test_D3_hard_kill_needs_the_signal_number_so_prose_cannot_trip_it():
    """The guard on the guard: bare "Killed"/"Terminated" are ordinary English
    and appear in log prose. A crash marker that fires on prose would re-create
    D2 from the other side."""
    assert not re.search(S.HARD_KILL_RE, "Killed the stale lock holder")
    assert not re.search(S.HARD_KILL_RE, "Terminated cleanly at 04:10")
    assert re.search(S.HARD_KILL_RE, "40470 Segmentation fault: 11  \"$PYTHON\"")
    # measured: logs/retrain_panel/2026-05-03.log:212 — a real SIGTERM death
    assert re.search(S.HARD_KILL_RE,
                     "retrain_panel.sh: line 76: 25446 Terminated: 15  ...")
    assert re.search(S.HARD_KILL_RE, "Segmentation fault (core dumped)")


# ── D4: "Training FAILED" matched nothing and was dropped ───────────────────

def test_D4_a_training_failure_is_a_FAILURE_not_an_undecided_run():
    """logs/weekly_wf_promote/2026-07-31.log, verbatim. Eight runs ended on
    this exact line (07-31, 07-23, 07-17, 07-16, 07-11, 07-10, 07-09, 07-04)
    and matched no pattern at all, so they classified `undecided` and were
    DROPPED from the tally — a defect that SHRINKS the streak the module
    exists to count."""
    text = _fx("weekly_training_failed.log")
    assert "Training FAILED — production artifact unchanged." in text
    assert S.classify_run(text, _watched("weekly-wf-promote")) == "failed"


def test_D4_the_pre_2026_06_training_failure_wording_is_covered_too():
    """logs/weekly_wf_promote/2026-05-17.log used the older phrasing; it is
    still inside the 90-day window."""
    old = ("Training FAILED — prior production artifact still in place "
           "(no overwrite happened).")
    assert re.search(_watched("weekly-wf-promote").failure_re, old, re.M)


def test_D4_undecided_still_exists_for_a_genuinely_unclassifiable_run():
    """Anti-over-correction: widening failure_re must not swallow everything.
    logs/weekly_wf_promote/2026-07-01.log is a hand-written operator note in
    the log directory; it reached no verdict and must stay `undecided`."""
    note = ("=== manual calibrator re-stamp 2026-07-01 ===\n"
            "calibrator hash changed: 833503b782eb -> cab0904424b0\n"
            "=== REJECTED ===\n")
    assert S.classify_run(note, _watched("weekly-wf-promote")) == "undecided"


# ── D1: a delegator's "acted" was only the child's exit code ────────────────

CALM_FRESH_DAY = dt.date(2026, 8, 4)


def _delegating(tmp_path, name, day, delegator_text, child_text):
    """Wire a delegating lane and its child over temp dirs, real patterns."""
    ddir, cdir = tmp_path / "delegator", tmp_path / "child"
    ddir.mkdir(exist_ok=True)
    cdir.mkdir(exist_ok=True)
    (ddir / f"{day.isoformat()}.log").write_text(delegator_text,
                                                 encoding="utf-8")
    if child_text is not None:
        (cdir / f"{day.isoformat()}.log").write_text(child_text,
                                                     encoding="utf-8")
    src = _watched(name).corroborator
    return _lane(name, ddir,
                 corroborator=S.Corroborator(name=src.name, log_dir=str(cdir),
                                             action_re=src.action_re))


@pytest.mark.parametrize("name,fixture", [
    ("conditional-retrain104",
     "conditional_retrain_chain_promoted_synth_from_emitter.log"),
    ("retrain-panel104",
     "retrain_panel_delegated_promoted_synth_from_emitter.log"),
])
def test_D1_a_CALM_FRESH_refusal_must_never_read_as_acted(tmp_path, name,
                                                          fixture):
    """THE defect. weekly_wf_promote.sh:513-520 — a reject while the served
    model is fresh is nominal RFC#210 governance, so since the 2026-08-04
    operator directive it exits 0. Both delegators print their success line
    from `if bash scripts/weekly_wf_promote.sh; then`, i.e. from that exit
    code. The child fixture here is the REAL 2026-08-04 log: gate rejected,
    fallback REFUSED, production unchanged, exit 0.

    One such run classified `acted` clears the entire streak — measured
    2026-08-18, conditional-retrain104 was sitting on 25 non-acting runs."""
    job = _delegating(tmp_path, name, CALM_FRESH_DAY, _fx(fixture),
                      _fx("weekly_calm_fresh_exit0_refusal.log"))
    assert S.classify_run(_fx(fixture), job, day=CALM_FRESH_DAY) == \
        "uncorroborated"


def test_D1_the_child_fixture_is_a_refusal_that_exits_zero():
    """Anti-vacuity for the test above: the corroborating log really is the
    CALM_FRESH shape (a refusal the wrapper reports with exit 0), and the
    weekly lane itself classifies it as a refusal.

    The fixture is the 20:19 run of logs/weekly_wf_promote/2026-08-04.log,
    bounded at its own "started" line. The full dated file holds FOUR runs
    that day (two of them ended on `Training FAILED`, which is why the whole
    file classifies `failed` — day-level granularity, both classes non-acting
    and counted identically)."""
    text = _fx("weekly_calm_fresh_exit0_refusal.log")
    assert "WF gate REJECTED staged model — production unchanged." in text
    assert '"decision": "REFUSE"' in text
    assert "governance nominal, calm notify, exit 0." in text
    assert S.classify_run(text, _watched("weekly-wf-promote")) == "refused"


@pytest.mark.parametrize("name,fixture", [
    ("conditional-retrain104",
     "conditional_retrain_chain_promoted_synth_from_emitter.log"),
    ("retrain-panel104",
     "retrain_panel_delegated_promoted_synth_from_emitter.log"),
])
def test_D1_a_MISSING_child_log_is_its_own_reason_never_acted(tmp_path, name,
                                                              fixture):
    """The exit-2 shape, and the reason it needs a DISTINCT outcome rather
    than being folded into `uncorroborated`: weekly_wf_promote's orch#799
    fail-closed `exit 2` (scripts/weekly_wf_promote.sh:211) fires BEFORE the
    `exec >> "$LOG"` redirect at :235, so the child never opens a dated log at
    all. "The child refused" and "the child left no record" are different
    incidents and the operator has to be able to tell them apart."""
    day = dt.date(2026, 8, 16)
    job = _delegating(tmp_path, name, day, _fx(fixture), None)
    assert S.classify_run(_fx(fixture), job, day=day) == "unwitnessed"


def test_D1_the_exit2_shape_is_real_and_currently_reports_FAIL(tmp_path):
    """logs/retrain_panel/2026-08-16.log, verbatim — the live 2026-08-18 state
    of this lane. The child's pre-redirect stderr lands in the DELEGATOR's log
    (there is no logs/weekly_wf_promote/2026-08-16.log), and the wrapper does
    exit non-zero today, so this run reports FAIL. The corroboration above is
    what keeps it that way if the wrapper ever swallows the exit code."""
    text = _fx("retrain_panel_delegated_fail_exit2.log")
    assert "no PINNED strategy config declares kind=xgb" in text
    assert S.classify_run(text, _watched("retrain-panel104"),
                          day=dt.date(2026, 8, 16)) == "failed"


def test_D1_the_conditional_lane_shows_the_same_exit2_shape(tmp_path):
    """logs/conditional_retrain_104/2026-08-17.log, verbatim — the anomaly
    trigger fired, the chain ran, and the child's pre-redirect stderr landed
    HERE because it never opened its own log. Same wrapper, same date, no
    logs/weekly_wf_promote/2026-08-17.log. Reports FAIL, and must never be
    mistaken for the healthy no-trigger idle."""
    text = _fx("conditional_retrain_chain_failed.log")
    assert "Firing retrain triggers: ['anomaly_vix_5pct']" in text
    assert "no PINNED strategy config declares kind=xgb" in text
    assert S.classify_run(text, _watched("conditional-retrain104"),
                          day=dt.date(2026, 8, 17)) == "failed"


@pytest.mark.parametrize("name,fixture", [
    ("conditional-retrain104",
     "conditional_retrain_chain_promoted_synth_from_emitter.log"),
    ("retrain-panel104",
     "retrain_panel_delegated_promoted_synth_from_emitter.log"),
])
def test_D1_a_GENUINE_promotion_still_clears_the_streak(tmp_path, name,
                                                        fixture):
    """The other half, and the one that keeps the fix from being a rubber
    stamp: when the child really did promote, the delegator's claim stands and
    the streak clears. A corroboration rule nothing can satisfy is just a
    permanent alarm."""
    day = dt.date(2026, 8, 15)
    job = _delegating(tmp_path, name, day, _fx(fixture),
                      _fx("weekly_promoted_synth_from_emitter.log"))
    assert S.classify_run(_fx(fixture), job, day=day) == "acted"
    assert S.check(job, as_of=dt.date(2026, 8, 18)) is None


def test_D1_a_fallback_promotion_also_corroborates():
    """RFC#210 freshness-fallback promotions change the served artifact, so
    they are actions (RenQuant#559 Step 4b). The corroborator uses the CHILD's
    own action pattern, so this holds by construction — pinned because a
    corroborator that only accepted `PASSED` would alarm forever on a lane
    that is promoting every week."""
    c = _watched("retrain-panel104").corroborator
    assert re.search(c.action_re,
                     "=== weekly_wf_promote FALLBACK-PROMOTED (rfc210) at "
                     "Sat Aug 15 — passed=False basis=freshness_fallback ===")


def test_D1_corroborators_use_the_CHILD_LANES_OWN_pattern_not_a_copy():
    """The drift guard. Two hand-copied regexes would silently diverge the
    first time the child's action vocabulary changes, and the delegator would
    go back to clearing on refusals."""
    child = _watched("weekly-wf-promote")
    for name in ("conditional-retrain104", "retrain-panel104"):
        c = _watched(name).corroborator
        assert c is not None, f"{name} delegates its verdict and must be corroborated"
        assert c.name == child.name
        assert c.action_re == child.action_re
        assert c.log_dir == child.log_dir


def test_D1_a_delegator_without_a_date_cannot_be_corroborated_so_is_not_acted():
    """Fail toward alarming: with no date there is no child log to read, and
    an unverifiable success claim must not clear a streak."""
    job = _watched("conditional-retrain104")
    text = _fx("conditional_retrain_chain_promoted_synth_from_emitter.log")
    assert S.classify_run(text, job) == "uncorroborated"


def test_D1_the_new_outcomes_keep_the_streak_alive_and_are_named_in_the_alarm(
        tmp_path):
    """End-to-end: three delegator runs that all CLAIMED success on refusing
    children must still alarm, and the message must say why the claims were
    not believed — an operator who reads "has not acted" about a job whose log
    says "complete" needs the reason in the same sentence."""
    ddir, cdir = tmp_path / "d", tmp_path / "c"
    ddir.mkdir()
    cdir.mkdir()
    claim = _fx("conditional_retrain_chain_promoted_synth_from_emitter.log")
    for day in ("2026-08-04", "2026-08-05"):
        (ddir / f"{day}.log").write_text(claim, encoding="utf-8")
        (cdir / f"{day}.log").write_text(
            _fx("weekly_calm_fresh_exit0_refusal.log"), encoding="utf-8")
    (ddir / "2026-08-06.log").write_text(claim, encoding="utf-8")  # no child log
    src = _watched("conditional-retrain104").corroborator
    job = _lane("conditional-retrain104", ddir,
                corroborator=S.Corroborator(name=src.name, log_dir=str(cdir),
                                            action_re=src.action_re))
    msg = S.check(job, as_of=dt.date(2026, 8, 7))
    assert msg is not None, "three uncleared success claims must alarm"
    assert "2026-08-06:unwitnessed" in msg and "2026-08-05:uncorroborated" in msg
    assert "CLAIMED SUCCESS" in msg
    assert "no promotion" in msg and "no dated log at all" in msg
    assert "weekly-wf-promote" in msg


def test_the_non_acting_vocabulary_is_complete():
    """Anti-drift: a new outcome that nobody added to NON_ACTING would break
    the streak silently — the exact failure class this module is about."""
    assert set(S.NON_ACTING) == {"refused", "failed", "crashed",
                                 "uncorroborated", "unwitnessed"}
    assert "acted" not in S.NON_ACTING and "undecided" not in S.NON_ACTING


def test_the_synthesised_fixtures_render_the_CONTRACTED_emitters():
    """The three `*_synth_from_emitter.log` fixtures assert a success shape
    that has never occurred. They are only legitimate while they render the
    CONTRACTED template — otherwise a D1 test could pass against a success
    line the wrappers do not emit."""
    want = {
        "weekly_promoted_synth_from_emitter.log": "weekly-wf-promote",
        "conditional_retrain_chain_promoted_synth_from_emitter.log":
            "conditional-retrain104",
        "retrain_panel_delegated_promoted_synth_from_emitter.log":
            "retrain-panel104",
    }
    for fixture, job in want.items():
        text = _fx(fixture)
        assert re.search(_watched(job).action_re, text), (fixture, job)
        stems = [row["template"].split("$")[0].strip("= ")
                 for row in _CONTRACT["lines"]
                 if row["job"] == job and row["kind"] == "action"]
        assert stems, f"{job} has no contracted action line"
        assert any(s and s in text for s in stems), (
            f"{fixture} does not render any CONTRACTED action template for "
            f"{job} — re-derive it from ops/renquant104/emitter_contract.json")
