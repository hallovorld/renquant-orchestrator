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


def test_log_marker_alarms_even_when_a_record_looks_normal(tree):
    cfg, data, logs = tree
    _profile(cfg, LANE.profile, pending=False)
    _db(data, LANE.tag, n_candidates=83)
    (logs / f"{DATE}_{LANE.log_stem}.log").write_text(
        "... Panel scoring contract failed (panel_scorer_load_failed) ...",
        encoding="utf-8")
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_FAIL_CLOSED


def test_missing_record_alarms_when_not_dormant(tree):
    cfg, _, _ = tree
    _profile(cfg, LANE.profile, pending=False)
    state, detail = _classify(LANE, tree)
    assert state == S.STATE_MISSING and state in S.ACTIONABLE
    assert "not dormant" in detail


def test_dormant_lane_is_quiet_and_only_config_can_declare_it(tree):
    cfg, _, _ = tree
    _profile(cfg, LANE.profile, pending=True)
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_DORMANT and state not in S.ACTIONABLE


def test_absent_profile_is_NOT_dormant(tree):
    """A vanished profile must never read as 'declared dormant' — that is the
    exact silence this sentinel exists to remove."""
    state, _ = _classify(LANE, tree)
    assert state == S.STATE_MISSING and state in S.ACTIONABLE


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


def test_manifest_declares_the_job_with_a_bounded_pending_install():
    manifest = json.loads(MANIFEST.read_text())
    jobs = manifest.get("jobs", manifest)
    assert JOB in jobs, "the scheduled surface must be declared in the reviewed manifest"
    entry = jobs[JOB]
    assert entry["program_args"][-1].endswith(
        "ops/renquant104/fleet_lane_sentinel_daily.sh")
    assert "fleet_lane_sentinel_" in entry["evidence_glob"]
    pending = [k for k in entry if k.endswith("_pending_install")]
    assert len(pending) == 1, "the pending state must be declared by exactly one dated key"
    assert "same change that installs" in entry[pending[0]].lower()
