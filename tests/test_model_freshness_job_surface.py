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
    assert len(runs) == 1, runs
    assert "renquant_orchestrator.model_freshness_monitor" in runs[0]
    assert "--notify" in runs[0]


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
