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
    #: 2026-08-04 (orch#801 round 3): the fleet-lane sentinel needs NO launchd
    #: job — it runs as the daily wrapper's last step, after the Step-5e fleet
    #: legs it inspects. That removes the cadence guess entirely (codex: a
    #: 15:30 slot chosen from a manual run's clock would have paged MISSING on
    #: a still-running fleet) and it removes the pending-install state with it.
    PENDING_INSTALL: set[str] = set()

    #: Jobs whose manifest entry declares a launchd INTENT beyond
    #: ProgramArguments (`run_at_load` / `keep_alive`, ops/run_surface_drift_check.py
    #: INTENT_KEYS) that the INSTALLED plist does not yet carry. Third
    #: presence-shaped relaxation, bounded exactly like the two above: the
    #: scheduled drift scan does NOT read this set and keeps alarming
    #: "<Key> intent NOT installed" until the operator bootouts/bootstraps the
    #: reviewed plist (containment protocol c — the designed reminder), and
    #: the exact-equality test below goes red the moment the install lands,
    #: forcing this entry's deletion. Agreement between an installed plist and
    #: its manifest entry is still never relaxed: a WRONG installed value (not
    #: merely a missing one) is a residual problem.
    #: 2026-08-29 (orch#1085): RunAtLoad=true declared for the two calendar-only
    #: rq105 jobs whose 06:15/06:25 slots a 10:38 boot swallowed on 08-28.
    #: Landing = operator `launchctl bootout` + `bootstrap` of the reviewed
    #: plists (doc/progress/2026-08-29-rq105-liveness-serving-chain.md).
    #: 2026-08-30: RunAtLoad=true declared for the dawn preflight (06:05) and
    #: the run-surface drift scan (07:00) — the same 08-28 boot dropped both
    #: (no dawn_pin_identity_2026-08-28.json; zero 08-28 lines in the drift
    #: scan's log). Landing = operator bootout/bootstrap of the two deploy/
    #: plists (doc/progress/2026-08-30-run-surface-checkers-truth.md).
    #: Now a dict: label -> the value the PREVIOUS reviewed plist carried on
    #: disk (None = key absent; the dawn preflight plist was reviewed with an
    #: explicit RunAtLoad=false). The relaxation matches exactly that value —
    #: still "the last reviewed definition, not yet re-bootstrapped", never a
    #: third value.
    PENDING_INTENT_INSTALL: dict[str, object] = {
        "com.renquant.rq105-batch-scores-export": None,
        "com.renquant.rq105-session-scheduler": None,
        "com.renquant.rq104-dawn-preflight": False,
        "com.renquant.run-surface-drift": None,
    }

    #: Jobs whose REVIEWED ProgramArguments changed and whose installed plist
    #: still carries the PREVIOUS reviewed definition, pending the operator's
    #: bootout/bootstrap. Fourth presence-shaped relaxation, bounded harder
    #: than the others: the entry names the sha256 of the previous reviewed
    #: ProgramArguments, and the relaxation applies ONLY while the installed
    #: digest equals it — an installed job running anything other than the
    #: last reviewed definition is not "pending install", it is the silent
    #: containment / job swap shape and stays a residual problem. The
    #: scheduled scan does NOT read this set and keeps alarming
    #: "ProgramArguments CHANGED" until the install lands (containment
    #: protocol c); the exact-equality test below goes red the moment it does,
    #: forcing this entry's deletion.
    #: 2026-08-30: com.renquant.run-surface-drift now runs the wrapper
    #: ops/run_surface_drift_scan.sh (boot catch-up guard + dated scan log);
    #: the installed plist still runs `.venv/bin/python ops/run_surface_drift_check.py`.
    PENDING_PROGRAM_ARGS_INSTALL: dict[str, str] = {
        "com.renquant.run-surface-drift":
            "bbd8f4724cd00a51d3b6322913361816653f429dcc404f86853fc1f24ebf0bb2",
    }

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
    #: 2026-08-04 07:56 PDT: the 103 trio's plists were REMOVED from the
    #: machine (grants-trail logged; decision #779, manifest already 40 jobs)
    #: and these entries left the set in the same change, exactly as the
    #: exact-equality test forces. Empty until a future retirement declares
    #: a pending state by name.
    #: Retired from the reviewed surface but still INSTALLED on the operator's disk,
    #: awaiting a one-grant `launchctl bootout`. The scheduled drift scan does NOT read
    #: this set and keeps alarming — that alarm is the designed reminder to finish the
    #: uninstall (CONTAINMENT PROTOCOL), and the exact-equality assertion below goes red
    #: the moment the plist is gone, forcing this entry's deletion.
    #: 2026-08-06: `com.renquant.crypto-session` was booted out and its plist removed
    #: from the machine, so `retiring` lost the label and the exact-equality test went
    #: red with `resolved=['com.renquant.crypto-session']` — exactly the designed
    #: prompt. The entry leaves the set in this change. (G2 crypto was KILLED
    #: 2026-07-18 by its preregistered gate; the job had kept firing every 900s
    #: against a target absent from BOTH checkouts — 1,322 runs, all exit 2. The
    #: standing record is tests/test_crypto_session_dead_job_evidence.py, which is
    #: NOT deleted: the evidence outlives the containment.)
    #: Empty until a future retirement declares a pending state by name.
    PENDING_UNINSTALL: set[str] = set()

    _PENDING_PATTERN = "manifested job {label} missing from disk"
    _UNMANIFESTED_PATTERN = "unmanifested com.renquant job on disk: "
    _INTENT_PATTERN = " intent NOT installed (manifest="
    _PROGRAM_ARGS_PATTERN = " ProgramArguments CHANGED (disk="

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
        self._pending_intent: set[str] = set()
        self._pending_program_args: set[str] = set()
        for prob in self._surface_problems():
            if "missing from disk" in prob and "manifested job " in prob:
                pending.add(prob.split("manifested job ")[1].split(" missing")[0])
                continue
            if self._PROGRAM_ARGS_PATTERN in prob:
                # Reviewed ProgramArguments changed. Relaxed ONLY while the
                # installed plist still runs the PREVIOUS reviewed definition
                # (digest equality with the recorded sha); anything else on
                # disk is a swap, not a pending install, and stays residual.
                label = prob.split("launchd: ")[1].split(" ")[0]
                previous = self.PENDING_PROGRAM_ARGS_INSTALL.get(label)
                if previous is not None:
                    import os
                    installed = drift.read_plist_program_args(os.path.expanduser(
                        f"~/Library/LaunchAgents/{label}.plist"))
                    if installed is not None and drift.program_args_digest(installed) == previous:
                        self._pending_program_args.add(label)
                        continue
            if self._UNMANIFESTED_PATTERN in prob:
                label = prob.split(self._UNMANIFESTED_PATTERN)[1].split(" ")[0]
                if label in self.PENDING_UNINSTALL:
                    retiring.add(label)
                    continue
            if self._INTENT_PATTERN in prob:
                # Declared intent, disk still carries the PREVIOUS reviewed
                # value (None = key absent, or the explicit value the last
                # reviewed plist had). Any other installed value is not this
                # shape and stays residual.
                label = prob.split("launchd: ")[1].split(" ")[0]
                if label in self.PENDING_INTENT_INSTALL and \
                        f"disk={self.PENDING_INTENT_INSTALL[label]!r})" in prob:
                    self._pending_intent.add(label)
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

    def test_declared_intents_not_yet_installed_are_exactly_the_named_set(self):
        """Exact-equality bound for the third relaxation (orch#1085). Once the
        operator bootstraps the reviewed RunAtLoad plists, `_pending_intent`
        loses the labels and this goes red with resolved=[...]: the
        PENDING_INTENT_INSTALL entries must then be deleted in a follow-up."""
        self._partition()
        expected = set(self.PENDING_INTENT_INSTALL)
        assert self._pending_intent == expected, (
            f"declared-intent-not-installed set changed: "
            f"unexpected={sorted(self._pending_intent - expected)} "
            f"resolved={sorted(expected - self._pending_intent)}")

    def test_reviewed_program_args_pending_install_are_exactly_the_named_set(self):
        """Exact-equality bound for the fourth relaxation (2026-08-30). Once the
        operator bootstraps the reviewed run-surface-drift plist (the wrapper),
        the installed digest stops matching the recorded PREVIOUS digest, the
        label leaves `_pending_program_args`, and this goes red with
        resolved=[...]: the PENDING_PROGRAM_ARGS_INSTALL entry must then be
        deleted in a follow-up. An installed digest that matches NEITHER the
        manifest NOR the recorded previous one never lands here — it is a
        residual problem by construction."""
        self._partition()
        assert self._pending_program_args == set(self.PENDING_PROGRAM_ARGS_INSTALL), (
            f"reviewed-program-args-pending-install set changed: "
            f"unexpected={sorted(self._pending_program_args - set(self.PENDING_PROGRAM_ARGS_INSTALL))} "
            f"resolved={sorted(set(self.PENDING_PROGRAM_ARGS_INSTALL) - self._pending_program_args)}")

    def test_the_recorded_previous_digest_is_not_the_reviewed_one(self):
        """The relaxation names the PREVIOUS definition; if someone records the
        CURRENT manifest digest the relaxation would accept an installed copy
        of the new definition as 'pending' and the exact-equality test could
        never go red. Machine-independent."""
        jobs = json.loads((REPO / "ops" / "launchd_manifest.json").read_text())["jobs"]
        for label, previous in self.PENDING_PROGRAM_ARGS_INSTALL.items():
            assert jobs[label]["program_args_sha256"] != previous, label

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


# --- class 1: how far behind origin/main is the checkout the jobs run from ----
#
# The module docstring has always named this ("run checkouts drifting from their
# reviewed refs") and nothing scheduled measured it. `ops/referenced_checkout_
# freshness.py` measured it correctly and was wired to nothing — not a launchd job,
# not the reviewed manifest. Measured by hand 2026-08-05: renquant-orchestrator-run
# was 36 commits behind with 21 jobs running from it, past its own bound of 20.
#
# Every test here injects a fake probe, so none of them touch the network, a real
# checkout, or the machine's own git state.

class _FakeProbe:
    FAILING_STATUSES = ("STALE", "NOT_A_CHECKOUT", "UNMEASURABLE")

    def __init__(self, report=None, raises=None):
        self._report, self._raises = report, raises

    def scan(self, *a, **k):
        if self._raises:
            raise self._raises
        return self._report

    def failing(self, report):
        return [r for r in report.get("results", [])
                if r.get("status") in self.FAILING_STATUSES]


def _inject(monkeypatch, probe):
    monkeypatch.setitem(sys.modules, "referenced_checkout_freshness", probe)


def _result(status, **kw):
    return {"checkout": "renquant-orchestrator-run", "status": status,
            "referenced_by_jobs": 21, "commits_behind": kw.pop("behind", None),
            "detail": kw.pop("detail", "d"), **kw}


def test_a_STALE_run_checkout_is_a_problem(monkeypatch):
    _inject(monkeypatch, _FakeProbe({"results": [
        _result("STALE", behind=36, detail="36 commits behind origin/main (bound 20)")]}))

    problems, _ = drift.check_referenced_checkout_freshness()

    assert len(problems) == 1
    assert "STALE" in problems[0]
    assert "36 commits behind" in problems[0]
    assert "21 job(s)" in problems[0]   # the blast radius, not just the fact


def test_UNMEASURABLE_is_a_problem_not_a_pass(monkeypatch):
    """could-not-check is not checked-and-found-fresh. This is the exact defect the
    probe exists for: a checkout comparing itself to its own unfetched origin/main
    answers '0 behind' with total confidence."""
    _inject(monkeypatch, _FakeProbe({"results": [
        _result("UNMEASURABLE", detail="fetch failed in the reference checkout")]}))

    problems, _ = drift.check_referenced_checkout_freshness()

    assert problems and "UNMEASURABLE" in problems[0]


def test_a_FRESH_checkout_is_reported_but_does_not_alarm(monkeypatch):
    """Anti-vacuity in the other direction: the check must be able to pass."""
    _inject(monkeypatch, _FakeProbe({"results": [_result("FRESH", behind=0)]}))

    problems, infos = drift.check_referenced_checkout_freshness()

    assert problems == []
    assert infos and "FRESH" in infos[0]


def test_measuring_NOTHING_is_a_problem(monkeypatch):
    """An empty result set is the shape that reads as green while checking zero
    checkouts — the vacuous pass this repo keeps meeting."""
    _inject(monkeypatch, _FakeProbe({"results": []}))

    problems, _ = drift.check_referenced_checkout_freshness()

    assert problems and "nothing was measured" in problems[0]


def test_a_probe_that_RAISES_does_not_read_as_clean(monkeypatch):
    _inject(monkeypatch, _FakeProbe(raises=RuntimeError("boom")))

    problems, _ = drift.check_referenced_checkout_freshness()

    assert problems and "scan failed" in problems[0]


def test_the_failing_set_comes_from_the_PROBE_not_a_second_list(monkeypatch):
    """Two enumerations of the same status list is how one of them quietly stops
    covering a status the other added. The drift check must defer to the probe."""
    class _ProbeThatCallsEverythingFine(_FakeProbe):
        def failing(self, report):
            return []

    _inject(monkeypatch, _ProbeThatCallsEverythingFine({"results": [
        _result("STALE", behind=999)]}))

    problems, infos = drift.check_referenced_checkout_freshness()

    # the drift check did NOT re-derive "STALE means bad" on its own
    assert problems == []
    assert infos and "STALE" in infos[0]


# ---------------------------------------------------------------------------
# watchlist trainability (2026-08-20): a ticker the book may BUY must be able
# to receive a model artifact. Two watchlists in two repos drifted to 145 vs
# 142 and nothing reported it; the three-name difference was skipped
# `no_artifact` every session, silently.
# ---------------------------------------------------------------------------
import pytest  # noqa: E402


def _cfgs(tmp_path: Path, served: list[str], trained: list[str]) -> tuple[str, str]:
    s = tmp_path / "served.json"
    t = tmp_path / "trained.json"
    s.write_text(json.dumps({"watchlist": served}))
    t.write_text(json.dumps({"watchlist": trained}))
    return str(s), str(t)


@pytest.fixture
def wl_paths(monkeypatch):
    """Point the check at fixtures instead of the operator's real configs.

    A test that reads the live config measures the operator's disk, so it goes
    red for the wrong reason on someone else's machine and vacuously green once
    the real drift is fixed.
    """
    def _apply(served, trained, tmp_path):
        sp, tp = _cfgs(tmp_path, served, trained)
        monkeypatch.setattr(drift, "SERVED_STRATEGY_CONFIG", sp)
        monkeypatch.setattr(drift, "TRAINING_STRATEGY_CONFIG", tp)
    return _apply


class TestTheRealDriftAlarms:
    def test_a_served_ticker_absent_from_training_is_a_problem(self, wl_paths, tmp_path):
        """The measured 2026-08-20 state, reduced: CRWV/RKLB/SPCX served, not trained."""
        wl_paths(["AAPL", "CRWV", "RKLB", "SPCX"], ["AAPL"], tmp_path)
        problems, _ = drift.check_watchlist_trainability()
        assert len(problems) == 1, problems
        for t in ("CRWV", "RKLB", "SPCX"):
            assert t in problems[0]
        assert "no_artifact" in problems[0], "the alarm must name the observable symptom"

    def test_a_covered_watchlist_is_clean(self, wl_paths, tmp_path):
        wl_paths(["AAPL", "MSFT"], ["AAPL", "MSFT", "SPY"], tmp_path)
        problems, infos = drift.check_watchlist_trainability()
        assert problems == []
        assert any("unaccounted=0" in i for i in infos), infos


class TestItCannotGoQUIETOnBadInput:
    """A check that returns clean when it could not read its inputs is worse
    than no check: `[[guards-that-validate-the-wrong-object]]`. An empty
    watchlist would make every subset test pass."""

    def test_a_missing_served_config_is_a_problem_not_a_pass(self, monkeypatch, tmp_path):
        monkeypatch.setattr(drift, "SERVED_STRATEGY_CONFIG", str(tmp_path / "nope.json"))
        monkeypatch.setattr(drift, "TRAINING_STRATEGY_CONFIG", str(tmp_path / "also_nope.json"))
        problems, infos = drift.check_watchlist_trainability()
        assert problems, "unreadable configs must alarm"
        assert all("UNVERIFIED" in p for p in problems), problems
        assert infos == []

    def test_an_empty_watchlist_is_treated_as_unreadable(self, wl_paths, tmp_path):
        """`{"watchlist": []}` would otherwise be a vacuous subset of anything."""
        wl_paths([], ["AAPL"], tmp_path)
        problems, _ = drift.check_watchlist_trainability()
        assert problems and "UNVERIFIED" in problems[0], problems

    def test_a_malformed_watchlist_is_treated_as_unreadable(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.json"
        bad.write_text('{"watchlist": "AAPL,MSFT"}')   # a string, not a list
        ok = tmp_path / "ok.json"
        ok.write_text(json.dumps({"watchlist": ["AAPL"]}))
        monkeypatch.setattr(drift, "SERVED_STRATEGY_CONFIG", str(bad))
        monkeypatch.setattr(drift, "TRAINING_STRATEGY_CONFIG", str(ok))
        problems, _ = drift.check_watchlist_trainability()
        assert problems and "UNVERIFIED" in problems[0], problems


class TestTheOppositeDirectionIsInfoOnly:
    def test_trained_not_served_does_not_alarm(self, wl_paths, tmp_path):
        wl_paths(["AAPL"], ["AAPL", "GHOST"], tmp_path)
        problems, infos = drift.check_watchlist_trainability()
        assert problems == [], "an unused artifact is waste, not a live defect"
        assert any("GHOST" in i for i in infos), infos


class TestItIsWiredIntoTheSCAN:
    """A check nobody calls is a document. This module's own history is that
    `referenced_checkout_freshness.py` did the right thing for weeks while
    wired to nothing."""

    def test_main_calls_it(self):
        src = (REPO / "ops" / "run_surface_drift_check.py").read_text(encoding="utf-8")
        main_body = src[src.index("def main("):]
        assert "check_watchlist_trainability()" in main_body


# --- launchd INTENTS beyond ProgramArguments are compared (orch#1085) --------
class TestLaunchdIntents:
    """A manifest entry that declares `run_at_load` / `keep_alive` is a claim
    about the INSTALLED plist. Before orch#1085 nothing compared it: the quote
    logger's keep_alive was recorded 2026-07-22 and never checked, and the two
    RunAtLoad intents this PR adds would have been equally decorative."""

    @staticmethod
    def _plist(agents: Path, label: str, **extra) -> None:
        import plistlib
        with open(agents / f"{label}.plist", "wb") as fh:
            plistlib.dump({"Label": label, "ProgramArguments": ["/x.sh"], **extra}, fh)

    @staticmethod
    def _manifest_with(agents: Path, path: Path, label: str, **intent) -> None:
        m = {"jobs": drift.scan_launchd_plists(str(agents))}
        m["jobs"][label].update(intent)
        path.write_text(json.dumps(m))

    def test_declared_run_at_load_missing_on_disk_is_a_problem(self, tmp_path):
        agents = tmp_path / "agents"; agents.mkdir()
        self._plist(agents, "com.renquant.x")
        mpath = tmp_path / "m.json"
        self._manifest_with(agents, mpath, "com.renquant.x", run_at_load=True)
        problems = drift.check_launchd_surface(str(mpath), str(agents))
        assert len(problems) == 1, problems
        assert "com.renquant.x RunAtLoad intent NOT installed" in problems[0]
        assert "manifest=True != disk=None" in problems[0]

    def test_declared_run_at_load_present_on_disk_is_clean(self, tmp_path):
        agents = tmp_path / "agents"; agents.mkdir()
        self._plist(agents, "com.renquant.x", RunAtLoad=True)
        mpath = tmp_path / "m.json"
        self._manifest_with(agents, mpath, "com.renquant.x", run_at_load=True)
        assert drift.check_launchd_surface(str(mpath), str(agents)) == []

    def test_declared_keep_alive_dict_is_compared_structurally(self, tmp_path):
        agents = tmp_path / "agents"; agents.mkdir()
        self._plist(agents, "com.renquant.x", KeepAlive={"SuccessfulExit": True})
        mpath = tmp_path / "m.json"
        self._manifest_with(agents, mpath, "com.renquant.x",
                            keep_alive={"SuccessfulExit": False})
        problems = drift.check_launchd_surface(str(mpath), str(agents))
        assert len(problems) == 1, problems
        assert "KeepAlive intent NOT installed" in problems[0]
        assert "disk={'SuccessfulExit': True}" in problems[0]

    def test_an_entry_without_a_declared_intent_makes_no_claim(self, tmp_path):
        """RunAtLoad on disk with nothing declared is not drift — the manifest
        pins ProgramArguments for every job and intents only where declared."""
        agents = tmp_path / "agents"; agents.mkdir()
        self._plist(agents, "com.renquant.x", RunAtLoad=True)
        mpath = tmp_path / "m.json"
        self._manifest_with(agents, mpath, "com.renquant.x")
        assert drift.check_launchd_surface(str(mpath), str(agents)) == []

    def test_the_committed_manifest_declares_the_boot_catchup_intents(self):
        """The reviewed intent for orch#1085 (two rq105 jobs) and 2026-08-30
        (dawn preflight, drift scan): every boot-catch-up job declares
        run_at_load=true, its committed plist carries RunAtLoad, and the
        plist's ProgramArguments digest equals the manifest's (the hashed
        surface and the reviewed plist agree)."""
        root = Path(__file__).resolve().parent.parent
        jobs = json.loads((root / "ops/launchd_manifest.json").read_text())["jobs"]
        for label, where in (("com.renquant.rq105-batch-scores-export", "ops/renquant105"),
                             ("com.renquant.rq105-session-scheduler", "ops/renquant105"),
                             ("com.renquant.rq104-dawn-preflight", "deploy"),
                             ("com.renquant.run-surface-drift", "deploy")):
            assert jobs[label].get("run_at_load") is True, label
            plist = root / where / f"{label}.plist"
            assert drift.read_plist_intents(str(plist))["run_at_load"] is True, label
            assert drift.program_args_digest(drift.read_plist_program_args(str(plist))) \
                == jobs[label]["program_args_sha256"], label
