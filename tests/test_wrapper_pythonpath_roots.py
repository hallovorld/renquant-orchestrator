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
def test_five_SCHEDULED_wrappers_currently_use_a_fallback():
    """Was 6 in #675 — that count included `run_liveness_check.sh`, which carries
    the idiom and which NOTHING SCHEDULES."""
    problems, _ = D.check_wrapper_pythonpath_roots(
        os.path.join(ROOT, "ops"), "/nonexistent-repos-root")
    sites = [p for p in problems if "by FALLBACK" in p]
    assert len(sites) == 5, problems


def test_the_unscheduled_wrapper_is_excluded_by_the_inventory():
    inv = D._scheduled_wrappers(os.path.join(ROOT, "ops", "launchd_manifest.json"),
                                os.path.join(ROOT, "ops"))
    paths = {os.path.basename(p) for _, p in inv if p}
    assert "run_liveness_check.sh" not in paths
    assert "run_shadow_serving.sh" in paths
