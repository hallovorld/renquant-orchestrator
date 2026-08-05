"""The re-capture tool must fix POSITIONS and refuse everything else."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ops.renquant104.recapture_emitter_contract import recapture  # noqa: E402


def _fixture(tmp_path: Path, script_lines: list[str], rows: list[dict]):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "w.sh").write_text("\n".join(script_lines) + "\n")
    return {"lines": rows, "wrappers": {"scripts/w.sh": "0" * 16}}


def test_a_shifted_line_is_repinned_and_the_digest_refreshed(tmp_path):
    c = _fixture(tmp_path, ["#!/bin/bash", "", "", 'echo "=== DONE at $(date) ==="'],
                 [{"job": "j", "kind": "action",
                   "template": "=== DONE at $(date) ===",
                   "source": "scripts/w.sh:2"}])
    changed = recapture(c, tmp_path)
    assert c["lines"][0]["source"] == "scripts/w.sh:4"
    assert c["wrappers"]["scripts/w.sh"] != "0" * 16
    assert any("scripts/w.sh:2 -> :4" in x for x in changed)


def test_duplicate_emit_sites_are_repinned_in_order_not_collapsed(tmp_path):
    c = _fixture(tmp_path,
                 ["a", 'echo "=== X ==="', "b", "c", 'echo "=== X ==="'],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:1"},
                  {"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:4"}])
    recapture(c, tmp_path)
    assert sorted(r["source"] for r in c["lines"]) == [
        "scripts/w.sh:2", "scripts/w.sh:5"]


def test_a_VANISHED_template_refuses_it_is_not_a_line_shift(tmp_path):
    c = _fixture(tmp_path, ["a", "b"],
                 [{"job": "j", "kind": "action", "template": "=== GONE ===",
                   "source": "scripts/w.sh:1"}])
    with pytest.raises(SystemExit) as exc:
        recapture(c, tmp_path)
    assert "0 emit site(s)" in str(exc.value)


def test_an_ADDED_emit_site_refuses_rather_than_silently_pinning_one(tmp_path):
    """A second site means the lane can now emit from a branch nobody classified."""
    c = _fixture(tmp_path, ['echo "=== X ==="', 'echo "=== X ==="'],
                 [{"job": "j", "kind": "action", "template": "=== X ===",
                   "source": "scripts/w.sh:1"}])
    with pytest.raises(SystemExit) as exc:
        recapture(c, tmp_path)
    assert "2 emit site(s)" in str(exc.value) and "1 row(s)" in str(exc.value)


def test_it_never_edits_a_template(tmp_path):
    c = _fixture(tmp_path, ["", 'echo "=== DONE at $(date) ==="'],
                 [{"job": "j", "kind": "action",
                   "template": "=== DONE at $(date) ===",
                   "source": "scripts/w.sh:1"}])
    recapture(c, tmp_path)
    assert c["lines"][0]["template"] == "=== DONE at $(date) ==="


def test_the_live_contract_is_in_sync_with_the_live_wrappers():
    """Same assertion the local drift test makes, reachable as one command."""
    umbrella = Path("/Users/renhao/git/github/RenQuant")
    if not umbrella.exists():
        pytest.skip("umbrella absent — the CI-enforced contract tests still ran")
    path = (Path(__file__).resolve().parent.parent / "ops" / "renquant104"
            / "emitter_contract.json")
    contract = json.loads(path.read_text())
    assert recapture(contract, umbrella) == [], (
        "emitter contract drifted — run "
        "`python -m ops.renquant104.recapture_emitter_contract --note '<why>'`")
