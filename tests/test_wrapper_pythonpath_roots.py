"""GOAL-3 #623 — which CHECKOUT a scheduled job imports from, decided by `ls`.

#623 rows R2/R3/R5/R6 share one shape: a defect filed against a copy that does not
run, because nothing said which copy executes. `check_import_resolution` pins the
symbols resolved in the SCANNER's own process — a different object. A wrapper builds
its own PYTHONPATH, so a symbol can resolve as reviewed in the scanner and
differently inside the job.

Measured 2026-07-31: six rq105 wrappers prefer `renquant-common-run/src`, which does
not exist on this machine, and silently fall back to the dev checkout — then sitting
on branch `fix/ntfy-non-ascii-title`, three commits behind origin/main.
"""

from __future__ import annotations

import importlib.util
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


def _wrapper(tmp_path, name="w.sh", preferred="sib-run/src", fallback="sib/src"):
    d = tmp_path / "ops"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(
        'X="$(dirname "$R")/%s"\n[ -d "$X" ] || X="$(dirname "$R")/%s"\n'
        'export PYTHONPATH="$X"\n' % (preferred, fallback),
        encoding="utf-8")
    return str(d)


def test_the_nested_quote_shape_is_actually_parsed(tmp_path):
    """Regression on MY OWN bug: the real wrappers write
    `X="$(dirname "$R")/…-run/src"`, whose value contains nested double quotes, so a
    `[^"]*` class matches nothing. My first regex did exactly that and found zero
    sites — only the residual assertion stopped it reading as clean."""
    ops = _wrapper(tmp_path)
    repos = tmp_path / "repos"
    (repos / "sib" / "src").mkdir(parents=True)
    problems, infos = D.check_wrapper_pythonpath_roots(ops, str(repos))
    assert len(problems) == 1
    assert "no checkout-fallback idiom found" not in problems[0]


def test_a_fired_fallback_is_LOUD(tmp_path):
    ops = _wrapper(tmp_path)
    repos = tmp_path / "repos"
    (repos / "sib" / "src").mkdir(parents=True)          # only the fallback exists
    problems, _ = D.check_wrapper_pythonpath_roots(ops, str(repos))
    assert "is ABSENT" in problems[0]
    assert "chosen by filesystem state" in problems[0]


def test_a_satisfied_preference_is_quiet(tmp_path):
    """CONTROL. Without this the check would flag the idiom itself, not the drift."""
    ops = _wrapper(tmp_path)
    repos = tmp_path / "repos"
    (repos / "sib-run" / "src").mkdir(parents=True)
    (repos / "sib" / "src").mkdir(parents=True)
    problems, infos = D.check_wrapper_pythonpath_roots(ops, str(repos))
    assert problems == []
    assert len(infos) == 1 and "present" in infos[0]


def test_neither_root_existing_is_a_DIFFERENT_problem(tmp_path):
    ops = _wrapper(tmp_path)
    repos = tmp_path / "repos"
    repos.mkdir()
    problems, _ = D.check_wrapper_pythonpath_roots(ops, str(repos))
    assert "cannot import its sibling at all" in problems[0]


def test_finding_no_idiom_is_a_PROBLEM_not_a_pass(tmp_path):
    """A check that goes quiet when its pattern stops matching is the exact shape
    #623 catalogues. This one already caught my broken regex."""
    d = tmp_path / "ops"
    d.mkdir()
    (d / "plain.sh").write_text("echo hi\n", encoding="utf-8")
    problems, _ = D.check_wrapper_pythonpath_roots(str(d), str(tmp_path))
    assert len(problems) == 1
    assert "no checkout-fallback idiom found" in problems[0]


def test_the_live_repo_has_six_such_wrappers():
    """Pins the measurement the progress doc reports."""
    problems, infos = D.check_wrapper_pythonpath_roots(
        os.path.join(ROOT, "ops"), "/nonexistent-repos-root")
    sites = [p for p in problems if p.startswith("pythonpath renquant105/")]
    assert len(sites) == 6, problems
