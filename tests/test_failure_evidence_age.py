"""A failing job's alarm must say HOW OLD the failure is.

Operator report 2026-08-05: *"the issue has been repeatedly showing up for
months! fix fundamentally asap!"*

`launchctl` retains a job's last exit code until its NEXT run. A job that stops
firing therefore keeps re-alarming with a code from the run that last happened,
every day, forever — and the row read **identically** whether the failure was
from last night or from April. Nothing in the alarm could tell the reader that
the SCHEDULE died rather than the check.

Measured on the live fleet the day this was written: of the 14 undispositioned
failing jobs, five had produced no output on either stream for 101, 80, 65, 34
and 33 days, and each of those last writes lands exactly on that job's own
scheduled slot (`retrain-panel104` is weekly Sun 10:00 and last wrote Sun
2026-04-26 10:00).

Every test here builds its own plist and log files under `tmp_path`, so none of
them can pass merely because of what happens to be installed on the box that
runs them.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import os
import plistlib
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "ops", "renquant104", "rq104_degradation_sentinel.py")

TODAY = dt.date(2026, 8, 5)


def _load():
    d = os.path.dirname(MOD)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("rq104_degradation_sentinel", MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = _load()


def _job(tmp_path, label, *, wrote_days_ago: int | None,
         stderr_days_ago: int | None = None):
    """Write a plist naming real log files, aged to order. Returns the plist dir."""
    out = tmp_path / f"{label}.out"
    err = tmp_path / f"{label}.err"
    out.write_text("", encoding="utf-8")
    err.write_text("", encoding="utf-8")
    for path, ago in ((out, wrote_days_ago), (err, stderr_days_ago)):
        if ago is None:
            path.unlink()
            continue
        when = dt.datetime.combine(
            TODAY - dt.timedelta(days=ago), dt.time(10, 0)).timestamp()
        os.utime(path, (when, when))
    plist_dir = tmp_path / "agents"
    plist_dir.mkdir(exist_ok=True)
    with open(plist_dir / f"{label}.plist", "wb") as fh:
        plistlib.dump({"Label": label,
                       "StandardOutPath": str(out),
                       "StandardErrorPath": str(err)}, fh)
    return plist_dir


class TestTheAgeIsMeasuredNotAssumed:

    def test_a_failure_from_101_days_ago_is_reported_as_a_FOSSIL(self, tmp_path):
        """The real `retrain-panel104` shape: weekly job, last wrote 2026-04-26,
        still alarming daily 101 days later."""
        d = _job(tmp_path, "com.renquant.retrain-panel104", wrote_days_ago=101)

        row = S.annotate_with_evidence_age(
            "com.renquant.retrain-panel104 exit=1", TODAY, d)

        assert "FOSSIL" in row
        assert "101d" in row
        assert "2026-04-26" in row
        # the row has to redirect the reader, not just label the age
        assert "still FIRES" in row or "still fires" in row.lower()

    def test_a_failure_from_last_night_is_NOT_a_fossil(self, tmp_path):
        """Anti-false-positive: crying 'fossil' on a live failure would teach the
        reader to ignore the label exactly when it matters."""
        d = _job(tmp_path, "com.renquant.ops-audit", wrote_days_ago=1)

        row = S.annotate_with_evidence_age("com.renquant.ops-audit exit=1", TODAY, d)

        assert "FOSSIL" not in row
        assert "1d ago" in row

    def test_the_boundary_belongs_to_the_fossil_side(self, tmp_path):
        """At exactly FOSSIL_AFTER_DAYS a weekly job has skipped a full slot."""
        d = _job(tmp_path, "com.renquant.x", wrote_days_ago=S.FOSSIL_AFTER_DAYS)

        assert "FOSSIL" in S.annotate_with_evidence_age("com.renquant.x exit=1", TODAY, d)

    def test_the_NEWER_of_the_two_streams_wins(self, tmp_path):
        """stderr staying quiet while stdout is written every night does not make
        the job stale — 'no output' means neither stream."""
        d = _job(tmp_path, "com.renquant.y", wrote_days_ago=2, stderr_days_ago=90)

        row = S.annotate_with_evidence_age("com.renquant.y exit=1", TODAY, d)

        assert "FOSSIL" not in row
        assert "2d ago" in row


class TestUnknownIsItsOwnAnswer:
    """could-not-check is not checked-and-found-recent. An unreadable plist must
    never render as a fresh failure, which is the direction that loses evidence."""

    def test_a_MISSING_plist_reports_the_age_as_unknown(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()

        row = S.annotate_with_evidence_age("com.renquant.gone exit=1", TODAY, agents)

        assert "UNKNOWN" in row
        assert "FOSSIL" not in row      # nor may it be silently promoted

    def test_a_plist_with_NO_log_paths_reports_unknown(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        with open(agents / "com.renquant.z.plist", "wb") as fh:
            plistlib.dump({"Label": "com.renquant.z"}, fh)

        assert "UNKNOWN" in S.annotate_with_evidence_age(
            "com.renquant.z exit=1", TODAY, agents)

    def test_a_CORRUPT_plist_does_not_crash_the_sentinel(self, tmp_path):
        """A monitoring tool must degrade, never abort — the sentinel is the thing
        that would otherwise report the whole fleet as healthy by dying."""
        agents = tmp_path / "agents"
        agents.mkdir()
        (agents / "com.renquant.bad.plist").write_bytes(b"\x00\x01not a plist")

        assert S.evidence_age_days("com.renquant.bad", TODAY, agents) == (None, None)


class TestItReachesTheALARMText:
    """A measurement the page does not carry is worth nothing —
    `deployed-but-dark`. The annotation must appear in the row the operator is
    actually sent, not only in a helper."""

    def test_the_launchd_alarm_line_carries_the_age(self, tmp_path, monkeypatch):
        d = _job(tmp_path, "com.renquant.retrain-panel104", wrote_days_ago=101)
        monkeypatch.setattr(S, "parse_launchctl_failures",
                            lambda out: ["com.renquant.retrain-panel104 exit=1"])
        monkeypatch.setattr(S, "load_acks", lambda *a, **k: {})

        class _Done:
            stdout = ""
        monkeypatch.setattr(S.subprocess, "run", lambda *a, **k: _Done())

        alarm, infos = S.check_launchd_exits(TODAY, d)

        assert alarm is not None
        assert "FOSSIL" in alarm and "101d" in alarm
