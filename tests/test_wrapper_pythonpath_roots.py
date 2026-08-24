"""GOAL-3 #623 — every SCHEDULED wrapper must declare one deterministic root.

Codex review of #675: the first version derived its subject list from the fallback
regex itself, so a **repaired** fleet was indistinguishable from a fleet with no
wrappers — fix every wrapper and the scan finds nothing, which the anti-vacuity guard
then reports as a problem. **A drift check that cannot go green after the documented
remediation is a ratchet, not a check.**

The inventory now comes from `ops/launchd_manifest.json`, independently of the defect.
That change also corrected the count: the previous PR said **6** wrappers carry the
fallback; **5** of them are scheduled. `ops/renquant105/run_liveness_check.sh` carries
it and **nothing runs it** — `com.renquant.rq105-liveness` executes
`rq105_liveness_check.py`, per both the manifest and the installed plist. Counting a
copy that does not execute is the exact defect #623 catalogues, committed by the check
built to find it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "ops", "run_surface_drift_check.py")


def _load():
    spec = importlib.util.spec_from_file_location("drift_pypath", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


D = _load()

FALLBACK = ('X="$(dirname "$R")/sib-run/src"\n'
            '[ -d "$X" ] || X="$(dirname "$R")/sib/src"\n'
            'export PYTHONPATH="$X"\n')
REMEDIATED = ('X="$(dirname "$R")/sib-run/src"\n'
              'export PYTHONPATH="$X"\n')


def _fixture(tmp_path, body, job="com.renquant.x", name="w.sh"):
    ops = tmp_path / "ops"
    ops.mkdir(parents=True, exist_ok=True)
    (ops / name).write_text(body, encoding="utf-8")
    man = tmp_path / "manifest.json"
    man.write_text(json.dumps({job: {"program_args": ["/anywhere/ops/" + name]}}),
                   encoding="utf-8")
    return str(ops), str(man)


# ------------------------------------------------------------- convergence --
def test_a_REMEDIATED_wrapper_passes(tmp_path):
    """THE property the first version lacked. One explicit root, no fallback,
    no problem — the check can go green after the remediation it documents."""
    ops, man = _fixture(tmp_path, REMEDIATED)
    problems, infos = D.check_wrapper_pythonpath_roots(ops, str(tmp_path), man)
    assert problems == [], problems
    assert any("deterministic root" in i for i in infos)


def test_the_nested_quote_fallback_is_still_detected(tmp_path):
    """Regression fixture kept: the real wrappers write a value containing NESTED
    double quotes, which a `[^"]*` class cannot span. My first regex did exactly
    that and matched nothing."""
    ops, man = _fixture(tmp_path, FALLBACK)
    problems, _ = D.check_wrapper_pythonpath_roots(ops, str(tmp_path), man)
    assert len(problems) == 1
    assert "by FALLBACK" in problems[0]


def test_a_fallback_that_does_NOT_fire_is_still_a_problem(tmp_path):
    """Unreviewed is unreviewed. A fallback landing on the right checkout today
    is luck, not review."""
    ops, man = _fixture(tmp_path, FALLBACK)
    (tmp_path / "sib-run" / "src").mkdir(parents=True)      # preferred EXISTS
    problems, _ = D.check_wrapper_pythonpath_roots(ops, str(tmp_path), man)
    assert len(problems) == 1
    assert "does not fire today" in problems[0]


# ------------------------------------------------------------- anti-vacuity --
def test_an_empty_inventory_is_a_PROBLEM_not_a_pass(tmp_path):
    """The only anti-vacuity condition left, and it is about the INVENTORY —
    never about whether the defect is still present."""
    ops = tmp_path / "ops"
    ops.mkdir()
    man = tmp_path / "m.json"
    man.write_text("{}", encoding="utf-8")
    problems, _ = D.check_wrapper_pythonpath_roots(str(ops), str(tmp_path), str(man))
    assert len(problems) == 1 and "no subjects" in problems[0]


def test_an_unreadable_manifest_is_reported_not_skipped(tmp_path):
    problems, _ = D.check_wrapper_pythonpath_roots(
        str(tmp_path), str(tmp_path), str(tmp_path / "nope.json"))
    assert len(problems) == 1 and "cannot read the scheduled inventory" in problems[0]


# -------------------------------------------------------------- live state --
def test_no_SCHEDULED_wrapper_uses_a_fallback_any_more():
    """This asserted `len(sites) == 5` until orch#1016 removed the idiom.

    A count-the-defect test has to be flipped when the defect goes, not deleted:
    the scan's convergence property — that a REMEDIATED fleet reads clean — is
    the thing most easily lost, and the docstring on
    `check_wrapper_pythonpath_roots` promises it explicitly ("A check that cannot
    go green after the documented remediation is not a check, it is a ratchet").
    Its partner is `test_a_planted_fallback_is_still_detected` below: green here
    must mean "no fallback", never "the scan stopped looking".
    """
    problems, infos = D.check_wrapper_pythonpath_roots(
        os.path.join(ROOT, "ops"), "/nonexistent-repos-root")
    sites = [p for p in problems if "by FALLBACK" in p]
    assert not sites, sites
    assert infos, "the scan produced no findings at all — it inspected nothing"


def test_a_planted_fallback_is_still_detected(tmp_path):
    """The control for the test above. Without it, deleting the matcher passes."""
    wrapper = tmp_path / "run_planted.sh"
    wrapper.write_text(
        '#!/bin/zsh\n'
        'RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"\n'
        '[ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"\n'
    )
    problems: list[str] = []
    infos: list[str] = []
    D._scan_wrapper_text("planted", wrapper.read_text(), str(tmp_path), problems, infos)
    assert any("by FALLBACK" in p for p in problems), problems


def test_the_unscheduled_wrapper_is_excluded_by_the_inventory():
    inv = D._scheduled_wrappers(os.path.join(ROOT, "ops", "launchd_manifest.json"),
                                os.path.join(ROOT, "ops"))
    paths = {os.path.basename(p) for _, _declared, p in inv if p}
    assert "run_liveness_check.sh" not in paths
    assert "run_shadow_serving.sh" in paths


# ---------------------------------------------------------------------------
# Codex on #675: an unresolvable manifest wrapper must not be an info line.
# ---------------------------------------------------------------------------

def _manifest(tmp_path, jobs, boundaries=None):
    """A synthetic manifest, so these tests measure the CONTRACT, not this machine.

    Every assertion below would otherwise depend on which wrappers happen to exist in
    the operator's checkout -- the "tests that measure the operator's disk" shape.
    """
    m = {"jobs": jobs}
    if boundaries is not None:
        m["wrapper_scope_boundaries"] = boundaries
    p = tmp_path / "m.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return str(p)


def test_an_unresolvable_wrapper_with_no_declared_owner_is_a_PROBLEM(tmp_path):
    """The inverted default. Previously this produced an info line and a clean exit."""
    mp = _manifest(tmp_path, {
        "com.renquant.ghost": {"program_args": ["/nowhere/at/all/ghost_job.sh"]}})
    problems, _ = D.check_wrapper_pythonpath_roots(
        os.path.join(ROOT, "ops"), "/nonexistent-repos-root", mp)
    assert any("ghost_job.sh" in p and "not covered by any declared scope boundary" in p
               for p in problems), problems


def test_a_wrapper_under_a_DECLARED_boundary_is_out_of_scope_and_names_its_owner(tmp_path):
    mp = _manifest(
        tmp_path,
        {"com.renquant.elsewhere": {"program_args": ["/other/repo/scripts/x.sh"]}},
        boundaries=[{"root": "/other/repo/scripts", "owner": "other-repo",
                     "why": "checked by other-repo's own scan"}])
    problems, infos = D.check_wrapper_pythonpath_roots(
        os.path.join(ROOT, "ops"), "/nonexistent-repos-root", mp)
    assert not [p for p in problems if "x.sh" in p], problems
    line = [i for i in infos if "x.sh" in i]
    assert line and "other-repo" in line[0] and "NOT inspected here" in line[0], infos


def test_every_wrapper_missing_no_longer_returns_CLEAN(tmp_path):
    """The exact fail-open codex named: a nonempty inventory, zero wrappers read.

    Two independent guards must fire -- each unowned wrapper, and the fact that
    nothing at all was inspected. A clean report over an empty set is a statement
    about nothing.
    """
    mp = _manifest(tmp_path, {
        f"com.renquant.j{i}": {"program_args": [f"/nowhere/j{i}.sh"]} for i in range(3)})
    problems, _ = D.check_wrapper_pythonpath_roots(
        os.path.join(ROOT, "ops"), "/nonexistent-repos-root", mp)
    assert len([p for p in problems if "not covered by any declared" in p]) == 3
    assert any("NONE inspected" in p for p in problems), problems


def test_a_declared_boundary_cannot_hide_a_wrapper_that_IS_present(tmp_path):
    """Scope is about absence only.

    If the wrapper resolves, it gets read regardless of any boundary -- otherwise a
    boundary entry would become a way to exempt a live wrapper from inspection, which
    is a much bigger hole than the one being closed.
    """
    wrapper = tmp_path / "real.sh"
    wrapper.write_text(
        'RQ_COMMON_SRC="/a/renquant-common-run/src"\n'
        '[ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="/a/renquant-common/src"\n'
        'export PYTHONPATH="$RQ_COMMON_SRC"\n', encoding="utf-8")
    ops_dir = str(tmp_path)
    mp = _manifest(
        tmp_path,
        {"com.renquant.present": {"program_args": [f"/anything/ops/{wrapper.name}"]}},
        boundaries=[{"root": "/anything", "owner": "someone-else", "why": "n/a"}])
    problems, _ = D.check_wrapper_pythonpath_roots(ops_dir, "/nonexistent-repos-root", mp)
    assert any("by FALLBACK" in p for p in problems), problems


def test_the_longest_matching_boundary_root_wins(tmp_path):
    """A nested owner must not be absorbed by the tree containing it."""
    mp = _manifest(
        tmp_path,
        {"com.renquant.nested": {"program_args": ["/top/inner/deep/j.sh"]}},
        boundaries=[{"root": "/top", "owner": "outer", "why": "broad"},
                    {"root": "/top/inner", "owner": "INNER", "why": "specific"}])
    _, infos = D.check_wrapper_pythonpath_roots(
        os.path.join(ROOT, "ops"), "/nonexistent-repos-root", mp)
    line = [i for i in infos if "j.sh" in i]
    assert line and "INNER" in line[0], infos


def test_a_boundary_root_is_a_path_prefix_not_a_substring(tmp_path):
    """`/top` must not own `/topsecret/...` -- prefix matching on raw strings is a
    classic way for a scope declaration to silently swallow a neighbour."""
    mp = _manifest(
        tmp_path,
        {"com.renquant.neighbour": {"program_args": ["/topsecret/j.sh"]}},
        boundaries=[{"root": "/top", "owner": "outer", "why": "broad"}])
    problems, _ = D.check_wrapper_pythonpath_roots(
        os.path.join(ROOT, "ops"), "/nonexistent-repos-root", mp)
    assert any("j.sh" in p for p in problems), problems


def test_coverage_is_reported_as_a_fraction_of_the_manifest(tmp_path):
    """"13 inspected" reads like full coverage; "13 of 33" does not."""
    _, infos = D.check_wrapper_pythonpath_roots(os.path.join(ROOT, "ops"))
    line = [i for i in infos if "manifested wrapper(s) inspected here" in i]
    assert line, infos
    assert " of " in line[0] and "unowned" in line[0], line


# -------- #682 option 2: read-only inspection across a declared boundary --------


def _xrepo_fixture(tmp_path, body, inspect="read-only-here"):
    """A manifested wrapper OUTSIDE ops/, covered by a boundary in inspect mode."""
    outside = tmp_path / "umbrella" / "scripts"
    outside.mkdir(parents=True, exist_ok=True)
    wrapper = outside / "far.sh"
    if body is not None:
        wrapper.write_text(body, encoding="utf-8")
    ops = tmp_path / "ops"
    ops.mkdir(parents=True, exist_ok=True)
    man = tmp_path / "manifest.json"
    boundary = {"root": str(outside), "owner": "umbrella (test)",
                "why": "test boundary"}
    if inspect:
        boundary["inspect"] = inspect
    man.write_text(json.dumps({
        "jobs": {"com.renquant.far": {"program_args": ["/bin/bash", str(wrapper)]}},
        "wrapper_scope_boundaries": [boundary],
    }), encoding="utf-8")
    return str(ops), str(tmp_path), str(man)


def test_xrepo_fallback_wrapper_is_a_PROBLEM_with_the_boundary_named(tmp_path):
    ops, root, man = _xrepo_fixture(tmp_path, FALLBACK)
    problems, _ = D.check_wrapper_pythonpath_roots(ops, root, man)
    hits = [p for p in problems if "FALLBACK" in p]
    assert len(hits) == 1
    assert "read-only across the repo boundary" in hits[0]
    assert "umbrella (test)" in hits[0]


def test_xrepo_clean_wrapper_is_INSPECTED_and_counted(tmp_path):
    ops, root, man = _xrepo_fixture(tmp_path, REMEDIATED)
    problems, infos = D.check_wrapper_pythonpath_roots(ops, root, man)
    assert not [p for p in problems if "FALLBACK" in p]
    assert any("1 inspected read-only across a declared boundary" in i
               for i in infos), infos
    # anti-vacuity: a cross-repo read IS an inspection, so no "NONE inspected"
    assert not [p for p in problems if "NONE inspected" in p]


def test_xrepo_UNREADABLE_subject_is_a_problem_not_a_skip(tmp_path):
    ops, root, man = _xrepo_fixture(tmp_path, body=None)   # file never written
    problems, _ = D.check_wrapper_pythonpath_roots(ops, root, man)
    assert [p for p in problems if "cannot be read" in p and "NO scan" in p]


def test_a_boundary_WITHOUT_inspect_mode_stays_out_of_scope(tmp_path):
    ops, root, man = _xrepo_fixture(tmp_path, FALLBACK, inspect=None)
    problems, infos = D.check_wrapper_pythonpath_roots(ops, root, man)
    # the legacy claim shape is preserved: not inspected, said out loud
    assert not [p for p in problems if "FALLBACK" in p]
    assert any("OUT OF SCOPE" in i and "NOT inspected" in i for i in infos)


def test_the_LIVE_manifest_declares_umbrella_scripts_inspected():
    """Pin the #682 remediation: the real boundary carries the inspect mode, so a
    future edit that quietly drops it re-opens the 19-wrapper gap loudly here."""
    man = json.load(open(os.path.join(ROOT, "ops", "launchd_manifest.json")))
    scripts = [b for b in man["wrapper_scope_boundaries"]
               if b["root"].endswith("/RenQuant/scripts")]
    assert len(scripts) == 1
    assert scripts[0].get("inspect") == "read-only-here"
