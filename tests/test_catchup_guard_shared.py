"""The SHARED boot catch-up guard (ops/catchup_guard.sh) — literal-cutoff mode,
and its wiring into the two wrappers that gained it on 2026-08-30: the dawn
preflight (session mode, slot 0605) and the run-surface drift scan (literal
2400 cutoff, slot 0700, every calendar day).

The rq105 contract of the same guard (session mode, the calendar helper, the
two rq105 wrappers) stays in tests/test_rq105_liveness_serving_chain.py §6.
Everything here runs the guard under `bash` (the CI runner has no zsh) with an
RQ_ROOT / helper stub in tmp_path — nothing reads the operator's disk.
"""
from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OPS = ROOT / "ops"
GUARD = OPS / "catchup_guard.sh"
HELPER = OPS / "catchup_cutoff.py"
DAWN = OPS / "renquant104" / "dawn_funnel_preflight.sh"
DRIFT_WRAPPER = OPS / "run_surface_drift_scan.sh"
MANIFEST = OPS / "launchd_manifest.json"


def _venv_root(tmp_path: Path) -> Path:
    rq = tmp_path / "rq"
    (rq / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    py = rq / ".venv" / "bin" / "python"
    if not py.exists():
        py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        py.chmod(0o755)
    return rq


def _stub_helper(tmp_path: Path, stdout: str = "1300", rc: int = 0) -> Path:
    """A helper that records that it was CALLED (literal mode must never call it)."""
    called = tmp_path / "helper_called.txt"
    helper = tmp_path / "catchup_cutoff.py"
    helper.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path({str(called)!r}).write_text(' '.join(sys.argv[1:]))\n"
        f"print({stdout!r})\nsys.exit({rc})\n")
    return helper


def _guard(tmp_path: Path, day: str, now: str, cutoff: str, *outputs: str, slot="0700",
           env=None, job="run-surface-drift"):
    log = tmp_path / "guard.log"
    cmd = (f'. "{GUARD}"; launchd_catchup_guard {job} {day} {now} {slot} {cutoff} "{log}" '
           + " ".join(f'"{o}"' for o in outputs))
    base = {"RQ_ROOT": str(_venv_root(tmp_path))} if env is None else env
    # hermetic: the ambient shell must not supply the guard's inputs
    ambient = {k: v for k, v in os.environ.items()
               if k not in ("RQ_ROOT", "CATCHUP_CUTOFF_HELPER", "PYTHONPATH")}
    res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                         env={**ambient, **base})
    lines = log.read_text().splitlines() if log.exists() else []
    return res.returncode, lines, res.stderr


# --- literal cutoff: a calendar-day job keeps its calendar-day behaviour -----

@pytest.mark.parametrize("day", ["2026-08-29", "2026-08-30", "2026-09-07"])  # Sat, Sun, Labor Day
def test_literal_cutoff_runs_on_non_session_days(tmp_path, day):
    """The drift scan fires every day; its catch-up must too. No calendar is
    consulted, so a weekend or a holiday is not a refusal."""
    rc, lines, _ = _guard(tmp_path, day, "1038", "2400", str(tmp_path / "scan.log"))
    assert rc == 0, lines
    assert len(lines) == 1 and " RUN " in lines[0] and "literal cutoff 2400" in lines[0]
    assert "calendar-day job" in lines[0]


def test_literal_mode_never_calls_the_helper_and_needs_no_helper_env(tmp_path):
    helper = _stub_helper(tmp_path)
    env = {"RQ_ROOT": str(_venv_root(tmp_path)), "CATCHUP_CUTOFF_HELPER": str(helper),
           "PYTHONPATH": str(tmp_path / "pinned-src")}
    rc, lines, _ = _guard(tmp_path, "2026-08-30", "1038", "2400", str(tmp_path / "scan.log"), env=env)
    assert rc == 0 and " RUN " in lines[0]
    assert not (tmp_path / "helper_called.txt").exists(), "literal mode consulted the calendar helper"
    # and without the session-mode variables it still works (only RQ_ROOT is required)
    rc, lines, err = _guard(tmp_path, "2026-08-30", "1038", "2400", str(tmp_path / "scan2.log"))
    assert rc == 0 and err == ""


@pytest.mark.parametrize("now,why", [
    ("0659", "before the 0700 slot"), ("0000", "before the 0700 slot"),
    ("2359", "at/after the 2359 cutoff"),
])
def test_literal_cutoff_window_edges(tmp_path, now, why):
    cutoff = "2359" if now == "2359" else "2400"
    rc, lines, _ = _guard(tmp_path, "2026-08-30", now, cutoff, str(tmp_path / "scan.log"))
    assert rc == 1 and len(lines) == 1 and " SKIP " in lines[0] and why in lines[0]


def test_literal_cutoff_is_idempotent_on_the_dated_output(tmp_path):
    out = tmp_path / "scan.log"
    out.write_text("")   # an EMPTY dated file still counts: the job fired
    rc, lines, _ = _guard(tmp_path, "2026-08-30", "1038", "2400", str(out))
    assert rc == 1 and "already present" in lines[0]


def test_session_mode_still_requires_the_helper_env_but_literal_does_not(tmp_path):
    """The requirement list is per mode: session needs RQ_ROOT + helper +
    PYTHONPATH; literal needs RQ_ROOT only. A missing RQ_ROOT is rc 2 in both."""
    rc, lines, err = _guard(tmp_path, "2026-08-31", "0900", "session", str(tmp_path / "x"),
                            env={"RQ_ROOT": str(_venv_root(tmp_path))})
    assert rc == 2 and lines == [] and "CATCHUP_CUTOFF_HELPER" in err
    rc, lines, err = _guard(tmp_path, "2026-08-31", "0900", "2400", str(tmp_path / "x"), env={})
    assert rc == 2 and lines == [] and "RQ_ROOT" in err


@pytest.mark.parametrize("bad", ["13:00", "noon", "130", "sessions", ""])
def test_an_unknown_cutoff_spec_is_a_usage_error_not_a_run(tmp_path, bad):
    log = tmp_path / "guard.log"
    cmd = (f'. "{GUARD}"; launchd_catchup_guard j 2026-08-31 0900 0700 "{bad}" "{log}" "{tmp_path}/x"')
    res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                         env={**os.environ, "RQ_ROOT": str(_venv_root(tmp_path))})
    assert res.returncode == 2 and not log.exists()
    assert "cutoff must be 'session' or a literal HHMM" in res.stderr


def test_the_old_six_argument_signature_is_a_usage_error(tmp_path):
    """The rq105 call shape before the move (no cutoff argument) must not be
    silently reinterpreted: `<guard_log>` would land in the cutoff slot."""
    log = tmp_path / "guard.log"
    cmd = f'. "{GUARD}"; launchd_catchup_guard j 2026-08-31 0900 0700 "{log}" "{tmp_path}/x"'
    res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                         env={**os.environ, "RQ_ROOT": str(_venv_root(tmp_path))})
    assert res.returncode == 2 and "usage" in res.stderr


def test_session_mode_with_the_real_helper_and_the_real_calendar(tmp_path):
    """One end-to-end session-mode run through the SHARED paths (the full
    matrix lives in the rq105 suite): a Sunday refuses, a normal session runs."""
    env = {"RQ_ROOT": str(_venv_root(tmp_path)), "CATCHUP_CUTOFF_HELPER": str(HELPER),
           "PYTHONPATH": str(ROOT / "src") + (os.pathsep + os.environ.get("PYTHONPATH", "")
                                                 if os.environ.get("PYTHONPATH") else ""),
           "TZ": "America/Los_Angeles"}
    rc, lines, _ = _guard(tmp_path, "2026-08-30", "1038", "session", str(tmp_path / "p.log"),
                          slot="0605", env=env, job="dawn-preflight")
    assert rc == 1 and "non-session" in lines[0], lines
    rc, lines, _ = _guard(tmp_path, "2026-08-31", "1038", "session", str(tmp_path / "p.log"),
                          slot="0605", env=env, job="dawn-preflight")
    assert rc == 0 and len(lines) == 2, lines   # the guard log accumulates
    assert " RUN " in lines[-1] and "session close 1300" in lines[-1], lines


# --- the two new wrappers are wired to the shared guard ---------------------

def _code(path: Path) -> list[str]:
    return [l for l in path.read_text().splitlines() if l.strip() and not l.strip().startswith("#")]


def test_dawn_preflight_sources_the_shared_guard_in_session_mode_before_the_pin_check():
    code = "\n".join(_code(DAWN))
    assert '. "$OPS_DIR/../catchup_guard.sh"' in code
    assert 'export CATCHUP_CUTOFF_HELPER="$OPS_DIR/../catchup_cutoff.py"' in code
    assert 'export RQ_ROOT="$REPO_DIR"' in code
    assert 'launchd_catchup_guard dawn-preflight "$(date +%F)" "$(date +%H%M)" 0605 session \\' in code
    assert '"$LOG_DIR/catchup_guard_dawn-preflight_$(date +%F).log"' in code
    # the idempotency witness is the probe log the bridge step writes
    assert code.index('LOG="$LOG_DIR/dawn_funnel_preflight_$(date +%F).log"') < code.index("launchd_catchup_guard ")
    guard_call = code.index("launchd_catchup_guard ")
    assert code[guard_call:].split("\n")[2].strip() == '"$LOG"'
    # AFTER the pinned PYTHONPATH export (the calendar comes from the pinned
    # orchestrator), BEFORE the pin check (a skip must not re-run it)
    assert code.index("export PYTHONPATH=") < guard_call < code.index("dawn_pin_identity_check.py")
    assert "1) exit 0 ;;" in code and 'echo "FATAL: catch-up guard error' in code
    # the plist slot the guard names is the plist's own
    with open(ROOT / "deploy" / "com.renquant.rq104-dawn-preflight.plist", "rb") as fh:
        plist = plistlib.load(fh)
    assert {(d["Hour"], d["Minute"]) for d in plist["StartCalendarInterval"]} == {(6, 5)}
    assert {d["Weekday"] for d in plist["StartCalendarInterval"]} == {1, 2, 3, 4, 5}
    assert plist["RunAtLoad"] is True


def test_drift_wrapper_sources_the_shared_guard_with_a_literal_cutoff_every_day():
    code = "\n".join(_code(DRIFT_WRAPPER))
    assert '. "$OPS_DIR/catchup_guard.sh"' in code
    assert 'launchd_catchup_guard run-surface-drift "$TS" "$(date +%H%M)" 0700 2400 \\' in code
    assert '"$LOG_DIR/catchup_guard_run-surface-drift_$TS.log"' in code
    assert 'SCAN_LOG="$LOG_DIR/run_surface_drift_$TS.log"' in code and '"$SCAN_LOG"' in code
    assert "session" not in code.split("launchd_catchup_guard ")[1].split("\n")[0]
    # the scan itself is unchanged and its stdout still reaches launchd (tee)
    assert '"$RQ_ROOT/.venv/bin/python" "$OPS_DIR/run_surface_drift_check.py" 2>&1 | tee -a "$SCAN_LOG"' in code
    assert "RC=${PIPESTATUS[0]}" in code and 'exit "$RC"' in code
    assert "1) exit 0 ;;" in code and 'echo "FATAL: catch-up guard error' in code
    # one deterministic root, restating the plist's environment; no fallback idiom
    assert 'export PYTHONPATH="$RQ_ORCH_ROOT/src:$RQ_ORCH_ROOT/ops"' in code
    assert "[ -d " not in code
    with open(ROOT / "deploy" / "com.renquant.run-surface-drift.plist", "rb") as fh:
        plist = plistlib.load(fh)
    assert plist["ProgramArguments"] == [
        "/Users/renhao/git/github/renquant-orchestrator-run/ops/run_surface_drift_scan.sh"]
    assert plist["RunAtLoad"] is True
    sci = plist["StartCalendarInterval"]
    assert isinstance(sci, dict) and sci == {"Hour": 7, "Minute": 0}, "the scan runs EVERY calendar day"
    assert plist["EnvironmentVariables"]["PYTHONPATH"] == \
        "/Users/renhao/git/github/renquant-orchestrator-run/src:/Users/renhao/git/github/renquant-orchestrator-run/ops"


def test_drift_wrapper_passes_the_drift_scans_own_pythonpath_check(tmp_path):
    """check_wrapper_pythonpath_roots must not flag the wrapper that runs it."""
    sys.path.insert(0, str(OPS))
    try:
        import run_surface_drift_check as drift
    finally:
        sys.path.pop(0)
    problems: list[str] = []
    infos: list[str] = []
    text = drift._with_sourced_text(str(DRIFT_WRAPPER), DRIFT_WRAPPER.read_text())
    drift._scan_wrapper_text("com.renquant.run-surface-drift", text, str(tmp_path), problems, infos)
    assert problems == [] and infos and "deterministic root" in infos[0]


def test_drift_wrapper_runs_end_to_end_with_a_stub_checker(tmp_path):
    """The whole wrapper under bash with RQ_ROOT / RQ_ORCH_ROOT in tmp_path and
    a stub run_surface_drift_check.py next to a COPY of the wrapper: the guard
    runs (slot passed, no dated log), the checker's lines reach BOTH stdout and
    the dated log, the rc line is appended, the exit code is the checker's; a
    second invocation the same day is a one-line guard skip."""
    rq = _venv_root(tmp_path)
    ops = tmp_path / "orch" / "ops"
    ops.mkdir(parents=True)
    (ops / "run_surface_drift_scan.sh").write_text(DRIFT_WRAPPER.read_text())
    (ops / "catchup_guard.sh").write_text(GUARD.read_text())
    (ops / "run_surface_drift_check.py").write_text("import sys\nprint('SCAN-LINE')\nsys.exit(1)\n")
    env = {**os.environ, "RQ_ROOT": str(rq), "RQ_ORCH_ROOT": str(tmp_path / "orch"), "TZ": "UTC"}
    # the guard reads the wall clock for HHMM; before 07:00 UTC it skips by design
    hhmm = subprocess.run(["date", "+%H%M"], capture_output=True, text=True, env=env).stdout.strip()
    if hhmm < "0700":
        pytest.skip("before the 07:00 slot in UTC — the wrapper would (correctly) skip")
    res = subprocess.run(["bash", str(ops / "run_surface_drift_scan.sh")], capture_output=True,
                         text=True, env=env)
    day = subprocess.run(["date", "+%Y-%m-%d"], capture_output=True, text=True, env=env).stdout.strip()
    dated = rq / "logs" / "rq104" / f"run_surface_drift_{day}.log"
    assert res.returncode == 1, (res.stdout, res.stderr)
    assert "SCAN-LINE" in res.stdout
    body = dated.read_text()
    assert "SCAN-LINE" in body and "run-surface-drift rc=1" in body.splitlines()[-1]
    guard_log = rq / "logs" / "rq104" / f"catchup_guard_run-surface-drift_{day}.log"
    assert " RUN " in guard_log.read_text()
    res2 = subprocess.run(["bash", str(ops / "run_surface_drift_scan.sh")], capture_output=True,
                          text=True, env=env)
    assert res2.returncode == 0 and res2.stdout == ""
    assert "already present" in guard_log.read_text().splitlines()[-1]
    assert dated.read_text() == body


def test_manifest_and_plists_agree_on_the_two_new_intents():
    sys.path.insert(0, str(OPS))
    try:
        import run_surface_drift_check as drift
    finally:
        sys.path.pop(0)
    jobs = json.loads(MANIFEST.read_text())["jobs"]
    for label in ("com.renquant.rq104-dawn-preflight", "com.renquant.run-surface-drift"):
        plist = ROOT / "deploy" / f"{label}.plist"
        assert jobs[label]["run_at_load"] is True
        assert jobs[label]["program_args"] == drift.read_plist_program_args(str(plist))
        assert jobs[label]["program_args_sha256"] == drift.program_args_digest(jobs[label]["program_args"])
        assert "_run_at_load_comment" in jobs[label]


def test_no_reference_to_the_old_rq105_guard_paths_remains():
    """The move is complete: nothing sources or names the retired paths."""
    stale = []
    for path in list(OPS.rglob("*.sh")) + list(OPS.rglob("*.py")) + list(OPS.rglob("*.plist")) + [MANIFEST]:
        if path in (GUARD, HELPER):
            continue        # their headers cite where they were born
        text = path.read_text(errors="replace")
        if "rq105_catchup_guard" in text or "rq105_catchup_cutoff" in text:
            stale.append(str(path.relative_to(ROOT)))
    assert stale == [], stale
    assert not (OPS / "renquant105" / "rq105_catchup_guard.sh").exists()
    assert not (OPS / "renquant105" / "rq105_catchup_cutoff.py").exists()
