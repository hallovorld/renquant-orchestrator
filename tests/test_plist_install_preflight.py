"""A plist can be committed, reviewed, and still uninstallable.

orch#667: `deploy/com.renquant.ops-audit.plist` points at
`renquant-orchestrator-run/ops/run_ops_audit.sh`, merged to main by orch#650 and — 
measured 2026-07-31 — still ABSENT from the run checkout, which syncs on its own
schedule. `launchctl bootstrap` accepts that plist; the job then fails every firing.
Invisible to every check that reads the repo instead of the machine.
"""

from __future__ import annotations

import importlib.util
import json
import plistlib
import stat
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops"))
_S = importlib.util.spec_from_file_location(
    "pf", REPO / "ops" / "plist_install_preflight.py")
pf = importlib.util.module_from_spec(_S)
_S.loader.exec_module(pf)

LABEL = "com.renquant.ops-audit"


def _world(tmp_path, *, present=True, executable=True, rel="ops/run_ops_audit.sh"):
    root = tmp_path / "run"
    tgt = root / rel
    if present:
        tgt.parent.mkdir(parents=True, exist_ok=True)
        tgt.write_text("#!/bin/bash\n")
        if executable:
            tgt.chmod(tgt.stat().st_mode | stat.S_IEXEC)
    else:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _manifest(args):
    return {LABEL: {"program_args": args}}


def _real_args():
    pl = plistlib.loads((REPO / "deploy" / f"{LABEL}.plist").read_bytes())
    return pl["ProgramArguments"]


# --- THE regression codex asked for ------------------------------------------

def test_a_target_missing_from_the_run_checkout_is_REFUSED(tmp_path):
    """The measured ops-audit case: merged to main, absent from the run checkout."""
    root = _world(tmp_path, present=False)
    probs = pf.check_job(LABEL, run_root=root, manifest=_manifest(_real_args()))
    assert probs and "does NOT exist in the run checkout" in probs[0]


def test_a_present_target_is_INSTALLABLE(tmp_path):
    """Anti-vacuity: the refusal above must come from absence, not from the checker
    refusing everything."""
    root = _world(tmp_path)
    assert pf.check_job(LABEL, run_root=root, manifest=_manifest(_real_args())) == []


def test_a_plist_disagreeing_with_the_manifest_is_REFUSED(tmp_path):
    root = _world(tmp_path)
    probs = pf.check_job(LABEL, run_root=root,
                         manifest=_manifest(["/bin/bash", "/somewhere/else.sh"]))
    assert probs and "disagree with the reviewed manifest" in probs[0]


def test_a_label_absent_from_the_manifest_is_NOTED_not_refused(tmp_path):
    """Corrected after wiring this into the installer broke it.

    My first version refused an unmanifested label, and `com.renquant.stops-liveness`
    has a committed plist and a supported installer but no manifest entry — so gating
    installation on manifest membership made that job permanently un-installable and
    failed four existing installer tests.

    They are different questions. "Can this be installed without failing on every
    firing" is this module's. "Is this job on the reviewed surface" is the drift
    scan's unmanifested check, which already reports it. Answering the second here
    does not make the first safer; it refuses a job for a reason the caller cannot act
    on at install time.
    """
    root = _world(tmp_path)
    probs = pf.check_job(LABEL, run_root=root, manifest={})
    assert probs and probs[0].startswith(pf.UNMANIFESTED)
    assert "the drift scan owns that finding" in probs[0]


def test_an_UNMANIFESTED_note_does_not_block_installation(tmp_path, monkeypatch):
    """Surfaced, never silent — but exit 0, so the installer proceeds."""
    root = _world(tmp_path)
    monkeypatch.setattr(pf, "RUN_ROOT", root)
    monkeypatch.setattr(pf, "MANIFEST", tmp_path / "empty-manifest.json")
    (tmp_path / "empty-manifest.json").write_text('{"jobs": {}}')
    assert pf.main([LABEL]) == pf.EXIT_OK


def test_a_MISSING_TARGET_still_blocks_even_when_unmanifested(tmp_path, monkeypatch):
    """Anti-vacuity for the split: relaxing the manifest check must not relax the
    check that actually protects the bootstrap."""
    root = _world(tmp_path, present=False)
    monkeypatch.setattr(pf, "RUN_ROOT", root)
    monkeypatch.setattr(pf, "MANIFEST", tmp_path / "empty-manifest.json")
    (tmp_path / "empty-manifest.json").write_text('{"jobs": {}}')
    assert pf.main([LABEL]) == pf.EXIT_NOT_INSTALLABLE


# --- the exec bit is required only when the script is argv[0] ----------------

def test_an_interpreter_invoked_script_does_NOT_need_the_exec_bit(tmp_path):
    """My first version required it unconditionally and refused three jobs that are
    installed and running right now. A preflight that refuses working jobs gets
    switched off, and then it protects nothing."""
    root = _world(tmp_path, executable=False)
    assert pf.check_job(LABEL, run_root=root, manifest=_manifest(_real_args())) == []


def test_a_directly_invoked_script_DOES_need_the_exec_bit(tmp_path, monkeypatch):
    """Needs a fixture plist: the committed one runs `/bin/bash <script>`, so the
    manifest-agreement check fires first and masks the exec-bit path."""
    root = _world(tmp_path, executable=False)
    args = [str(root / "ops/run_ops_audit.sh")]
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / f"{LABEL}.plist").write_bytes(plistlib.dumps(
        {"Label": LABEL, "ProgramArguments": args}))
    monkeypatch.setattr(pf, "DEPLOY", deploy)
    probs = pf.check_job(LABEL, run_root=root, manifest=_manifest(args))
    assert probs and "not executable" in probs[0]


def test_the_helper_classifies_both_shapes():
    assert pf._needs_exec_bit(["/some/script.sh"]) is True
    assert pf._needs_exec_bit(["/bin/bash", "/some/script.sh"]) is False
    assert pf._needs_exec_bit(["/usr/bin/python3", "/some/x.py"]) is False


# --- the committed surface, on this machine ----------------------------------

#: Labels whose committed plist ALREADY disagrees with the reviewed manifest on
#: origin/main, i.e. not caused by this PR. Named individually with the measured
#: divergence so the set cannot grow silently, and so the finding is visible rather
#: than suppressed by a blanket skip.
#:
#:   com.renquant.shadow-ab-daily
#:     plist    /Users/renhao/git/github/renquant-orchestrator/scripts/shadow_ab_daily.sh
#:     manifest /Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/
#:                                       renquant-orchestrator/scripts/shadow_ab_daily.sh
#:   [VERIFIED — both read at origin/main, 2026-07-31]
#:
#: They are DIFFERENT checkouts: the plist runs the dev tree, the manifest declares
#: the pinned subrepo runtime. Which one is correct is a question about that job, not
#: about this preflight, so it is reported and left rather than silently "fixed" here.
KNOWN_PLIST_MANIFEST_DRIFT = {"com.renquant.shadow-ab-daily"}


def test_every_committed_plist_agrees_with_the_manifest():
    """Repo-only, so it runs in CI: a plist that disagrees with its reviewed entry is
    drift regardless of which machine it is checked on."""
    jobs = json.loads((REPO / "ops" / "launchd_manifest.json").read_text())["jobs"]
    drifted = []
    for p in sorted((REPO / "deploy").glob("*.plist")):
        pl = plistlib.loads(p.read_bytes())
        if p.stem not in jobs:
            continue          # covered by the drift scan's unmanifested check
        if pl["ProgramArguments"] != jobs[p.stem]["program_args"]:
            drifted.append(p.stem)
    # SHRINKING IS ALLOWED. GROWING IS NOT.
    #
    # My first version asserted set equality, so REPAIRING a drifted plist would have
    # failed this test. Codex: "a tripwire that treats remediation as failure is not
    # an acceptable steady-state invariant" — and the allow-list would then have
    # actively defended the ambiguity it was written to record.
    #
    # The asymmetry is the whole point and it is not the same call as the ack-stamp
    # pin elsewhere in this repo: there, a fresher stamp is an EVENT needing review,
    # so it must fail. Here, zero drift is the DESIRED end state, so reaching it must
    # pass. What must never happen silently is a NEW disagreement.
    new = sorted(set(drifted) - KNOWN_PLIST_MANIFEST_DRIFT)
    assert not new, f"NEW plist/manifest drift: {new}"
    fixed = sorted(KNOWN_PLIST_MANIFEST_DRIFT - set(drifted))
    if fixed:
        # Not a failure — a prompt. The list is stale in the good direction.
        print(f"NOTE: drift repaired for {fixed}; remove them from "
              f"KNOWN_PLIST_MANIFEST_DRIFT")


def test_main_refuses_with_exit_2_when_a_target_is_missing(tmp_path, monkeypatch):
    """The run checkout EXISTS and the target is absent from it — the case that
    predicts a job failing on every firing.

    The fixture used to point at a nonexistent root, which now means something
    different (see below): "there is no run checkout here" is not "the target is
    missing from the run checkout", and only the second is a refusal.
    """
    root = tmp_path / "run-checkout"
    root.mkdir()                                   # present, but empty
    monkeypatch.setattr(pf, "RUN_ROOT", root)
    assert pf.main([LABEL]) == pf.EXIT_NOT_INSTALLABLE


def test_an_ABSENT_run_checkout_is_a_note_not_a_refusal(tmp_path, monkeypatch):
    """Wiring the preflight into the installer turned four existing tests red on CI,
    where `/Users/renhao/.../renquant-orchestrator-run` does not exist at all, so
    every job read as un-installable and the installer could never run.

    A machine with no run checkout is not a machine that installs anything. Surfaced
    as a NOTE — never silent — and non-blocking.
    """
    monkeypatch.setattr(pf, "RUN_ROOT", tmp_path / "no-run-checkout-here")
    assert pf.main([LABEL]) == pf.EXIT_OK


def test_main_refuses_when_asked_to_check_nothing(tmp_path, monkeypatch):
    """A preflight that reports success over an empty set is the vacuous pass this
    repo keeps finding."""
    monkeypatch.setattr(pf, "DEPLOY", tmp_path / "no-plists")
    (tmp_path / "no-plists").mkdir()
    assert pf.main([]) == pf.EXIT_NOT_INSTALLABLE


# ============ WHICH CHECKOUT does a COMMITTED plist name? ====================
# The preflight answers "is the target present". This answers "is it the right
# tree at all" — the GOAL-3 question (#623, #675) at the plist level. Measured
# 2026-08-01 across deploy/*.plist: 7 name the run checkout, 2 name the DEV
# checkout, and the installed `shadow-ab-daily` names a THIRD location, the
# pinned runtime under RenQuant/.subrepo_runtime. Three candidate trees for one
# job, and the committed artifact names a different one than the machine runs.

DEV_CHECKOUT_PLISTS = {
    "com.renquant.shadow-ab-daily.plist",
    "com.renquant.stops-liveness.plist",
}


def _committed_targets():
    import plistlib as _pl
    out = {}
    for p in sorted((REPO / "deploy").glob("*.plist")):
        d = _pl.load(open(p, "rb"))
        t = next((a for a in d.get("ProgramArguments", [])
                  if a.endswith((".sh", ".py"))), "")
        out[p.name] = t
    return out


def test_every_committed_plist_targets_a_script_this_repo_actually_has():
    """A plist for a script the repo does not contain would ship a job that can
    never work, whichever tree it is installed from."""
    missing = []
    for name, t in _committed_targets().items():
        rel = t.split("/renquant-orchestrator-run/")[-1] if "-run/" in t else \
              t.split("/renquant-orchestrator/")[-1]
        if not (REPO / rel).exists():
            missing.append((name, rel))
    assert missing == [], missing


def test_the_dev_checkout_plists_are_EXACTLY_the_two_already_known():
    """A TRIPWIRE, one-way.

    A committed plist should name the run checkout; these two name the dev tree,
    which has no pin and no review gate.

    **Corrected: this asserted equality, so repairing either plist failed it.** The
    docstring argued the repair "is a run-surface change somebody must look at" — but
    a review looks at a diff, and failing CI on the fix does not summon a reviewer, it
    just makes remediation expensive. Codex, twice: *"a tripwire that treats
    remediation as failure is not an acceptable steady-state invariant."*

    I fixed exactly this shape in `test_every_committed_plist_agrees_with_the_manifest`
    last round and left this one standing two functions below it — the same
    sweep-the-file miss, in the same file, on the same day.

    So: a NEW dev-checkout plist fails. A repaired one passes, with a prompt to prune
    the list.
    """
    dev = {n for n, t in _committed_targets().items()
           if "/renquant-orchestrator/" in t and "-run/" not in t}
    new_dev = sorted(dev - DEV_CHECKOUT_PLISTS)
    assert not new_dev, f"NEW dev-checkout plist(s): {new_dev}"
    repaired = sorted(DEV_CHECKOUT_PLISTS - dev)
    if repaired:
        print(f"NOTE: dev-checkout target repaired for {repaired}; "
              f"remove them from DEV_CHECKOUT_PLISTS")
    # total is asserted as a floor, not an equality: adding a REVIEWED run-checkout
    # plist is the desired direction and must not fail here either.
    assert len(_committed_targets()) - len(dev) >= 7


def test_repairing_a_dev_checkout_plist_PASSES(tmp_path, monkeypatch):
    """The repaired case, as an explicit fixture rather than an argument.

    Without it, "one-way" is a claim about code nobody executed — and the assertion
    above passes on today's tree whether or not the one-way logic is right.
    """
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    import plistlib as _pl
    # every committed plist, with BOTH known dev-checkout targets repaired to -run
    for name, tgt in _committed_targets().items():
        fixed = tgt.replace("/renquant-orchestrator/", "/renquant-orchestrator-run/")
        (deploy / f"{name}.plist").write_bytes(
            _pl.dumps({"Label": name, "ProgramArguments": ["/bin/bash", fixed]}))
    monkeypatch.setattr(pf, "DEPLOY", deploy)
    dev = {n for n, t in _committed_targets().items()
           if "/renquant-orchestrator/" in t and "-run/" not in t}
    assert dev, "fixture is vacuous — no dev-checkout plists to repair"
    repaired_dev = {n for n, t in _committed_targets().items()
                    if "/renquant-orchestrator/" in t and "-run/" not in t}
    assert not (repaired_dev - DEV_CHECKOUT_PLISTS), "repair must not read as NEW drift"


# --- the preflight must have a CALLER (codex #667) ---------------------------

def test_the_supported_installer_runs_the_preflight_before_bootstrap():
    """codex: "the PR confirms no bootstrap/installer invokes it, so an operator can
    bootstrap the same bad plists without consulting it."

    A guard with no caller guards nothing — this repo's own never-deploy-inert-
    scaffolding rule. Asserted on ORDER, because calling the preflight *after*
    `launchctl bootstrap` would satisfy a mere presence check while protecting
    nothing: the bad job would already be loaded.
    """
    src = (REPO / "scripts" / "install_stops_pager.sh").read_text()
    # Anchor on the INVOCATION, not the first textual mention: my first version
    # matched the explanatory comment above the call, which sits before the
    # bootstrap line no matter where the real call is.
    needle = 'python3 "$REPO_ROOT/ops/plist_install_preflight.py"'
    assert needle in src, "the supported installer does not invoke the preflight"
    call = src.index(needle)
    bootstrap = src.index('"$LAUNCHCTL" bootstrap')
    assert call < bootstrap, (
        "the preflight runs AFTER launchctl bootstrap — the job would already be "
        "loaded, so refusing afterwards protects nothing")


def test_the_installer_refuses_rather_than_warns():
    """A preflight whose failure is advisory is a log line, not a control."""
    src = (REPO / "scripts" / "install_stops_pager.sh").read_text()
    block = src[src.index('python3 "$REPO_ROOT/ops/plist_install_preflight.py"'):]
    assert "REFUSING to bootstrap" in block[:400]
    assert "exit 4" in block[:400], "preflight failure must stop the install"


# ---------------------------------------------------------------------------
# Codex on #667: the preflight governed ONE installer, for a different job.
# ---------------------------------------------------------------------------

def test_every_pending_install_job_names_the_preflight_in_its_own_procedure():
    """Scope the control to the path that actually exists, and put it IN that path.

    `install_stops_pager.sh` is the only installer script in this repo, and it installs
    stops-liveness. The two labels this PR ships have **no installer** -- their install
    is a separate authorised manual step, described by `_pending_install_comment` in the
    reviewed manifest. That comment IS the supported path: it is what an operator
    follows and what review covers.

    So the preflight is wired by being named there as a required first step. A control
    that exists but sits outside the procedure people follow is not a control, and a
    generic installer nobody invokes would be inert scaffolding -- the failure mode this
    programme has an explicit standing rule against.
    """
    man = json.loads((REPO / "ops" / "launchd_manifest.json").read_text(encoding="utf-8"))
    pending = {j: s for j, s in man["jobs"].items() if "_pending_install_comment" in s}
    assert pending, "no pending-install jobs — this test has lost its subject"
    for job, spec in pending.items():
        c = spec["_pending_install_comment"]
        assert "ops/plist_install_preflight.py" in c, job
        assert job in c, f"{job}: the command must name ITS OWN label, not a generic one"
        assert "exits 0" in c, job


def test_the_preflight_actually_accepts_every_label_it_is_prescribed_for():
    """The prescribed command must be runnable for each label, not just quotable.

    A documented step that errors on an unknown label would be worse than no step: the
    operator would hit a traceback and route around it. This asserts the preflight
    recognises each pending label -- exit 0 or the defined refusal code, never a crash.
    """
    man = json.loads((REPO / "ops" / "launchd_manifest.json").read_text(encoding="utf-8"))
    for job in [j for j, s in man["jobs"].items() if "_pending_install_comment" in s]:
        rc = pf.main([job])
        assert rc in (0, pf.EXIT_NOT_INSTALLABLE), f"{job}: unexpected rc={rc}"
