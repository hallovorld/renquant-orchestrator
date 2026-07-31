"""Tests for ops/run_surface_drift_check.py (GOAL-5 AC2).

Real temporary git repos for the checkout checks; fixture plists +
manifests for the launchd surface. The drill case: a daily104 swapped to a
/tmp sell-only wrapper (the 2026-07-15 silent containment) MUST alarm.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))

import run_surface_drift_check as drift  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
    )
    return res.stdout.strip()


def _make_repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "f.txt").write_text("v1\n")
    _git(repo, "add", "f.txt")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c1")
    return repo


class TestCheckoutChecks:
    def test_clean_at_pin_ok(self, tmp_path):
        repo = _make_repo(tmp_path, "r1")
        head = _git(repo, "rev-parse", "HEAD")
        problems, infos = drift.check_checkout(str(repo), head, "runtime/r1")
        assert problems == []

    def test_wrong_head_alarm(self, tmp_path):
        repo = _make_repo(tmp_path, "r1")
        problems, _ = drift.check_checkout(str(repo), "0" * 40, "runtime/r1")
        assert any("!= expected" in p for p in problems)

    def test_tracked_modification_alarm(self, tmp_path):
        repo = _make_repo(tmp_path, "r1")
        head = _git(repo, "rev-parse", "HEAD")
        (repo / "f.txt").write_text("hotfix\n")  # the un-upstreamed hotfix case
        problems, _ = drift.check_checkout(str(repo), head, "runtime/r1")
        assert any("uncommitted tracked change" in p for p in problems)

    def test_untracked_is_info_not_alarm(self, tmp_path):
        repo = _make_repo(tmp_path, "r1")
        head = _git(repo, "rev-parse", "HEAD")
        (repo / "scratch.log").write_text("x")
        problems, infos = drift.check_checkout(str(repo), head, "runtime/r1")
        assert problems == []
        assert any("untracked" in i for i in infos)

    def test_missing_checkout_alarm(self, tmp_path):
        problems, _ = drift.check_checkout(str(tmp_path / "nope"), None, "runtime/x")
        assert any("missing" in p for p in problems)


def _write_plist(agents: Path, label: str, program_args: list[str]) -> None:
    import plistlib
    with open(agents / f"{label}.plist", "wb") as fh:
        plistlib.dump({"Label": label, "ProgramArguments": program_args}, fh)


def _manifest(agents: Path, path: Path) -> None:
    m = {"jobs": drift.scan_launchd_plists(str(agents))}
    path.write_text(json.dumps(m))


class TestLaunchdSurface:
    def test_matching_surface_ok(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        _write_plist(agents, "com.renquant.daily104", ["/repo/scripts/daily_104.sh"])
        mpath = tmp_path / "manifest.json"
        _manifest(agents, mpath)
        assert drift.check_launchd_surface(str(mpath), str(agents)) == []

    def test_silent_containment_swap_alarms(self, tmp_path):
        """The 2026-07-15 incident drill: daily104 swapped to a /tmp wrapper."""
        agents = tmp_path / "agents"
        agents.mkdir()
        _write_plist(agents, "com.renquant.daily104", ["/repo/scripts/daily_104.sh"])
        mpath = tmp_path / "manifest.json"
        _manifest(agents, mpath)
        _write_plist(agents, "com.renquant.daily104", ["/tmp/renquant104-sell-only-guard.sh"])
        problems = drift.check_launchd_surface(str(mpath), str(agents))
        assert any("CHANGED" in p and "daily104" in p for p in problems)

    def test_unmanifested_job_alarms(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        mpath = tmp_path / "manifest.json"
        _manifest(agents, mpath)  # empty manifest
        _write_plist(agents, "com.renquant.new-job", ["/x.sh"])
        problems = drift.check_launchd_surface(str(mpath), str(agents))
        assert any("unmanifested" in p for p in problems)

    def test_manifested_job_missing_from_disk_alarms(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        _write_plist(agents, "com.renquant.daily104", ["/repo/scripts/daily_104.sh"])
        mpath = tmp_path / "manifest.json"
        _manifest(agents, mpath)
        (agents / "com.renquant.daily104.plist").unlink()
        problems = drift.check_launchd_surface(str(mpath), str(agents))
        assert any("missing from disk" in p for p in problems)

    def test_disabled_and_bak_files_ignored(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        _write_plist(agents, "com.renquant.daily104", ["/repo/scripts/daily_104.sh"])
        mpath = tmp_path / "manifest.json"
        _manifest(agents, mpath)
        # backup/disabled artifacts must not register as unmanifested jobs
        (agents / "com.renquant.open104.plist.disabled.20260513").write_text("junk")
        (agents / "com.renquant.daily104.plist.bak.20260502").write_text("junk")
        assert drift.check_launchd_surface(str(mpath), str(agents)) == []

    def test_unreadable_manifest_alarms(self, tmp_path):
        problems = drift.check_launchd_surface(str(tmp_path / "nope.json"), str(tmp_path))
        assert any("unreadable" in p for p in problems)


class TestManifestGeneration:
    def test_manifest_round_trips_clean(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        _write_plist(agents, "com.renquant.a", ["/a.sh", "--x"])
        _write_plist(agents, "com.renquant.b", ["/b.sh"])
        m = drift.generate_manifest(str(agents))
        mpath = tmp_path / "m.json"
        mpath.write_text(json.dumps(m))
        assert drift.check_launchd_surface(str(mpath), str(agents)) == []

    #: Jobs DECLARED on the reviewed run surface that are not yet installed.
    #: Declaring before installing is deliberate (the manifest is the reviewed
    #: surface, the plist on disk is the live one; declaring first gives the
    #: install something to be checked against). Each entry must be named here,
    #: so the set cannot grow silently into manifest rot.
    PENDING_INSTALL = {
        # aggregator for the six ops detectors — orch#650
        "com.renquant.ops-audit",
        # model-freshness monitor — declared before this session
        "com.renquant.rq104-model-freshness",
    }

    _PENDING_PATTERN = "manifested job {label} missing from disk"

    @staticmethod
    def _surface_problems():
        import os
        if not os.path.isdir(os.path.expanduser("~/Library/LaunchAgents")):
            import pytest
            pytest.skip("not on the operator machine")
        return list(drift.check_launchd_surface())

    def _partition(self):
        """(pending-missing labels, residual problems).

        EVERY problem lands in exactly one bucket. There is no third,
        silently-ignored category — which is what the first version of this
        retarget had, and what codex rejected.
        """
        pending, residual = set(), []
        for prob in self._surface_problems():
            if "missing from disk" in prob and "manifested job " in prob:
                pending.add(prob.split("manifested job ")[1].split(" missing")[0])
            else:
                residual.append(prob)
        return pending, residual

    def test_no_unmanifested_job_runs_on_disk(self):
        """STRICT, no allow-list. A job on disk but absent from the manifest is
        code nobody approved — the "silent containment / job swap" shape."""
        assert [p for p in self._surface_problems() if "unmanifested" in p] == []

    def test_NO_residual_problem_of_any_other_kind(self):
        """The one my first retarget missed (codex BLOCKER on this PR).

        That version kept only "unmanifested" plus the named missing-from-disk
        set and IGNORED everything else — so an installed job whose
        ProgramArguments or hash had drifted from the reviewed manifest produced
        a problem that BOTH new tests passed over. The old exact `== []` caught
        it; my replacement had re-opened it.

        The pending allow-list may relax installation ABSENCE only. Agreement
        between an installed job and its reviewed manifest is never relaxed.
        Asserting the RESIDUAL rather than naming forbidden categories is the
        point: strings nobody has anticipated fail by default.
        """
        _, residual = self._partition()
        assert residual == [], residual

    def test_declared_but_uninstalled_jobs_are_exactly_the_named_set(self):
        """RETARGETED 2026-07-31, deliberately, and it was red for months.

        The old assertion was `check_launchd_surface() == []` — the manifest must
        match the live surface EXACTLY. The system deliberately violates that: a
        job may be declared on the reviewed surface before its plist is
        installed, and com.renquant.rq104-model-freshness has been in that state
        all along. So it failed on the operator's machine on every branch, and a
        permanently-red test trains its reader to ignore local failures.

        This bounds the ONE relaxation; the residual test above forbids the rest.
        """
        pending, _ = self._partition()
        assert pending == self.PENDING_INSTALL, (
            f"declared-but-uninstalled set changed: "
            f"unexpected={sorted(pending - self.PENDING_INSTALL)} "
            f"resolved={sorted(self.PENDING_INSTALL - pending)}")


