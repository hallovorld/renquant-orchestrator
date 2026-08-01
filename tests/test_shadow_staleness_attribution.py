"""Two DEGRADED lanes, two different remedies — and the cheap-looking one is unfixable.

Measured as of the 2026-07-31 session: `topdecile_clf_blend_leg` is 94d stale and sits
EXACTLY on the corpus frontier (0d beyond), while `hf_patchtst` is 625d stale and 531d
beyond a frontier that was available to it. The sentinel's two alarms read identically.

The frontier is never treated as a bare fact: the rawlabel provenance currently carries an
invalidation receipt newer than its own stamp, so every verdict derived from it is marked
provisional. `UNKNOWN` is a real outcome, not a synonym for healthy.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

import pytest

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops" / "renquant104"
sys.path.insert(0, str(OPS))

import shadow_staleness_attribution as A  # noqa: E402

ASOF = dt.date(2026, 7, 31)
CERT = {"frontier": "2026-04-28", "trust": A.CERTIFIED, "why": None}


def _prov(tmp, **over):
    d = {"source_panel_frontier": "2026-04-28", "built_at": "2026-07-26T17:02:30Z"}
    d.update(over)
    p = tmp / "prov.json"
    p.write_text(json.dumps(d))
    return p


def _receipt(tmp, at="2026-07-30T20:12:50Z", reason="coverage != source panel"):
    p = tmp / "inv.json"
    p.write_text(json.dumps({"invalidated_at": at, "reason": reason}))
    return p


# ------------------------------------------------------- the discriminating result --
def test_the_clf_lane_is_FRONTIER_BOUND_at_exactly_zero_days():
    r = A.attribute("topdecile_clf_blend_leg", "stale_94d_limit_28d", ASOF, CERT)
    assert r["status"] == A.FRONTIER_BOUND
    assert r["implied_cutoff"] == "2026-04-28"
    assert r["beyond_frontier_days"] == 0
    assert "retraining this lane cannot reduce its staleness" in r["remedy"]


def test_the_patchtst_lane_is_INDEPENDENTLY_STALE_by_531_days():
    r = A.attribute("hf_patchtst", "stale_625d_limit_28d", ASOF, CERT)
    assert r["status"] == A.INDEPENDENTLY_STALE
    assert r["implied_cutoff"] == "2024-11-13"
    assert r["beyond_frontier_days"] == 531
    assert "the fault is in the lane, not the corpus" in r["remedy"]


def test_the_LARGER_number_is_the_fixable_one():
    """The inversion that makes the two identical alarms actively misleading."""
    clf = A.attribute("clf", "stale_94d_limit_28d", ASOF, CERT)
    pt = A.attribute("pt", "stale_625d_limit_28d", ASOF, CERT)
    assert pt["stale_days"] > clf["stale_days"]
    assert pt["status"] == A.INDEPENDENTLY_STALE and clf["status"] == A.FRONTIER_BOUND


def test_a_lane_FRESHER_than_the_frontier_is_still_frontier_bound_not_negative_fault():
    r = A.attribute("x", "stale_10d_limit_28d", ASOF, CERT)
    assert r["status"] == A.FRONTIER_BOUND
    assert r["beyond_frontier_days"] < 0


# ------------------------------------------------------------- frontier trust states --
def test_an_INVALIDATION_RECEIPT_newer_than_the_stamp_makes_every_verdict_provisional(tmp_path):
    f = A.read_frontier(_prov(tmp_path), _receipt(tmp_path))
    assert f["trust"] == A.INVALIDATED and f["frontier"] == "2026-04-28"
    assert A.attribute("x", "stale_94d_limit_28d", ASOF, f)["provisional"] is True


def test_an_OLDER_receipt_does_not_invalidate_a_newer_provenance(tmp_path):
    f = A.read_frontier(_prov(tmp_path, built_at="2026-07-31T00:00:00Z"),
                        _receipt(tmp_path, at="2026-07-30T20:12:50Z"))
    assert f["trust"] == A.CERTIFIED


def test_an_UNREADABLE_receipt_is_not_an_ABSENT_one(tmp_path):
    """Treating a corrupt receipt as absent would let it certify the corpus."""
    bad = tmp_path / "inv.json"
    bad.write_text("{not json")
    f = A.read_frontier(_prov(tmp_path), bad)
    assert f["trust"] == A.INVALIDATED


def test_a_receipt_with_NO_timestamp_invalidates_rather_than_being_ignored(tmp_path):
    p = tmp_path / "inv.json"
    p.write_text(json.dumps({"reason": "something"}))
    assert A.read_frontier(_prov(tmp_path), p)["trust"] == A.INVALIDATED


@pytest.mark.parametrize("prov,why", [
    ({"source_panel_frontier": 7}, "no `source_panel_frontier` string"),
    ({"source_panel_frontier": "not-a-date"}, "not a date"),
    ({}, "no `source_panel_frontier` string"),
])
def test_a_MALFORMED_provenance_yields_ABSENT_not_a_guessed_frontier(tmp_path, prov, why):
    p = tmp_path / "prov.json"
    p.write_text(json.dumps(prov))
    f = A.read_frontier(p, None)
    assert f["trust"] == A.ABSENT and f["frontier"] is None
    assert why in f["why"]


def test_a_provenance_that_is_a_LIST_does_not_raise(tmp_path):
    p = tmp_path / "prov.json"
    p.write_text("[]")
    assert A.read_frontier(p, None)["trust"] == A.ABSENT


def test_a_missing_provenance_is_ABSENT_and_attributes_NOTHING(tmp_path):
    f = A.read_frontier(tmp_path / "nope.json", None)
    r = A.attribute("x", "stale_94d_limit_28d", ASOF, f)
    assert r["status"] == A.UNKNOWN
    assert "frontier not established" in r["why"]


# ------------------------------------------------------------------------ plumbing --
def test_a_reason_with_no_stale_term_is_UNKNOWN_not_zero():
    r = A.attribute("x", "degraded: thin_coverage", ASOF, CERT)
    assert r["status"] == A.UNKNOWN and "stale_days" not in r


def test_exit_3_when_the_frontier_cannot_be_established(tmp_path):
    assert A.main(["--as-of", "2026-07-31", "--lane", "x=stale_94d_limit_28d",
                   "--provenance", str(tmp_path / "nope.json")]) == 3


def test_exit_1_only_when_a_lane_is_INDEPENDENTLY_stale(tmp_path):
    p = _prov(tmp_path)
    assert A.main(["--as-of", "2026-07-31", "--lane", "clf=stale_94d_limit_28d",
                   "--provenance", str(p)]) == 0
    assert A.main(["--as-of", "2026-07-31", "--lane", "pt=stale_625d_limit_28d",
                   "--provenance", str(p)]) == 1


def test_a_bad_as_of_is_a_usage_error_not_a_clean_run(tmp_path):
    assert A.main(["--as-of", "nope", "--lane", "x=stale_1d_limit_2d",
                   "--provenance", str(_prov(tmp_path))]) == 2


def test_json_mode_carries_the_trust_state(tmp_path, capsys):
    A.main(["--as-of", "2026-07-31", "--lane", "pt=stale_625d_limit_28d",
            "--provenance", str(_prov(tmp_path)),
            "--invalid-receipt", str(_receipt(tmp_path)), "--json"])
    rep = json.loads(capsys.readouterr().out)
    assert rep["frontier"]["trust"] == A.INVALIDATED
    assert rep["lanes"][0]["provisional"] is True
    assert rep["n_independently_stale"] == 1
