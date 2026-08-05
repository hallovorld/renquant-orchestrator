"""GOAL-6: does each serving artifact make a claim that can be CHECKED?

orch#726 filed three defects on 2026-08-01. Re-measured 2026-08-05: two were
already fixed (no `/tmp` path survives anywhere in the prod artifact or the
pinned config) and one was unchanged (the clf lane carries no
`wf_gate_metadata` in either location). Nobody noticed for four days because
checking meant reading two artifacts by hand.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops" / "renquant104"))
import serving_certification_probe as P  # noqa: E402


def _artifact(root: Path, rel: str, payload: dict):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _stamped(manifest: str | None = None):
    m = {"recipe_id": "r"}
    if manifest:
        m["sanity_manifest_path"] = manifest
    return {"metadata": {"wf_gate_metadata": m}}


class TestTheThreeShapesOrch726Found:
    def test_a_resolving_claim_is_CHECKABLE(self, tmp_path):
        man = tmp_path / "m.json"
        man.write_text("{}", encoding="utf-8")
        _artifact(tmp_path, "prod/panel-ltr.alpha158_fund.json", _stamped(str(man)))
        r = P.probe_one("x", "prod/panel-ltr.alpha158_fund.json", tmp_path)
        assert r["state"] == P.STATE_CLAIM and r["state"] not in P.ACTIONABLE

    def test_a_claim_pointing_at_a_MISSING_path_is_actionable(self, tmp_path):
        """orch#726's first two halves: worse than no claim, because it reads as
        certified."""
        _artifact(tmp_path, "prod/panel-ltr.alpha158_fund.json",
                  _stamped("/tmp/gone-forever/manifest.json"))
        r = P.probe_one("x", "prod/panel-ltr.alpha158_fund.json", tmp_path)
        assert r["state"] == P.STATE_DANGLING and r["state"] in P.ACTIONABLE
        assert "/tmp/gone-forever/manifest.json" in r["detail"]

    def test_NO_stamp_in_EITHER_location_is_actionable(self, tmp_path):
        _artifact(tmp_path, "shadow/panel-clf.top-decile.fwd60.json", {"kind": "x"})
        r = P.probe_one("x", "shadow/panel-clf.top-decile.fwd60.json", tmp_path)
        assert r["state"] == P.STATE_NO_STAMP and r["state"] in P.ACTIONABLE

    def test_the_LEGACY_top_level_key_still_counts_as_a_claim(self, tmp_path):
        """An artifact with only the legacy key DOES make a claim; calling it
        stampless would be the wrong-object error one level in."""
        _artifact(tmp_path, "prod/panel-ltr.alpha158_fund.json",
                  {"wf_gate_metadata": {"recipe_id": "r"}})
        r = P.probe_one("x", "prod/panel-ltr.alpha158_fund.json", tmp_path)
        assert r["state"] == P.STATE_CLAIM


class TestAbsenceReadsAsAbsence:
    def test_an_UNREADABLE_artifact_is_not_an_absent_claim(self, tmp_path):
        p = tmp_path / "prod/panel-ltr.alpha158_fund.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{not json", encoding="utf-8")
        r = P.probe_one("x", "prod/panel-ltr.alpha158_fund.json", tmp_path)
        assert r["state"] == P.STATE_UNREADABLE and r["state"] in P.ACTIONABLE
        assert "not an absent claim" in r["detail"]

    def test_a_MISSING_artifact_is_its_own_state(self, tmp_path):
        r = P.probe_one("x", "prod/nope.json", tmp_path)
        assert r["state"] == P.STATE_ABSENT and r["state"] in P.ACTIONABLE


def test_it_refuses_to_judge_the_claim_it_finds(tmp_path):
    """The prior question only. Conflating 'a claim exists' with 'the claim is
    good' is what let one lane's 43 folds read as coverage for a lane with zero."""
    man = tmp_path / "m.json"
    man.write_text("{}", encoding="utf-8")
    _artifact(tmp_path, "prod/panel-ltr.alpha158_fund.json", _stamped(str(man)))
    text = P.render(P.probe(tmp_path))
    assert "does NOT judge it" in text
    assert "says nothing about whether it is a good claim" in \
        P.probe(tmp_path)[0]["detail"]


def test_the_LIVE_serving_set_is_what_the_record_describes():
    """Bound to reality: prod makes a checkable claim, clf makes none. If either
    changes, orch#726/#788 must be re-derived rather than inherited."""
    if not P.ARTIFACTS.exists():
        pytest.skip("umbrella artifacts absent — the unit tests above still ran")
    rows = {r["artifact"]: r for r in P.probe()}
    prod = next(v for k, v in rows.items() if k.startswith("prod"))
    clf = next(v for k, v in rows.items() if k.startswith("clf"))
    assert prod["state"] == P.STATE_CLAIM, prod
    assert clf["state"] == P.STATE_NO_STAMP, (
        "the clf lane's stamp state changed — re-derive orch#726/#788", clf)
