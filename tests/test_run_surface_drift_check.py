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

    def test_committed_manifest_matches_live_surface(self):
        """The repo's committed manifest must describe the CURRENT machine —
        a stale manifest would alarm on every firing. (Skipped off-machine.)"""
        import os
        if not os.path.isdir(os.path.expanduser("~/Library/LaunchAgents")):
            import pytest
            pytest.skip("not on the operator machine")
        problems = drift.check_launchd_surface()
        assert problems == [], f"committed manifest is stale: {problems[:3]}"


#: Jobs DECLARED on the reviewed surface whose plist is not installed yet.
#: orch#666 introduces the canonical copy of this set as
#: TestManifestGeneration.PENDING_INSTALL; when both branches land, DELETE this
#: one and import that. Two copies of a set that must stay in sync is the twin
#: shape this org keeps a registry for — recorded here so the duplication is
#: temporary by construction rather than by good intentions.
_PENDING_INSTALL = {
    "com.renquant.ops-audit",
    "com.renquant.rq104-model-freshness",
}


def test_every_pending_install_job_ships_an_installable_plist():
    """A job declared on the reviewed surface with no committed plist can only be
    installed by authoring one on the spot, unreviewed — which defeats the point
    of declaring it first.

    Measured 2026-07-31 before this change: BOTH pending jobs
    (com.renquant.ops-audit, com.renquant.rq104-model-freshness) had no plist
    under deploy/.

    The first version of this test exempted ops-audit BY NAME because its wrapper
    was still unmerged. orch#650 has since MERGED, so `ops/run_ops_audit.sh` is on
    main and the exemption is gone — the rule is now universal over every pending
    job, with NO allow-list. An exemption that outlives its reason is how a
    temporary carve-out becomes permanent.
    """
    import plistlib
    repo = Path(__file__).resolve().parent.parent
    manifest = json.loads((repo / "ops" / "launchd_manifest.json").read_text())["jobs"]
    # every job DECLARED in the manifest but absent from deploy/ would be
    # uninstallable without authoring a plist on the spot, unreviewed
    for label in sorted(_PENDING_INSTALL):
        path = repo / "deploy" / f"{label}.plist"
        assert path.exists(), f"{label} declared with no installable plist"
        pl = plistlib.loads(path.read_bytes())
        assert pl["Label"] == label
        assert pl["ProgramArguments"] == manifest[label]["program_args"], label
        assert pl["StandardOutPath"] and pl["StandardErrorPath"], label
        assert pl["EnvironmentVariables"]["RQ_ORCH_ROOT"], label
    # ordering: ops-audit 06:30 -> drift 07:00 -> freshness 07:30, so the
    # aggregate verdict is on disk before the narrower jobs fire
    hours = {l: plistlib.loads((repo / "deploy" / f"{l}.plist").read_bytes())
             ["StartCalendarInterval"]["Hour"]
             for l in _PENDING_INSTALL}
    assert hours["com.renquant.ops-audit"] < hours["com.renquant.rq104-model-freshness"]
