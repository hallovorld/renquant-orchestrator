"""A watched lane vanishing from config must not report clean.

END-TO-END through the sentinel's OWN reader and patrol path — deliberately not through
`is_valid_v1_record`. Reviewed `[codex on renquant-pipeline#240]`: *"exercising
is_valid_v1_record alone tests parsing, not the consumer path the PR claims to repair."*
That was right, and it was right about my own claim: the producer-side fix made the
record parse and it was still dropped at the lane filter one line later.

The shape being pinned: `_patrol_lane` treats a window with no records as the LIVENESS
checker's domain and stays quiet. A lane removed from config produces exactly that window
— every per-lane record is absent, because the only record emitted belongs to no lane —
so the one failure this sentinel exists to catch reported clean.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "renquant104" / "rq104_shadow_scorer_sentinel.py"


def _load():
    spec = importlib.util.spec_from_file_location("sent", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


S = _load()
DAYS = [dt.date(2026, 7, 29), dt.date(2026, 7, 30), dt.date(2026, 7, 31)]


def _sink(tmp_path, rows):
    p = tmp_path / "shadow_scorer_health.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return str(p)


def _record(day, shadow_name, state, status=None, actionable=None,
            _skip_validation=False):
    """A schema-valid v1 record. Built here rather than imported so this test fails if
    the sentinel's OWN validator drifts from what the producer emits."""
    status = status if status is not None else S.STATUS_EXPECTED_SKIP
    rec = {
        "schema": "shadow_scorer_health.v1",
        "run_date": day.isoformat(),
        "run_id": "r-" + day.isoformat(),
        "shadow_name": shadow_name,
        "kind": None,
        "artifact_path": None,
        "loaded": False,
        "scored": False,
        "status": status,
        "state": state,
        "actionable": (actionable if actionable is not None
                       else status != S.STATUS_FAULT),
        "reasons": ["no shadow_models configured"],
        "n_candidates": 0,
        "n_scored": 0,
        "staleness_days": None,
        "coverage_frac": None,
    }
    # SELF-CHECK. Without it this helper can drift into emitting records the sentinel's
    # own validator rejects, and every "the lane produced no per-lane record" assertion
    # below would pass for the WRONG reason -- which is exactly what happened on the
    # first run of this file (`n_scored` was missing, so nothing parsed at all).
    if not _skip_validation:
        assert S.is_valid_v1_record(rec), (
            "test helper emitted a record the sentinel refuses; the assertions below "
            "would then hold vacuously")
    return rec


def _lane(name=None):
    return S.WatchedLane(name=name or S.SHADOW_NAME, runs_db=None, mlruns_dir=None,
                         purpose="the GOAL-4 feed")


def _patrol(monkeypatch, tmp_path, rows, lane=None):
    """Drive the REAL patrol path and capture whether it alarmed."""
    monkeypatch.setattr(S, "SHADOW_HEALTH_JSONL", _sink(tmp_path, rows))
    alerts = []
    monkeypatch.setattr(S, "alert",
                        lambda subject, body, **kw: alerts.append((subject, body)))
    out: list[str] = []
    rc = S._patrol_lane(lane or _lane(), DAYS, DAYS[-1], out)
    return rc, out, alerts


# --- the defect -------------------------------------------------------------

def test_BEFORE_SHAPE_a_task_level_record_reaches_no_per_lane_record(tmp_path,
                                                                    monkeypatch):
    """Why the per-lane map is empty: the record belongs to no lane. Pinning this makes
    the rest of the file meaningful rather than assumed."""
    monkeypatch.setattr(S, "SHADOW_HEALTH_JSONL", _sink(tmp_path, [
        _record(d, S.TASK_LEVEL_SHADOW_NAME, S.STATE_NO_SHADOW_MODELS) for d in DAYS]))
    recs = S.read_health_records(DAYS, _lane())
    assert all(recs.get(d) is None for d in DAYS), recs
    assert not S._matches_shadow_lane(S.TASK_LEVEL_SHADOW_NAME)


def test_a_lane_ABSENT_FROM_CONFIG_now_ALARMS(tmp_path, monkeypatch):
    """The whole point. Before this change the same input returned 0, silently."""
    rc, out, alerts = _patrol(monkeypatch, tmp_path, [
        _record(d, S.TASK_LEVEL_SHADOW_NAME, S.STATE_NO_SHADOW_MODELS) for d in DAYS])
    assert rc == S.EXIT_ALARM, (rc, out)
    assert out and "ABSENT FROM CONFIG" in out[0]
    assert alerts and "SHADOW LANE ABSENT FROM CONFIG" in alerts[0][0]
    assert "restore the lane" in alerts[0][1]


def test_the_alarm_names_the_DAYS_and_the_denominator(tmp_path, monkeypatch):
    """A count with no denominator cannot distinguish one bad day from a dead lane."""
    rc, out, _ = _patrol(monkeypatch, tmp_path, [
        _record(DAYS[0], S.TASK_LEVEL_SHADOW_NAME, S.STATE_NO_SHADOW_MODELS)])
    assert rc == S.EXIT_ALARM
    assert "1 of 3 day(s)" in out[0], out[0]


# --- anti-vacuity: it must still be QUIET where quiet is right ---------------

def test_a_GENUINELY_SILENT_window_still_defers_to_liveness(tmp_path, monkeypatch):
    """No records at all is still the liveness checker's domain, not an alarm here."""
    rc, out, alerts = _patrol(monkeypatch, tmp_path, [])
    assert rc == 0 and out == [] and alerts == []


def test_a_task_level_record_with_a_DIFFERENT_state_does_not_alarm(tmp_path,
                                                                  monkeypatch):
    """Only `no_shadow_models` means the lane is gone. `disabled` is a deliberate off
    switch and must not be reported as a vanished lane."""
    rc, out, alerts = _patrol(monkeypatch, tmp_path, [
        _record(d, S.TASK_LEVEL_SHADOW_NAME, "disabled") for d in DAYS])
    assert rc == 0 and out == [] and alerts == []


def test_a_HEALTHY_lane_is_untouched(tmp_path, monkeypatch):
    """If the lane reports normally the new branch is never reached — the guard is on
    'no per-lane record', not on the presence of a task-level one."""
    rows = [_record(d, S.SHADOW_NAME, "ok", status=S.STATUS_OK) for d in DAYS]
    rows += [_record(d, S.TASK_LEVEL_SHADOW_NAME, S.STATE_NO_SHADOW_MODELS)
             for d in DAYS]
    rc, out, alerts = _patrol(monkeypatch, tmp_path, rows)
    assert not any("ABSENT FROM CONFIG" in p for p in out), out


def test_a_task_level_record_for_a_DAY_OUTSIDE_the_window_is_ignored(tmp_path,
                                                                    monkeypatch):
    """Otherwise an old line in an append-only sink alarms forever."""
    rc, out, alerts = _patrol(monkeypatch, tmp_path, [
        _record(dt.date(2026, 1, 4), S.TASK_LEVEL_SHADOW_NAME,
                S.STATE_NO_SHADOW_MODELS)])
    assert rc == 0 and out == [] and alerts == []


def test_a_MALFORMED_task_level_line_does_not_alarm_and_does_not_crash(tmp_path,
                                                                      monkeypatch):
    """A record failing the validator is not evidence of anything."""
    bad = _record(DAYS[0], S.TASK_LEVEL_SHADOW_NAME, S.STATE_NO_SHADOW_MODELS,
                  _skip_validation=True)
    bad["actionable"] = "yes"          # violates the producer invariant
    assert not S.is_valid_v1_record(bad)
    rc, out, alerts = _patrol(monkeypatch, tmp_path, [bad])
    assert rc == 0 and out == [] and alerts == []
