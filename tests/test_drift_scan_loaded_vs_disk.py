"""A reviewed launchd change on disk is not a launchd change in force.

Measured 2026-07-29 while verifying the rq105 export fix: the plist was
switched to the wrapper at 06:29:53, fourteen minutes AFTER that morning's
06:15:04 run had already produced `score_source=prod` from the old definition.
The job had in fact been re-bootstrapped — but nothing in the drift scan
established that. It took hand-comparing three timestamps (plist mtime, output
mtime, `launchctl print ... runs =`) to tell "deployed, not yet run" apart from
"not working".

The manifest-vs-disk check cannot see this: a plist edited and never reloaded
matches the manifest perfectly while launchd keeps serving the old program.
"""
from __future__ import annotations

import json
import plistlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))
import run_surface_drift_check as D  # noqa: E402

WRAPPER = ["/bin/zsh", "/repo/ops/renquant105/run_batch_scores_export.sh"]
MODULE = ["/usr/bin/python3", "/repo/ops/renquant105/export_batch_scores.py"]

# Verbatim shape of `launchctl print gui/<uid>/<label>` on this machine.
LAUNCHCTL_OUTPUT = """\
com.renquant.rq105-batch-scores-export = {
\tactive count = 0
\tstate = not running
\tprogram = /bin/zsh
\targuments = {
\t\t/bin/zsh
\t\t/repo/ops/renquant105/run_batch_scores_export.sh
\t}

\tstdout path = /logs/out
\truns = 0
}
"""


def _write_plist(tmp_path: Path, label: str, args: list[str]) -> Path:
    d = tmp_path / "agents"
    d.mkdir(exist_ok=True)
    p = d / f"{label}.plist"
    with open(p, "wb") as fh:
        plistlib.dump({"Label": label, "ProgramArguments": args}, fh)
    return p


def _write_manifest(tmp_path: Path, label: str, args: list[str]) -> Path:
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({"jobs": {label: {
        "program_args": args,
        "program_args_sha256": D.program_args_digest(args),
    }}}))
    return m


LABEL = "com.renquant.rq105-batch-scores-export"


def test_parses_the_real_launchctl_output(monkeypatch):
    class R:
        returncode = 0
        stdout = LAUNCHCTL_OUTPUT
    monkeypatch.setattr(D.subprocess, "run", lambda *a, **k: R())
    assert D.read_loaded_program_args(LABEL) == WRAPPER


def test_the_defect_this_exists_for(tmp_path, monkeypatch):
    """Disk says wrapper, launchd is still running the module."""
    _write_plist(tmp_path, LABEL, WRAPPER)
    manifest = _write_manifest(tmp_path, LABEL, WRAPPER)
    monkeypatch.setattr(D, "read_loaded_program_args", lambda label: MODULE)

    # the manifest-vs-disk check is perfectly happy...
    assert D.check_launchd_surface(str(manifest), str(tmp_path / "agents")) == []
    # ...and the reviewed change is not in force
    problems = D.check_launchd_loaded(str(manifest), str(tmp_path / "agents"))
    assert len(problems) == 1
    assert "RUNNING a different program" in problems[0]
    assert "NOT in force" in problems[0]


def test_agreement_is_silent(tmp_path, monkeypatch):
    _write_plist(tmp_path, LABEL, WRAPPER)
    manifest = _write_manifest(tmp_path, LABEL, WRAPPER)
    monkeypatch.setattr(D, "read_loaded_program_args", lambda label: list(WRAPPER))
    assert D.check_launchd_loaded(str(manifest), str(tmp_path / "agents")) == []


def test_an_unloaded_job_is_not_reported_as_drift(tmp_path, monkeypatch):
    """Deliberately-unloaded jobs are a liveness question, not drift.

    Reporting them here would alarm on every job the operator has stopped.
    """
    _write_plist(tmp_path, LABEL, WRAPPER)
    manifest = _write_manifest(tmp_path, LABEL, WRAPPER)
    monkeypatch.setattr(D, "read_loaded_program_args", lambda label: None)
    assert D.check_launchd_loaded(str(manifest), str(tmp_path / "agents")) == []


def test_a_job_missing_from_disk_is_left_to_the_disk_check(tmp_path, monkeypatch):
    """No double-reporting: the disk check already names this one."""
    (tmp_path / "agents").mkdir()
    manifest = _write_manifest(tmp_path, LABEL, WRAPPER)
    monkeypatch.setattr(D, "read_loaded_program_args", lambda label: MODULE)
    assert D.check_launchd_loaded(str(manifest), str(tmp_path / "agents")) == []
    # ...and it IS reported there
    disk = D.check_launchd_surface(str(manifest), str(tmp_path / "agents"))
    assert any("missing from disk" in p for p in disk)


def test_launchctl_failure_is_not_drift(monkeypatch):
    class R:
        returncode = 113
        stdout = ""
    monkeypatch.setattr(D.subprocess, "run", lambda *a, **k: R())
    assert D.read_loaded_program_args(LABEL) is None


def test_launchctl_raising_is_not_drift(monkeypatch):
    def boom(*a, **k):
        raise OSError("launchctl missing")
    monkeypatch.setattr(D.subprocess, "run", boom)
    assert D.read_loaded_program_args(LABEL) is None


def test_output_without_an_arguments_block_yields_none(monkeypatch):
    class R:
        returncode = 0
        stdout = "com.renquant.x = {\n\tprogram = /bin/true\n}\n"
    monkeypatch.setattr(D.subprocess, "run", lambda *a, **k: R())
    assert D.read_loaded_program_args("com.renquant.x") is None


def test_unreadable_manifest_is_reported(tmp_path):
    problems = D.check_launchd_loaded(str(tmp_path / "nope.json"), str(tmp_path))
    assert problems and "manifest unreadable" in problems[0]


def test_main_aggregates_the_new_check(monkeypatch, capsys):
    monkeypatch.setattr(D, "check_git_surfaces", lambda: ([], []))
    monkeypatch.setattr(D, "check_umbrella_branch", lambda: [])
    monkeypatch.setattr(D, "check_launchd_surface", lambda *a, **k: [])
    monkeypatch.setattr(D, "check_launchd_loaded", lambda *a, **k: ["LOADED DRIFT"])
    monkeypatch.setattr(D, "alert", lambda *a, **k: None)
    rc = D.main([])
    assert rc != 0
    assert "LOADED DRIFT" in capsys.readouterr().out


@pytest.mark.parametrize("trailing", ["", "\n", "\n\n"])
def test_parse_is_robust_to_trailing_whitespace(monkeypatch, trailing):
    class R:
        returncode = 0
        stdout = LAUNCHCTL_OUTPUT + trailing
    monkeypatch.setattr(D.subprocess, "run", lambda *a, **k: R())
    assert D.read_loaded_program_args(LABEL) == WRAPPER
