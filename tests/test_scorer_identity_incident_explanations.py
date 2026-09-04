"""A RECORDED incident explains exactly one scorer-identity boundary.

2026-08-31 07:17:50 PDT the live-tree pull truncated the git-tracked momentum
ledger (5 rows → 1); the monitor's receipt/ledger-append/rollback paths can
never legitimize a same-path replacement, so from 2026-09-04 (the first full
run after the incident) it re-paged the SAME boundary CRITICAL every day —
an all-red alarm nobody reads. The committed registry
``ops/renquant104/scorer_identity_incident_explanations.json`` records that
one boundary; the loader accepts no wildcard fields and the match binds the
lane key, BOTH run ids exactly, and BOTH stamped digests.

Hermetic: synthetic runs/ledgers under tmp_path; the shipped registry is read
but nothing live is touched.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from renquant_orchestrator import scorer_identity_monitor as sim

LEDGER = "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/momentum/momentum_artifact_ledger.jsonl"
LANE = f"shadow:{LEDGER}"
PREV_SHA = "sha256:a1149c5666703b4525f352806acd5abf48d92d54d5f4c012d7448ebfe098f086"
CURR_SHA = "sha256:9aa2d8c9571bad950ed9dc50e4437504503be233a5be581b5df39bea65a047e6"
PREV_RUN = "2026-08-31-live-ba1899f8"
CURR_RUN = "2026-08-31-live-5a0c9139"


def _run(run_id: str, stamp: str, sha: str, lane: str = LANE, path: str = LEDGER) -> sim.RunIdentity:
    return sim.RunIdentity(
        run_id=run_id, run_date=stamp[:10],
        created_at=datetime.fromisoformat(stamp),
        lanes={lane: sim.LaneIdentity(lane=lane, artifact_sha=sha, artifact_path=path)},
        usable=True,
    )


def _incident(**over) -> sim.IncidentExplanation:
    base = dict(
        lane=LANE, prev_run_id=PREV_RUN, curr_run_id=CURR_RUN,
        prev_sha=PREV_SHA, curr_sha=CURR_SHA,
        reason="live-tree pull truncated the tracked ledger",
        evidence="RenQuant#638", recorded_by="test", recorded_at="2026-09-04",
    )
    base.update(over)
    return sim.IncidentExplanation(**base)


def _boundary_runs():
    return [
        _run(PREV_RUN, "2026-08-31T14:12:25+00:00", PREV_SHA),
        _run(CURR_RUN, "2026-08-31T14:24:37+00:00", CURR_SHA),
    ]


def _write_registry(path: Path, incidents: list[dict], schema: int = 1) -> Path:
    path.write_text(json.dumps({"schema_version": schema, "incidents": incidents}), encoding="utf-8")
    return path


def test_recorded_incident_explains_exactly_that_boundary():
    report = sim.evaluate(_boundary_runs(), [], incidents=[_incident()])
    assert report["status"] != sim.STATUS_CRITICAL, report["lines"]
    info = [ln for ln in report["lines"] if ln.startswith("INFO:")]
    assert info and "incident recorded 2026-09-04 by test" in info[0], info
    assert "silent scorer swap" not in "\n".join(report["lines"])


def test_without_a_record_the_truncation_is_still_critical():
    report = sim.evaluate(_boundary_runs(), [], incidents=[])
    assert report["status"] == sim.STATUS_CRITICAL
    assert any(ln.startswith("CRITICAL:") and LANE in ln for ln in report["lines"])


def test_record_binds_run_ids_lane_and_both_digests():
    for over in (
        {"prev_run_id": "2026-08-31-live-ffffffff"},
        {"curr_run_id": "2026-09-01-live-ffffffff"},
        {"lane": "shadow:/elsewhere/momentum_artifact_ledger.jsonl"},
        {"prev_sha": "sha256:" + "0" * 64},
        {"curr_sha": "sha256:" + "0" * 64},
        {"curr_sha": "sha256:9aa2d8c"},          # < 16 hex never matches
    ):
        report = sim.evaluate(_boundary_runs(), [], incidents=[_incident(**over)])
        assert report["status"] == sim.STATUS_CRITICAL, over


def test_prefix_digests_match_like_receipts_do():
    """A 16-hex record prefix binds the full stamped digest (the receipt rule)."""
    rec = _incident(prev_sha="sha256:a1149c5666703b45", curr_sha="sha256:9aa2d8c9571bad95")
    assert sim.evaluate(_boundary_runs(), [], incidents=[rec])["status"] != sim.STATUS_CRITICAL


def test_lineup_changes_are_not_eligible():
    """A lane joining/leaving is a membership change; a record cannot launder it."""
    runs = [
        _run(PREV_RUN, "2026-08-31T14:12:25+00:00", sim._ABSENT),
        _run(CURR_RUN, "2026-08-31T14:24:37+00:00", CURR_SHA),
    ]
    rec = _incident(prev_sha=sim._ABSENT)
    assert sim.evaluate(runs, [], incidents=[rec])["status"] == sim.STATUS_CRITICAL


def test_a_record_does_not_leak_onto_a_later_identical_transition():
    """Same lane, same digests, DIFFERENT run ids → unexplained (no generalising)."""
    runs = [
        _run("2026-09-10-live-aaaaaaaa", "2026-09-10T14:00:00+00:00", PREV_SHA),
        _run("2026-09-11-live-bbbbbbbb", "2026-09-11T14:00:00+00:00", CURR_SHA),
    ]
    assert sim.evaluate(runs, [], incidents=[_incident()])["status"] == sim.STATUS_CRITICAL


def test_loader_fails_closed_on_missing_malformed_or_wildcard_entries(tmp_path):
    assert sim.load_incident_explanations(None) == []
    assert sim.load_incident_explanations(tmp_path / "absent.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert sim.load_incident_explanations(bad) == []
    assert sim.load_incident_explanations(_write_registry(tmp_path / "schema.json", [], schema=2)) == []
    entry = dict(lane=LANE, prev_run_id=PREV_RUN, curr_run_id=CURR_RUN, prev_sha=PREV_SHA,
                 curr_sha=CURR_SHA, reason="r", evidence="e", recorded_by="b", recorded_at="2026-09-04")
    for missing in entry:
        broken = {k: v for k, v in entry.items() if k != missing}
        assert sim.load_incident_explanations(_write_registry(tmp_path / f"{missing}.json", [broken])) == [], missing
        blank = dict(entry, **{missing: "  "})
        assert sim.load_incident_explanations(_write_registry(tmp_path / f"{missing}_blank.json", [blank])) == [], missing
    ok = sim.load_incident_explanations(_write_registry(tmp_path / "ok.json", [entry, "not-a-dict"]))
    assert len(ok) == 1 and ok[0].curr_run_id == CURR_RUN


def test_shipped_registry_is_wellformed_and_names_the_0831_truncation_only():
    path = sim.default_incident_explanations_path()
    assert path.exists(), path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == sim.INCIDENT_EXPLANATIONS_SCHEMA
    loaded = sim.load_incident_explanations(path)
    assert len(loaded) == len(payload["incidents"]) == 1, "every shipped entry must load; one incident recorded"
    rec = loaded[0]
    assert (rec.lane, rec.prev_run_id, rec.curr_run_id) == (LANE, PREV_RUN, CURR_RUN)
    assert rec.prev_sha == PREV_SHA and rec.curr_sha == CURR_SHA
    assert "RenQuant#638" in rec.evidence
    # the shipped record explains the real boundary and nothing else
    assert sim.evaluate(_boundary_runs(), [], incidents=loaded)["status"] != sim.STATUS_CRITICAL
    later = [
        _run("2026-09-10-live-aaaaaaaa", "2026-09-10T14:00:00+00:00", PREV_SHA),
        _run("2026-09-11-live-bbbbbbbb", "2026-09-11T14:00:00+00:00", CURR_SHA),
    ]
    assert sim.evaluate(later, [], incidents=loaded)["status"] == sim.STATUS_CRITICAL


def test_cli_threads_the_registry_and_dev_null_disables_it(tmp_path, monkeypatch):
    """`--incident-explanations` reaches build_report; /dev/null loads nothing."""
    seen: dict[str, object] = {}

    def fake_build_report(**kwargs):
        seen.update(kwargs)
        return {"status": sim.STATUS_OK, "exit_code": 0, "lines": [], "summary": "ok",
                "freshness": {"warn": False}}

    monkeypatch.setattr(sim, "build_report", fake_build_report)
    reg = _write_registry(tmp_path / "reg.json", [])
    assert sim.main(["--repo-root", str(tmp_path), "--incident-explanations", str(reg), "--quiet"]) == 0
    assert Path(seen["incident_explanations_path"]) == reg
    seen.clear()
    assert sim.main(["--repo-root", str(tmp_path), "--quiet"]) == 0
    assert Path(seen["incident_explanations_path"]) == sim.default_incident_explanations_path()
    assert sim.load_incident_explanations(Path("/dev/null")) == []
