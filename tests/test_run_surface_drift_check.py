"""Tests for ops/run_surface_drift_check.py (GOAL-5 AC2).

Real temporary git repos for the checkout checks; fixture plists +
manifests for the launchd surface. The drill case: a daily104 swapped to a
/tmp sell-only wrapper (the 2026-07-15 silent containment) MUST alarm.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops"))

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
    #: 2026-08-03 22:58Z: ALL THREE declared-pending jobs were installed under
    #: the operator's 104/105 perfection directive (ops-audit,
    #: rq104-model-freshness, rq104-silent-refusal — bootstrap verified, first
    #: hand-runs logged real findings). The silent-refusal install surfaced a
    #: superseded twin plist (ops/renquant104/…-sentinel.plist, 07-29: python
    #: direct invocation, weekly Sun 08:11, `-sentinel` label) disagreeing with
    #: the 07-31 REVIEWED deploy/ copy (wrapper, daily 16:00); the reviewed
    #: surface won and the twin was deleted. Empty until a future reviewed job
    #: declares a pending state by name.
    PENDING_INSTALL: set[str] = set()

    #: Jobs REMOVED from the reviewed surface whose plist is still installed on
    #: the operator machine, pending the uninstall item of a tracked grant.
    #: Mirror of PENDING_INSTALL, equally bounded: each entry must name its
    #: decision record and its removal path, and the exact-equality test below
    #: goes red the moment the plist is actually booted out — the entry (and
    #: this relaxation) must then be deleted, so the set cannot rot. The
    #: SCHEDULED drift scan (com.renquant.run-surface-drift running
    #: ops/run_surface_drift_check.py) does NOT read this set and keeps
    #: alarming "unmanifested job on disk" until the bootout — per the
    #: containment protocol that alarm is the DESIGNED reminder, not a defect.
    #: 2026-08-02 22:48Z: the weekly-retrain-patchtst bootout EXECUTED under
    #: the operator's verbal grant (orch#755 checklist item c; decision
    #: orch#741) — the entry left this set in the same change, exactly as the
    #: exact-equality test below was designed to force. Empty until a future
    #: retirement declares a pending state by name.
    PENDING_UNINSTALL: set[str] = set()

    _PENDING_PATTERN = "manifested job {label} missing from disk"
    _UNMANIFESTED_PATTERN = "unmanifested com.renquant job on disk: "

    @staticmethod
    def _surface_problems():
        import os
        if not os.path.isdir(os.path.expanduser("~/Library/LaunchAgents")):
            import pytest
            pytest.skip("not on the operator machine")
        return list(drift.check_launchd_surface())

    def _partition(self):
        """(pending-install labels, pending-uninstall labels, residual problems).

        EVERY problem lands in exactly one bucket. There is no silently-ignored
        category — which is what the first version of the 2026-07-31 retarget
        had, and what codex rejected. An unmanifested job NOT named in
        PENDING_UNINSTALL falls through to residual and fails by default.
        """
        pending, retiring, residual = set(), set(), []
        for prob in self._surface_problems():
            if "missing from disk" in prob and "manifested job " in prob:
                pending.add(prob.split("manifested job ")[1].split(" missing")[0])
                continue
            if self._UNMANIFESTED_PATTERN in prob:
                label = prob.split(self._UNMANIFESTED_PATTERN)[1].split(" ")[0]
                if label in self.PENDING_UNINSTALL:
                    retiring.add(label)
                    continue
            residual.append(prob)
        return pending, retiring, residual

    def test_no_unmanifested_job_runs_on_disk(self):
        """STRICT except the named PENDING_UNINSTALL set. A job on disk but
        absent from the manifest is code nobody approved — the "silent
        containment / job swap" shape. The ONE exception is a job whose removal
        from the manifest IS the reviewed change (orch#741 retirement) with the
        bootout a named item of a tracked grant; anything unnamed still fails
        here via the residual bucket."""
        _, _, residual = self._partition()
        assert [p for p in residual if "unmanifested" in p] == []

    def test_NO_residual_problem_of_any_other_kind(self):
        """The one my first retarget missed (codex BLOCKER on this PR).

        That version kept only "unmanifested" plus the named missing-from-disk
        set and IGNORED everything else — so an installed job whose
        ProgramArguments or hash had drifted from the reviewed manifest produced
        a problem that BOTH new tests passed over. The old exact `== []` caught
        it; my replacement had re-opened it.

        The two pending allow-lists may relax installation PRESENCE only, in
        both directions (declared-not-yet-installed, retired-not-yet-removed).
        Agreement between an installed job and its reviewed manifest entry is
        never relaxed. Asserting the RESIDUAL rather than naming forbidden
        categories is the point: strings nobody has anticipated fail by default.
        """
        _, _, residual = self._partition()
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
        pending, _, _ = self._partition()
        assert pending == self.PENDING_INSTALL, (
            f"declared-but-uninstalled set changed: "
            f"unexpected={sorted(pending - self.PENDING_INSTALL)} "
            f"resolved={sorted(self.PENDING_INSTALL - pending)}")

    def test_retired_but_still_installed_jobs_are_exactly_the_named_set(self):
        """Exact-equality mirror of the pending-install bound. Once the operator
        boots the plist out, `retiring` loses the label and this goes red with
        resolved=[...]: the PENDING_UNINSTALL entry must then be deleted in a
        follow-up PR. The relaxation cannot outlive the state it names."""
        _, retiring, _ = self._partition()
        assert retiring == self.PENDING_UNINSTALL, (
            f"retired-but-still-installed set changed: "
            f"unexpected={sorted(retiring - self.PENDING_UNINSTALL)} "
            f"resolved={sorted(self.PENDING_UNINSTALL - retiring)}")



# --- AC5 has a scheduled surface declared (2026-07-31) -----------------------
def test_ac5_silent_refusal_sentinel_is_manifested():
    """GOAL-5 AC5's sentinel is merged to main and had NO scheduled surface.

    Measured 2026-07-31: absent from ops/launchd_manifest.json and from
    `launchctl list`; run by hand for the first time it immediately found
    weekly-retrain-patchtst dead for four weeks (3 crashes on one corpus-drift
    error). "AC5 merged" and "AC5 deployed" were four weeks apart.

    This pins the DECLARATION. Installing the plist is a separate machine
    landing; until then the drift scan reports the job missing from disk, and
    that alarm is the intended, tracked reminder.
    """
    import hashlib
    manifest = json.loads((REPO / "ops" / "launchd_manifest.json").read_text())["jobs"]
    label = "com.renquant.rq104-silent-refusal"
    assert label in manifest, sorted(manifest)
    spec = manifest[label]
    assert spec["program_args"][-1].endswith(
        "ops/renquant104/run_silent_refusal_sentinel.sh"), spec
    assert spec["program_args_sha256"] == hashlib.sha256(
        json.dumps(spec["program_args"]).encode()).hexdigest()
    # DATED evidence, not an append-only .out. The exit code alone cannot separate
    # "found a silent refusal" from "crashed" (#622), and an undated append-only
    # stream cannot be attributed to any run at all (#663).
    assert "silent_refusal_20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].log" in spec["evidence_glob"]


def test_the_committed_plist_matches_the_manifest_entry():
    """A plist that disagrees with the manifest is the drift this repo exists to
    catch — it must not ship disagreeing with itself on day one."""
    import plistlib
    label = "com.renquant.rq104-silent-refusal"
    pl = plistlib.loads((REPO / "deploy" / f"{label}.plist").read_bytes())
    manifest = json.loads((REPO / "ops" / "launchd_manifest.json").read_text())["jobs"]
    assert pl["Label"] == label
    assert pl["ProgramArguments"] == manifest[label]["program_args"]
    # runs AFTER the 15:00 degradation sentinel so a day's refusals are already
    # classified, and the two alarms never interleave
    assert pl["StartCalendarInterval"]["Hour"] == 16
    # launchd sinks are for output from a run that never reached its own dated
    # evidence; the readable record is the wrapper's silent_refusal_<date>.log.
    assert pl["StandardOutPath"].endswith("launchd_silent_refusal.out")
    assert pl["StandardErrorPath"].endswith("launchd_silent_refusal.err")
    assert pl["EnvironmentVariables"]["RQ_ORCH_ROOT"]



# --- every emitted line must carry its own date (2026-07-31) ------------------
class TestOutputLinesCarryTheirDate:
    """The StandardOutPath is append-only with no date in its filename.

    Measured 2026-07-31: 0 of 18 lines began with a date, and the file held a
    CONTAINMENT alarm that had already been resolved — indistinguishable from a
    live one. These pin the leading stamp on every path out of `main`.
    """

    STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2} ")

    def _run(self, monkeypatch, capsys, *, problems, infos):
        # STOP ENUMERATING. This block used to list the producers by hand and went
        # stale on the 5th, the 7th, the 8th and then the 9th -- each time silently,
        # each time discovered by a red suite rather than by the list. The comment I
        # left last time said the next producer would break it; it did, one round
        # later.
        #
        # The shape is read from HOW main() USES each call, by AST:
        #     `p, i = fn()`        -> returns a pair
        #     `problems += fn()`   -> returns a list
        # My first attempt derived it from the return ANNOTATION and broke on
        # check_umbrella_deploy_lag, which has none. An annotation is a decoration;
        # the call site is the contract.
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(drift.main))
        pair, single = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                fn = getattr(node.value.func, "id", None)
                if fn and isinstance(node.targets[0], ast.Tuple):
                    pair.add(fn)
            if isinstance(node, ast.AugAssign) and isinstance(node.value, ast.Call):
                fn = getattr(node.value.func, "id", None)
                if fn:
                    single.add(fn)
        producers = (pair | single) - {"check_git_surfaces"}
        assert len(producers) >= 6, producers      # anti-vacuity: it must find them
        for name in sorted(producers):
            if not hasattr(drift, name):
                continue
            monkeypatch.setattr(
                drift, name,
                (lambda *a, **k: ([], [])) if name in pair else (lambda *a, **k: []))
        monkeypatch.setattr(
            drift, "check_git_surfaces", lambda: (list(problems), list(infos)))
