"""The reviewed surface for the weekly momentum TRAIN job must agree with itself.

GOAL-7 slice 5 (renquant-model doc/design/2026-08-02-momentum-pipeline-architecture.md,
build-order item 5), REVIEWED-SURFACE half: wrapper + manifest entry + plist land
merged-but-dark; the plist install and the model/s104 pin set are one operator grant
(model#197 ordering). Three artifacts describe this job — the plist launchd would
load, the manifest entry the drift scan compares against, and the wrapper both point
at — and a hand-typed digest that drifts from its own `program_args` would make the
drift scan compare a stale constant and pass forever, so the digest is RE-DERIVED
with the drift scan's own function rather than asserted as a literal
(the test_model_freshness_job_surface.py precedent).

The wrapper's evidence contract is deliberately the INVERSE of
run_model_freshness_monitor.sh's: exec-redirect FIRST, so every refusal lands in the
dated log (the conditional-retrain silent-pre-exec-death lesson, orch#754 trail).
The behavior tests below pin exactly that: a refused run STILL leaves a dated log
whose content says REFUSED, and the #638 concern (fresh evidence for a run that
never happened) is answered by content — every exit path writes a terminal marker.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import os
import plistlib
import re
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LABEL = "com.renquant.momentum-train-weekly"
PLIST = REPO / "ops" / "renquant104" / f"{LABEL}.plist"
WRAPPER = REPO / "ops" / "renquant104" / "momentum_train_weekly.sh"
MANIFEST = REPO / "ops" / "launchd_manifest.json"

_SPEC = importlib.util.spec_from_file_location(
    "run_surface_drift_check", REPO / "ops" / "run_surface_drift_check.py")
drift = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(drift)


def _entry() -> dict:
    return json.loads(MANIFEST.read_text())["jobs"][LABEL]


# --------------------------------------------------------- reviewed surface --
def test_the_manifest_carries_the_job():
    assert LABEL in json.loads(MANIFEST.read_text())["jobs"]


def test_the_digest_is_the_drift_scans_own_function_of_the_args():
    """Not a transcribed literal: edit program_args and forget the digest, and
    the drift scan would compare live plists against a hash of the OLD args."""
    e = _entry()
    assert e["program_args_sha256"] == drift.program_args_digest(e["program_args"])


def test_the_plist_and_the_manifest_describe_the_SAME_command():
    got = plistlib.loads(PLIST.read_bytes())
    assert got["Label"] == LABEL
    assert list(got["ProgramArguments"]) == _entry()["program_args"]


def test_the_wrapper_named_by_the_surface_exists_in_this_repo():
    """The manifest points into the RUN checkout, which is this repo deployed."""
    named = Path(_entry()["program_args"][-1])
    assert named.name == WRAPPER.name
    assert named.parent.name == WRAPPER.parent.name
    assert WRAPPER.exists()
    assert os.access(WRAPPER, os.X_OK)


def test_the_evidence_glob_matches_what_the_wrapper_writes():
    """#627: liveness scored on StandardOutPath gave FALSE stale readings for
    every wrapper that redirects to a dated file."""
    stem = "momentum_train_"
    e = _entry()
    assert stem in e["evidence_glob"]
    assert "20[0-9][0-9]" in e["evidence_glob"]
    assert stem in WRAPPER.read_text()


def test_the_pending_install_state_is_fully_retired_for_this_job():
    """Grant C step (c) RE-EXECUTED after the corrected-order gates
    (pipeline#255 + RenQuant#554 + orch#761 merged; orch#759 record): the job
    is INSTALLED and verified loaded, so the merged-but-dark declaration must
    be GONE from both reviewed surfaces — a lingering pending marker over an
    installed job would teach the drift scan to trust a stale state. The
    inverse rot (uninstalled job with no marker) stays caught by the drift
    test's exact-equality set against launchctl."""
    e = _entry()
    assert "_pending_install_comment" not in e
    assert "_install_precondition_comment" not in e
    from test_run_surface_drift_check import TestManifestGeneration as T
    assert LABEL not in T.PENDING_INSTALL
    # No pending-install label may dangle: each must BE a manifested job.
    jobs = json.loads(MANIFEST.read_text())["jobs"]
    for pending in T.PENDING_INSTALL:
        assert pending in jobs, f"PENDING_INSTALL names an unmanifested job: {pending}"


def test_the_schedule_is_weekly_saturday_after_the_wf_refresh_cluster():
    """Design: weekly cadence aligned with the WF world. weekly-wf-promote and
    weekly-fundamental-refresh fire Saturday 04:00 (installed plists, read
    2026-08-02); this job must follow them on the SAME Saturday (fresh
    Friday-close surfaces) and must not take 05:30 — the slot the retiring
    weekly-retrain-patchtst occupies until its #755 bootout grant executes."""
    entries = plistlib.loads(PLIST.read_bytes())["StartCalendarInterval"]
    assert len(entries) == 1, entries        # weekly means ONE calendar entry
    e = entries[0]
    assert e["Weekday"] == 6, e              # Saturday
    assert (e["Hour"], e["Minute"]) > (4, 0), e
    assert (e["Hour"], e["Minute"]) != (5, 30), e


# ------------------------------------------------- one deterministic root ----
def test_the_wrapper_carries_NO_fallback_idiom():
    """The #675/#751 rule: a `[ -d ... ] || VAR=` fallback lets filesystem state
    pick which checkout executes. The drift scan reads every manifested wrapper
    and alarms on the idiom; this pins the same property at the source level
    with the scan's OWN regex, so the two cannot drift apart."""
    assert drift._FALLBACK_RE.search(WRAPPER.read_text()) is None


def test_the_fallback_regex_is_not_vacuous():
    """Anti-vacuity control: if _FALLBACK_RE were renamed or loosened to match
    nothing, the test above would pass forever. It must still catch the exact
    two-line shape the rq105 wrappers carried."""
    fixture = ('X="$(dirname "$R")/sib-run/src"\n'
               '[ -d "$X" ] || X="$(dirname "$R")/sib/src"\n')
    assert drift._FALLBACK_RE.search(fixture) is not None


def test_the_drift_scans_own_wrapper_scan_reports_the_wrapper_clean():
    """Run the production scan function over this wrapper's text: zero problems
    and the deterministic-root info line (it declares PYTHONPATH)."""
    problems: list[str] = []
    infos: list[str] = []
    drift._scan_wrapper_text(LABEL, WRAPPER.read_text(), "/nonexistent-repos-root",
                             problems, infos)
    assert problems == [], problems
    assert any("deterministic root" in i for i in infos), infos


def test_the_wrapper_pins_the_pinned_model_runtime_root():
    """One reviewed root: the PINNED runtime checkout materialised by the
    umbrella — never a dev checkout, never an alternative root."""
    body = WRAPPER.read_text()
    assert '.subrepo_runtime/repos/renquant-model' in body
    assert 'export PYTHONPATH="$MODEL_RUNTIME/src"' in body


def _invocations(path: Path) -> list[str]:
    """Lines that RUN something, excluding comments and log prose (the
    test_model_freshness_job_surface.py lesson: prose that mentions a mutation
    is not a mutation)."""
    out = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("echo ", 'echo"', "echo'")):
            continue
        out.append(line)
    return out


def test_exactly_two_python_commands_run_and_both_are_the_train_cli():
    """Allowlist, not a banned-substring list: this wrapper runs the TRAIN CLI
    twice — the v0 lane, then the v1_fast shadow lane (model#199 item 2) —
    and nothing else. A third invocation slipping in (a promote, a config
    write) fails here by count before anyone reads what it does. The v0
    invocation is pinned FLAG-FREE: byte-identical to the pre-#199 reviewed
    command, so the prod-bound lane's meaning cannot change under an old OR
    new pinned CLI."""
    runs = [l for l in _invocations(WRAPPER)
            if l.startswith(('"$PYTHON"', "$PYTHON"))]
    assert len(runs) == 2, runs
    v0, fast = runs
    assert '"$TRAIN_CLI"' in v0
    assert "--asof" in v0 and '--out-root "$OUT_ROOT"' in v0
    assert "--params-version" not in v0, "the v0 lane must stay flag-free"
    assert '"$TRAIN_CLI"' in fast
    assert "--params-version v1_fast" in fast
    assert '--out-root "$OUT_ROOT_FAST"' in fast


def test_the_out_root_follows_the_197_serving_convention():
    """model#197: the JOB publishes to artifacts/momentum/<cutoff>/ under the
    strategy serving root (the root s104 artifact_path entries resolve under).
    The CLI appends <asof>/momentum_residual_v0.json itself, so the wrapper's
    out-root is exactly <serving root>/artifacts/momentum — and the fast lane
    (model#199 item 2) publishes its OWN ledger + dated dirs under the sibling
    artifacts/momentum_fast, the path the s104 fast shadow entry pins."""
    body = WRAPPER.read_text()
    assert 'SERVING_ROOT="$RQ_ROOT/backtesting/renquant_104"' in body
    assert 'OUT_ROOT="$SERVING_ROOT/artifacts/momentum"' in body
    assert 'OUT_ROOT_FAST="$SERVING_ROOT/artifacts/momentum_fast"' in body


# ------------------------------------------------------ behavior (fake root) --
# The wrapper's contract under a fake umbrella root: refusals LAND IN THE DATED
# LOG (exec-first — the inverse of the model-freshness ordering, on purpose),
# exit codes pass through, and argv is exactly the reviewed invocation.

def _fake_root(tmp_path, *, cli=True, python_body="exit 0",
               python_body_second=None) -> Path:
    """Stub umbrella. The stub interpreter APPENDS argv (the wrapper now runs
    the TRAIN CLI twice — v0 then v1_fast, model#199 item 2) and can exit
    differently per call (`python_body_second`) so the lane-independence
    contract is testable; it defaults to `python_body` for both calls."""
    root = tmp_path / "umbrella"
    (root / ".venv" / "bin").mkdir(parents=True)
    model = root / ".subrepo_runtime" / "repos" / "renquant-model"
    (model / "src").mkdir(parents=True)
    if cli:
        (model / "tools").mkdir(parents=True)
        (model / "tools" / "momentum_train_run.py").write_text("# stub\n")
    py = root / ".venv" / "bin" / "python"
    second = python_body if python_body_second is None else python_body_second
    py.write_text("#!/bin/sh\n"
                  f'printf \'%s\\n\' "$@" >> "{root}/argv.txt"\n'
                  'echo "CLI ran"\n'
                  f'if [ -f "{root}/first_call_done" ]; then\n'
                  f"  {second}\n"
                  "else\n"
                  f'  : > "{root}/first_call_done"\n'
                  f"  {python_body}\n"
                  "fi\n")
    py.chmod(py.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return root


def _run(root: Path):
    env = dict(os.environ, RQ_ROOT=str(root))
    env.pop("PYTHONPATH", None)
    return subprocess.run(["/bin/bash", str(WRAPPER)], env=env,
                          capture_output=True, text=True, timeout=60)


def _log(root: Path) -> Path | None:
    logs = sorted((root / "logs" / "rq104").glob("momentum_train_*.log")) \
        if (root / "logs" / "rq104").exists() else []
    assert len(logs) <= 1, logs
    return logs[0] if logs else None


def test_a_missing_train_cli_refusal_LANDS_IN_THE_DATED_LOG(tmp_path):
    """THE CONTRACT THIS WRAPPER EXISTS TO KEEP. The pin has not been advanced
    past model#196: the wrapper must refuse with rc 64 AND the refusal must be
    readable in the dated log — not lost to launchd's shared .err, which is the
    silent-pre-exec-death shape the conditional-retrain diagnosis surfaced."""
    root = _fake_root(tmp_path, cli=False)
    r = _run(root)
    assert r.returncode == 64, (r.returncode, r.stderr)
    log = _log(root)
    assert log is not None, "refusal produced no dated evidence"
    body = log.read_text()
    assert "REFUSED" in body
    assert "model#196" in body           # names the unmet precondition
    assert "end rc=64" in body           # terminal marker on the refusal path


def test_a_missing_pinned_checkout_names_the_run_surface_sync(tmp_path):
    root = _fake_root(tmp_path)
    import shutil
    shutil.rmtree(root / ".subrepo_runtime")
    r = _run(root)
    assert r.returncode == 64
    body = _log(root).read_text()
    assert "run-surface sync" in body


def test_a_non_executable_interpreter_refusal_is_logged(tmp_path):
    root = _fake_root(tmp_path)
    (root / ".venv" / "bin" / "python").chmod(0o644)
    r = _run(root)
    assert r.returncode == 64
    assert "REFUSED" in _log(root).read_text()


def test_success_passes_rc_through_and_argv_is_the_reviewed_invocation(tmp_path):
    root = _fake_root(tmp_path, python_body="exit 0")
    r = _run(root)
    assert r.returncode == 0, (r.returncode, r.stderr)
    argv = (root / "argv.txt").read_text().splitlines()
    today = _dt.date.today().isoformat()
    cli = str(root / ".subrepo_runtime/repos/renquant-model/tools/momentum_train_run.py")
    assert argv == [
        # LANE 1 — v0, flag-free: byte-identical to the pre-#199 invocation.
        cli,
        "--asof", today,
        "--out-root", str(root / "backtesting/renquant_104/artifacts/momentum"),
        # LANE 2 — v1_fast into its OWN out-root (model#199 item 2).
        cli,
        "--asof", today,
        "--params-version", "v1_fast",
        "--out-root", str(root / "backtesting/renquant_104/artifacts/momentum_fast"),
    ], argv
    body = _log(root).read_text()
    assert "CLI ran" in body
    assert "train CLI exit=0" in body
    assert "fast train CLI exit=0" in body
    assert "end rc=0 fast_rc=0" in body
    assert f"momentum_train_{today}.log" == _log(root).name


@pytest.mark.parametrize("code", [3, 4, 5])
def test_cli_refusal_codes_pass_through_unswallowed(tmp_path, code):
    """The CLI's exit code IS the payload (3 surfaces missing / 4 artifact
    exists / 5 ledger refused). A wrapper that flattens it to 0 would make
    launchd record every refusal as success. The stub exits `code` on BOTH
    calls; the wrapper's exit is the V0 lane's code by contract."""
    root = _fake_root(tmp_path, python_body=f"exit {code}")
    r = _run(root)
    assert r.returncode == code, (r.returncode, r.stderr)
    body = _log(root).read_text()
    assert f"train CLI exit={code}" in body
    assert f"fast train CLI exit={code}" in body
    assert f"end rc={code} fast_rc={code}" in body


def test_a_fast_lane_failure_is_logged_but_NEVER_propagated(tmp_path):
    """THE model#199-item-2 contract: v0 is bound for the prod MoE, the fast
    lane is a shadow patrol — a fast failure must not block the slow
    artifact. v0 exits 0, fast exits 9: launchd must record 0, and the dated
    log must carry the fast verdict so the failure stays legible."""
    root = _fake_root(tmp_path, python_body="exit 0", python_body_second="exit 9")
    r = _run(root)
    assert r.returncode == 0, (r.returncode, r.stderr)
    body = _log(root).read_text()
    assert "train CLI exit=0" in body
    assert "fast train CLI exit=9" in body
    assert "end rc=0 fast_rc=9" in body


def test_a_v0_failure_does_not_stop_the_fast_lane_and_still_owns_the_rc(tmp_path):
    """Independent lanes, both directions: v0 exits 3 (surfaces missing),
    fast exits 0 — the wrapper must still run the fast step (argv shows both
    invocations) and must still exit with the V0 code."""
    root = _fake_root(tmp_path, python_body="exit 3", python_body_second="exit 0")
    r = _run(root)
    assert r.returncode == 3, (r.returncode, r.stderr)
    argv = (root / "argv.txt").read_text().splitlines()
    assert argv.count("--asof") == 2, "the fast lane did not run after a v0 failure"
    assert "--params-version" in argv
    assert "end rc=3 fast_rc=0" in _log(root).read_text()


def test_the_wrapper_writes_nothing_outside_the_log_dir(tmp_path):
    """The WRAPPER's own writes are the dated log only — artifacts are the
    CLI's to write (here a stub that writes argv.txt + its call-count
    marker). Snapshot the tree, run, diff."""
    root = _fake_root(tmp_path, python_body="exit 0")
    before = {str(p.relative_to(root)) for p in root.rglob("*")}
    _run(root)
    after = {str(p.relative_to(root)) for p in root.rglob("*")}
    new = {p for p in after - before if not p.startswith("logs")}
    # the stub CLI's own records, nothing else — nothing from the wrapper.
    assert new == {"argv.txt", "first_call_done"}, new
