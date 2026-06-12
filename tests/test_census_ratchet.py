"""Gate-writer census ratchet (eng plan S2-PR4 / errata C(iii)).

Enforced in CI only (CENSUS_ENFORCE=1, where sibling checkouts are
pinned to main by the workflow); locally the sibling renquant-pipeline
working checkout tracks the DEPLOYED pin, which legitimately predates
recent retirements — enforcing there would punish merged-not-deployed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RATCHET = ROOT / "scripts" / "engineering" / "census_ratchet.json"


@pytest.mark.skipif(os.environ.get("CENSUS_ENFORCE") != "1",
                    reason="ratchet enforced in CI only (siblings @ main)")
def test_gate_writer_ratchet():
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from renquant_orchestrator.engineering_census import build_engineering_census

    pipeline_src = ROOT.parent / "renquant-pipeline" / "src"
    assert pipeline_src.exists(), (
        f"renquant-pipeline sibling missing at {pipeline_src} — a missing "
        f"census subject must FAIL, not pass with count=0")
    ratchet = json.loads(RATCHET.read_text())
    census = build_engineering_census(github_root=ROOT.parent)
    count = census["gate_writers"]["count"]
    assert count <= ratchet["max_buy_blocked_writers"], (
        f"gate writers grew: census={count} > "
        f"ratchet={ratchet['max_buy_blocked_writers']} — new gates must "
        f"submit to the GateRegistry, never write buy_blocked "
        f"(writers: {[w['file'] for w in census['gate_writers']['writers']]})")
    assert ratchet["max_buy_blocked_writers"] >= ratchet["floor"]


def test_ratchet_file_well_formed():
    ratchet = json.loads(RATCHET.read_text())
    assert isinstance(ratchet["max_buy_blocked_writers"], int)
    assert ratchet["floor"] == 3  # the three designated choke points
