"""A task-level health record must survive the READER, not just the parser.

`renquant-pipeline#240` made the zero-shadow health record name its lane
`__task_level__` so it would stop being discarded. Reviewed `[codex on pipeline#240]`:

> *"the producer-side normalization belongs in renquant-pipeline, but it does not make
> the task-level record visible to the deployed consumer. The orchestrator reader
> accepts a valid record and then retains it only when its `shadow_name` matches a
> watched lane. `__task_level__` matches no configured lane, so the record is still
> dropped before classification; exercising `is_valid_v1_record` alone tests parsing,
> not the consumer path the PR claims to repair."*

Correct on every point — the producer half alone changed nothing a consumer could see.
This file is the coordinated consumer change's regression, and it runs records through
the REAL reader (`read_health_records`) and the REAL classifier (`classify`), not
through the validator.

THE OPERATIONAL OUTCOME, which the review also asked to be stated. A day on which the
shadow task ran and found no shadow models is `status=expected_skip`,
`state=no_shadow_models`, and `expected_skip` is deliberately QUIET. The win is not that
the sentinel stops alarming — it is WHY it stays quiet:

  * before: the record was dropped, the day fell through to the fallback, and a lane
    with no runs DB yields `feed_present=False` -> **FEED_DARK**, an alarm manufactured
    out of a healthy no-op;
  * after: the day carries an explicit "the task ran, there were no shadow models"
    record, and is quiet **for a stated reason** rather than by accident.

Silence that is indistinguishable from a missing check is the failure mode this whole
programme is about, so a quiet outcome only counts when the evidence for it arrived.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
sys.path.insert(0, str(ROOT / "ops" / "renquant104"))

_spec = importlib.util.spec_from_file_location(
    "_sentinel_taskrec", ROOT / "ops" / "renquant104" / "rq104_shadow_scorer_sentinel.py")
S = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = S
_spec.loader.exec_module(S)

DAY = dt.date(2026, 7, 30)


def _record(shadow_name, *, status, state, **over):
    rec = {
        "schema": "shadow_scorer_health.v1",
        "run_date": DAY.isoformat(),
        "shadow_name": shadow_name,
        "status": status,
        "state": state,
        "loaded": False,
        "n_scored": 0,
        "actionable": status != S.STATUS_FAULT,
        "reasons": [],
    }
    rec.update(over)
    return rec


@pytest.fixture()
def sink(tmp_path, monkeypatch):
    """Point the reader at a temp JSONL and silence both fallbacks.

    The fallbacks are silenced deliberately. Without that, the first version of
    `test_a_record_for_ANOTHER_lane_is_still_dropped` passed the sink stage and then
    read a record out of THIS MACHINE'S shadow runs DB
    (`source='shadow_runs_db_fallback'`) — so the assertion was about the operator's
    disk, not about the reader. That is the defect this programme has caught five times
    in two days, and it appeared inside the test written to fix a sixth.

    These tests are about one edge: sink -> reader -> classifier. The fallbacks have
    their own tests.
    """
    path = tmp_path / "shadow_health.jsonl"
    monkeypatch.setattr(S, "SHADOW_HEALTH_JSONL", str(path))
    monkeypatch.setattr(S, "_read_from_shadow_db", lambda *a, **k: {})
    monkeypatch.setattr(S, "_read_from_mlflow", lambda *a, **k: {})

    def write(*records):
        with path.open("w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        return path
    return write


def test_a_task_level_record_REACHES_the_classifier(sink):
    """THE repair. Before the consumer change this record was dropped at the reader
    and the day came back `None`."""
    sink(_record(S.TASK_LEVEL_SHADOW_NAME,
                 status=S.STATUS_EXPECTED_SKIP, state="no_shadow_models"))
    got = S.read_health_records([DAY])
    assert got[DAY] is not None, "the task-level record was dropped before classification"
    assert got[DAY].shadow_name == S.TASK_LEVEL_SHADOW_NAME
    verdict, reasons = S.classify(got[DAY])
    assert verdict == S.HEALTHY, (verdict, reasons)


def test_a_record_for_ANOTHER_lane_is_still_dropped(sink):
    """ANTI-VACUITY. Without this, the fix could be "retain everything", which would
    make the sentinel report a different lane's health as its own."""
    written = sink(_record("some_other_lane", status=S.STATUS_FAULT,
                           state="load_failed"))
    assert written.exists() and written.read_text().strip(), "fixture wrote nothing"
    # the reader stage codex named, asserted directly...
    assert S._read_from_pipeline_sink([DAY]) == {}
    # ...and nothing sink-sourced survives to the classifier.
    assert S.read_health_records([DAY])[DAY] is None


def test_the_lanes_OWN_record_still_reaches_the_classifier(sink):
    """Control: the ordinary path must be untouched by the task-level allowance."""
    sink(_record(S.SHADOW_NAME, status=S.STATUS_OK, state="ok",
                 loaded=True, n_scored=42))
    got = S.read_health_records([DAY])
    assert got[DAY] is not None and got[DAY].shadow_name == S.SHADOW_NAME
    assert S.classify(got[DAY])[0] == S.HEALTHY


def test_a_LANE_SPECIFIC_record_is_not_clobbered_by_a_later_task_level_line(sink):
    """Precedence, and it is not hypothetical: the reader is last-record-wins per date.

    A task-level record explains an ABSENCE. If the lane actually reported that day,
    the lane's own record is the more specific evidence, and a task-level line written
    afterwards must not overwrite it — otherwise a real lane FAULT could be silenced by
    a subsequent "the task skipped" line for the same date.
    """
    sink(_record(S.SHADOW_NAME, status=S.STATUS_FAULT, state="load_failed",
                 reasons=["artifact would not load"]),
         _record(S.TASK_LEVEL_SHADOW_NAME,
                 status=S.STATUS_EXPECTED_SKIP, state="no_shadow_models"))
    got = S.read_health_records([DAY])
    assert got[DAY].shadow_name == S.SHADOW_NAME, "a task-level line clobbered the lane"
    verdict, reasons = S.classify(got[DAY])
    assert verdict == S.LOAD_FAIL and reasons == ["artifact would not load"]


def test_the_reverse_order_ALSO_keeps_the_lane_record(sink):
    """Pairs with the test above so the precedence is about SPECIFICITY, not order."""
    sink(_record(S.TASK_LEVEL_SHADOW_NAME,
                 status=S.STATUS_EXPECTED_SKIP, state="no_shadow_models"),
         _record(S.SHADOW_NAME, status=S.STATUS_FAULT, state="load_failed",
                 reasons=["artifact would not load"]))
    got = S.read_health_records([DAY])
    assert got[DAY].shadow_name == S.SHADOW_NAME
    assert S.classify(got[DAY])[0] == S.LOAD_FAIL


def test_a_task_level_FAULT_still_alarms(sink):
    """The allowance must not become a blanket silencer. `__task_level__` decides
    WHICH records are visible, never whether they are faults — `status` does that."""
    sink(_record(S.TASK_LEVEL_SHADOW_NAME, status=S.STATUS_FAULT,
                 state="not_scored", reasons=["shadow task raised"]))
    got = S.read_health_records([DAY])
    verdict, reasons = S.classify(got[DAY])
    assert verdict == S.LOAD_FAIL and reasons == ["shadow task raised"]


def test_the_constant_matches_the_producers(sink):
    """The two repos agree on the literal by test, not by import.

    The consumer deliberately does NOT import `TASK_LEVEL_SHADOW_NAME` from
    renquant-pipeline: this sentinel has to keep reading records on a host whose
    pipeline predates the constant, and a failed import would silently restore the
    drop. The cost of duplicating a literal is that the two can diverge — so it is
    pinned here, and pipeline#240 pins the same string on its side.
    """
    assert S.TASK_LEVEL_SHADOW_NAME == "__task_level__"
    assert S._is_task_level("__task_level__") is True
    assert S._is_task_level(S.SHADOW_NAME) is False
    assert S._is_task_level("__task_level__x") is False
