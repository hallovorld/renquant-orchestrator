"""Staleness must be measured against each job's OWN cadence, and be able to pass.

#621's four dead rq105 jobs had exit codes 0, 0, 0 and 1 — so the existing
exit-code sentinel could not see them. This scan measures elapsed *scheduled firings*
instead. Everything below is hermetic: `now`, the agents directory and both external
commands are injected, so no test depends on this machine's launchd state.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import plistlib
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parent.parent / "ops"
_SPEC = importlib.util.spec_from_file_location(
    "launchd_liveness_scan", OPS / "launchd_liveness_scan.py")
lv = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(lv)

WEEKDAYS_1315 = [{"Weekday": d, "Hour": 13, "Minute": 15} for d in range(1, 6)]


def _plist(dirpath: Path, label: str, **keys) -> Path:
    p = dirpath / f"{label}.plist"
    with p.open("wb") as fh:
        plistlib.dump({"Label": label, **keys}, fh)
    return p


# --- expected_firings: the measurement the whole tool rests on -----------------

def test_a_weekday_schedule_counts_only_weekdays():
    # Mon 2026-07-06 .. Mon 2026-07-13 inclusive of the later fire
    since = dt.datetime(2026, 7, 6, 14, 0)     # just after Monday's 13:15
    until = dt.datetime(2026, 7, 13, 14, 0)    # just after the next Monday's
    # Tue,Wed,Thu,Fri of week 1 + Mon of week 2 = 5
    assert lv.expected_firings(WEEKDAYS_1315, since, until) == 5


def test_a_weekly_job_is_not_stale_after_three_days():
    """The whole point of measuring against the job's own cadence. A fixed
    day-threshold would flag this."""
    weekly = [{"Weekday": 1, "Hour": 4, "Minute": 0}]
    since = dt.datetime(2026, 7, 6, 5, 0)
    assert lv.expected_firings(weekly, since, since + dt.timedelta(days=3)) == 0
    assert lv.expected_firings(weekly, since, since + dt.timedelta(days=8)) == 1


def test_the_interval_is_half_open():
    """A firing exactly at `since` must not be counted (it produced the log we are
    measuring from); one exactly at `until` must be."""
    sched = [{"Hour": 12, "Minute": 0}]
    exact = dt.datetime(2026, 7, 6, 12, 0)
    assert lv.expected_firings(sched, exact, exact + dt.timedelta(hours=1)) == 0
    assert lv.expected_firings(sched, exact - dt.timedelta(hours=1), exact) == 1


def test_sunday_is_accepted_as_both_0_and_7():
    """launchd allows either; treating only one as Sunday would silently mis-count."""
    sunday = dt.datetime(2026, 7, 5, 0, 0)   # a Sunday
    for wd in (0, 7):
        n = lv.expected_firings([{"Weekday": wd, "Hour": 9, "Minute": 0}],
                                sunday, sunday + dt.timedelta(days=1))
        assert n == 1, f"Weekday={wd}"


def test_a_schedule_with_no_weekday_fires_every_day():
    n = lv.expected_firings([{"Hour": 6, "Minute": 30}],
                            dt.datetime(2026, 7, 6, 7, 0),
                            dt.datetime(2026, 7, 13, 7, 0))
    assert n == 7


def test_a_backwards_interval_is_zero_not_negative():
    now = dt.datetime(2026, 7, 6, 12, 0)
    assert lv.expected_firings(WEEKDAYS_1315, now, now - dt.timedelta(days=5)) == 0
    assert lv.expected_firings(WEEKDAYS_1315, now, now) == 0


def test_a_single_dict_schedule_is_normalised():
    assert lv.schedule_entries({"StartCalendarInterval": {"Hour": 1}}) == [{"Hour": 1}]
    assert lv.schedule_entries({}) is None
    assert lv.schedule_entries({"StartCalendarInterval": []}) is None


# --- classification -----------------------------------------------------------

def _scan_one(tmp_path, label="com.renquant.t", now=None, **plist_keys):
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    _plist(agents, label, **plist_keys)
    return lv.scan_job(label, now=now or dt.datetime(2026, 7, 30, 12, 0),
                       agents_dir=agents, launchctl_runner=lambda argv: "")


def test_a_freshly_written_log_is_EVIDENCE_FRESH(tmp_path):
    log = tmp_path / "job.out"
    log.write_text("ran\n")
    import os
    ts = dt.datetime(2026, 7, 30, 6, 30).timestamp()
    os.utime(log, (ts, ts))
    r = _scan_one(tmp_path, StandardOutPath=str(log),
                 StartCalendarInterval=[{"Hour": 6, "Minute": 25}])
    assert r["status"] == lv.EVIDENCE_FRESH
    assert r["missed_firings"] == 0


def test_a_stale_log_is_NO_EVIDENCE_and_reports_the_count(tmp_path):
    log = tmp_path / "job.out"
    log.write_text("")
    import os
    ts = dt.datetime(2026, 7, 2, 13, 45).timestamp()   # #621's shadow-serving date
    os.utime(log, (ts, ts))
    r = _scan_one(tmp_path, StandardOutPath=str(log),
                 StartCalendarInterval=WEEKDAYS_1315)
    assert r["status"] == lv.NO_EVIDENCE_STALE
    assert r["missed_firings"] >= 17, r["missed_firings"]
    assert r["size_bytes"] == 0


def test_the_wording_never_claims_the_job_did_not_run(tmp_path):
    """#621 is explicit that 0-byte stdout does not prove a job did not run. A tool
    that overstates its evidence sends people to fix the wrong thing."""
    log = tmp_path / "job.out"
    log.write_text("")
    import os
    ts = dt.datetime(2026, 6, 1, 13, 45).timestamp()
    os.utime(log, (ts, ts))
    r = _scan_one(tmp_path, StandardOutPath=str(log),
                 StartCalendarInterval=WEEKDAYS_1315)
    assert "does NOT prove" in r["detail"]
    assert "no evidence" in r["detail"].lower()


def test_no_StandardOutPath_is_UNJUDGEABLE_not_fresh(tmp_path):
    """Structurally invisible is worse than stale, and must not read as healthy."""
    r = _scan_one(tmp_path, StartCalendarInterval=WEEKDAYS_1315)
    assert r["status"] == lv.UNJUDGEABLE_NO_LOG_PATH
    assert "can never be judged" in r["detail"]


def test_no_schedule_is_UNJUDGEABLE_not_stale(tmp_path):
    """A KeepAlive job has no cadence. Measuring it against a calendar would be
    validating the wrong object."""
    log = tmp_path / "job.out"
    log.write_text("x")
    r = _scan_one(tmp_path, StandardOutPath=str(log), KeepAlive=True)
    assert r["status"] == lv.UNJUDGEABLE_NO_SCHEDULE
    assert "cadence undefined" in r["detail"]


def test_an_absent_log_file_is_NO_EVIDENCE(tmp_path):
    r = _scan_one(tmp_path, StandardOutPath=str(tmp_path / "never-written.out"),
                 StartCalendarInterval=WEEKDAYS_1315)
    assert r["status"] == lv.NO_EVIDENCE_STALE
    assert "absent" in r["detail"]


def test_a_manifested_job_with_no_plist_is_UNJUDGEABLE(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    r = lv.scan_job("com.renquant.ghost", now=dt.datetime(2026, 7, 30),
                    agents_dir=agents, launchctl_runner=lambda argv: "")
    assert r["status"] == lv.UNJUDGEABLE_NO_PLIST


# --- the plist loader must read what LAUNCHD reads ----------------------------

def test_a_plist_with_dashes_in_a_comment_loads_via_the_plutil_fallback(tmp_path):
    """THE REGRESSION. `--` inside an XML comment is illegal to expat but fine for
    Apple's parser, and two real plists carry a `---` prose underline. Classifying
    them as malformed would have been a FALSE finding sending someone to fix files
    that are not broken."""
    good = {"Label": "x", "StandardOutPath": "/tmp/x.out"}
    body = plistlib.dumps(good).decode()
    with_comment = body.replace(
        "<dict>", "<dict>\n  <!-- WHY THIS EXISTS\n  --------------- -->", 1)
    p = tmp_path / "c.plist"
    p.write_text(with_comment)

    with pytest.raises(Exception):
        with p.open("rb") as fh:
            plistlib.load(fh)          # expat refuses

    loaded = lv.load_plist(p, plutil_runner=lambda argv: plistlib.dumps(good))
    assert loaded["StandardOutPath"] == "/tmp/x.out"


def test_a_genuinely_unreadable_plist_still_raises(tmp_path):
    """Negative case: the fallback must not paper over a real failure."""
    p = tmp_path / "bad.plist"
    p.write_text("this is not a plist at all")
    with pytest.raises(Exception):
        lv.load_plist(p, plutil_runner=lambda argv: b"")


# --- launchd's exit status is not an exit code --------------------------------

@pytest.mark.parametrize("raw,code", [(0, 0), (256, 1), (512, 2), (768, 3)])
def test_launchd_status_is_decoded(raw, code):
    assert lv.decode_launchd_status(raw)["exit_code"] == code


def test_a_signal_is_reported_separately():
    d = lv.decode_launchd_status(9)
    assert d["signal"] == 9 and d["exit_code"] == 0


def test_no_status_available_decodes_to_None():
    assert lv.decode_launchd_status(None)["exit_code"] is None


# --- exit codes and read-only contract ---------------------------------------

def test_an_unreadable_manifest_exits_2(tmp_path):
    assert lv.main(["--manifest", str(tmp_path / "nope.json")]) == 2


def test_a_manifest_with_no_jobs_exits_2(tmp_path):
    p = tmp_path / "m.json"
    p.write_text("[]")
    assert lv.main(["--manifest", str(p)]) == 2


def test_manifest_labels_handles_the_pair_list_shape(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps([["com.renquant.a", {"program_args": []}],
                             ["com.renquant.b", {"program_args": []}]]))
    assert lv.manifest_labels(p) == ["com.renquant.a", "com.renquant.b"]


def test_the_scan_does_not_modify_a_log_it_reads(tmp_path):
    log = tmp_path / "job.out"
    log.write_text("payload")
    before = (log.read_bytes(), log.stat().st_mtime)
    _scan_one(tmp_path, StandardOutPath=str(log),
             StartCalendarInterval=WEEKDAYS_1315)
    assert (log.read_bytes(), log.stat().st_mtime) == before
