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


def test_a_label_absent_from_the_manifest_is_REFUSED(tmp_path):
    root = _world(tmp_path)
    probs = pf.check_job(LABEL, run_root=root, manifest={})
    assert probs and "not in the reviewed manifest" in probs[0]


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
    assert set(drifted) == KNOWN_PLIST_MANIFEST_DRIFT, (
        f"plist/manifest drift set changed: "
        f"new={sorted(set(drifted) - KNOWN_PLIST_MANIFEST_DRIFT)} "
        f"fixed={sorted(KNOWN_PLIST_MANIFEST_DRIFT - set(drifted))}")


def test_main_refuses_with_exit_2_when_a_target_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "RUN_ROOT", tmp_path / "empty-run-checkout")
    assert pf.main([LABEL]) == pf.EXIT_NOT_INSTALLABLE


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
    """A TRIPWIRE, not an allowance. A committed plist should name the run
    checkout; these two name the dev tree, which has no pin and no review gate.

    It fails BOTH ways on purpose: a third dev-checkout plist fails it, and so
    does repairing either of these — because that repair is a run-surface change
    somebody must look at rather than absorb silently.
    """
    dev = {n for n, t in _committed_targets().items()
           if "/renquant-orchestrator/" in t and "-run/" not in t}
    assert dev == DEV_CHECKOUT_PLISTS, dev
    assert len(_committed_targets()) - len(dev) == 7
