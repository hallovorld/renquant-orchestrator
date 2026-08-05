"""The fleet sentinel must alarm on the shapes that actually went wrong."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant104"))
import fleet_lane_sentinel as S  # noqa: E402

DATE = "2026-08-04"


def _profile(dirpath: Path, name: str, *, pending: bool) -> None:
    comp1 = {"artifact_path": "artifacts/x.json"}
    if pending:
        comp1["_2026_08_04_pending_first_artifact"] = "declared dormant"
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / name).write_text(json.dumps({
        "ranking": {"panel_scoring": {"kind": "blend", "components": [
            {"artifact_path": "artifacts/prod.json"}, comp1]}}}), encoding="utf-8")


def _db(dirpath: Path, tag: str, *, n_candidates: int) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(dirpath / f"runs.{tag}.db")
    con.execute("CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT, "
                "n_candidates INT, n_buys INT, n_exits INT, created_at TEXT)")
    con.execute("INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?)",
                ("r1", DATE, n_candidates, 1, 0, "2026-08-04 21:00:00"))
    con.commit(); con.close()


def _db_zero(dirpath: Path, tag: str) -> None:
    """A row for a run that recorded but scored nothing — the fail-closed shape."""
    dirpath.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(dirpath / f"runs.{tag}.db")
    con.execute("CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT, "
                "n_candidates INT, n_buys INT, n_exits INT, created_at TEXT)")
    con.execute("INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?)",
                ("r1", DATE, 0, 0, 0, "2026-08-04 21:00:00"))
    con.commit(); con.close()


@pytest.fixture
def tree(tmp_path):
    cfg, data, logs = tmp_path / "cfg", tmp_path / "data", tmp_path / "logs"
    for d in (cfg, data, logs):
        d.mkdir(parents=True, exist_ok=True)
    return cfg, data, logs


def _classify(lane, tree, **kw):
    cfg, data, logs = tree
    return S.classify(lane, DATE, configs_dir=cfg, data_dir=data, logs_dir=logs, **kw)


LANE = S.FLEET[3]  # RCS — the lane that actually failed


def test_healthy_lane_is_recorded_not_alarmed(tree):
    cfg, data, _ = tree
    _profile(cfg, LANE.profile, pending=False)
    _db(data, LANE.tag, n_candidates=83)
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_RECORDED and state not in S.ACTIONABLE
    assert "candidates=83" in detail


def test_the_RCS_shape_alarms_zero_candidates(tree):
    """The measured 2026-08-04 defect: the lane ran, the scorer refused, the
    record exists with zero candidates. Must be ACTIONABLE."""
    cfg, data, _ = tree
    _profile(cfg, LANE.profile, pending=False)
    _db(data, LANE.tag, n_candidates=0)
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_FAIL_CLOSED and state in S.ACTIONABLE
    assert "ZERO candidates" in detail


def test_a_repaired_lane_stops_alarming_but_the_earlier_failure_is_reported(tree):
    """MEASURED 2026-08-04 running this sentinel against its own incident:
    RCS fail-closed at 21:02, was fixed, re-ran healthy at 22:02 — and the
    session log still carried the earlier marker. A marker-first rule kept
    alarming on a REPAIRED lane, which trains its reader to ignore it. The
    record is per-run and latest-wins, so a healthy latest record supersedes
    an earlier marker — and the note says so, rather than hiding it."""
    cfg, data, logs = tree
    _profile(cfg, LANE.profile, pending=False)
    _db(data, LANE.tag, n_candidates=83)
    (logs / f"{DATE}_{LANE.log_stem}.log").write_text(
        "... Panel scoring contract failed (panel_scorer_load_failed) ...",
        encoding="utf-8")
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_RECORDED and state not in S.ACTIONABLE
    assert "EARLIER run" in detail and "supersedes" in detail


def test_marker_without_any_record_still_alarms(tree):
    """The marker's real job: a lane that refused before writing a record."""
    cfg, _, logs = tree
    _profile(cfg, LANE.profile, pending=False)
    (logs / f"{DATE}_{LANE.log_stem}.log").write_text(
        "... panel_scoring_fail_closed ...", encoding="utf-8")
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_FAIL_CLOSED and state in S.ACTIONABLE
    assert "NO record" in detail


def test_zero_candidate_record_alarms_and_mentions_the_marker(tree):
    cfg, data, logs = tree
    _profile(cfg, LANE.profile, pending=False)
    _db(data, LANE.tag, n_candidates=0)
    (logs / f"{DATE}_{LANE.log_stem}.log").write_text(
        "... panel_scorer_load_failed ...", encoding="utf-8")
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_FAIL_CLOSED
    assert "ZERO candidates" in detail and "fail-closed marker" in detail


def test_missing_record_alarms_when_not_dormant(tree):
    cfg, data, _ = tree
    _profile(cfg, LANE.profile, pending=False)
    _db(data, S.PROD_TAG, n_candidates=80)   # the SESSION ran; this lane did not
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_MISSING and state in S.ACTIONABLE
    assert "not dormant" in detail


def test_dormant_lane_is_quiet_and_only_config_can_declare_it(tree):
    cfg, _, _ = tree
    _profile(cfg, LANE.profile, pending=True)
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_DORMANT and state not in S.ACTIONABLE


def test_absent_profile_is_NOT_dormant_and_alarms_BEFORE_any_session(tree):
    """A vanished profile must never read as 'declared dormant' — that is the
    exact silence this sentinel exists to remove.

    [codex on orch#811] It must also alarm with NO prod row. A missing profile
    is a CONFIG defect that is true whether or not anything ran; the wrapper
    will skip that rail on its next run. My first version of the session check
    wrote a prod row here, which erased exactly this pre-session detection case.
    """
    _, data, _ = tree
    assert S.session_state(DATE, data) == S.SESSION_NOT_STARTED
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_PROFILE_DEFECT and state in S.ACTIONABLE
    assert "will skip this rail" in detail


def test_dormancy_cannot_be_declared_by_editing_the_sentinel(tree):
    """Dormancy is sourced ONLY from the pinned profile; the module exposes no
    lane-level mute list that could silence a lane outside review."""
    src = (Path(__file__).resolve().parent.parent
           / "ops/renquant104/fleet_lane_sentinel.py").read_text()
    for banned in ("MUTED", "SKIP_LANES", "IGNORE_LANES", "QUIET_LANES"):
        assert banned not in src, f"a mute list ({banned}) would bypass review"


def test_every_served_fleet_lane_is_registered():
    """Anti-drift: the registry must carry every callsign the runner serves."""
    callsigns = {l.callsign for l in S.FLEET}
    assert callsigns == {"RC", "RSs", "Rf", "RCS", "RCf"}, callsigns
    assert len({l.tag for l in S.FLEET}) == 5
    assert len({l.profile for l in S.FLEET}) == 5
    assert len({l.log_stem for l in S.FLEET}) == 5


def test_patrol_partitions_lanes_into_alarms_and_info(tree):
    cfg, data, _ = tree
    for lane in S.FLEET:
        _profile(cfg, lane.profile, pending=(lane.callsign in ("Rf", "RCf")))
        if lane.callsign in ("RC", "RSs"):
            _db(data, lane.tag, n_candidates=80)
        elif lane.callsign == "RCS":
            _db(data, lane.tag, n_candidates=0)
    cfgd, datad, logsd = tree
    alarms, info = S.patrol(DATE, configs_dir=cfgd, data_dir=datad, logs_dir=logsd)
    assert len(alarms) == 1 and "RCS" in alarms[0]
    assert len(info) == 4


# ── the SCHEDULED surface (codex on orch#801: a checker nobody runs is the
#    deployed-but-dark gap this sentinel exists to close) ────────────────────

WRAPPER = (Path(__file__).resolve().parent.parent
           / "ops/renquant104/fleet_lane_sentinel_daily.sh")
MANIFEST = Path(__file__).resolve().parent.parent / "ops/launchd_manifest.json"
JOB = "com.renquant.rq104-fleet-lane-sentinel"


def test_wrapper_passes_the_session_date_explicitly():
    """Never left to the checker's own default: a wrapper firing after
    midnight UTC must still classify the session it was scheduled for."""
    src = WRAPPER.read_text()
    assert 'SESSION_DATE="${1:-$(date +%Y-%m-%d)}"' in src
    assert '"$SENTINEL" --date "$SESSION_DATE"' in src


def test_wrapper_propagates_the_actionable_failure_and_pages():
    src = WRAPPER.read_text()
    assert 'RC=$?' in src
    assert 'if [ "$RC" -eq 1 ]; then' in src
    assert "FLEET-LANE-ALARM" in src
    assert "exit 1" in src
    # the alarm carries the offending lane lines, not just a log pointer
    assert "grep -E '^\\[(FAIL_CLOSED|MISSING)\\]'" in src


def test_wrapper_exec_redirects_before_any_work():
    """The orch#754 evidence contract: a pre-exec death must not vanish."""
    src = WRAPPER.read_text()
    idx_exec = src.index('exec >>"$LOG" 2>&1')
    idx_run = src.index('"$SENTINEL" --date')
    assert idx_exec < idx_run
    for marker in ("REFUSED:", "FLEET-SENTINEL-REFUSED", "fleet_lane_sentinel OK",
                   "fleet_lane_sentinel ALARM", "fleet_lane_sentinel ERROR"):
        assert marker in src, marker


def test_no_launchd_job_is_declared_for_this_sentinel():
    """Round 3 (codex): the sentinel runs as the DAILY WRAPPER's last step,
    after the very Step-5e legs it inspects — so there is no cadence to guess
    and no plist to install. A launchd entry would reintroduce both problems
    (the first draft picked 15:30 PT from a MANUAL run's clock; a scheduled
    13:55 run's fleet legs are still moving then, and the job would have paged
    MISSING on a healthy fleet)."""
    manifest = json.loads(MANIFEST.read_text())
    jobs = manifest.get("jobs", manifest)
    assert JOB not in jobs, (
        "this sentinel must not acquire a launchd job: its correct trigger is "
        "daily-run completion, not a clock"
    )


def test_wrapper_is_invocable_with_an_explicit_session_date():
    """What the daily wrapper's last step relies on: positional date arg."""
    src = WRAPPER.read_text()
    assert 'SESSION_DATE="${1:-$(date +%Y-%m-%d)}"' in src


# ── GOAL-1: "has not run" is not "has failed" ────────────────────────────────
#
# MEASURED 2026-08-05 03:45 PT, nine hours before the daily run: this sentinel
# reported 3 ACTIONABLE lane states on a date where NOTHING had run. That is the
# exact ambiguity GOAL-1 exists to remove — an operator seeing MISSING cannot
# tell "the lane crashed" from "the day has not started".


def test_no_PROD_row_makes_an_absent_lane_NOT_YET_RUN(tree):
    cfg, data, _ = tree
    _profile(cfg, LANE.profile, pending=False)          # no prod db, no lane db
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_NOT_YET_RUN
    assert state not in S.ACTIONABLE
    assert "has not run yet" in detail


def test_a_PROD_row_restores_MISSING_as_ACTIONABLE(tree):
    """The load-bearing half: this must NOT become a silencer. If prod ran and a
    lane did not record, that lane is still an alarm."""
    cfg, data, _ = tree
    _profile(cfg, LANE.profile, pending=False)
    _db(data, S.PROD_TAG, n_candidates=80)              # the session DID run
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_MISSING and state in S.ACTIONABLE


def test_a_FAIL_CLOSED_lane_stays_actionable_even_with_no_PROD_row(tree):
    """Order matters: a lane that DID record a fail-closed run is judged on its
    own evidence and is never downgraded by the session check — even though no
    PROD row exists, which would otherwise mean NOT_YET_RUN."""
    cfg, data, logs = tree
    _profile(cfg, LANE.profile, pending=False)
    _db_zero(data, LANE.tag)                 # recorded, but scored nothing
    (logs / f"{DATE}_{LANE.log_stem}.log").write_text(
        "panel_scoring_fail_closed(83)", encoding="utf-8")
    assert S.session_started(DATE, data) is False
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_FAIL_CLOSED and state in S.ACTIONABLE


def test_DORMANCY_still_wins_over_the_session_check(tree):
    """Dormancy is a config fact; it must not depend on whether anything ran."""
    cfg, _, _ = tree
    _profile(cfg, LANE.profile, pending=True)
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_DORMANT


def test_session_started_reads_PROD_not_the_lane(tree):
    """Anti-vacuity: a lane's own db must not be mistaken for the session."""
    _, data, _ = tree
    assert S.session_started(DATE, data) is False
    _db(data, LANE.tag, n_candidates=83)
    assert S.session_started(DATE, data) is False, "a lane row is not a session"
    _db(data, S.PROD_TAG, n_candidates=80)
    assert S.session_started(DATE, data) is True


def test_the_all_clear_SAYS_the_session_has_not_run(tree, capsys, monkeypatch):
    """A silent all-clear on a date nothing ran is the same ambiguity one level
    up — the operator must be told which of the two they are looking at."""
    cfg, data, logs = tree
    for lane in S.FLEET:
        _profile(cfg, lane.profile, pending=False)
    monkeypatch.setattr(S, "DATA", data)
    monkeypatch.setattr(S, "PINNED_CONFIGS", cfg)
    monkeypatch.setattr(S, "LOGS", logs)
    rc = S.main(["--date", DATE])
    out = capsys.readouterr().out
    assert rc == 0
    assert "has NOT RUN" in out
    assert "lanes accounted for" not in out


def test_directories_resolve_at_CALL_time_not_at_import(tree, monkeypatch):
    """Found while writing the NOT_YET_RUN test: `main()` bound DATA/LOGS as
    parameter defaults at import, so a redirected run silently measured the REAL
    tree. A watcher that reads production when you point it elsewhere is worse
    than one that errors."""
    cfg, data, logs = tree
    _profile(cfg, LANE.profile, pending=False)
    monkeypatch.setattr(S, "DATA", data)
    monkeypatch.setattr(S, "PINNED_CONFIGS", cfg)
    monkeypatch.setattr(S, "LOGS", logs)
    state, _ = S.classify(LANE, DATE)            # no explicit dirs
    assert state == S.STATE_NOT_YET_RUN, (
        "classify read a directory bound at import instead of the current one")
    assert S.session_started(DATE) is False


# ── [codex on orch#811] "cannot read the evidence" is not "no evidence" ──────

def _corrupt_db(dirpath: Path, tag: str) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / f"runs.{tag}.db").write_bytes(b"this is not a sqlite file")


def test_an_UNREADABLE_prod_db_keeps_the_lane_ACTIONABLE(tree):
    """The silencer this change could have become: if runs.alpaca.db is
    corrupt after a REAL session, a lane that also failed before writing its own
    row must NOT be downgraded to the quiet NOT_YET_RUN."""
    cfg, data, _ = tree
    _profile(cfg, LANE.profile, pending=False)
    _corrupt_db(data, S.PROD_TAG)
    assert S.session_state(DATE, data) == S.SESSION_UNKNOWN
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_MISSING and state in S.ACTIONABLE
    assert "could NOT BE READ" in detail


def test_session_state_is_THREE_valued_not_two(tree):
    _, data, _ = tree
    assert S.session_state(DATE, data) == S.SESSION_NOT_STARTED
    _db(data, S.PROD_TAG, n_candidates=80)
    assert S.session_state(DATE, data) == S.SESSION_STARTED
    _corrupt_db(data, S.PROD_TAG)
    assert S.session_state(DATE, data) == S.SESSION_UNKNOWN


def test_an_unreadable_LANE_db_is_ACTIONABLE_not_quiet(tree):
    """[codex on orch#812] I fixed the fold-in for the PROD db and left the SAME
    error one function over: a corrupt runs.<lane>.db returned None and fell
    through to the quiet NOT_YET_RUN. An unreadable evidence source is an
    independently detected fault — "cannot say" is never "fine"."""
    cfg, data, _ = tree
    _profile(cfg, LANE.profile, pending=False)
    _corrupt_db(data, LANE.tag)
    assert S.session_state(DATE, data) == S.SESSION_NOT_STARTED
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_EVIDENCE_UNREADABLE and state in S.ACTIONABLE
    assert "could not be read" in detail


def test_an_unreadable_LANE_db_is_actionable_with_PROD_started_too(tree):
    cfg, data, _ = tree
    _profile(cfg, LANE.profile, pending=False)
    _db(data, S.PROD_TAG, n_candidates=80)
    _corrupt_db(data, LANE.tag)
    assert S.session_state(DATE, data) == S.SESSION_STARTED
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_EVIDENCE_UNREADABLE and state in S.ACTIONABLE


def test_an_unreadable_LANE_db_is_actionable_even_when_DORMANT(tree):
    """Dormancy declares a component pending; it says nothing about whether the
    lane's own evidence can be read."""
    cfg, data, _ = tree
    _profile(cfg, LANE.profile, pending=True)
    _corrupt_db(data, LANE.tag)
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_EVIDENCE_UNREADABLE and state in S.ACTIONABLE


def test_a_PROFILE_ABSENT_lane_is_never_downgraded_by_the_session_check(tree):
    cfg, data, _ = tree
    for prep in (lambda: None,
                 lambda: _db(data, S.PROD_TAG, n_candidates=80),
                 lambda: _corrupt_db(data, S.PROD_TAG)):
        prep()
        state, _ = _classify(LANE, tree)
        assert state == S.STATE_PROFILE_DEFECT and state in S.ACTIONABLE


def test_an_UNPARSEABLE_profile_alarms_BEFORE_any_session(tree):
    """[codex on orch#812] Existence is not enough. The wrapper gates these
    lanes on file existence alone and then hands the path to the runner, whose
    loader hard-parses it with json.loads — so a malformed profile is a real
    pre-session failure, and checking only exists() silenced it until the
    session ran."""
    cfg, data, _ = tree
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / LANE.profile).write_text("{not json at all", encoding="utf-8")
    assert S.session_state(DATE, data) == S.SESSION_NOT_STARTED
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_PROFILE_DEFECT and state in S.ACTIONABLE
    assert "not valid JSON" in detail


def test_a_profile_that_is_not_an_OBJECT_also_alarms(tree):
    cfg, _, _ = tree
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / LANE.profile).write_text('["a", "list"]', encoding="utf-8")
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_PROFILE_DEFECT
    assert "not a JSON object" in detail


def test_a_profile_defect_is_never_downgraded_by_ANY_session_state(tree):
    cfg, data, _ = tree
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / LANE.profile).write_text("{broken", encoding="utf-8")
    for prep in (lambda: None,
                 lambda: _db(data, S.PROD_TAG, n_candidates=80),
                 lambda: _corrupt_db(data, S.PROD_TAG)):
        prep()
        state, _ = _classify(LANE, tree)
        assert state == S.STATE_PROFILE_DEFECT and state in S.ACTIONABLE


def test_a_VALID_profile_is_not_a_defect(tree):
    """Anti-false-positive: the check must not reject healthy profiles."""
    cfg, _, _ = tree
    _profile(cfg, LANE.profile, pending=False)
    assert S.profile_defect(LANE, cfg) is None
    _profile(cfg, LANE.profile, pending=True)
    assert S.profile_defect(LANE, cfg) is None
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_DORMANT


# ── [codex on orch#812] dormancy is checked AGAINST evidence, not before it ──

def test_a_dormant_lane_that_FAIL_CLOSED_says_so_instead_of_hiding_it(tree):
    """The fast lanes still EXECUTE daily; the pending-artifact marker only says
    the fast artifact is unpublished. Returning DORMANT before looking at the
    row or log meant a dormant lane with a fail-closed marker reported quiet
    with no mention of it — a quiet state that hides its evidence is how the
    reader stops being able to tell quiet from broken."""
    cfg, data, logs = tree
    _profile(cfg, LANE.profile, pending=True)
    _db_zero(data, LANE.tag)
    (logs / f"{DATE}_{LANE.log_stem}.log").write_text(
        "panel_scorer_load_failed", encoding="utf-8")
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_DORMANT           # still quiet — this IS expected
    assert "fail-closed" in detail            # ... but it is SAID
    assert "candidates=0" in detail


def test_a_dormant_lane_that_actually_SCORED_is_ACTIONABLE(tree):
    """A stale dormancy declaration is precisely how a lane goes dark without
    anyone noticing: it scored, so the profile's 'pending first artifact' is no
    longer true."""
    cfg, data, _ = tree
    _profile(cfg, LANE.profile, pending=True)
    _db(data, LANE.tag, n_candidates=83)      # it SCORED
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_MISSING and state in S.ACTIONABLE
    assert "declaration is STALE" in detail


def test_a_dormant_lane_with_no_evidence_is_still_plainly_quiet(tree):
    """Anti-false-positive: the ordinary dormant case must not become noisy."""
    cfg, _, _ = tree
    _profile(cfg, LANE.profile, pending=True)
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_DORMANT and state not in S.ACTIONABLE
    assert "fail-closed" not in detail and "STALE" not in detail


# ── [codex on orch#812] the PATTERN, not one more instance ──────────────────

def _unreadable_log(logs: Path, lane, date=DATE) -> Path:
    """A log that EXISTS but cannot be read (a directory in its place)."""
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / f"{date}_{lane.log_stem}.log"
    path.mkdir()
    return path


def test_an_unreadable_LOG_is_actionable_not_quiet(tree):
    """The third fold-in: _log_says_fail_closed caught OSError and returned
    False, so an unreadable log became 'no marker' and the lane fell through to
    a quiet state."""
    cfg, data, logs = tree
    _profile(cfg, LANE.profile, pending=False)
    _unreadable_log(logs, LANE)
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_EVIDENCE_UNREADABLE and state in S.ACTIONABLE
    assert "session log could not be read" in detail


def test_an_unreadable_LOG_is_actionable_even_when_DORMANT(tree):
    cfg, _, logs = tree
    _profile(cfg, LANE.profile, pending=True)
    _unreadable_log(logs, LANE)
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_EVIDENCE_UNREADABLE and state in S.ACTIONABLE


def test_an_ABSENT_log_is_still_a_legitimate_no_marker(tree):
    """Anti-false-positive: absence is fine, unreadability is not."""
    cfg, data, _ = tree
    _profile(cfg, LANE.profile, pending=False)
    _db(data, LANE.tag, n_candidates=83)
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_RECORDED


def test_NO_evidence_reader_silently_defaults_on_an_unreadable_source():
    """Invert the default, do not enumerate. This module folded 'cannot read'
    into 'absent' three separate times, each fixed alone before the next was
    found. Every reader must raise EvidenceUnreadable rather than return a
    default, so a FOURTH instance cannot be added quietly."""
    import inspect

    src = inspect.getsource(S)
    for reader in ("_tag_record", "_log_says_fail_closed"):
        body = src[src.index(f"def {reader}("):]
        body = body[:min([body.index(m) for m in ("\ndef ", "\nclass ")
                          if m in body] or [len(body)])]
        assert "raise EvidenceUnreadable" in body or "raise DbUnreadable" in body, (
            f"{reader} does not raise on an unreadable source")
        assert "        return False\n    return any" not in body, reader
    assert issubclass(S.DbUnreadable, S.EvidenceUnreadable)
    assert S.STATE_EVIDENCE_UNREADABLE in S.ACTIONABLE
