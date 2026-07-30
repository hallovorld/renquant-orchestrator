"""#623 R2 generalised: which copy would a reader edit?

R2 cost five weeks of `book_to_price = 1.68e19` because a fix landed on the umbrella's
dead `fetch_sec_fundamentals.py` while the live producer was in `renquant-base-data`.
This pins the whole shadow surface so a new one cannot appear unregistered.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parent.parent / "ops"
_SPEC = importlib.util.spec_from_file_location(
    "umbrella_script_shadow_check", OPS / "umbrella_script_shadow_check.py")
sh = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sh)

REG = json.loads((OPS / "umbrella_script_shadows.json").read_text())


def test_the_committed_registry_verifies_clean():
    assert sh.verify(REG) == []


def test_the_measured_shape_is_pinned():
    """These counts ARE the finding. If one moves, the finding moved."""
    pairs = REG["pairs"]
    assert len(pairs) == 44
    assert sum(1 for v in pairs.values() if v["class"] == sh.DIVERGED) == 26
    assert sum(1 for v in pairs.values() if v["class"] == sh.IDENTICAL) == 18
    assert sum(1 for v in pairs.values()
               if v["referenced_by_a_scheduled_surface"]) == 12


def test_r2_itself_is_NOT_caught_and_that_limit_is_documented():
    """The instance that motivated this tool is OUTSIDE its reach, and that must stay
    visible rather than being assumed covered.

    R2 is umbrella `fetch_sec_fundamentals.py` vs base-data `sec_fundamentals.py` —
    **different stems**. This sweep matches on identical stem, so it cannot see a
    renamed twin, which is precisely the kind hardest to spot by eye. Anyone reading
    "44 shadow pairs registered" must not conclude the twin surface is covered.
    """
    assert "fetch_sec_fundamentals.py" not in REG["pairs"], (
        "the sweep now catches R2 — widen this test and the documented scope together")
    src = (OPS / "umbrella_script_shadow_check.py").read_text()
    assert "SCOPE LIMIT" in src and "fetch_sec_fundamentals.py" in src, (
        "the limitation must be stated in the tool, not only in a test")


def test_matching_is_by_stem_so_the_scope_claim_is_checkable():
    src = (OPS / "umbrella_script_shadow_check.py").read_text()
    assert "Path(line).stem" in src, (
        "if matching stops being stem-based the documented scope limit is stale")


# --- the check must be able to FAIL ------------------------------------------

def test_an_unregistered_shadow_is_reported():
    reg = copy.deepcopy(REG)
    victim = next(iter(reg["pairs"]))
    del reg["pairs"][victim]
    problems = sh.verify(reg)
    assert len(problems) == 1 and "NEW shadow" in problems[0]


def test_a_registered_pair_that_no_longer_shadows_is_reported():
    reg = copy.deepcopy(REG)
    reg["pairs"]["definitely_not_a_real_script.py"] = {
        "subrepo": "x", "subrepo_path": "y", "class": sh.IDENTICAL,
        "umbrella_bytes": 1, "subrepo_bytes": 1,
        "referenced_by_a_scheduled_surface": False}
    problems = sh.verify(reg)
    assert len(problems) == 1 and "no longer shadows" in problems[0]


def test_a_class_change_is_reported():
    """Two copies converging or diverging is exactly the event worth knowing about."""
    reg = copy.deepcopy(REG)
    name = next(n for n, v in reg["pairs"].items() if v["class"] == sh.DIVERGED)
    reg["pairs"][name]["class"] = sh.IDENTICAL
    problems = sh.verify(reg)
    assert len(problems) == 1 and "class changed" in problems[0]


def test_an_empty_registry_is_a_problem_not_a_pass():
    assert sh.verify({"pairs": {}}) != []
    assert sh.verify({}) != []


# --- safety: never git inside the umbrella -----------------------------------

def test_the_tool_never_runs_git_inside_the_umbrella():
    """A sub-agent's `git reset --hard` in that shared live checkout caused an incident.
    This asserts the source never pairs `git -C` with the umbrella path."""
    src = (OPS / "umbrella_script_shadow_check.py").read_text()
    for line in src.splitlines():
        if '"git"' in line and "-C" in line:
            assert "UMBRELLA" not in line, f"git -C against the umbrella: {line.strip()}"
    assert 'str(GITHUB / repo)' in src, "git is only ever run against sibling checkouts"


def test_subrepo_state_is_read_from_origin_main_not_the_worktree():
    """A sibling can sit on a feature branch; comparing against a checked-out tree makes
    the answer depend on someone else's uncommitted state."""
    src = (OPS / "umbrella_script_shadow_check.py").read_text()
    assert '"origin/main"' in src and 'f"origin/main:{rel}"' in src


# --- exit codes ---------------------------------------------------------------

def test_missing_registry_exits_2(tmp_path):
    assert sh.main(["--registry", str(tmp_path / "nope.json")]) == 2


def test_unreadable_registry_exits_2(tmp_path):
    p = tmp_path / "r.json"
    p.write_text("{truncated")
    assert sh.main(["--registry", str(p)]) == 2


def test_drift_exits_1(tmp_path):
    reg = copy.deepcopy(REG)
    del reg["pairs"][next(iter(reg["pairs"]))]
    p = tmp_path / "r.json"
    p.write_text(json.dumps(reg))
    assert sh.main(["--registry", str(p)]) == 1


def test_clean_exits_0():
    assert sh.main([]) == 0


def test_emit_never_writes(tmp_path, capsys):
    p = tmp_path / "r.json"
    p.write_text("SENTINEL")
    assert sh.main(["--emit", "--registry", str(p)]) == 0
    assert p.read_text() == "SENTINEL"
    assert json.loads(capsys.readouterr().out)["pairs"]
