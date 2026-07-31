"""A run bundle persisted to /tmp is evidence designed to disappear.

This programme already has the failure this guards against: the live WF-gate
incumbent's `sanity_manifest_path` is `/tmp/gbdt_manifest_abs.json` and **the file no
longer exists**, so its PASS cannot be re-derived from its own record. A run bundle
written to `/tmp` reproduces that by construction — `/tmp` is cleared on reboot and,
because the flag takes a fixed path, each session overwrites the last regardless.

Scope is deliberately narrow: **run bundles only.** Rehearsal intermediates under
`/tmp/renquant-live-rehearsal/` are scratch by design and are not touched here.
"""

from __future__ import annotations

import pytest

# Imported as a package member, not via spec_from_file_location: the module uses
# relative imports (`from .runtime_paths import ...`), so loading it as a standalone
# file raises ImportError. Loading a module a different way than production does is
# the wrong-object trap in miniature.
from renquant_orchestrator import scheduled_jobs as sj

#: Flags whose VALUE is a run bundle that must outlive the session.
BUNDLE_FLAGS = ("--bridge-bundle-output",)


def _commands(payload) -> list[tuple[str, list]]:
    out = []
    for job in payload["jobs"]:
        # rehearsal_command is included ON PURPOSE: it is where the bridge jobs
        # actually declare --bridge-bundle-output. My first version checked only
        # `command` and `native_cutover_command`, found nothing, and would have been a
        # guard over an empty set — caught by the anti-vacuity test below.
        for key in ("command", "rehearsal_command", "native_cutover_command"):
            cmd = job.get(key)
            if cmd:
                out.append((f"{job.get('job_id', '?')}.{key}", list(cmd)))
    return out


def test_no_scheduled_job_writes_a_run_bundle_into_tmp():
    """THE REGRESSION. Both daily and live bridge jobs pointed at /tmp."""
    offenders = []
    for name, cmd in _commands(sj.inventory_payload()):
        for i, arg in enumerate(cmd[:-1]):
            if str(arg) in BUNDLE_FLAGS and str(cmd[i + 1]).startswith("/tmp"):
                offenders.append((name, cmd[i + 1]))
    assert offenders == [], (
        f"run bundles persisted to /tmp — evidence designed to disappear: {offenders}")


def test_the_bundle_flag_is_still_present_so_the_guard_is_not_vacuous():
    """If the flag were dropped entirely the test above would pass for the wrong
    reason. At least one job must still declare a bundle output."""
    found = [
        (name, cmd[i + 1])
        for name, cmd in _commands(sj.inventory_payload())
        for i, arg in enumerate(cmd[:-1])
        if str(arg) in BUNDLE_FLAGS
    ]
    assert found, "no job declares --bridge-bundle-output; the /tmp guard checks nothing"


def test_every_declared_bundle_path_is_absolute_and_under_a_repo_root():
    for name, cmd in _commands(sj.inventory_payload()):
        for i, arg in enumerate(cmd[:-1]):
            if str(arg) in BUNDLE_FLAGS:
                val = str(cmd[i + 1])
                assert val.startswith("/"), f"{name}: {val!r} is not absolute"
                assert "/logs/" in val, (
                    f"{name}: {val!r} is not under a logs/ directory — bundles belong "
                    f"beside the session logs they describe")


@pytest.mark.parametrize("bad", ["/tmp/x.json", "/tmp/renquant/x.json"])
def test_the_guard_actually_fires_on_a_tmp_path(bad):
    """Prove the check can FAIL. A guard exercising only the happy path certifies
    nothing."""
    cmd = ["renquant-orchestrator", "run-job", "x", "--", "--bridge-bundle-output", bad]
    offenders = [
        (i, cmd[i + 1]) for i, a in enumerate(cmd[:-1])
        if a in BUNDLE_FLAGS and cmd[i + 1].startswith("/tmp")
    ]
    assert offenders, "the detection logic missed an obvious /tmp bundle path"
