"""Silent-refusal sentinel (GOAL-5 AC5).

The incident these pin: a weekly job that exits 0 every run while declining
to promote anything. Liveness says healthy, the served artifact ages to 622
days, and nothing alarms.
"""
from __future__ import annotations

import datetime as dt
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


def test_crash_marker_outranks_a_refusal_in_the_same_run(tmp_path):
    # measured: the 07-03 run hit CorpusRefreshError, printed
    # "promote: refused", and exited rc=0. It did not choose to decline.
    job = _job(tmp_path, {})
    assert S.classify_run(CRASHED + REFUSED, job) == "crashed"


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
                     "=== Gated WF promote chain FAILED (anomaly_vix_5pct) at Fri ===")
    assert re.search(j.action_re,
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
                     "=== retrain_panel delegated weekly_wf_promote FAIL at Sun ===")
    assert re.search(j.action_re,
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
    ("scripts/conditional_retrain_104.sh", "Gated WF promote chain complete"),
    ("scripts/retrain_panel.sh", "delegated weekly_wf_promote PASS"),
])
def test_action_patterns_are_pinned_to_their_emitter_sources(script, pattern):
    """The doctrine amendment's enforcement: an action pattern read off source instead
    of history must MATCH that source, so a reworded emitter breaks here rather than
    silently blinding the watch. Skips LOUDLY where the umbrella is absent (CI)."""
    src = Path("/Users/renhao/git/github/RenQuant") / script
    if not src.exists():
        pytest.skip(f"{src} absent on this machine — emitter pin not verifiable here")
    assert pattern in src.read_text(errors="ignore"), (
        f"{script} no longer emits '{pattern}' — the watch for it is now blind; "
        f"update the pattern from the CURRENT emitter, do not delete this test")


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
