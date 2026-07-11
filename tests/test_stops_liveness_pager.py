"""Hermetic tests for the software-stop liveness pager package.

S-FRAC stage-3 ops (#471 operator shortlist item 2: pager scheduled nowhere,
page never test-fired). Everything here runs without network, launchd, or the
umbrella checkout: the wrapper's checker-invocation/ntfy/paths are
env-injectable (RENQUANT_STOPS_PAGER_*), a throwaway local HTTP server
records "pages", and the installer's launchctl is replaced by a recording
stub. Page/no-page tests use RENQUANT_STOPS_PAGER_CHECKER_CMD (a TEST-ONLY
escape hatch documented in the wrapper's header) to substitute a fake checker
process, so they never touch a real lock file, git, or renquant_pipeline —
the checker itself moved to renquant-execution#29 (this package's Codex
review, 2026-07-11) and is tested THERE
(renquant-execution tests/test_software_stops_liveness.py); this suite only
covers the WRAPPER's own paging/exit-code/pin-resolution-wiring logic.

What is NOT covered hermetically (and is the operator landing demo instead):
real ntfy.sh delivery, real launchd bootstrap, and the checker running end
-to-end against the pinned renquant-execution/renquant-pipeline checkouts
with real dependencies installed. Tests here pin the contract: plist shape,
live-topic wiring, page/no-page per checker exit class, delivery-failure exit
codes, echo-first dry-run, and that the wrapper resolves the pinned sibling
src roots via renquant_orchestrator.runtime_paths (never a hardcoded
umbrella/.venv path) — including the pin-resolution-failure page path,
exercised for real against a deliberately empty repo root (no lock file),
using only stdlib (runtime_paths.py has no third-party dependency).
"""
from __future__ import annotations

import plistlib
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLIST_PATH = REPO_ROOT / "deploy" / "com.renquant.stops-liveness.plist"
WRAPPER = REPO_ROOT / "scripts" / "stops_liveness_pager.sh"
INSTALLER = REPO_ROOT / "scripts" / "install_stops_pager.sh"

LIVE_OPS_TOPIC = "renquant"  # the live sell-only loop's alert channel


# ---------------------------------------------------------------- fixtures

class _NtfyRecorder(BaseHTTPRequestHandler):
    """Minimal local stand-in for ntfy.sh: records every POST."""

    requests: list[dict] = []

    def do_POST(self):  # noqa: N802 — http.server API
        length = int(self.headers.get("Content-Length", 0))
        type(self).requests.append(
            {
                "path": self.path,
                "title": self.headers.get("Title", ""),
                "priority": self.headers.get("Priority", ""),
                "body": self.rfile.read(length).decode(),
            }
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):  # silence test output
        pass


@pytest.fixture()
def ntfy_server():
    _NtfyRecorder.requests = []
    server = HTTPServer(("127.0.0.1", 0), _NtfyRecorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", _NtfyRecorder.requests
    finally:
        server.shutdown()


def _fake_checker(tmp_path: Path, exit_code: int, message: str) -> Path:
    path = tmp_path / "fake_checker.py"
    path.write_text(
        "import sys\n"
        f"print({message!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return path


def _run_wrapper(tmp_path: Path, *, checker_exit: int, checker_msg: str,
                 ntfy_base: str, topic: str = "test-topic") -> subprocess.CompletedProcess:
    checker = _fake_checker(tmp_path, checker_exit, checker_msg)
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        # TEST-ONLY escape hatch (see wrapper header doc): replaces the
        # pin-resolved "$PYTHON -m renquant_execution.software_stops_liveness"
        # invocation entirely, so these tests never touch a real lock file,
        # git, or renquant_pipeline.
        "RENQUANT_STOPS_PAGER_CHECKER_CMD": f"python3 {checker}",
        "RENQUANT_STOPS_PAGER_NTFY_BASE": ntfy_base,
        "RENQUANT_STOPS_PAGER_NTFY_TOPIC": topic,
    }
    return subprocess.run(
        ["bash", str(WRAPPER)],
        env=env, text=True, capture_output=True, timeout=60,
    )


# ------------------------------------------------------------- plist shape

def test_plist_parses_and_schedules_the_wrapper():
    """Launchd contract: shell wrapper (rq105 ops convention — never python
    directly), 10-minute all-day interval (the checker self-gates to market
    sessions), no RunAtLoad, logs under the NEUTRAL orchestrator-owned
    operational root (~/.renquant/ops/ — sibling to R-PIN's
    ~/.renquant/deploy/ neutral state root), never the umbrella logs tree."""
    with open(PLIST_PATH, "rb") as fh:
        plist = plistlib.load(fh)

    assert plist["Label"] == "com.renquant.stops-liveness"
    args = plist["ProgramArguments"]
    assert args[0] in ("/bin/bash", "/bin/zsh"), "must run through a shell wrapper"
    assert args[-1].endswith("scripts/stops_liveness_pager.sh")
    assert plist["StartInterval"] == 600
    assert plist["RunAtLoad"] is False
    assert ".renquant/ops/stops-liveness" in plist["StandardOutPath"]
    assert ".renquant/ops/stops-liveness" in plist["StandardErrorPath"]
    assert "RenQuant/logs" not in plist["StandardOutPath"]
    assert "RenQuant/logs" not in plist["StandardErrorPath"]


def test_plist_pins_the_live_ops_topic():
    """The page must land on the LIVE ops channel — the same topic the live
    sell-only loop alerts on — declared as explicit plist configuration
    (deploy-plist convention from com.renquant.shadow-ab-daily.plist)."""
    with open(PLIST_PATH, "rb") as fh:
        plist = plistlib.load(fh)
    env = plist["EnvironmentVariables"]
    assert env["RENQUANT_STOPS_PAGER_NTFY_TOPIC"] == LIVE_OPS_TOPIC


def test_plist_supplies_explicit_python_and_data_root_not_via_umbrella_venv():
    """Codex review (2026-07-11) of this package's prior revision: the
    checker must not be invoked through RenQuant/.venv. The plist still
    configures an explicit interpreter + data root (RUNTIME CONTRACT — the
    wrapper itself has no default), but the interpreter path must not
    reference the umbrella's .venv, and the checker module must be the
    execution-repo one."""
    with open(PLIST_PATH, "rb") as fh:
        plist = plistlib.load(fh)
    env = plist["EnvironmentVariables"]
    assert "RENQUANT_STOPS_PAGER_PYTHON" in env
    assert "RENQUANT_STOPS_PAGER_DATA_ROOT" in env
    assert "RenQuant/.venv" not in env["RENQUANT_STOPS_PAGER_PYTHON"]
    assert "RenQuant/.venv" not in plist["ProgramArguments"][-1]


def test_wrapper_defaults_match_the_plist_topic_and_execution_repo_checker():
    content = WRAPPER.read_text(encoding="utf-8")
    # ad hoc invocation (no plist env) must page the same live topic
    assert f'NTFY_TOPIC:-{LIVE_OPS_TOPIC}}}' in content
    # the checker now lives in renquant-execution, invoked as a module via
    # the pinned sibling-checkout PYTHONPATH resolver (runtime_paths), never
    # the deprecated umbrella script or its venv.
    assert "renquant_execution.software_stops_liveness" in content
    assert "resolve_subrepo_src_roots" in content
    assert "check_software_stops_liveness.py" not in content
    assert "RenQuant/.venv" not in content
    assert ".subrepo_runtime" not in content, (
        "no hardcoded umbrella subrepo_runtime path — resolution goes "
        "through runtime_paths.resolve_subrepo_src_roots instead"
    )


def test_wrapper_and_installer_exist_and_are_executable():
    for script in (WRAPPER, INSTALLER):
        assert script.exists(), f"{script} missing"
        assert script.stat().st_mode & 0o111, f"{script} not executable"


# ----------------------------------------------------- wrapper page logic

def test_wrapper_ok_exit_pages_nothing(tmp_path, ntfy_server):
    base, requests = ntfy_server
    proc = _run_wrapper(tmp_path, checker_exit=0, checker_msg="OK: fresh",
                        ntfy_base=base)
    assert proc.returncode == 0, proc.stderr
    assert requests == [], "an OK check must not page"


def test_wrapper_stale_pages_and_propagates_exit(tmp_path, ntfy_server):
    base, requests = ntfy_server
    msg = "STALE: 2 ARMED software stop(s) ... positions UNPROTECTED"
    proc = _run_wrapper(tmp_path, checker_exit=1, checker_msg=msg, ntfy_base=base)
    assert proc.returncode == 1, proc.stderr
    assert len(requests) == 1
    page = requests[0]
    assert page["path"] == "/test-topic"
    assert "STALE" in page["body"]
    assert "SOFTWARE-STOP watchdog" in page["title"]
    assert page["priority"] == "urgent"


def test_wrapper_corrupt_pages_and_propagates_exit(tmp_path, ntfy_server):
    base, requests = ntfy_server
    proc = _run_wrapper(tmp_path, checker_exit=2,
                        checker_msg="CORRUPT: registry unreadable", ntfy_base=base)
    assert proc.returncode == 2, proc.stderr
    assert len(requests) == 1
    assert "CORRUPT" in requests[0]["body"]


def test_wrapper_checker_crash_pages_error(tmp_path, ntfy_server):
    """A checker crash (import error after a pin move, ...) must page too —
    dying dark is the #471 failure class this package exists to close."""
    base, requests = ntfy_server
    proc = _run_wrapper(tmp_path, checker_exit=3, checker_msg="boom", ntfy_base=base)
    assert proc.returncode == 3, proc.stderr
    assert len(requests) == 1
    assert "ERROR" in requests[0]["body"]
    assert "exit=3" in requests[0]["body"]


def test_wrapper_alarm_delivery_failure_exits_70(tmp_path):
    proc = _run_wrapper(tmp_path, checker_exit=1, checker_msg="STALE: ...",
                        ntfy_base="http://127.0.0.1:9")  # closed port
    assert proc.returncode == 70
    assert "DELIVERY FAILED" in proc.stderr


# ------------------------------------------------ RUNTIME CONTRACT / wiring

def test_wrapper_requires_python_and_data_root_without_test_override(tmp_path):
    """RUNTIME CONTRACT (Codex r2 on #460, same discipline as
    shadow_ab_daily.sh): with no RENQUANT_STOPS_PAGER_CHECKER_CMD test
    override, the wrapper must fail closed (hard abort, no page attempt —
    matching shadow_ab_daily.sh's own required-var checks) when the
    interpreter or data root is not explicitly supplied. No default may
    point at any repo."""
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path)}
    proc = subprocess.run(
        ["bash", str(WRAPPER)], env=env, text=True, capture_output=True, timeout=60,
    )
    assert proc.returncode != 0
    assert "RENQUANT_STOPS_PAGER_PYTHON" in proc.stderr


def test_wrapper_resolves_pinned_sibling_src_roots_via_runtime_paths(tmp_path, ntfy_server):
    """Real (non-fake) exercise of the production PYTHONPATH-resolution
    path — no RENQUANT_STOPS_PAGER_CHECKER_CMD override — against a
    deliberately empty repo root (no subrepos.lock.json). runtime_paths.py
    has no third-party dependency, so this runs with plain python3: the
    resolver fails (no lock file), which the wrapper must treat exactly
    like a checker crash (page, don't die dark) rather than silently
    exiting clean."""
    base, requests = ntfy_server
    empty_repo_root = tmp_path / "empty-repo-root"
    empty_repo_root.mkdir()
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "RENQUANT_STOPS_PAGER_PYTHON": "python3",
        "RENQUANT_STOPS_PAGER_DATA_ROOT": str(tmp_path),
        "RENQUANT_REPO_ROOT": str(empty_repo_root),
        "RENQUANT_STOPS_PAGER_NTFY_BASE": base,
        "RENQUANT_STOPS_PAGER_NTFY_TOPIC": "test-topic",
    }
    proc = subprocess.run(
        ["bash", str(WRAPPER)], env=env, text=True, capture_output=True, timeout=60,
    )
    assert proc.returncode not in (0, 1, 2), proc.stderr  # crash class, not a normal verdict
    assert len(requests) == 1
    assert "PIN RESOLUTION FAILED" in requests[0]["body"]


# ------------------------------------------------------------- test-fire

def _run_test_fire(tmp_path: Path, ntfy_base: str) -> subprocess.CompletedProcess:
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "RENQUANT_STOPS_PAGER_NTFY_BASE": ntfy_base,
        "RENQUANT_STOPS_PAGER_NTFY_TOPIC": "test-topic",
    }
    return subprocess.run(
        ["bash", str(WRAPPER), "--test-fire", "STALE"],
        env=env, text=True, capture_output=True, timeout=60,
    )


def test_test_fire_emits_one_marked_page_and_exits_zero(tmp_path, ntfy_server):
    base, requests = ntfy_server
    proc = _run_test_fire(tmp_path, base)
    assert proc.returncode == 0, proc.stderr
    assert len(requests) == 1
    page = requests[0]
    assert "TEST-FIRE STALE" in page["body"]
    assert "NOT a real alarm" in page["body"]
    assert "TEST-FIRE" in page["title"]
    # the drill must tell the operator what to record...
    assert "delivery latency" in page["body"] and "response" in page["body"]
    # ...and must NOT claim this package satisfies the 15-minute target
    # (Codex review, 2026-07-11): it must state the honest gap instead.
    assert "18-28" in page["body"]
    assert "does NOT meet" in page["body"]


def test_test_fire_delivery_failure_exits_nonzero(tmp_path):
    proc = _run_test_fire(tmp_path, "http://127.0.0.1:9")
    assert proc.returncode == 70
    assert "DELIVERY FAILED" in proc.stderr


# ------------------------------------------------------------- installer

def _installer_env(tmp_path: Path) -> dict:
    launchctl_stub = tmp_path / "launchctl_stub.sh"
    launchctl_log = tmp_path / "launchctl_calls.log"
    launchctl_stub.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{launchctl_log}"\n'
        # `print` is the status probe: report not-loaded so status paths
        # stay deterministic in tests.
        '[ "$1" = "print" ] && exit 1\n'
        "exit 0\n",
        encoding="utf-8",
    )
    launchctl_stub.chmod(0o755)
    return {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "RENQUANT_STOPS_PAGER_AGENT_DIR": str(tmp_path / "LaunchAgents"),
        "RENQUANT_STOPS_PAGER_LAUNCHCTL": str(launchctl_stub),
        "RENQUANT_STOPS_PAGER_LOG_DIR": str(tmp_path / "logs"),
    }


def _run_installer(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(INSTALLER), *args],
        env=_installer_env(tmp_path), text=True, capture_output=True, timeout=60,
    )


def test_install_dry_run_echoes_and_changes_nothing(tmp_path):
    proc = _run_installer(tmp_path, "install")
    assert proc.returncode == 0, proc.stderr
    assert "DRY-RUN" in proc.stdout
    assert "+ cp " in proc.stdout
    assert "bootstrap" in proc.stdout
    assert not (tmp_path / "LaunchAgents").exists(), "dry-run must not create files"
    assert not (tmp_path / "launchctl_calls.log").exists(), "dry-run must not call launchctl"


def test_install_apply_copies_plist_and_bootstraps(tmp_path):
    proc = _run_installer(tmp_path, "install", "--apply")
    assert proc.returncode == 0, proc.stderr
    dst = tmp_path / "LaunchAgents" / "com.renquant.stops-liveness.plist"
    assert dst.read_bytes() == PLIST_PATH.read_bytes()
    assert (tmp_path / "logs").is_dir(), "log dir must exist before launchd writes to it"
    calls = (tmp_path / "launchctl_calls.log").read_text().splitlines()
    assert any(c.startswith("bootout ") for c in calls)
    assert any(c.startswith("bootstrap gui/") for c in calls)
    # idempotent: a second apply converges without error
    again = _run_installer(tmp_path, "install", "--apply")
    assert again.returncode == 0, again.stderr
    assert "already in sync" in again.stdout


def test_uninstall_apply_removes_plist_and_boots_out(tmp_path):
    _run_installer(tmp_path, "install", "--apply")
    proc = _run_installer(tmp_path, "uninstall", "--apply")
    assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / "LaunchAgents" / "com.renquant.stops-liveness.plist").exists()


def test_status_is_readonly_and_reports_not_installed(tmp_path):
    proc = _run_installer(tmp_path, "status")
    assert proc.returncode == 0, proc.stderr
    assert "NOT INSTALLED" in proc.stdout
    assert not (tmp_path / "LaunchAgents").exists()


def test_installer_test_fire_routes_to_wrapper(tmp_path, ntfy_server):
    base, requests = ntfy_server
    env = _installer_env(tmp_path)
    env["RENQUANT_STOPS_PAGER_NTFY_BASE"] = base
    env["RENQUANT_STOPS_PAGER_NTFY_TOPIC"] = "test-topic"
    proc = subprocess.run(
        ["bash", str(INSTALLER), "test-fire", "STALE"],
        env=env, text=True, capture_output=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert len(requests) == 1
    assert "TEST-FIRE STALE" in requests[0]["body"]


def test_installer_rejects_unknown_command(tmp_path):
    proc = _run_installer(tmp_path, "frobnicate")
    assert proc.returncode == 64
    assert "usage:" in proc.stderr
