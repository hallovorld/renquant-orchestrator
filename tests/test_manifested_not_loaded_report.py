"""GOAL-5 — "not loaded" hides three different situations with three remedies.

`check_launchd_loaded` deliberately does not ALARM on an unloaded job: it would fire
on every job an operator has deliberately unloaded. That decision is right. Saying
nothing at all is not — a job in the REVIEWED manifest that is not loaded is either a
manifest nobody updated on retirement, or a job that silently fell out of launchd, and
nothing distinguishes those.

So this reports, and never alarms. Measured 2026-08-01 on 43 manifested jobs: 6 not
loaded, across all three kinds.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "ops", "run_surface_drift_check.py")


def _load():
    spec = importlib.util.spec_from_file_location("drift_notloaded", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


D = _load()


def test_it_never_returns_a_PROBLEM_for_an_unloaded_job():
    """The load-bearing constraint: it must not undo the deliberate decision in
    `check_launchd_loaded` by adding the alarm through a side door."""
    problems, infos = D.report_manifested_not_loaded()
    assert problems == [], problems
    assert infos, "reporting nothing is the failure mode this replaces"


def test_the_three_kinds_are_named_separately():
    _p, infos = D.report_manifested_not_loaded()
    text = "\n".join(infos)
    for kind in ("retired_or_silently_unloaded", "never_installed",
                 "run_checkout_unsynced"):
        assert kind in text, kind


def test_the_indistinguishability_is_stated_not_implied():
    _p, infos = D.report_manifested_not_loaded()
    assert any("RETIRED or fell out of launchd silently" in i for i in infos)


def test_an_unreadable_manifest_is_a_PROBLEM_not_an_empty_report(tmp_path):
    """A reporter that goes quiet when its input is missing is indistinguishable
    from one that found nothing."""
    problems, infos = D.report_manifested_not_loaded(str(tmp_path / "nope.json"))
    assert len(problems) == 1 and "unreadable" in problems[0]
    assert infos == []


def test_the_live_count_matches_the_documented_measurement():
    _p, infos = D.report_manifested_not_loaded()
    head = infos[0]
    assert "of 43 manifested job(s) are NOT loaded" in head
    n = int(head.split("launchd: ")[1].split(" of ")[0])
    assert n == 6, head
