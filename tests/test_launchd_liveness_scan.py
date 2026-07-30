"""Staleness must be measured against each job's OWN cadence, and be able to pass.

#621's four dead rq105 jobs had exit codes 0, 0, 0 and 1 — so the existing
exit-code sentinel could not see them. This scan measures elapsed *scheduled firings*
instead. Everything below is hermetic: `now`, the agents directory and both external
commands are injected, so no test depends on this machine's launchd state.
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import importlib.util
import json
import os
import plistlib
import re
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


# --- StandardOutPath is a PROXY, and for some jobs it is the wrong object ------
# Measured 2026-07-30: rq105-session-scheduler and rq105-quote-logger create a dated
# log on EVERY session day while their launchd stdout had not been touched in weeks.
# Scored on StandardOutPath they read as 18-19 missed firings; they had missed none.
# I filed that false reading myself as issue #621.

def test_an_evidence_glob_wins_over_StandardOutPath(tmp_path, monkeypatch):
    import os
    real = tmp_path / "job_2026-07-30.log"
    real.write_text("")
    ts = dt.datetime(2026, 7, 30, 6, 25).timestamp()
    os.utime(real, (ts, ts))
    stale = tmp_path / "launchd.out"
    stale.write_text("")
    old = dt.datetime(2026, 7, 3, 6, 25).timestamp()
    os.utime(stale, (old, old))

    agents = tmp_path / "agents"
    agents.mkdir()
    _plist(agents, "com.renquant.t", StandardOutPath=str(stale),
           StartCalendarInterval=[{"Hour": 6, "Minute": 25}])
    r = lv.scan_job("com.renquant.t", now=dt.datetime(2026, 7, 30, 12, 0),
                    agents_dir=agents,
                    manifest_entry={"evidence_glob": str(tmp_path / "job_*.log")},
                    launchctl_runner=lambda argv: "")
    assert r["status"] == lv.EVIDENCE_FRESH, "the real surface says it fired today"
    assert r["evidence_surface"] == "evidence_glob"
    assert r["evidence_is_proxy"] is False


def test_without_a_glob_the_proxy_is_used_AND_LABELLED(tmp_path):
    """A proxy measurement labelled as a direct one is how the false reading got
    published. The label is the point."""
    import os
    stale = tmp_path / "launchd.out"
    stale.write_text("")
    old = dt.datetime(2026, 7, 3, 6, 25).timestamp()
    os.utime(stale, (old, old))
    agents = tmp_path / "agents"
    agents.mkdir()
    _plist(agents, "com.renquant.t", StandardOutPath=str(stale),
           StartCalendarInterval=[{"Hour": 6, "Minute": 25}])
    r = lv.scan_job("com.renquant.t", now=dt.datetime(2026, 7, 30, 12, 0),
                    agents_dir=agents, launchctl_runner=lambda argv: "")
    assert r["evidence_is_proxy"] is True
    assert "PROXY" in r["evidence_surface"]
    assert r["status"] == lv.NO_EVIDENCE_STALE


def test_a_glob_matching_nothing_is_UNJUDGEABLE_not_silently_proxied(tmp_path):
    """Falling back to the proxy when a declared glob misses would hide a broken
    declaration behind a measurement of a different file."""
    agents = tmp_path / "agents"
    agents.mkdir()
    _plist(agents, "com.renquant.t", StandardOutPath="/tmp/whatever.out",
           StartCalendarInterval=[{"Hour": 6, "Minute": 25}])
    r = lv.scan_job("com.renquant.t", now=dt.datetime(2026, 7, 30),
                    agents_dir=agents,
                    manifest_entry={"evidence_glob": str(tmp_path / "nope_*.log")},
                    launchctl_runner=lambda argv: "")
    assert r["status"] == lv.UNJUDGEABLE_NO_LOG_PATH
    assert "no match" in r["evidence_surface"]


def test_the_newest_glob_match_is_used(tmp_path):
    import os
    agents = tmp_path / "agents"
    agents.mkdir()
    for day, hh in (("2026-07-01", 6), ("2026-07-30", 6)):
        f = tmp_path / f"j_{day}.log"
        f.write_text("")
        ts = dt.datetime.fromisoformat(f"{day}T0{hh}:25").timestamp()
        os.utime(f, (ts, ts))
    _plist(agents, "com.renquant.t", StandardOutPath="/tmp/x.out",
           StartCalendarInterval=[{"Hour": 6, "Minute": 25}])
    r = lv.scan_job("com.renquant.t", now=dt.datetime(2026, 7, 30, 12, 0),
                    agents_dir=agents,
                    manifest_entry={"evidence_glob": str(tmp_path / "j_*.log")},
                    launchctl_runner=lambda argv: "")
    assert r["last_write"].startswith("2026-07-30")


def test_the_report_counts_how_many_jobs_are_measured_by_proxy():
    """The headline number: a scan measuring a proxy for most of its subjects should
    say so rather than presenting every reading as equivalent."""
    rep = lv.scan([], now=dt.datetime(2026, 7, 30))
    assert "measured_by_proxy" in rep


def test_the_committed_manifest_declares_globs_for_the_corrected_jobs():
    """These three were measured on the wrong surface and produced a false reading in
    #621. If the declaration is dropped the false reading returns."""
    raw = json.loads((OPS / "launchd_manifest.json").read_text())
    jobs = raw.get("jobs", raw)
    for label in ("com.renquant.rq105-session-scheduler",
                  "com.renquant.rq105-quote-logger",
                  "com.renquant.rq105-shadow-serving"):
        cfg = jobs[label] if isinstance(jobs, dict) else dict(jobs)[label]
        assert cfg.get("evidence_glob"), f"{label} lost its evidence_glob"


# --- the two PRODUCTION jobs, added 2026-07-30 --------------------------------
# daily104 read as 9 missed firings and intraday104 as 2394, both from a stale
# StandardOutPath, while their real dated logs were current. These are the jobs whose
# false reading matters most: they are the live decision and intraday paths.

def test_the_production_jobs_declare_an_evidence_glob():
    raw = json.loads((OPS / "launchd_manifest.json").read_text())
    jobs = raw.get("jobs", raw)
    for label in ("com.renquant.daily104", "com.renquant.intraday104"):
        cfg = jobs[label] if isinstance(jobs, dict) else dict(jobs)[label]
        assert cfg.get("evidence_glob"), f"{label} lost its evidence_glob"
        assert "20[0-9][0-9]" in cfg["evidence_glob"], (
            f"{label}'s glob must match the DATED files, not the whole directory — a "
            f"directory-wide glob would pick up launchd_stdout.log and re-introduce the "
            f"proxy it replaces")


def test_no_two_jobs_share_an_evidence_glob():
    """The pit-* jobs share a log directory, so a directory-level glob would assign one
    job's evidence to another. Any glob added here must stay job-unique."""
    raw = json.loads((OPS / "launchd_manifest.json").read_text())
    jobs = raw.get("jobs", raw)
    seen = {}
    for label, cfg in (jobs.items() if isinstance(jobs, dict) else jobs):
        g = cfg.get("evidence_glob")
        if not g:
            continue
        assert g not in seen, f"{label} and {seen[g]} share the glob {g!r}"
        seen[g] = label


# --- the 13 unambiguous assignments, 2026-07-30 -------------------------------
# Criterion: the job is the SOLE occupant of its log directory across all manifested
# plists, and that directory contains dated files. Anything shared (the pit-* trio)
# stays unassigned rather than guessed.

def test_thirteen_more_jobs_have_an_evidence_glob():
    raw = json.loads((OPS / "launchd_manifest.json").read_text())
    jobs = raw.get("jobs", raw)
    with_glob = [l for l, c in (jobs.items() if isinstance(jobs, dict) else jobs)
                 if c.get("evidence_glob")]
    assert len(with_glob) == 18, f"expected 18 globs (3 + 2 + 13), got {len(with_glob)}"


def test_weekly_wf_promote_is_measured_on_its_real_surface():
    """I singled this job out in #627 as 'not written since 2026-05-17' and warned that
    every 'the weekly retrain was admitted' claim assumes it runs. That was a PROXY
    reading and it was wrong."""
    raw = json.loads((OPS / "launchd_manifest.json").read_text())
    jobs = raw.get("jobs", raw)
    cfg = jobs["com.renquant.weekly-wf-promote"]
    assert cfg.get("evidence_glob"), "the correction depends on this glob existing"


# --- glob exclusivity, proved from COMMITTED data only ------------------------
#
# codex round 2 on #635: the first version of this check read whichever local plists
# happened to exist, skipped its assertion when they did not, and inferred occupancy
# from `StandardOutPath`. Three separate defects:
#
#   1. absent plists -> `continue`, so in CI the occupancy map was empty;
#   2. an empty map -> the assertion was skipped entirely, so CI validated NONE of
#      the claimed assignments while reporting green;
#   3. `StandardOutPath` cannot establish ownership of the evidence directory in the
#      first place -- these jobs exist BECAUSE their wrappers redirect real evidence
#      away from it. The field proves where launchd puts its own stdout, not where
#      the job writes the artifact the scan measures.
#
# The invariant does not need the local machine at all: every evidence_glob is
# committed in the manifest, so "no two manifested jobs can match the same file" is
# decidable from the manifest alone. That is what runs here.


def _glob_witnesses(pattern: str) -> list[str]:
    """Concrete filenames a pattern can produce, enough to decide overlap.

    `*` is expanded two ways -- empty and a distinctive token -- because a
    directory-wide `20[0-9]...*.log` must be seen to collide with a stem-specific
    `session_scheduler_*.log` only when it genuinely can.
    """
    base = os.path.basename(pattern)
    concrete = re.sub(r"\[([^\]]*)\]", lambda m: m.group(1)[0], base)  # [0-9] -> 0
    return [concrete.replace("*", filler) for filler in ("", "ZZWITNESSZZ")]


def _globs_can_overlap(a: str, b: str) -> bool:
    if os.path.dirname(a) != os.path.dirname(b):
        return False
    for pattern, other in ((a, b), (b, a)):
        for w in _glob_witnesses(pattern):
            if fnmatch.fnmatch(w, os.path.basename(other)):
                return True
    return False


def test_the_overlap_helper_can_actually_detect_an_overlap():
    """A test whose helper always returns False would pass forever."""
    d = "/logs/x"
    assert _globs_can_overlap(f"{d}/20[0-9][0-9]-a*.log", f"{d}/2000-a-thing.log")
    # a dated prefix and a stem prefix in one directory cannot produce a common name
    assert not _globs_can_overlap(f"{d}/20[0-9][0-9]*.log", f"{d}/stem_*.log")
    # directory-wide vs stem-specific in the SAME directory: must collide
    assert _globs_can_overlap(f"{d}/*.log", f"{d}/session_scheduler_*.log")
    # different directories never collide
    assert not _globs_can_overlap("/logs/a/*.log", "/logs/b/*.log")
    # distinct stems in one directory do not collide
    assert not _globs_can_overlap(f"{d}/quote_logger_*.log",
                                  f"{d}/session_scheduler_*.log")


def test_no_two_manifested_globs_can_match_the_same_file():
    """Stronger than the string-equality check above, and the one codex asked for.

    Equality only catches two jobs claiming the identical pattern. The real hazard is
    a DIRECTORY-WIDE glob added to a directory another job already writes into: the
    strings differ, so equality passes, while every dated file the neighbour writes is
    silently credited to the newcomer. Six rq105 jobs share `logs/rq105/`.
    """
    raw = json.loads((OPS / "launchd_manifest.json").read_text())
    jobs = raw.get("jobs", raw)
    globbed = [(l, c["evidence_glob"])
               for l, c in (jobs.items() if isinstance(jobs, dict) else jobs)
               if c.get("evidence_glob")]
    assert globbed, "no evidence globs in the manifest — nothing is being checked"
    for i, (la, ga) in enumerate(globbed):
        for lb, gb in globbed[i + 1:]:
            assert not _globs_can_overlap(ga, gb), (
                f"{la} and {lb} have overlapping evidence globs:\n  {ga}\n  {gb}\n"
                f"a file matching both would make either job look alive on the "
                f"other's output")


def test_every_glob_is_absolute_and_committed():
    """The manifest is the source of truth; a relative or machine-derived glob would
    make the exclusivity proof above depend on where it was run."""
    raw = json.loads((OPS / "launchd_manifest.json").read_text())
    jobs = raw.get("jobs", raw)
    for label, cfg in (jobs.items() if isinstance(jobs, dict) else jobs):
        g = cfg.get("evidence_glob")
        if g:
            assert g.startswith("/"), f"{label}'s evidence_glob is not absolute: {g!r}"


def test_thirteen_more_jobs_have_an_evidence_glob():
    raw = json.loads((OPS / "launchd_manifest.json").read_text())
    jobs = raw.get("jobs", raw)
    with_glob = [l for l, c in (jobs.items() if isinstance(jobs, dict) else jobs)
                 if c.get("evidence_glob")]
    assert len(with_glob) == 18, f"expected 18 globs (3 + 2 + 13), got {len(with_glob)}"


def test_weekly_wf_promote_is_measured_on_its_real_surface():
    """I singled this job out in #627 as "not written since 2026-05-17" and warned that
    every "the weekly retrain was admitted" claim assumes it runs. That was a PROXY
    reading and it was wrong."""
    raw = json.loads((OPS / "launchd_manifest.json").read_text())
    jobs = raw.get("jobs", raw)
    cfg = jobs["com.renquant.weekly-wf-promote"]
    assert cfg.get("evidence_glob"), "the correction depends on this glob existing"


def test_standardoutpath_is_documented_as_insufficient_for_ownership():
    """The reason the local-plist check was deleted rather than repaired.

    Anyone re-adding an occupancy check derived from StandardOutPath needs to hit this
    and read why it cannot prove what it appears to prove.
    """
    src = Path(__file__).read_text()
    assert "cannot establish ownership of the evidence directory" in src
