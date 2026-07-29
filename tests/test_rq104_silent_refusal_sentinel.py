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
    assert "2026-07-11:failed" in msg


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
    assert "2026-07-18:refused" in msg and "2026-07-11:failed" in msg


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
    assert S.classify_run(CRASHED + REFUSED, job) == "failed"


def test_corpus_refresh_error_is_recognised_without_a_traceback(tmp_path):
    job = _job(tmp_path, {})
    assert S.classify_run("CorpusRefreshError: sidecar rejected\n", job) == "failed"


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


def test_registry_watches_the_job_from_the_incident():
    names = {j.name for j in S.WATCHED}
    assert "weekly-retrain-patchtst" in names, (
        "the job whose months-long silent refusal motivated this sentinel "
        "must be in the registry"
    )


@pytest.mark.parametrize("text,expected", [
    (REFUSED, "refused"),
    (ACTED, "acted"),
    (CRASHED, "failed"),
    ("", "undecided"),
])
def test_classify_run(text, expected, tmp_path):
    job = _job(tmp_path, {})
    assert S.classify_run(text, job) == expected
