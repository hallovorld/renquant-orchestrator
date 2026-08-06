"""A job launchd is RUNNING that no reviewed surface declares must be loud.

Both pre-existing launchd checks enumerate a declared set — one walks the plists
on disk, the other walks the manifest. A job bootstrapped from a path outside the
scanned directory and never manifested is invisible to both. These tests pin the
new check that starts from launchd instead.

`loaded_labels` is injected everywhere: a test that read this machine's real
launchd domain would be vacuously green on CI and would go red on the operator's
box for reasons that have nothing to do with the code.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ops.run_surface_drift_check import (  # noqa: E402
    check_launchd_loaded_undeclared, read_loaded_labels,
)


def _manifest(tmp_path: pathlib.Path, labels) -> str:
    p = tmp_path / "launchd_manifest.json"
    p.write_text(json.dumps(
        {"jobs": {l: {"program_args": ["/bin/sh", f"/tmp/{l}.sh"]} for l in labels}}),
        encoding="utf-8")
    return str(p)


def _agents(tmp_path: pathlib.Path) -> str:
    d = tmp_path / "LaunchAgents"
    d.mkdir(exist_ok=True)
    return str(d)


# --- the hole this closes -------------------------------------------------

def test_loaded_with_no_plist_and_no_manifest_entry_is_reported(tmp_path):
    """The invisible case: bootstrapped from outside the scanned directory."""
    m = _manifest(tmp_path, ["com.renquant.daily104"])
    out = check_launchd_loaded_undeclared(
        m, _agents(tmp_path),
        loaded_labels=["com.renquant.daily104", "com.renquant.ghost"])
    assert len(out) == 1
    assert "com.renquant.ghost" in out[0]
    assert "NO plist in the scanned directory" in out[0]


def test_a_fully_declared_domain_is_silent(tmp_path):
    m = _manifest(tmp_path, ["com.renquant.daily104", "com.renquant.intraday104"])
    out = check_launchd_loaded_undeclared(
        m, _agents(tmp_path),
        loaded_labels=["com.renquant.daily104", "com.renquant.intraday104"])
    assert out == []


def test_a_manifested_job_that_is_NOT_loaded_is_not_reported_here(tmp_path):
    """Unloaded-ness is a liveness question another check owns. Reporting it
    here would fire on every job the operator deliberately unloaded."""
    m = _manifest(tmp_path, ["com.renquant.daily104", "com.renquant.retired"])
    out = check_launchd_loaded_undeclared(
        m, _agents(tmp_path), loaded_labels=["com.renquant.daily104"])
    assert out == []


def test_non_renquant_labels_are_ignored(tmp_path):
    """The check filters by prefix ITSELF rather than trusting its caller to
    have done it. Otherwise the day the caller changes, every Apple agent on
    the box is reported as an undeclared RenQuant job and the noise buries the
    one real finding."""
    m = _manifest(tmp_path, [])
    out = check_launchd_loaded_undeclared(
        m, _agents(tmp_path),
        loaded_labels=["com.apple.something", "com.renquant.ghost"])
    assert len(out) == 1
    assert "com.renquant.ghost" in out[0]
    assert all("com.apple" not in p for p in out)


# --- the refusals ---------------------------------------------------------

def test_blind_branch_message_names_itself(monkeypatch, tmp_path):
    import ops.run_surface_drift_check as M
    monkeypatch.setattr(M, "read_loaded_labels",
                        lambda: (None, "launchctl exit 1: boom"))
    m = _manifest(tmp_path, ["com.renquant.daily104"])
    out = M.check_launchd_loaded_undeclared(m, _agents(tmp_path))
    assert len(out) == 1
    assert "BLIND" in out[0]
    assert "boom" in out[0]


def test_unreadable_manifest_refuses_rather_than_reporting_everything(tmp_path):
    """A manifest that will not parse must not make every loaded job look
    undeclared — that turns one defect into forty."""
    bad = tmp_path / "m.json"
    bad.write_text("{not json", encoding="utf-8")
    out = check_launchd_loaded_undeclared(
        str(bad), _agents(tmp_path),
        loaded_labels=["com.renquant.a", "com.renquant.b"])
    assert len(out) == 1
    assert "manifest unreadable" in out[0]


# --- the message must not invite the wrong remedy -------------------------

def test_message_forbids_silencing_by_editing_the_manifest(tmp_path):
    """CLAUDE.md's containment protocol: never silence the drift alarm by
    editing the reviewed surface outside review."""
    m = _manifest(tmp_path, [])
    out = check_launchd_loaded_undeclared(
        m, _agents(tmp_path), loaded_labels=["com.renquant.ghost"])
    assert "do not" in out[0].lower()
    assert "outside a reviewed change" in out[0]


# --- the launchctl parser -------------------------------------------------

def test_parser_skips_the_header_and_keeps_only_renquant(monkeypatch):
    import ops.run_surface_drift_check as M

    class R:
        returncode = 0
        stdout = ("PID\tStatus\tLabel\n"
                  "4281\t0\tcom.apple.CryptoTokenKit.ahp.agent\n"
                  "-\t2\tcom.renquant.crypto-session\n"
                  "123\t0\tcom.renquant.daily104\n")
        stderr = ""

    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: R())
    labels, detail = M.read_loaded_labels()
    assert labels == ["com.renquant.crypto-session", "com.renquant.daily104"]
    assert detail == ""


def test_parser_returns_None_on_nonzero_exit(monkeypatch):
    import ops.run_surface_drift_check as M

    class R:
        returncode = 1
        stdout = ""
        stderr = "nope"

    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: R())
    labels, detail = M.read_loaded_labels()
    assert labels is None
    assert "exit 1" in detail


def test_parser_returns_None_when_launchctl_cannot_be_invoked(monkeypatch):
    import ops.run_surface_drift_check as M

    def boom(*a, **k):
        raise OSError("no launchctl")

    monkeypatch.setattr(M.subprocess, "run", boom)
    labels, detail = M.read_loaded_labels()
    assert labels is None
    assert "invocation failed" in detail
