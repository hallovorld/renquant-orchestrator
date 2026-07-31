"""GOAL-5 — "not loaded" hides three different situations with three remedies.

`check_launchd_loaded` deliberately does not ALARM on an unloaded job: it would fire
on every job an operator has deliberately unloaded. That decision is right. Saying
nothing at all is not — a job in the REVIEWED manifest that is not loaded is either a
manifest nobody updated on retirement, or a job that silently fell out of launchd, and
nothing distinguishes those.

These tests classify a SYNTHETIC manifest against a MOCKED launchd. The first version
of this file called the live macOS launchd and pinned the census of this laptop
(`n == 6`), which is not a property of the code: Linux CI has no launchd at all, read
0 unloaded jobs, and went red — while two of the tests passed locally for exactly the
reason they failed there. A test whose subject is the operator's disk measures the
disk, not the classifier. The live census now lives in
`doc/progress/2026-07-31-manifested-not-loaded.md` as a dated observation, where a
changing machine is expected rather than a build failure.
"""

from __future__ import annotations

import json
import plistlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
import run_surface_drift_check as D  # noqa: E402

#: (label suffix, plist installed?, target file exists?) -> the kind it must land in.
BOTH_PRESENT = ("retired", True, True)          # -> retired_or_silently_unloaded
PLIST_ABSENT = ("uninstalled", False, True)     # -> never_installed
TARGET_ABSENT = ("unsynced", False, False)      # -> run_checkout_unsynced


def _fixture(tmp_path, jobs, monkeypatch):
    """jobs: (suffix, has_plist, has_target, launchd_status). Returns (args, labels).

    Nothing here touches the machine's own manifest, LaunchAgents directory or
    launchctl: the manifest is written into tmp_path, the agents dir is tmp_path's,
    and launchd is replaced by a lookup table.
    """
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    manifest_jobs: dict[str, dict] = {}
    status_by_label: dict[str, str] = {}
    labels: dict[str, str] = {}
    for suffix, has_plist, has_target, status in jobs:
        label = f"com.renquant.{suffix}"
        labels[suffix] = label
        target = tmp_path / f"{suffix}.sh"
        if has_target:
            target.write_text("#!/bin/sh\n")
        args = ["/bin/bash", str(target)]
        manifest_jobs[label] = {"program_args": args,
                                "program_args_sha256": D.program_args_digest(args)}
        if has_plist:
            with open(agents / f"{label}.plist", "wb") as fh:
                plistlib.dump({"Label": label, "ProgramArguments": args}, fh)
        status_by_label[label] = status
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"jobs": manifest_jobs}))
    monkeypatch.setattr(D, "read_loaded_program_args",
                        lambda label: (status_by_label[label], None, ""))
    return (str(manifest), str(agents)), labels


def _all_three_kinds(tmp_path, monkeypatch, also=()):
    jobs = [(*spec, D.LOADED_NOT_LOADED)
            for spec in (BOTH_PRESENT, PLIST_ABSENT, TARGET_ABSENT)]
    return _fixture(tmp_path, jobs + list(also), monkeypatch)


def _kind_line(infos, kind):
    hits = [i for i in infos if f"[{kind}]" in i]
    assert len(hits) <= 1, hits
    return hits[0] if hits else ""


def test_the_three_kinds_are_classified_from_plist_and_target_presence(
        tmp_path, monkeypatch):
    """The whole point of the report: each kind has a different remedy, so each is
    named separately and a label appears under exactly one of them."""
    args, labels = _all_three_kinds(tmp_path, monkeypatch)
    _p, infos = D.report_manifested_not_loaded(*args)
    expected = {"retired_or_silently_unloaded": labels["retired"],
                "never_installed": labels["uninstalled"],
                "run_checkout_unsynced": labels["unsynced"]}
    for kind, label in expected.items():
        line = _kind_line(infos, kind)
        assert label in line, (kind, line)
        for other in set(expected.values()) - {label}:
            assert other not in line, (kind, other, line)


def test_a_LOADED_job_is_not_reported_at_all(tmp_path, monkeypatch):
    """Anti-vacuity for the test above: if the classifier listed every manifested
    job, it would still pass. A loaded job must be absent from every line."""
    args, labels = _all_three_kinds(
        tmp_path, monkeypatch, also=[("running", True, True, D.LOADED_OK)])
    _p, infos = D.report_manifested_not_loaded(*args)
    assert labels["running"] not in "\n".join(infos)
    assert infos[0] == "launchd: 3 of 4 manifested job(s) are NOT loaded", infos[0]


def test_a_BLIND_launchctl_is_not_counted_as_an_unloaded_job(tmp_path, monkeypatch):
    """`unreadable`/`unparsed` mean the checker could not see, not that the job is
    gone. Counting them as unloaded would manufacture a run-checkout-unsynced finding
    for every job at once the moment a permission change or a macOS output-shape
    change broke the read — and `check_launchd_loaded` already ALARMS on that status,
    which is the right place for it.

    This is also what the CI failure was made of: on Linux every label reads
    `unreadable`, so the report must be empty rather than 43 spurious findings.
    """
    jobs = [("blind1", True, True, D.LOADED_UNREADABLE),
            ("blind2", False, False, D.LOADED_UNPARSED),
            (*BOTH_PRESENT, D.LOADED_NOT_LOADED)]
    args, labels = _fixture(tmp_path, jobs, monkeypatch)
    _p, infos = D.report_manifested_not_loaded(*args)
    text = "\n".join(infos)
    assert labels["blind1"] not in text and labels["blind2"] not in text
    assert infos[0] == "launchd: 1 of 3 manifested job(s) are NOT loaded", infos[0]


def test_it_never_returns_a_PROBLEM_for_an_unloaded_job(tmp_path, monkeypatch):
    """The load-bearing constraint: it must not undo the deliberate decision in
    `check_launchd_loaded` by adding the alarm through a side door. Asserted over a
    fixture where all three kinds are PRESENT — the earlier version asserted it
    against live launchd, so in CI it was asserting that a report over ZERO unloaded
    jobs raises no alarm, which nothing could have failed."""
    args, _labels = _all_three_kinds(tmp_path, monkeypatch)
    problems, infos = D.report_manifested_not_loaded(*args)
    assert problems == [], problems
    assert len(infos) >= 4, infos       # head + three kinds


def test_the_indistinguishability_is_stated_when_that_kind_is_PRESENT(
        tmp_path, monkeypatch):
    args, _labels = _all_three_kinds(tmp_path, monkeypatch)
    _p, infos = D.report_manifested_not_loaded(*args)
    assert any("RETIRED or fell out of launchd silently" in i for i in infos)


def test_the_indistinguishability_is_NOT_stated_when_that_kind_is_ABSENT(
        tmp_path, monkeypatch):
    """Pairs with the test above. Without this one, a sentence appended
    unconditionally to every report would pass both — and would then be asserting an
    ambiguity about jobs that are not in that state."""
    jobs = [(*PLIST_ABSENT, D.LOADED_NOT_LOADED), (*TARGET_ABSENT, D.LOADED_NOT_LOADED)]
    args, _labels = _fixture(tmp_path, jobs, monkeypatch)
    _p, infos = D.report_manifested_not_loaded(*args)
    assert not any("RETIRED or fell out" in i for i in infos), infos
    assert _kind_line(infos, "retired_or_silently_unloaded") == ""


def test_an_unreadable_manifest_is_a_PROBLEM_not_an_empty_report(tmp_path):
    """A reporter that goes quiet when its input is missing is indistinguishable
    from one that found nothing."""
    problems, infos = D.report_manifested_not_loaded(str(tmp_path / "nope.json"))
    assert len(problems) == 1 and "unreadable" in problems[0]
    assert infos == []
