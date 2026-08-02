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


# ---------------------------------------------------------------------------
# ROUND 2 — codex on #689: the likelier removal is ONE lane dropped from a list,
# which emits no task-level signal at all.
# ---------------------------------------------------------------------------

OTHER = "topdecile_clf_blend_leg"

#: The watched lane reporting on a date BEFORE the window. Required for the
#: partial-removal branch, and the requirement is the point: without a prior appearance
#: "others reported and this lane did not" says nothing, because the health sink is
#: written PER TASK and a lane from another task is legitimately absent from it forever.
#: With it, the inference is a DISAPPEARANCE -- this lane used to write here and stopped.
PRIOR = [_record(dt.date(2026, 7, 20), S.SHADOW_NAME, "ok", status=S.STATUS_OK)]


def test_the_WATCHED_lane_removed_while_ANOTHER_REMAINS_alarms(tmp_path, monkeypatch):
    """The case codex named. `no_shadow_models` never fires here: the task still has a
    shadow lane, just not this one. Before this round the window looked identical to
    'no runs' and fell through to the liveness skip."""
    rc, out, alerts = _patrol(monkeypatch, tmp_path, PRIOR + [
        _record(d, OTHER, "ok", status=S.STATUS_OK) for d in DAYS])
    assert rc == S.EXIT_ALARM, (rc, out)
    assert "ABSENT FROM CONFIG" in out[0], out
    assert OTHER in out[0], out
    assert "while others remain" in alerts[0][1], alerts[0][1]


def test_the_alarm_NAMES_the_lanes_that_did_report(tmp_path, monkeypatch):
    """'Something else reported' is not actionable; WHICH lanes reported is."""
    rc, out, _ = _patrol(monkeypatch, tmp_path, PRIOR + [
        _record(DAYS[0], OTHER, "ok", status=S.STATUS_OK),
        _record(DAYS[1], "another_leg", "ok", status=S.STATUS_OK)])
    assert rc == S.EXIT_ALARM
    assert "another_leg" in out[0] and OTHER in out[0], out[0]
    assert "2 of 3 day(s)" in out[0], out[0]


def test_a_DECORATED_form_of_the_watched_lane_counts_as_PRESENT(tmp_path, monkeypatch):
    """`hf_patchtst_v2` IS the watched lane. Matching by equality instead of the lane's
    own `matches()` would alarm on a healthy renamed lane — a false positive on the
    exact rename this sentinel is supposed to tolerate."""
    rows = [_record(d, S.SHADOW_NAME + "_v2", "ok", status=S.STATUS_OK) for d in DAYS]
    rc, out, alerts = _patrol(monkeypatch, tmp_path, rows)
    assert not any("ABSENT FROM CONFIG" in p for p in out), out


def test_TOTAL_removal_still_reports_as_total_removal_not_as_partial(tmp_path,
                                                                    monkeypatch):
    """The two branches must not shadow each other: a task-level record present means
    NO lanes were configured, which is a different message from 'others remain'."""
    rc, out, alerts = _patrol(monkeypatch, tmp_path, [
        _record(d, S.TASK_LEVEL_SHADOW_NAME, S.STATE_NO_SHADOW_MODELS) for d in DAYS])
    assert rc == S.EXIT_ALARM
    assert "no shadow models" in alerts[0][0].lower(), alerts[0][0]
    assert "while others remain" not in alerts[0][1]


def test_a_task_level_record_is_NOT_counted_as_an_observed_lane(tmp_path, monkeypatch):
    """Otherwise a totally-unconfigured task looks like it still had a lane."""
    monkeypatch.setattr(S, "SHADOW_HEALTH_JSONL", _sink(tmp_path, [
        _record(d, S.TASK_LEVEL_SHADOW_NAME, S.STATE_NO_SHADOW_MODELS) for d in DAYS]))
    assert S.read_observed_lane_names(DAYS) == {}


def test_ANTI_VACUITY_a_HEALTHY_watched_lane_beside_others_stays_quiet(tmp_path,
                                                                      monkeypatch):
    """The new branch must fire on absence, not on the presence of other lanes."""
    rows = [_record(d, S.SHADOW_NAME, "ok", status=S.STATUS_OK) for d in DAYS]
    rows += [_record(d, OTHER, "ok", status=S.STATUS_OK) for d in DAYS]
    rc, out, alerts = _patrol(monkeypatch, tmp_path, rows)
    assert not any("ABSENT FROM CONFIG" in p for p in out), out


def test_another_lane_reporting_OUTSIDE_the_window_does_not_alarm(tmp_path, monkeypatch):
    rc, out, alerts = _patrol(monkeypatch, tmp_path, [
        _record(dt.date(2026, 1, 4), OTHER, "ok", status=S.STATUS_OK)])
    assert rc == 0 and out == [] and alerts == []


def test_a_lane_that_NEVER_used_this_sink_is_NEVER_judged_by_it(tmp_path, monkeypatch):
    """The guard that fixes 8 false positives found while building this.

    The health sink is written PER TASK. Patrolling a lane that belongs to a different
    task (or is MLflow-backed) against a sink full of another task's records must not
    read as "absent from config" — it is absent from a file it never wrote to.
    """
    rc, out, alerts = _patrol(monkeypatch, tmp_path,
                              [_record(d, OTHER, "ok", status=S.STATUS_OK)
                               for d in DAYS],
                              lane=S.WatchedLane(name="a_lane_from_another_task",
                                                 runs_db=None, mlruns_dir=None,
                                                 purpose=None))
    assert rc == 0 and out == [] and alerts == [], (rc, out, alerts)


def test_the_prior_appearance_may_be_OUTSIDE_the_window(tmp_path, monkeypatch):
    """Otherwise a lane removed longer ago than the window is unprovable — which is
    precisely the case that has gone unnoticed the longest."""
    monkeypatch.setattr(S, "SHADOW_HEALTH_JSONL", _sink(tmp_path, PRIOR))
    assert S.lane_ever_reported_here(S._matches_shadow_lane) is True


# --- orch#765: task-level evidence scoped to the pinned config identity ------

def _stamped(rec, digest):
    rec = dict(rec)
    rec["task_config_sha256"] = digest
    rec["task_config_path"] = "/x/strategy_config.json"
    return rec


def _cfg_file(tmp_path):
    p = tmp_path / "strategy_config.json"
    p.write_text('{"ranking": {"panel_scoring": {"shadow_models": []}}}',
                 encoding="utf-8")
    import hashlib
    return str(p), "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def test_scoping_a_MATCHING_stamp_still_counts_as_removal_evidence(tmp_path):
    cfg, digest = _cfg_file(tmp_path)
    rows = [_stamped(_record(d, S.TASK_LEVEL_SHADOW_NAME, S.STATE_NO_SHADOW_MODELS), digest)
            for d in DAYS]
    import unittest.mock as m
    with m.patch.object(S, "SHADOW_HEALTH_JSONL", _sink(tmp_path, rows)):
        states, ambiguous, unavailable = S.read_task_level_states(DAYS, config_path=cfg)
    assert set(states.values()) == {S.STATE_NO_SHADOW_MODELS}
    assert not ambiguous


def test_scoping_a_MISMATCHED_stamp_is_another_profiles_record(tmp_path):
    """The measured shadow_blend vector: its stamped no_shadow_models must
    NOT become evidence about the pinned config."""
    cfg, _digest = _cfg_file(tmp_path)
    rows = [_stamped(_record(d, S.TASK_LEVEL_SHADOW_NAME, S.STATE_NO_SHADOW_MODELS),
                     "sha256:" + "ab" * 8) for d in DAYS]
    import unittest.mock as m
    with m.patch.object(S, "SHADOW_HEALTH_JSONL", _sink(tmp_path, rows)):
        states, ambiguous, unavailable = S.read_task_level_states(DAYS, config_path=cfg)
    assert not states
    assert not ambiguous


def test_scoping_an_UNSTAMPED_record_is_ambiguous_not_evidence(tmp_path):
    cfg, _digest = _cfg_file(tmp_path)
    rows = [_record(d, S.TASK_LEVEL_SHADOW_NAME, S.STATE_NO_SHADOW_MODELS) for d in DAYS]
    import unittest.mock as m
    with m.patch.object(S, "SHADOW_HEALTH_JSONL", _sink(tmp_path, rows)):
        states, ambiguous, unavailable = S.read_task_level_states(DAYS, config_path=cfg)
    assert not states
    assert set(ambiguous.values()) == {S.STATE_NO_SHADOW_MODELS}


def test_scoping_INACTIVE_without_a_config_keeps_the_240_contract(tmp_path):
    rows = [_record(d, S.TASK_LEVEL_SHADOW_NAME, S.STATE_NO_SHADOW_MODELS) for d in DAYS]
    import unittest.mock as m
    with m.patch.object(S, "SHADOW_HEALTH_JSONL", _sink(tmp_path, rows)):
        states, ambiguous, unavailable = S.read_task_level_states(DAYS)
    assert set(states.values()) == {S.STATE_NO_SHADOW_MODELS}
    assert not ambiguous


def test_scoping_an_UNREADABLE_config_excludes_all_evidence(tmp_path):
    """Round-2 review: an EXPLICIT config whose digest cannot be established
    must not fall back to the unscoped path — every task-level record is
    ambiguous, none count as removal evidence, and the flag says so."""
    rows = [_stamped(_record(d, S.TASK_LEVEL_SHADOW_NAME,
                             S.STATE_NO_SHADOW_MODELS), "sha256:" + "cd" * 8)
            for d in DAYS]
    import unittest.mock as m
    with m.patch.object(S, "SHADOW_HEALTH_JSONL", _sink(tmp_path, rows)):
        states, ambiguous, unavailable = S.read_task_level_states(
            DAYS, config_path=str(tmp_path / "does_not_exist.json"))
    assert unavailable is True
    assert not states
    assert set(ambiguous.values()) == {S.STATE_NO_SHADOW_MODELS}
