"""orch#1085 — rq105 liveness covers the SERVING CHAIN, and the calendar-only
jobs catch up after a boot.

Incident (2026-08-28, all paths [VERIFIED] read-only on 2026-08-29): the host
booted 10:38 local; launchd never fired the 06:15 batch-score export or the
06:25 scheduler (a StartCalendarInterval slot missed across a boot is not
backfilled); ``data/rq105/batch_scores_2026-08-28.{json,meta.json}`` were never
written; ``logs/rq105/shadow_serving_2026-08-28.log`` was one line —
``SKIP upstream: no frozen batch-score export`` — and
``shadow_realtime_serving.jsonl``'s last ``session_date`` stayed 2026-08-27.
``rq105_liveness_check.py`` printed ``rq105 liveness OK 2026-08-28`` because it
looked only at the three tick collectors.

The first test reconstructs that filesystem state in tmp_path and asserts the
check now FAILS with ``export_missing`` (and ``serving_noop``) through the same
alert path as a dead collector. The rest pin the green day, the DISARMED
scheduler (expected dark, named in the OK line), the ARMED-but-dark scheduler,
the path literals against their wrappers/resolvers, the shell catch-up guard,
and the reviewed RunAtLoad surface.
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "ops"))
sys.path.insert(0, str(ROOT / "ops" / "renquant105"))

import rq105_liveness_check as liveness  # noqa: E402

OPS = ROOT / "ops" / "renquant105"
INCIDENT_DAY = dt.date(2026, 8, 28)
INCIDENT_ISO = "2026-08-28"
# The literal first (and only) line of shadow_serving_2026-08-28.log.
INCIDENT_SKIP_LINE = (
    "2026-08-28T20:45:05Z SKIP upstream: no frozen batch-score export "
    "(/Users/renhao/git/github/RenQuant/data/rq105/batch_scores_2026-08-28.json / "
    "/Users/renhao/git/github/RenQuant/data/rq105/batch_scores_2026-08-28.meta.json missing)"
)


# ---------------------------------------------------------------------------
# fixture builder: an RQ root under tmp_path
# ---------------------------------------------------------------------------
def _fake_send(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def send(title, body, topic=None, *, priority=None, tags=None, timeout=5.0, env_file=None):
        calls.append({"title": title, "body": body, "priority": priority, "tags": tags})
        return True

    mod = types.ModuleType("renquant_common.notify")
    mod.send = send
    monkeypatch.setitem(sys.modules, "renquant_common.notify", mod)
    return calls


class Root:
    """Builds the on-disk state the check reads, rooted at tmp_path."""

    def __init__(self, tmp_path: Path, monkeypatch, day: dt.date = INCIDENT_DAY):
        self.rq = tmp_path / "RenQuant"
        self.day = day
        self.iso = day.isoformat()
        self.logs = self.rq / "logs" / "rq105"
        self.pilot = self.rq / "logs" / "renquant105_pilot"
        self.data = self.rq / "data" / "rq105"
        for d in (self.logs, self.pilot, self.data):
            d.mkdir(parents=True)
        monkeypatch.setattr(liveness, "RQ", str(self.rq))
        monkeypatch.setattr(liveness, "LOGS", str(self.logs))
        monkeypatch.setattr(liveness, "_is_session_day", lambda d: True)
        # The three tick collectors have their own test files; hold them green
        # here so every verdict below is the serving chain's alone.
        monkeypatch.setattr(liveness, "check_collector_data_outputs", lambda root, as_of: {})
        for mod in liveness._WRAPPER_LOGS:
            (self.logs / f"{mod}_{self.iso}.log").write_text("")

    # -- export bundle -------------------------------------------------------
    def bundle(self, session_date: str | None = None) -> "Root":
        sd = session_date or self.iso
        (self.data / f"batch_scores_{self.iso}.json").write_text(json.dumps({"AAPL": 0.7}))
        (self.data / f"batch_scores_{self.iso}.meta.json").write_text(json.dumps({
            "run_id": "run-x", "session_date": sd, "source_run_date": "2026-08-27",
            "score_content_sha256": "deadbeef", "n": 1}))
        (self.logs / f"batch_scores_export_{self.iso}.log").write_text("exported 1/1\n")
        return self

    # -- shadow serving ------------------------------------------------------
    def serving(self, *, rows_for: tuple[str, ...] = (), log_first_line: str | None = None) -> "Root":
        first = log_first_line if log_first_line is not None else \
            "[OBSERVE-ONLY] renquant105 Stage-1 shadow real-time serving"
        (self.logs / f"shadow_serving_{self.iso}.log").write_text(first + "\n  as_of: x\n")
        with open(self.pilot / "shadow_realtime_serving.jsonl", "a", encoding="utf-8") as fh:
            for sd in rows_for:
                for t in ("AAPL", "MSFT"):
                    fh.write(json.dumps({
                        "schema_version": "v1", "record_kind": "shadow_realtime_score",
                        "session_date": sd, "ticker": t, "as_of": f"{sd}T10:00:00-04:00",
                        "batch_score": 0.5, "shadow_score": 0.6}) + "\n")
        return self

    def serving_skipped_upstream(self) -> "Root":
        (self.logs / f"shadow_serving_{self.iso}.log").write_text(INCIDENT_SKIP_LINE + "\n")
        return self

    # -- scheduler -----------------------------------------------------------
    def scheduler_rows(self, *session_dates: str, kind: str = "intraday_decision_shadow_tick") -> "Root":
        with open(self.pilot / "intraday_decisions_shadow.jsonl", "a", encoding="utf-8") as fh:
            for sd in session_dates:
                for i in range(3):
                    fh.write(json.dumps({
                        "schema_version": "rq105-intraday-shadow-v1", "kind": kind,
                        "session_date": sd, "tick_index": i, "live_state": {}}) + "\n")
        return self

    def armed(self, payload: dict | str | None = None) -> "Root":
        p = self.data / "intraday_decisioning.armed.json"
        if payload is None:
            payload = {"armed": True, "operator": "op", "armed_at": "2026-08-27T13:00:00Z",
                       "authority": "S3-c #1044"}
        p.write_text(payload if isinstance(payload, str) else json.dumps(payload))
        return self


def _codes(calls: list[dict]) -> set[str]:
    return {ln.split(":")[0] for ln in calls[0]["body"].splitlines()
            if ln.split(":")[0] in {liveness.FAIL_EXPORT_MISSING, liveness.FAIL_SERVING_NOOP,
                                    liveness.FAIL_SCHEDULER_DARK, liveness.FAIL_ARMING_INVALID}}


# ---------------------------------------------------------------------------
# 1. the 2026-08-28 state now FAILS
# ---------------------------------------------------------------------------
def test_the_08_28_state_fails_export_missing(tmp_path, monkeypatch, capsys):
    """Reconstruct 08-28: tick collectors fine (their logs present), NO bundle,
    NO export wrapper log (launchd never fired), serving log = the one SKIP
    upstream line, serving jsonl last row 08-27, scheduler jsonl last row
    08-26, arming file ABSENT. Old check: OK. New check: rc=1, urgent alert,
    export_missing + serving_noop; the disarmed scheduler is NOT a failure."""
    calls = _fake_send(monkeypatch)
    r = Root(tmp_path, monkeypatch)
    r.serving_skipped_upstream()
    with open(r.pilot / "shadow_realtime_serving.jsonl", "w") as fh:
        fh.write(json.dumps({"record_kind": "shadow_realtime_score", "session_date": "2026-08-27",
                             "ticker": "AAPL"}) + "\n")
    r.scheduler_rows("2026-08-26")

    rc = liveness.main(INCIDENT_DAY)

    assert rc == 1
    assert len(calls) == 1
    assert calls[0]["title"].startswith("🚨") and "DOWN" in calls[0]["title"]
    assert calls[0]["priority"] == "urgent"
    assert _codes(calls) == {liveness.FAIL_EXPORT_MISSING, liveness.FAIL_SERVING_NOOP}
    body = calls[0]["body"]
    assert f"batch_scores_{INCIDENT_ISO}.json" in body
    assert "wrapper log ABSENT" in body, "the boot-missed-slot diagnosis must be in the page"
    assert "SKIP upstream" in body
    assert "scheduler: [scheduler DISARMED: arming file absent" in body
    out = capsys.readouterr().out
    assert "rq105 liveness OK" not in out


def test_export_missing_is_the_verdict_even_when_serving_somehow_has_rows(tmp_path, monkeypatch):
    """The comparison that would have failed on 08-28 is meta.session_date ==
    today. A stale bundle re-stamped from another day is export_missing too."""
    calls = _fake_send(monkeypatch)
    r = Root(tmp_path, monkeypatch).bundle(session_date="2026-08-27").serving(rows_for=(INCIDENT_ISO,))
    assert liveness.main(INCIDENT_DAY) == 1
    assert _codes(calls) == {liveness.FAIL_EXPORT_MISSING}
    assert "session_date='2026-08-27' != '2026-08-28'" in calls[0]["body"]


# ---------------------------------------------------------------------------
# 2. green day
# ---------------------------------------------------------------------------
def test_green_day_disarmed_prints_ok_with_scheduler_state_named(tmp_path, monkeypatch, capsys):
    calls = _fake_send(monkeypatch)
    Root(tmp_path, monkeypatch).bundle().serving(rows_for=("2026-08-27", INCIDENT_ISO))
    rc = liveness.main(INCIDENT_DAY)
    assert rc == 0
    assert calls == []
    out = capsys.readouterr().out.strip()
    assert out.startswith(f"rq105 liveness OK {INCIDENT_ISO} [scheduler DISARMED: arming file absent"), out


def test_explicit_armed_false_is_disarmed_not_invalid(tmp_path, monkeypatch, capsys):
    """rq105_arming documents two disarm paths: delete the file, or set
    "armed": false. Both are EXPECTED dark, named in the OK line."""
    calls = _fake_send(monkeypatch)
    Root(tmp_path, monkeypatch).bundle().serving(rows_for=(INCIDENT_ISO,)).armed(
        {"armed": False, "operator": "op", "armed_at": "x", "authority": "y"})
    assert liveness.main(INCIDENT_DAY) == 0
    assert calls == []
    assert '[scheduler DISARMED: arming file present with "armed": false' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 3. serving no-op shapes
# ---------------------------------------------------------------------------
def test_serving_log_present_but_no_row_for_today_is_serving_noop(tmp_path, monkeypatch):
    """A producer refusal (rc=4) or a serving crash writes a log whose first
    line is NOT 'SKIP upstream' and appends no rows: the row is load-bearing."""
    calls = _fake_send(monkeypatch)
    Root(tmp_path, monkeypatch).bundle().serving(
        rows_for=("2026-08-27",),
        log_first_line="2026-08-28T20:45:05Z SKIP producer-refused (rc=3): snapshot not produced")
    assert liveness.main(INCIDENT_DAY) == 1
    assert _codes(calls) == {liveness.FAIL_SERVING_NOOP}
    assert "last session_date in tail='2026-08-27'" in calls[0]["body"]


def test_serving_log_missing_is_serving_noop(tmp_path, monkeypatch):
    calls = _fake_send(monkeypatch)
    Root(tmp_path, monkeypatch).bundle()
    assert liveness.main(INCIDENT_DAY) == 1
    assert _codes(calls) == {liveness.FAIL_SERVING_NOOP}
    assert "never fired" in calls[0]["body"]


# ---------------------------------------------------------------------------
# 4. scheduler: armed
# ---------------------------------------------------------------------------
def test_armed_but_dark_fails_scheduler_dark(tmp_path, monkeypatch):
    """Valid arming file, bundle + serving fine, NO scheduler record for today
    (last = 08-26) and no session_scheduler wrapper log: scheduler_dark, with
    the boot-missed-slot diagnosis."""
    calls = _fake_send(monkeypatch)
    Root(tmp_path, monkeypatch).bundle().serving(rows_for=(INCIDENT_ISO,)).armed() \
        .scheduler_rows("2026-08-26")
    assert liveness.main(INCIDENT_DAY) == 1
    assert _codes(calls) == {liveness.FAIL_SCHEDULER_DARK}
    body = calls[0]["body"]
    assert "scheduler ARMED (operator=op" in body
    assert "last session_date in tail='2026-08-26'" in body
    assert "wrapper log ABSENT" in body


def test_armed_and_ticking_is_ok_and_named(tmp_path, monkeypatch, capsys):
    calls = _fake_send(monkeypatch)
    Root(tmp_path, monkeypatch).bundle().serving(rows_for=(INCIDENT_ISO,)).armed() \
        .scheduler_rows("2026-08-27", INCIDENT_ISO)
    assert liveness.main(INCIDENT_DAY) == 0
    assert calls == []
    out = capsys.readouterr().out
    assert f"rq105 liveness OK {INCIDENT_ISO} [scheduler ARMED: operator=op" in out
    assert "3 tick record(s)" in out


def test_manifest_record_alone_proves_the_scheduler_ran(tmp_path, monkeypatch):
    Root(tmp_path, monkeypatch).bundle().serving(rows_for=(INCIDENT_ISO,)).armed() \
        .scheduler_rows(INCIDENT_ISO, kind="intraday_session_manifest")
    assert liveness.main(INCIDENT_DAY) == 0


def test_foreign_record_kinds_do_not_count(tmp_path, monkeypatch):
    """Only the scheduler's own writer kinds prove the scheduler ran."""
    calls = _fake_send(monkeypatch)
    Root(tmp_path, monkeypatch).bundle().serving(rows_for=(INCIDENT_ISO,)).armed() \
        .scheduler_rows(INCIDENT_ISO, kind="intraday_entry_plan_shadow")
    assert liveness.main(INCIDENT_DAY) == 1
    assert _codes(calls) == {liveness.FAIL_SCHEDULER_DARK}


@pytest.mark.parametrize("payload", [
    "{not json",
    {"armed": True},                                   # missing required fields
    {"armed": "true", "operator": "o", "armed_at": "a", "authority": "b"},  # not literal true
])
def test_present_but_invalid_arming_file_fails_arming_invalid(tmp_path, monkeypatch, payload):
    """A malformed authorization runs the scheduler dark while it LOOKS armed —
    the silent-no-op shape. Never classified as expected-dark."""
    calls = _fake_send(monkeypatch)
    Root(tmp_path, monkeypatch).bundle().serving(rows_for=(INCIDENT_ISO,)).armed(payload) \
        .scheduler_rows(INCIDENT_ISO)
    assert liveness.main(INCIDENT_DAY) == 1
    assert _codes(calls) == {liveness.FAIL_ARMING_INVALID}


def test_non_session_day_keeps_the_early_skip(tmp_path, monkeypatch, capsys):
    calls = _fake_send(monkeypatch)
    Root(tmp_path, monkeypatch)  # nothing else on disk
    monkeypatch.setattr(liveness, "_is_session_day", lambda d: False)
    assert liveness.main(dt.date(2026, 8, 29)) == 0
    assert calls == []
    assert "not an NYSE session day" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 5. the literals are bound to the wrappers and the producers' resolvers
# ---------------------------------------------------------------------------
def test_path_literals_match_the_wrappers_and_module_resolvers(tmp_path):
    root = Path("/x/RenQuant")
    serving_sh = (OPS / "run_shadow_serving.sh").read_text()
    sched_sh = (OPS / "run_session_scheduler.sh").read_text()
    assert '--shadow-log "$RQ_ROOT/logs/renquant105_pilot/shadow_realtime_serving.jsonl"' in serving_sh
    assert '--scheduler-log "$RQ_ROOT/logs/renquant105_pilot/intraday_decisions_shadow.jsonl"' in serving_sh
    assert 'SCORES="$RQ_ROOT/data/rq105/batch_scores_$TS.json"' in serving_sh
    assert 'META="$RQ_ROOT/data/rq105/batch_scores_$TS.meta.json"' in serving_sh
    assert 'ARMING_FILE="$RQ_ROOT/data/rq105/intraday_decisioning.armed.json"' in sched_sh
    assert liveness._serving_jsonl_path(root) == root / "logs/renquant105_pilot/shadow_realtime_serving.jsonl"
    assert liveness._scheduler_jsonl_path(root) == root / "logs/renquant105_pilot/intraday_decisions_shadow.jsonl"
    assert liveness._arming_file_path(root) == root / "data/rq105/intraday_decisioning.armed.json"
    assert liveness._batch_bundle_paths(root, "2026-08-28") == (
        root / "data/rq105/batch_scores_2026-08-28.json",
        root / "data/rq105/batch_scores_2026-08-28.meta.json")
    from renquant_orchestrator.intraday_session_scheduler import default_shadow_log_path as sched_default
    from renquant_orchestrator.shadow_realtime_serving import default_shadow_log_path as serving_default
    assert sched_default(root) == liveness._scheduler_jsonl_path(root)
    assert serving_default(root) == liveness._serving_jsonl_path(root)
    # The SKIP marker is the wrapper's literal, and it is the wrapper's FIRST
    # and only line on the upstream-skip path.
    assert 'skip_log "SKIP upstream: no frozen batch-score export' in serving_sh
    assert liveness._SERVING_SKIP_UPSTREAM_MARKER in INCIDENT_SKIP_LINE


def test_scheduler_record_kinds_are_the_scheduler_modules_own():
    from renquant_orchestrator import intraday_session_scheduler as s
    assert set(liveness._SCHEDULER_RECORD_KINDS) == {s.RECORD_KIND_TICK, s.RECORD_KIND_MANIFEST}


# ---------------------------------------------------------------------------
# 6. shell catch-up guard (bash: the CI runner has no zsh)
# ---------------------------------------------------------------------------
def _guard(tmp_path: Path, dow: int, now: str, *outputs: str, slot="0615", cutoff="1300"):
    log = tmp_path / "guard.log"
    cmd = (f'. "{OPS / "rq105_catchup_guard.sh"}"; rq105_catchup_guard batch-scores-export '
           f'{dow} {now} {slot} {cutoff} "{log}" ' + " ".join(f'"{o}"' for o in outputs))
    res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    lines = log.read_text().splitlines() if log.exists() else []
    return res.returncode, lines, res.stderr


def test_guard_runs_on_a_weekday_after_the_slot_when_output_is_missing(tmp_path):
    rc, lines, _ = _guard(tmp_path, 5, "1038", str(tmp_path / "b.json"), str(tmp_path / "b.meta.json"))
    assert rc == 0
    assert len(lines) == 1 and " RUN " in lines[0] and "missing output" in lines[0]


def test_guard_runs_at_exactly_the_slot(tmp_path):
    rc, lines, _ = _guard(tmp_path, 1, "0615", str(tmp_path / "b.json"))
    assert rc == 0 and " RUN " in lines[0]


@pytest.mark.parametrize("dow,now,why", [
    (6, "1038", "weekend"), (7, "0700", "weekend"),
    (3, "0614", "before the 0615 slot"), (3, "0000", "before the 0615 slot"),
    (3, "1300", "at/after the 1300 cutoff"), (3, "2359", "at/after the 1300 cutoff"),
])
def test_guard_skips_outside_the_window(tmp_path, dow, now, why):
    rc, lines, _ = _guard(tmp_path, dow, now, str(tmp_path / "b.json"))
    assert rc == 1
    assert len(lines) == 1 and " SKIP " in lines[0] and why in lines[0]


def test_guard_is_idempotent_when_every_output_exists(tmp_path):
    (tmp_path / "b.json").write_text("{}"); (tmp_path / "b.meta.json").write_text("{}")
    rc, lines, _ = _guard(tmp_path, 2, "0900", str(tmp_path / "b.json"), str(tmp_path / "b.meta.json"))
    assert rc == 1 and "already present" in lines[0]
    # one of two outputs missing -> run (the bundle is a PAIR)
    (tmp_path / "b.meta.json").unlink()
    rc, lines, _ = _guard(tmp_path, 2, "0900", str(tmp_path / "b.json"), str(tmp_path / "b.meta.json"))
    assert rc == 0 and len(lines) == 2


def test_guard_usage_error_is_2_not_a_silent_skip(tmp_path):
    rc, lines, err = _guard(tmp_path, 2, "0900")  # no outputs named
    assert rc == 2 and lines == [] and "usage" in err
    rc, _, err = _guard(tmp_path, 2, "09x0", str(tmp_path / "b"))
    assert rc == 2 and "non-numeric" in err


def test_wrappers_call_the_guard_with_the_reviewed_slots_and_treat_errors_as_fatal():
    exp = (OPS / "run_batch_scores_export.sh").read_text()
    sch = (OPS / "run_session_scheduler.sh").read_text()
    assert '. "$RQ105_OPS_DIR/rq105_catchup_guard.sh"' in exp and '. "$RQ105_OPS_DIR/rq105_catchup_guard.sh"' in sch
    assert 'rq105_catchup_guard batch-scores-export "$(date +%u)" "$(date +%H%M)" 0615 1300' in exp
    assert 'rq105_catchup_guard session-scheduler "$(date +%u)" "$(date +%H%M)" 0625 1300' in sch
    assert '"$RQ_ROOT/data/rq105/batch_scores_$TS.json"' in exp and '"$RQ_ROOT/data/rq105/batch_scores_$TS.meta.json"' in exp
    assert '"$LOG_DIR/session_scheduler_$TS.log"' in sch
    for text in (exp, sch):
        assert "1) exit 0 ;;" in text and "*) echo \"FATAL: catch-up guard error" in text
    # The guard must run BEFORE the pinned-common resolver: a skip needs no pin.
    assert exp.index("rq105_catchup_guard ") < exp.index("rq105_common_src.sh")
    assert sch.index("rq105_catchup_guard ") < sch.index("rq105_common_src.sh")


def test_guard_logs_never_match_the_manifest_evidence_globs():
    """A load-time SKIP must not read as 'the job fired today' to the drift /
    liveness scans: the guard's dated file lies outside each evidence_glob."""
    jobs = json.loads((ROOT / "ops/launchd_manifest.json").read_text())["jobs"]
    for label, guard in (("com.renquant.rq105-batch-scores-export", "catchup_guard_batch-scores-export_2026-08-29.log"),
                         ("com.renquant.rq105-session-scheduler", "catchup_guard_session-scheduler_2026-08-29.log")):
        glob = jobs[label]["evidence_glob"]
        assert not fnmatch.fnmatch(os.path.join(os.path.dirname(glob), guard), glob), (label, glob)


def test_plists_carry_run_at_load_and_stay_weekday_calendar_jobs():
    import plistlib
    for name in ("batch-scores-export", "session-scheduler"):
        with open(OPS / f"com.renquant.rq105-{name}.plist", "rb") as fh:
            plist = plistlib.load(fh)
        assert plist.get("RunAtLoad") is True, name
        assert {d["Weekday"] for d in plist["StartCalendarInterval"]} == {1, 2, 3, 4, 5}
