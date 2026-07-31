"""#623 R2 generalised: which copy would a reader edit?

R2 cost five weeks of `book_to_price = 1.68e19` because a fix landed on the umbrella's
dead `fetch_sec_fundamentals.py` while the live producer was in `renquant-base-data`.
This pins the whole shadow surface so a new one cannot appear unregistered.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parent.parent / "ops"
_SPEC = importlib.util.spec_from_file_location(
    "umbrella_script_shadow_check", OPS / "umbrella_script_shadow_check.py")
sh = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sh)

REG = json.loads((OPS / "umbrella_script_shadows.json").read_text())

# The survey reads the umbrella checkout on THIS machine. CI has no umbrella, so the
# assertions that compare the registry against a live tree are integration tests about
# the operator's disk, not unit tests of the logic. They are skipped where the tree is
# absent — with an explicit reason, and paired with `test_absent_umbrella_is_*` below,
# which run everywhere and assert that absence is reported LOUDLY rather than as clean.
# Skipping the comparison is fine; skipping quietly and calling it a pass is not.
needs_umbrella = pytest.mark.skipif(
    not sh.umbrella_present(),
    reason=f"no umbrella checkout at {sh.UMBRELLA / 'scripts'} — survey cannot run here")


# --- the environment dependency itself, asserted everywhere -------------------

def test_absent_umbrella_is_never_reported_as_clean(monkeypatch, tmp_path):
    """An unrunnable check must not read as a passing one.

    Before this, a missing umbrella made `survey()` return zero pairs and `verify()`
    reported all 44 registered scripts as "no longer shadows anything" — 44 false
    drift findings whose real cause was that the check had nothing to look at. In CI
    that is a red herring; on an operator's machine with a moved checkout it is worse,
    because "re-emit" is exactly the wrong remedy and would erase the registry.
    """
    monkeypatch.setattr(sh, "UMBRELLA", tmp_path / "no-umbrella-here")
    problems = sh.verify(REG)
    assert len(problems) == 1
    assert problems[0].startswith(sh.UNVERIFIABLE)
    assert "were NOT checked" in problems[0]


def test_absent_umbrella_exits_2_not_1(monkeypatch, tmp_path):
    """Exit 2 = could not check; exit 1 = checked and found drift. Distinct on purpose."""
    monkeypatch.setattr(sh, "UMBRELLA", tmp_path / "no-umbrella-here")
    p = tmp_path / "r.json"
    p.write_text(json.dumps(REG))
    assert sh.main(["--registry", str(p)]) == 2


@needs_umbrella
def test_the_committed_registry_verifies_clean():
    assert sh.verify(REG) == []


def test_the_measured_shape_is_pinned():
    """These counts ARE the finding. If one moves, the finding moved."""
    pairs = REG["pairs"]
    assert len(pairs) == 44
    assert sum(1 for v in pairs.values() if v["class"] == sh.DIVERGED) == 26
    assert sum(1 for v in pairs.values() if v["class"] == sh.IDENTICAL) == 18
    assert sum(1 for v in pairs.values()
               if v["referenced_by_a_scheduled_surface"]) == 12


def test_r2_itself_is_NOT_caught_and_that_limit_is_documented():
    """The instance that motivated this tool is OUTSIDE its reach, and that must stay
    visible rather than being assumed covered.

    R2 is umbrella `fetch_sec_fundamentals.py` vs base-data `sec_fundamentals.py` —
    **different stems**. This sweep matches on identical stem, so it cannot see a
    renamed twin, which is precisely the kind hardest to spot by eye. Anyone reading
    "44 shadow pairs registered" must not conclude the twin surface is covered.
    """
    assert "fetch_sec_fundamentals.py" not in REG["pairs"], (
        "the sweep now catches R2 — widen this test and the documented scope together")
    src = (OPS / "umbrella_script_shadow_check.py").read_text()
    assert "SCOPE LIMIT" in src and "fetch_sec_fundamentals.py" in src, (
        "the limitation must be stated in the tool, not only in a test")


def test_matching_is_by_stem_so_the_scope_claim_is_checkable():
    src = (OPS / "umbrella_script_shadow_check.py").read_text()
    assert "Path(line).stem" in src, (
        "if matching stops being stem-based the documented scope limit is stale")


# --- the check must be able to FAIL ------------------------------------------

@needs_umbrella
def test_an_unregistered_shadow_is_reported():
    reg = copy.deepcopy(REG)
    victim = next(iter(reg["pairs"]))
    del reg["pairs"][victim]
    problems = sh.verify(reg)
    assert len(problems) == 1 and "NEW shadow" in problems[0]


@needs_umbrella
def test_a_registered_pair_that_no_longer_shadows_is_reported():
    reg = copy.deepcopy(REG)
    reg["pairs"]["definitely_not_a_real_script.py"] = {
        "subrepo": "x", "subrepo_path": "y", "class": sh.IDENTICAL,
        "umbrella_bytes": 1, "subrepo_bytes": 1,
        "referenced_by_a_scheduled_surface": False}
    problems = sh.verify(reg)
    assert len(problems) == 1 and "no longer shadows" in problems[0]


@needs_umbrella
def test_a_class_change_is_reported():
    """Two copies converging or diverging is exactly the event worth knowing about."""
    reg = copy.deepcopy(REG)
    name = next(n for n, v in reg["pairs"].items() if v["class"] == sh.DIVERGED)
    reg["pairs"][name]["class"] = sh.IDENTICAL
    problems = sh.verify(reg)
    assert len(problems) == 1 and "class changed" in problems[0]


def test_an_empty_registry_is_a_problem_not_a_pass():
    assert sh.verify({"pairs": {}}) != []
    assert sh.verify({}) != []


# --- safety: never git inside the umbrella -----------------------------------

def test_the_tool_never_runs_git_inside_the_umbrella():
    """A sub-agent's `git reset --hard` in that shared live checkout caused an incident.
    This asserts the source never pairs `git -C` with the umbrella path."""
    src = (OPS / "umbrella_script_shadow_check.py").read_text()
    for line in src.splitlines():
        if '"git"' in line and "-C" in line:
            assert "UMBRELLA" not in line, f"git -C against the umbrella: {line.strip()}"
    assert 'str(GITHUB / repo)' in src, "git is only ever run against sibling checkouts"


def test_subrepo_state_is_read_from_origin_main_not_the_worktree():
    """A sibling can sit on a feature branch; comparing against a checked-out tree makes
    the answer depend on someone else's uncommitted state."""
    src = (OPS / "umbrella_script_shadow_check.py").read_text()
    assert '"origin/main"' in src and 'f"origin/main:{rel}"' in src


# --- exit codes ---------------------------------------------------------------

def test_missing_registry_exits_2(tmp_path):
    assert sh.main(["--registry", str(tmp_path / "nope.json")]) == 2


def test_unreadable_registry_exits_2(tmp_path):
    p = tmp_path / "r.json"
    p.write_text("{truncated")
    assert sh.main(["--registry", str(p)]) == 2


@needs_umbrella
def test_drift_exits_1(tmp_path):
    reg = copy.deepcopy(REG)
    del reg["pairs"][next(iter(reg["pairs"]))]
    p = tmp_path / "r.json"
    p.write_text(json.dumps(reg))
    assert sh.main(["--registry", str(p)]) == 1


@needs_umbrella
def test_committed_registry_has_no_DRIFT_from_the_live_surface():
    """Was `test_clean_exits_0`, asserting `main([]) == 0`.

    RETARGETED 2026-07-31, deliberately and not silently. The property this test
    exists for is *the committed registry still matches the live surface* — no new
    shadow, none vanished, none changed class. That property is unchanged and is
    asserted directly here, on `verify()`, which is where it lives.

    What changed is that "no drift" no longer implies exit 0: a registered
    divergence that a SCHEDULED job executes is now a finding unless the registry
    justifies it (see the class below). The old assertion conflated the two, so
    keeping it as written would have quietly required the new rule to never fire.
    The exit code now has its own test rather than riding on this one.
    """
    reg = json.loads(Path(sh.REGISTRY).read_text(encoding="utf-8"))
    assert sh.verify(reg) == []


@needs_umbrella
def test_emit_never_writes(tmp_path, capsys):
    p = tmp_path / "r.json"
    p.write_text("SENTINEL")
    assert sh.main(["--emit", "--registry", str(p)]) == 0
    assert p.read_text() == "SENTINEL"
    assert json.loads(capsys.readouterr().out)["pairs"]


# --- the sibling half: same fail-open shape as the umbrella half --------------
#
# codex round 2 on #634: fixing the umbrella side left the sibling side open.
# `_sh()` discarded return codes, so an unreachable sibling, a missing origin/main
# or a failed ls-tree all looked identical to "this repo has an empty src/ tree".
# `--emit` would then write a registry missing that repo's pairs, and `verify`
# could report clean over a surface it never read.

def test_sh_raises_instead_of_returning_empty_on_failure():
    """The root of the fail-open: stdout was returned whatever the exit code."""
    with pytest.raises(sh.Unverifiable):
        sh._sh(["git", "-C", "/definitely/not/a/repo", "rev-parse", "HEAD"])


def test_missing_sibling_checkout_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(sh, "GITHUB", tmp_path / "empty-github-root")
    problems = sh.check_siblings()
    assert problems and all("sibling checkout missing" in p for p in problems)


def test_sibling_without_origin_main_is_reported(monkeypatch, tmp_path):
    """A checkout can exist and still be unreadable — e.g. never fetched."""
    root = tmp_path / "gh"
    for repo in sh.SIBLINGS:
        (root / repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(sh, "GITHUB", root)
    problems = sh.check_siblings()
    assert problems and all("no readable origin/main" in p for p in problems)


def test_survey_refuses_rather_than_returning_a_partial_answer(monkeypatch, tmp_path):
    monkeypatch.setattr(sh, "GITHUB", tmp_path / "empty-github-root")
    with pytest.raises(sh.Unverifiable):
        sh.survey()


def test_emit_refuses_to_print_a_partial_registry(monkeypatch, tmp_path, capsys):
    """The dangerous path: emitted output is committed and becomes the baseline."""
    monkeypatch.setattr(sh, "GITHUB", tmp_path / "empty-github-root")
    assert sh.main(["--emit"]) == 2
    out = capsys.readouterr()
    assert out.out.strip() == "", "a partial registry must never reach stdout"
    assert "REFUSING to emit" in out.err


def test_verify_reports_unverifiable_when_a_sibling_is_unreachable(
        monkeypatch, tmp_path):
    """The subtle half of codex's finding: an unreachable sibling with no
    already-registered pair produces an EMPTY diff, which reads as clean."""
    monkeypatch.setattr(sh, "GITHUB", tmp_path / "empty-github-root")
    problems = sh.verify(REG)
    assert len(problems) == 1
    assert problems[0].startswith(sh.UNVERIFIABLE)
    assert "were NOT checked" in problems[0]


def test_unreachable_sibling_exits_2_not_0(monkeypatch, tmp_path):
    monkeypatch.setattr(sh, "GITHUB", tmp_path / "empty-github-root")
    p = tmp_path / "r.json"
    p.write_text(json.dumps(REG))
    assert sh.main(["--registry", str(p)]) == 2


@needs_umbrella
def test_the_exact_silent_clean_scenario_codex_described(monkeypatch):
    """One unreachable sibling that has NO registered pair used to report CLEAN.

    This is the precise hole, reproduced before fixing it: `renquant-pipeline` has
    zero pairs in the registry, so when its `ls-tree` silently returned b"" the
    live/known diff was empty and `verify()` returned `[]`. Nothing was wrong with
    the registry — the tool simply never looked at that repo and said so by saying
    nothing. Guarding on `check_siblings()` is what makes it speak up.

    **Machine-local by nature, and marked as such after it broke CI.** Reproducing the
    OLD behaviour needs a working umbrella AND working siblings with exactly one
    broken — on a machine with no umbrella, `verify()` returns at the umbrella branch
    before the sibling logic is ever reached, so the demonstration cannot run. I wrote
    it as if it were hermetic, which is the same machine-dependence defect this PR is
    about; it is a demonstration, not the guarantee.

    The CI guarantee for this fix is the hermetic set above —
    `test_sh_raises_instead_of_returning_empty_on_failure`,
    `test_missing_sibling_checkout_is_reported`,
    `test_sibling_without_origin_main_is_reported`,
    `test_survey_refuses_rather_than_returning_a_partial_answer`,
    `test_emit_refuses_to_print_a_partial_registry`,
    `test_verify_reports_unverifiable_when_a_sibling_is_unreachable` and
    `test_unreachable_sibling_exits_2_not_0` — all of which run everywhere.
    """
    victim = "renquant-pipeline"
    assert not any(v["subrepo"] == victim for v in REG["pairs"].values()), (
        f"{victim} now has registered pairs — pick another zero-pair sibling or this "
        f"test no longer reproduces the silent-clean case")

    real = sh._sh
    monkeypatch.setattr(
        sh, "_sh", lambda argv: b"" if victim in " ".join(argv) else real(argv))
    monkeypatch.setattr(sh, "check_siblings", lambda: [])   # the gate under test
    assert sh.verify(REG) == [], "expected the OLD fail-open behaviour here"

    monkeypatch.undo()
    monkeypatch.setattr(sh, "GITHUB", Path("/definitely/not/a/github/root"))
    problems = sh.verify(REG)
    assert len(problems) == 1 and problems[0].startswith(sh.UNVERIFIABLE)



# --- a registered divergence on a SCHEDULED surface is not "OK" (2026-07-31) ---
class TestScheduledSurfaceDivergence:
    """`verify()` checks DRIFT from the baseline. These check the VERDICT.

    They monkeypatch `verify` to return no problems, because the subject here is
    what the tool concludes once drift is ruled out — not drift detection, which
    the tests above already cover against the real surface.

    The two controls are load-bearing:
      * an UNSCHEDULED divergence must stay silent, or the check alarms on all 26
        registered divergences and gets switched off wholesale;
      * a JUSTIFIED scheduled divergence must stay silent, or there is no path back
        to green, which ends the same way.
    """

    @staticmethod
    def _pair(**kw):
        base = {"class": sh.DIVERGED, "referenced_by_a_scheduled_surface": True,
                "subrepo": "renquant-model", "subrepo_path": "x.py",
                "subrepo_bytes": 100, "umbrella_bytes": 200}
        base.update(kw)
        return base

    def _run(self, monkeypatch, tmp_path, capsys, pairs):
        monkeypatch.setattr(sh, "verify", lambda reg: [])
        p = tmp_path / "reg.json"
        p.write_text(json.dumps({"schema_version": 1, "pairs": pairs}))
        rc = sh.main(["--registry", str(p)])
        return rc, capsys.readouterr().out

    def test_scheduled_divergence_is_a_finding(self, monkeypatch, tmp_path, capsys):
        rc, out = self._run(monkeypatch, tmp_path, capsys, {"a.py": self._pair()})
        assert rc == 1
        assert "SCHEDULED surface" in out
        assert "a.py" in out and "+100 B" in out

    def test_UNscheduled_divergence_stays_silent(self, monkeypatch, tmp_path, capsys):
        rc, out = self._run(monkeypatch, tmp_path, capsys, {
            "a.py": self._pair(referenced_by_a_scheduled_surface=False)})
        assert rc == 0
        assert "no drift" in out

    def test_a_JUSTIFIED_scheduled_divergence_stays_silent(self, monkeypatch, tmp_path,
                                                          capsys):
        rc, _ = self._run(monkeypatch, tmp_path, capsys, {
            "a.py": self._pair(accepted_because="umbrella pin lags orch#620")})
        assert rc == 0

    def test_a_BLANK_justification_does_not_count(self, monkeypatch, tmp_path, capsys):
        rc, _ = self._run(monkeypatch, tmp_path, capsys, {
            "a.py": self._pair(accepted_because="   ")})
        assert rc == 1

    def test_IDENTICAL_on_a_scheduled_surface_is_never_a_finding(self, monkeypatch,
                                                                 tmp_path, capsys):
        rc, _ = self._run(monkeypatch, tmp_path, capsys, {
            "a.py": self._pair(**{"class": "IDENTICAL"})})
        assert rc == 0

    def test_every_offender_is_NAMED_with_its_byte_delta(self, monkeypatch, tmp_path,
                                                         capsys):
        """A count alone cannot be acted on."""
        rc, out = self._run(monkeypatch, tmp_path, capsys, {
            "a.py": self._pair(subrepo_bytes=1000, umbrella_bytes=900),
            "b.py": self._pair(subrepo="renquant-execution", subrepo_bytes=10,
                               umbrella_bytes=30)})
        assert rc == 1
        assert "a.py" in out and "-100 B" in out
        assert "b.py" in out and "+20 B" in out and "renquant-execution" in out


@needs_umbrella
def test_the_live_registry_has_nine_unjustified_scheduled_divergences():
    """Pins the measured number so issue #656 and the progress doc cannot rot."""
    reg = json.loads(Path(sh.REGISTRY).read_text(encoding="utf-8"))
    hot = [k for k, v in reg["pairs"].items()
           if v.get("class") == sh.DIVERGED
           and v.get("referenced_by_a_scheduled_surface")
           and not str(v.get("accepted_because") or "").strip()]
    assert len(hot) == 9, sorted(hot)
    assert "fit_calibrator_alpha158_fund.py" in hot
    assert sh.main([]) == 1
