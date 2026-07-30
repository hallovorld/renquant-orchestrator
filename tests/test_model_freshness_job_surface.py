"""The scheduled surface for the model-freshness monitor must agree with itself.

Three artifacts describe this job: the plist launchd actually loads, the manifest
entry the drift scan compares against, and the wrapper both point at. A hand-typed
digest that drifts from its own `program_args` would make the drift scan compare a
stale constant and pass forever — the recurring shape on this programme is a check
whose subject is not what the reader assumes, so the digest here is RE-DERIVED with
the drift scan's own function rather than asserted as a literal.
"""

from __future__ import annotations

import importlib.util
import json
import plistlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LABEL = "com.renquant.rq104-model-freshness"
PLIST = REPO / "ops" / "renquant104" / f"{LABEL}.plist"
WRAPPER = REPO / "ops" / "renquant104" / "run_model_freshness_monitor.sh"
MANIFEST = REPO / "ops" / "launchd_manifest.json"

_SPEC = importlib.util.spec_from_file_location(
    "run_surface_drift_check", REPO / "ops" / "run_surface_drift_check.py")
drift = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(drift)


def _entry() -> dict:
    return json.loads(MANIFEST.read_text())["jobs"][LABEL]


def test_the_manifest_carries_the_job():
    assert LABEL in json.loads(MANIFEST.read_text())["jobs"]


def test_the_digest_is_the_drift_scans_own_function_of_the_args():
    """Not a transcribed literal. If someone edits program_args and forgets the
    digest, the drift scan would compare live plists against a hash of the OLD
    args and report clean while the surface moved."""
    e = _entry()
    assert e["program_args_sha256"] == drift.program_args_digest(e["program_args"])


def test_the_plist_and_the_manifest_describe_the_SAME_command():
    """The manifest is only a guard if it pins what launchd will actually run."""
    got = plistlib.loads(PLIST.read_bytes())
    assert got["Label"] == LABEL
    assert list(got["ProgramArguments"]) == _entry()["program_args"]


def test_the_wrapper_named_by_the_surface_exists_in_this_repo():
    """The manifest points into the RUN checkout, which is this repo deployed. A
    surface naming a script that does not exist here would install a job that
    cannot run."""
    named = Path(_entry()["program_args"][-1])
    assert named.name == WRAPPER.name
    assert named.parent.name == WRAPPER.parent.name
    assert WRAPPER.exists()


def test_the_evidence_glob_matches_what_the_wrapper_writes():
    """#627's lesson: scoring liveness on StandardOutPath gave FALSE stale
    readings for every wrapper that redirects to a dated file. The glob must
    match the wrapper's real filename pattern, so pin the stem in both."""
    stem = "model_freshness_"
    assert stem in _entry()["evidence_glob"]
    assert stem in WRAPPER.read_text()


def test_the_wrapper_does_not_swallow_the_monitors_exit_code():
    """The exit code IS the payload (0 healthy / 1 warn / 2 escalate / 3 breach).
    Piping into tee makes `$?` report tee's status, which is 0 forever."""
    body = WRAPPER.read_text()
    assert "PIPESTATUS[0]" in body
    assert 'exit "$RC"' in body


def _invocations(path: Path) -> list[str]:
    """Lines that RUN something, excluding comments and log prose.

    Two earlier versions of the guard below got their subject wrong. The first
    scanned the whole file and tripped on the wrapper's header, which names the
    things it promises not to do. The second stripped comments but still tripped on
    an `echo` whose text says "promotes/fits/retrains nothing". Prose that mentions
    a mutation is not a mutation — the object to check is the set of commands the
    shell actually executes.
    """
    out = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("echo ", "echo\"", "echo'")):
            continue
        out.append(line)
    return out


def test_the_wrapper_stays_observe_only():
    """Design §5 defers the 28-day CEILING until a validated remediation path
    exists. Scheduling the monitor must not smuggle the gate in: no promotion, no
    retrain trigger, no config mutation."""
    body = "\n".join(_invocations(WRAPPER))
    for forbidden in ("promote", "--retrain", "model_staleness_days",
                      "strategy_config.json"):
        assert forbidden not in body, forbidden


def test_exactly_one_python_command_runs_and_it_is_the_monitor():
    """The tightest statement of observe-only: this wrapper runs the monitor and
    nothing else. A banned-substring list can only catch mutations someone thought
    to name; an allowlist of invocations catches the ones they did not."""
    # A variable ASSIGNMENT that names the interpreter (`PYTHON=...`,
    # `export PYTHONPATH=...`) is not an invocation. Filtering on the substring
    # alone counted three "runs" where the shell executes one.
    runs = [l for l in _invocations(WRAPPER)
            if l.startswith(('"$PYTHON"', "$PYTHON"))]
    # TWO invocations by design since the #638 evidence-ordering fix: a read-only
    # import PROBE that must run before any evidence is committed, then the monitor.
    # Naming both explicitly keeps this an allowlist -- loosening it to "at least one
    # is the monitor" would let a third, mutating call slip in unnoticed.
    assert len(runs) == 2, runs
    probe, run = runs
    assert probe.startswith('"$PYTHON" -c "import renquant_orchestrator.model_freshness_monitor"'), probe
    assert "renquant_orchestrator.model_freshness_monitor" in run
    assert "--notify" in run


def test_the_observe_only_check_is_not_vacuous():
    """Anti-vacuity control: the filter must not simply eat the whole file.
    Without this, a bug that returned [] would make both guards pass forever."""
    body = _invocations(WRAPPER)
    assert len(body) >= 15, body
    assert any("model_freshness_monitor" in l for l in body)


def test_the_schedule_lands_before_the_dawn_preflight():
    """A freshness verdict that arrives after the funnel probe cannot inform it.
    Dawn preflight fires 06:05; this must precede it on the same weekdays."""
    got = plistlib.loads(PLIST.read_bytes())
    entries = got["StartCalendarInterval"]
    assert {e["Weekday"] for e in entries} == {1, 2, 3, 4, 5}
    for e in entries:
        assert (e["Hour"], e["Minute"]) < (6, 5), e


# --- codex BLOCKER on #638: evidence must not exist unless the monitor ran --------
# The first wrapper created the dated log BEFORE env setup, so a setup failure left a
# fresh evidence file and no run, and the liveness scan (which scores this job on
# exactly that glob) would report it alive. These tests build a fake umbrella root and
# break one prerequisite at a time.

import os
import stat
import subprocess
import textwrap


def _fake_root(tmp_path, *, python_body="exit 0", probe_body="exit 0",
               env_sh=None, log_dir_ok=True):
    root = tmp_path / "umbrella"
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    if log_dir_ok:
        (root / "logs" / "rq104").mkdir(parents=True)
    py = root / ".venv" / "bin" / "python"
    # The wrapper calls this twice with different argv: `-c "import ..."` (the probe)
    # and `-m ...` (the run). A stub that ignored argv made the probe consume the
    # run's exit code, which is how the anti-vacuity test first failed -- the stub
    # was the wrong object, not the wrapper.
    py.write_text("#!/bin/sh\n"
                  'case "$1" in -c) ' + probe_body + ';; esac\n'
                  + python_body + "\n")
    py.chmod(py.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    (root / "scripts" / "subrepo_env.sh").write_text(env_sh if env_sh is not None else
        textwrap.dedent(f"""\
        renquant_load_subrepo_env() {{ return 0; }}
        renquant_subrepo_root() {{ echo "{root}"; }}
        renquant_subrepo_pythonpath() {{ echo "{root}/src"; }}
        """))
    return root


def _run(root, tmp_path):
    env = dict(os.environ, RQ_ROOT=str(root))
    env.pop("PYTHONPATH", None)
    return subprocess.run(["/bin/bash", str(WRAPPER)], env=env,
                          capture_output=True, text=True, timeout=120)


def _logs(root):
    d = root / "logs" / "rq104"
    return sorted(d.glob("model_freshness_*.log")) if d.exists() else []


def test_a_missing_umbrella_root_writes_no_evidence(tmp_path):
    r = _run(tmp_path / "nope", tmp_path)
    assert r.returncode == 4, r.stderr
    assert "PREREQ FAILED" in r.stderr


def test_a_non_executable_interpreter_writes_no_evidence(tmp_path):
    root = _fake_root(tmp_path)
    (root / ".venv" / "bin" / "python").chmod(0o644)
    r = _run(root, tmp_path)
    assert r.returncode == 4, r.stderr
    assert _logs(root) == [], "evidence landed for a run that never happened"


def test_an_unreadable_subrepo_env_writes_no_evidence(tmp_path):
    root = _fake_root(tmp_path)
    (root / "scripts" / "subrepo_env.sh").unlink()
    r = _run(root, tmp_path)
    assert r.returncode == 4, r.stderr
    assert _logs(root) == []


def test_an_empty_subrepo_root_writes_no_evidence(tmp_path):
    """`renquant_subrepo_root` returning "" used to flow straight into PYTHONPATH."""
    root = _fake_root(tmp_path, env_sh=textwrap.dedent("""\
        renquant_load_subrepo_env() { return 0; }
        renquant_subrepo_root() { echo ""; }
        renquant_subrepo_pythonpath() { echo ""; }
        """))
    r = _run(root, tmp_path)
    assert r.returncode == 4, r.stderr
    assert _logs(root) == []


def test_an_unimportable_monitor_writes_no_evidence(tmp_path):
    """THE CASE THAT MATTERS MOST: everything resolves, but PYTHONPATH points at a
    checkout without the module. Without the import probe this reached the run step
    and published a log for a ModuleNotFoundError."""
    root = _fake_root(tmp_path, probe_body="exit 1")   # import probe fails
    r = _run(root, tmp_path)
    assert r.returncode == 4, r.stderr
    assert "not importable" in r.stderr
    assert _logs(root) == []


def test_evidence_appears_only_after_the_monitor_returns(tmp_path):
    """Anti-vacuity control. If the prerequisites hold, a log MUST be published and
    MUST carry the terminal marker — otherwise the tests above would pass simply
    because the wrapper never writes anything at all."""
    root = _fake_root(tmp_path, python_body='echo "monitor ran"; exit 3')
    r = _run(root, tmp_path)
    assert r.returncode == 3, (r.returncode, r.stderr)   # monitor's tier passes through
    logs = _logs(root)
    assert len(logs) == 1, logs
    body = logs[0].read_text()
    assert "monitor ran" in body
    assert "monitor exit=3" in body
    assert "monitor end" in body, "terminal marker missing"


def test_no_temp_file_is_left_behind_on_failure(tmp_path):
    """The temp log lives beside the evidence path, so a leaked one would match the
    evidence_glob prefix and could be mistaken for evidence by a looser matcher."""
    root = _fake_root(tmp_path, probe_body="exit 1")
    _run(root, tmp_path)
    d = root / "logs" / "rq104"
    assert list(d.glob("model_freshness_*")) == []
