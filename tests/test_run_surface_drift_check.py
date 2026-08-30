"""Tests for ops/run_surface_drift_check.py (GOAL-5 AC2).

Real temporary git repos for the checkout checks; fixture plists +
manifests for the launchd surface. The drill case: a daily104 swapped to a
/tmp sell-only wrapper (the 2026-07-15 silent containment) MUST alarm.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

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

# --- The COMMITTED manifest against FIXTURE plists (hermetic) ---------------
#
# Until 2026-08-30 the tests below this line read ~/Library/LaunchAgents: they
# partitioned the real disk's drift problems into named "pending install" /
# "pending uninstall" relaxations and asserted the residual was empty. That
# made them (a) skipped on every machine but the operator's, so CI never ran
# them, and (b) red on the operator's machine for the whole window between a
# reviewed plist change merging and the operator's bootout/bootstrap — by
# design, as the forcing function for deleting the relaxation entries, but a
# red default suite trains its reader to ignore red (the 2026-07-31 lesson,
# re-learned). The scheduled drift scan (ops/run_surface_drift_scan.sh) is the
# daily alarm for disk != manifest; a unit test that ALSO measures the
# operator's disk is a second, worse instrument for the same fact
# (memory: tests-that-measure-the-operators-disk).
#
# So: the committed manifest is now exercised against plists written under
# tmp_path — the "installed == manifest" and the "installed != manifest"
# directions both — and the real-disk reading survives only as the opt-in
# smoke test at the bottom (RENQUANT_DRIFT_DISK_TESTS=1).

MANIFEST_PATH = REPO / "ops" / "launchd_manifest.json"

#: The four jobs whose reviewed RunAtLoad=true intent (orch#1085 2026-08-29 for
#: the two rq105 jobs; orch#1098 2026-08-30 for dawn + drift) was installed by
#: the operator on 2026-08-30 11:29 PT (bootout / cp / bootstrap; `launchctl
#: print` runs=1). The relaxations that named them (PENDING_INTENT_INSTALL,
#: PENDING_PROGRAM_ARGS_INSTALL) were deleted in the same change that wrote
#: this list; the fixtures below replay the pre-landing disk state and assert
#: the scan still alarms on it — the alarm is the containment-protocol (c)
#: reminder, and this pins that it cannot be lost.
RUN_AT_LOAD_LANDED_2026_08_30 = (
    "com.renquant.rq104-dawn-preflight",
    "com.renquant.run-surface-drift",
    "com.renquant.rq105-batch-scores-export",
    "com.renquant.rq105-session-scheduler",
)

#: com.renquant.run-surface-drift's PREVIOUS reviewed definition (direct python
#: invocation, replaced by the ops/run_surface_drift_scan.sh wrapper in
#: orch#1098) and its digest as the manifest recorded it. Kept so the
#: "installed still runs the previous definition" shape stays a tested alarm.
PREVIOUS_DRIFT_PROGRAM_ARGS = [
    "/Users/renhao/git/github/RenQuant/.venv/bin/python",
    "/Users/renhao/git/github/renquant-orchestrator-run/ops/run_surface_drift_check.py",
]
PREVIOUS_DRIFT_PROGRAM_ARGS_SHA256 = (
    "bbd8f4724cd00a51d3b6322913361816653f429dcc404f86853fc1f24ebf0bb2"
)

#: The two earnings jobs DECLARED on the reviewed surface 2026-08-30
#: (orch#1102; wrappers + plists in umbrella RenQuant#627, merged the same
#: day) and NOT yet installed — the operator's landing batch (cp the two
#: plists from the umbrella's scripts/launchd/ + bootstrap) is pending. Until
#: it lands, the scheduled drift scan alarms `manifested job … missing from
#: disk` for exactly these two labels (containment protocol c — the designed
#: reminder); the hermetic test below pins that alarm shape, and the opt-in
#: operator-disk class names the same two as its PENDING_INSTALL relaxation.
#: Delete from BOTH places once the exact-equality test goes red with
#: resolved=[...].
EARNINGS_JOBS_PENDING_INSTALL_2026_08_30 = (
    "com.renquant.daily-earnings-surprise",
    "com.renquant.earnings-calendar-refresh",
)

#: Where the reviewed plist for each intent-declaring job is committed.
COMMITTED_PLISTS = {
    "com.renquant.rq104-dawn-preflight": "deploy/com.renquant.rq104-dawn-preflight.plist",
    "com.renquant.run-surface-drift": "deploy/com.renquant.run-surface-drift.plist",
    "com.renquant.rq105-batch-scores-export":
        "ops/renquant105/com.renquant.rq105-batch-scores-export.plist",
    "com.renquant.rq105-session-scheduler":
        "ops/renquant105/com.renquant.rq105-session-scheduler.plist",
    "com.renquant.rq105-quote-logger": "ops/renquant105/com.renquant.rq105-quote-logger.plist",
}


def _manifest_jobs() -> dict:
    return json.loads(MANIFEST_PATH.read_text())["jobs"]


def _write_plist_dict(agents: Path, label: str, data: dict) -> None:
    import plistlib
    with open(agents / f"{label}.plist", "wb") as fh:
        plistlib.dump({"Label": label, **data}, fh)


def _fixture_agents_from_manifest(tmp_path: Path) -> Path:
    """One plist per manifested job carrying EXACTLY the reviewed
    ProgramArguments and every declared intent (RunAtLoad / KeepAlive).
    Nothing under ~/Library is read."""
    agents = tmp_path / "agents"
    agents.mkdir()
    for label, spec in _manifest_jobs().items():
        data: dict = {"ProgramArguments": list(spec["program_args"])}
        for mkey, pkey in drift.INTENT_KEYS:
            if mkey in spec:
                data[pkey] = spec[mkey]
        _write_plist_dict(agents, label, data)
    return agents


_ABSENT = object()


def _rewrite_plist(agents: Path, label: str, **changes) -> None:
    """Edit one fixture plist in place: a key set to ``_ABSENT`` is removed."""
    import plistlib
    path = agents / f"{label}.plist"
    with open(path, "rb") as fh:
        data = plistlib.load(fh)
    for key, value in changes.items():
        if value is _ABSENT:
            data.pop(key, None)
        else:
            data[key] = value
    with open(path, "wb") as fh:
        plistlib.dump(data, fh)


class TestCommittedManifestAgainstFixtures:
    """The committed ops/launchd_manifest.json, both directions, hermetic."""

    def test_every_sha_is_the_digest_of_its_program_args(self):
        """Machine-independent self-consistency: a manifest whose recorded
        digest does not match its own program_args would alarm on a CORRECT
        install. Every entry, not a sample."""
        for label, spec in _manifest_jobs().items():
            assert spec["program_args_sha256"] == drift.program_args_digest(
                spec["program_args"]), label

    def test_installed_equals_manifest_is_clean(self, tmp_path):
        """installed == manifest, for every manifested job, intents included → no issue."""
        agents = _fixture_agents_from_manifest(tmp_path)
        assert drift.check_launchd_surface(str(MANIFEST_PATH), str(agents)) == []

    def test_committed_reviewed_plists_equal_their_manifest_entries(self, tmp_path):
        """The plists this repo ships (deploy/, ops/renquant105/) are what the
        operator installs; each must agree with its manifest entry in
        ProgramArguments AND declared intent, or the reviewed surface
        disagrees with itself on day one. Restricted manifest so the other
        35 jobs (no committed plist here) are not 'missing from disk'."""
        import shutil
        agents = tmp_path / "agents"
        agents.mkdir()
        jobs = _manifest_jobs()
        for label, rel in COMMITTED_PLISTS.items():
            assert (REPO / rel).is_file(), rel
            shutil.copy(REPO / rel, agents / f"{label}.plist")
        mpath = tmp_path / "manifest.json"
        mpath.write_text(json.dumps({"jobs": {l: jobs[l] for l in COMMITTED_PLISTS}}))
        assert drift.check_launchd_surface(str(mpath), str(agents)) == []

    def test_the_four_landed_jobs_declare_run_at_load(self):
        for label in RUN_AT_LOAD_LANDED_2026_08_30:
            assert _manifest_jobs()[label].get("run_at_load") is True, label

    def test_declared_intent_absent_from_installed_plist_alarms(self, tmp_path):
        """The pre-2026-08-30 disk: the four RunAtLoad intents reviewed but
        not yet bootstrapped (key absent). Exactly four problems, one per
        label, naming the intent and both values — and NOTHING else, so the
        alarm is attributable."""
        agents = _fixture_agents_from_manifest(tmp_path)
        for label in RUN_AT_LOAD_LANDED_2026_08_30:
            _rewrite_plist(agents, label, RunAtLoad=_ABSENT)
        problems = drift.check_launchd_surface(str(MANIFEST_PATH), str(agents))
        assert len(problems) == 4, problems
        for label in RUN_AT_LOAD_LANDED_2026_08_30:
            assert any(
                p.startswith(f"launchd: {label} RunAtLoad intent NOT installed ")
                and "(manifest=True != disk=None)" in p
                and "containment protocol c" in p
                for p in problems), (label, problems)

    def test_explicit_wrong_intent_value_alarms(self, tmp_path):
        """The dawn preflight's previous reviewed plist carried an explicit
        RunAtLoad=false; a wrong VALUE alarms exactly like an absent key."""
        agents = _fixture_agents_from_manifest(tmp_path)
        _rewrite_plist(agents, "com.renquant.rq104-dawn-preflight", RunAtLoad=False)
        problems = drift.check_launchd_surface(str(MANIFEST_PATH), str(agents))
        assert len(problems) == 1, problems
        assert problems[0].startswith(
            "launchd: com.renquant.rq104-dawn-preflight RunAtLoad intent NOT installed "
            "(manifest=True != disk=False)"), problems

    def test_keep_alive_intent_is_compared_as_a_value(self, tmp_path):
        """A non-boolean intent (the quote logger's KeepAlive dict) is
        compared by value: `true` on disk is not `{SuccessfulExit: false}`."""
        agents = _fixture_agents_from_manifest(tmp_path)
        _rewrite_plist(agents, "com.renquant.rq105-quote-logger", KeepAlive=True)
        problems = drift.check_launchd_surface(str(MANIFEST_PATH), str(agents))
        assert len(problems) == 1, problems
        assert "rq105-quote-logger KeepAlive intent NOT installed" in problems[0]

    def test_previous_drift_definition_on_disk_alarms_as_changed(self, tmp_path):
        """The drift job's PREVIOUS reviewed ProgramArguments (direct python
        invocation) installed against the wrapper manifest: exactly one
        `ProgramArguments CHANGED` naming the job. This is the state the
        deleted PENDING_PROGRAM_ARGS_INSTALL relaxation named; it must keep
        alarming — a checker that silently accepts its own previous
        definition would never notice a rollback."""
        assert drift.program_args_digest(PREVIOUS_DRIFT_PROGRAM_ARGS) == \
            PREVIOUS_DRIFT_PROGRAM_ARGS_SHA256
        assert _manifest_jobs()["com.renquant.run-surface-drift"]["program_args_sha256"] \
            != PREVIOUS_DRIFT_PROGRAM_ARGS_SHA256
        agents = _fixture_agents_from_manifest(tmp_path)
        _rewrite_plist(agents, "com.renquant.run-surface-drift",
                       ProgramArguments=PREVIOUS_DRIFT_PROGRAM_ARGS)
        problems = drift.check_launchd_surface(str(MANIFEST_PATH), str(agents))
        assert len(problems) == 1, problems
        assert problems[0].startswith(
            "launchd: com.renquant.run-surface-drift ProgramArguments CHANGED (disk=")
        assert "run_surface_drift_scan.sh" in problems[0]  # the reviewed one is named

    def test_manifested_job_missing_and_unmanifested_job_alarm(self, tmp_path):
        """Presence, both directions, on the committed manifest."""
        agents = _fixture_agents_from_manifest(tmp_path)
        (agents / "com.renquant.run-surface-drift.plist").unlink()
        _write_plist_dict(agents, "com.renquant.not-reviewed", {"ProgramArguments": ["/x"]})
        problems = drift.check_launchd_surface(str(MANIFEST_PATH), str(agents))
        assert problems == [
            "launchd: manifested job com.renquant.run-surface-drift missing from disk",
            "launchd: unmanifested com.renquant job on disk: com.renquant.not-reviewed "
            "(add to ops/launchd_manifest.json via a reviewed change)",
        ]

    def test_the_two_earnings_jobs_absent_from_disk_alarm_as_missing(self, tmp_path):
        """The pre-landing disk for orch#1102: the two earnings jobs declared
        but not installed. Exactly two problems, both `missing from disk`,
        one per label, and NOTHING else — the shape the scheduled scan
        reports until the operator's landing batch, and the shape the opt-in
        PENDING_INSTALL relaxation names (same tuple, one source)."""
        for label in EARNINGS_JOBS_PENDING_INSTALL_2026_08_30:
            assert label in _manifest_jobs(), label
        agents = _fixture_agents_from_manifest(tmp_path)
        for label in EARNINGS_JOBS_PENDING_INSTALL_2026_08_30:
            (agents / f"{label}.plist").unlink()
        problems = drift.check_launchd_surface(str(MANIFEST_PATH), str(agents))
        assert problems == [
            f"launchd: manifested job {label} missing from disk"
            for label in sorted(EARNINGS_JOBS_PENDING_INSTALL_2026_08_30)
        ], problems


# --- Operator-disk smoke test (OPT-IN: RENQUANT_DRIFT_DISK_TESTS=1) ---------

OPERATOR_DISK_ENV = "RENQUANT_DRIFT_DISK_TESTS"
operator_disk = pytest.mark.skipif(
    os.environ.get(OPERATOR_DISK_ENV, "") != "1",
    reason=f"reads ~/Library/LaunchAgents; opt in with {OPERATOR_DISK_ENV}=1 on the "
           "operator machine (the scheduled drift scan is the daily instrument)",
)


def test_operator_disk_smoke_is_opt_in_and_named():
    """The default suite must be hermetic: the real-disk class below is
    skipped unless the operator opts in by the documented variable."""
    assert OPERATOR_DISK_ENV == "RENQUANT_DRIFT_DISK_TESTS"
    src = Path(__file__).read_text()
    assert "@operator_disk\nclass TestOperatorDiskSurface" in src


@operator_disk
class TestOperatorDiskSurface:
    """Reads the operator's ~/Library/LaunchAgents. Same partition as the
    scheduled scan's problems: every problem lands in exactly one bucket —
    a NAMED pending-install / pending-uninstall relaxation, or residual,
    which fails. A relaxation names a state the operator has not yet landed;
    the exact-equality tests go red the moment it lands, forcing deletion."""

    #: Jobs DECLARED on the reviewed run surface that are not yet installed.
    #: History: 2026-08-03 all three then-pending jobs installed; 2026-08-04
    #: (orch#801) the fleet-lane sentinel needs no launchd job; 2026-08-30
    #: (orch#1102) the two earnings jobs declared, plists in umbrella
    #: RenQuant#627, install pending the operator's landing batch — see
    #: EARNINGS_JOBS_PENDING_INSTALL_2026_08_30 above (one source for this
    #: set and the hermetic alarm test). Delete the entries once the
    #: exact-equality test below goes red with resolved=[...].
    PENDING_INSTALL: set[str] = set(EARNINGS_JOBS_PENDING_INSTALL_2026_08_30)

    #: Jobs whose manifest entry declares an INTENT (run_at_load / keep_alive)
    #: the installed plist does not yet carry: label -> the value the PREVIOUS
    #: reviewed plist had on disk (None = key absent). 2026-08-29 (orch#1085)
    #: named the two rq105 jobs; 2026-08-30 (orch#1098) added dawn (previous
    #: value False) + drift. All four LANDED 2026-08-30 11:29 PT and left this
    #: dict in the same change (see RUN_AT_LOAD_LANDED_2026_08_30 above, whose
    #: fixture tests now carry the alarm-on-absence proof). Empty until a
    #: future reviewed intent declares a pending state by name.
    PENDING_INTENT_INSTALL: dict[str, object] = {}

    #: Jobs whose REVIEWED ProgramArguments changed while the installed plist
    #: still runs the PREVIOUS reviewed definition: label -> sha256 of that
    #: previous definition; relaxed ONLY while the installed digest equals it.
    #: 2026-08-30 named com.renquant.run-surface-drift (previous digest
    #: bbd8f472…, now PREVIOUS_DRIFT_PROGRAM_ARGS_SHA256 above); LANDED the
    #: same day and left this dict in the same change. Empty until a future
    #: reviewed ProgramArguments change declares a pending state by name.
    PENDING_PROGRAM_ARGS_INSTALL: dict[str, str] = {}

    #: Jobs REMOVED from the reviewed surface whose plist is still installed,
    #: pending the uninstall item of a tracked grant. History: 2026-08-02
    #: weekly-retrain-patchtst booted out (orch#741/#755); 2026-08-04 the 103
    #: trio removed (#779); 2026-08-06 crypto-session removed (evidence stays
    #: in tests/test_crypto_session_dead_job_evidence.py). Empty until a
    #: future retirement declares a pending state by name.
    PENDING_UNINSTALL: set[str] = set()

    _UNMANIFESTED_PATTERN = "unmanifested com.renquant job on disk: "
    _INTENT_PATTERN = " intent NOT installed (manifest="
    _PROGRAM_ARGS_PATTERN = " ProgramArguments CHANGED (disk="

    @staticmethod
    def _surface_problems():
        if not os.path.isdir(os.path.expanduser("~/Library/LaunchAgents")):
            pytest.skip("no ~/Library/LaunchAgents on this machine")
        return list(drift.check_launchd_surface())

    def _partition(self):
        """(pending-install labels, pending-uninstall labels, residual).
        No silently-ignored category (codex on the 2026-07-31 retarget)."""
        pending, retiring, residual = set(), set(), []
        self._pending_intent: set[str] = set()
        self._pending_program_args: set[str] = set()
        for prob in self._surface_problems():
            if "missing from disk" in prob and "manifested job " in prob:
                pending.add(prob.split("manifested job ")[1].split(" missing")[0])
                continue
            if self._PROGRAM_ARGS_PATTERN in prob:
                label = prob.split("launchd: ")[1].split(" ")[0]
                previous = self.PENDING_PROGRAM_ARGS_INSTALL.get(label)
                if previous is not None:
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
                label = prob.split("launchd: ")[1].split(" ")[0]
                if label in self.PENDING_INTENT_INSTALL and \
                        f"disk={self.PENDING_INTENT_INSTALL[label]!r})" in prob:
                    self._pending_intent.add(label)
                    continue
            residual.append(prob)
        return pending, retiring, residual

    def test_no_residual_problem_of_any_kind(self):
        _, _, residual = self._partition()
        assert residual == [], residual

    def test_declared_but_uninstalled_jobs_are_exactly_the_named_set(self):
        pending, _, _ = self._partition()
        assert pending == self.PENDING_INSTALL, (
            f"unexpected={sorted(pending - self.PENDING_INSTALL)} "
            f"resolved={sorted(self.PENDING_INSTALL - pending)}")

    def test_declared_intents_not_yet_installed_are_exactly_the_named_set(self):
        self._partition()
        expected = set(self.PENDING_INTENT_INSTALL)
        assert self._pending_intent == expected, (
            f"unexpected={sorted(self._pending_intent - expected)} "
            f"resolved={sorted(expected - self._pending_intent)}")

    def test_reviewed_program_args_pending_install_are_exactly_the_named_set(self):
        self._partition()
        expected = set(self.PENDING_PROGRAM_ARGS_INSTALL)
        assert self._pending_program_args == expected, (
            f"unexpected={sorted(self._pending_program_args - expected)} "
            f"resolved={sorted(expected - self._pending_program_args)}")

    def test_retired_but_still_installed_jobs_are_exactly_the_named_set(self):
        _, retiring, _ = self._partition()
        assert retiring == self.PENDING_UNINSTALL, (
            f"unexpected={sorted(retiring - self.PENDING_UNINSTALL)} "
            f"resolved={sorted(self.PENDING_UNINSTALL - retiring)}")


def test_recorded_previous_digests_are_never_the_reviewed_ones():
    """Machine-independent guard on the (currently empty) relaxation dict: a
    PREVIOUS digest equal to the manifest's would accept an installed copy of
    the NEW definition as 'pending' and the exact-equality test could never
    go red."""
    jobs = _manifest_jobs()
    for label, previous in TestOperatorDiskSurface.PENDING_PROGRAM_ARGS_INSTALL.items():
        assert jobs[label]["program_args_sha256"] != previous, label


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
