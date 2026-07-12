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
codes, echo-first dry-run, and that the wrapper resolves the pinned
checkouts through the R-PIN Stage-1 runtime inventory via
renquant_orchestrator.deployment_manifest.load_runtime_inventory (never a
hardcoded umbrella/.venv path, never the umbrella lock file) — including a
REAL end-to-end resolution against a schema-valid fake inventory pointing
at a stub execution checkout, and the resolution-failure page path against
an empty state root, using only stdlib (deployment_manifest.py has no
third-party dependency).

Round 5 (Codex CHANGES_REQUESTED, 2026-07-12T04:32:57Z): install_stops_pager.sh
`install --apply` now runs a fail-closed pre-install guard that refuses to
arm the pager unless a versioned, VALID registry already exists at the
configured data root, resolved through the SAME pin-resolution approach and
verified by (a hermetic stub of) the real renquant_execution /
renquant_pipeline validators — never a re-derived schema. The
"install --apply registry guard" tests below cover missing-registry,
corrupt-registry, and the legitimate zero-armed-stops-but-valid case,
reusing `_fake_state_root`'s fixture machinery with a different stub module
(`_STUB_REGISTRY_MODULE`).

Round 6 (Codex CHANGES_REQUESTED, 2026-07-12T10:57:11Z): the round-5 guard's
`resolve_pager_env_var` let an already-exported ambient environment variable
win over the plist's own EnvironmentVariables value -- but launchd never
inherits the interactive shell environment, only the plist it was
bootstrapped with, so an ambient override could pass the guard against a
valid registry while installing a job armed against a completely different,
unverified path. Fixed: the guard (`plist_env_var`) now derives data
root/interpreter/broker EXCLUSIVELY from `$PLIST_SRC` (now itself
overridable via `RENQUANT_STOPS_PAGER_PLIST_SRC`, test-only). The install
guard tests below therefore point that override at a throwaway plist
(`_write_fake_plist`) carrying a controlled `EnvironmentVariables` dict
rather than setting `RENQUANT_STOPS_PAGER_DATA_ROOT`/`_PYTHON` directly in
the subprocess environment; a dedicated regression test
(`test_install_apply_ignores_ambient_env_and_uses_plist_value_only`) proves
an ambient decoy pointing at a valid registry is ignored when the plist's
own value does not resolve to one.

Round 7 (Codex CHANGES_REQUESTED, 2026-07-12T11:33:56Z): the round-5/6 guard
imported renquant_execution's PRIVATE `_pipeline_stops_api()` /
`resolve_registry_path` as in-process Python objects — a leading-underscore
name is an implementation detail, not a versioned cross-repo contract, so a
future execution-repo pin advance could turn this arming-time safety check
into an import failure or silently change its validation semantics. Fixed:
the guard now only resolves PYTHONPATH itself (a legitimate
orchestrator-owned path-resolution concern that imports nothing from
renquant_execution/renquant_pipeline), then shells out to the pinned
renquant-execution's PUBLIC `--validate-registry` CLI mode
(renquant-execution#30) exactly like `stops_liveness_pager.sh`'s own
liveness check already does, and interprets only that subprocess's exit
code + message. `_STUB_REGISTRY_MODULE` changed accordingly: it is now a
minimal argparse-driven CLI script (invoked via `python3 -m
renquant_execution.software_stops_liveness --validate-registry ...`, same
"shell out to a stub module" mechanism `_STUB_CLI` above already
exercises) rather than a module of importable names — only the MECHANISM
changed; the guard's actual safety assertions (refuse on missing/corrupt,
no plist copy, no launchctl call) are unchanged and re-verified below.
"""
from __future__ import annotations

import json
import plistlib
import subprocess
import sys
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


def test_plist_supplies_explicit_python_and_data_root_not_via_umbrella():
    """The plist configures explicit interpreter + data root (RUNTIME
    CONTRACT). Neither may reference the deprecated umbrella."""
    with open(PLIST_PATH, "rb") as fh:
        plist = plistlib.load(fh)
    env = plist["EnvironmentVariables"]
    assert "RENQUANT_STOPS_PAGER_PYTHON" in env
    assert "RENQUANT_STOPS_PAGER_DATA_ROOT" in env
    assert "RenQuant" not in env["RENQUANT_STOPS_PAGER_DATA_ROOT"], (
        "data root must be the neutral runtime-state path, not the umbrella"
    )
    assert ".renquant/runtime/software-stops" in env["RENQUANT_STOPS_PAGER_DATA_ROOT"]
    assert "RenQuant/.venv" not in env["RENQUANT_STOPS_PAGER_PYTHON"]
    assert "RenQuant/.venv" not in plist["ProgramArguments"][-1]


def test_wrapper_defaults_match_the_plist_topic_and_execution_repo_checker():
    content = WRAPPER.read_text(encoding="utf-8")
    # ad hoc invocation (no plist env) must page the same live topic
    assert f'NTFY_TOPIC:-{LIVE_OPS_TOPIC}}}' in content
    # the checker now lives in renquant-execution, invoked as a module via
    # the R-PIN runtime-inventory reader (deployment_manifest), never the
    # deprecated umbrella script, its venv, or its lock file.
    assert "renquant_execution.software_stops_liveness" in content
    assert "load_runtime_inventory" in content, (
        "resolution must go through the deployment_manifest reader API, "
        "not ad-hoc JSON parsing"
    )
    assert "deploy_state_root" in content
    assert "check_software_stops_liveness.py" not in content
    assert "RenQuant/.venv" not in content
    assert ".subrepo_runtime" not in content, (
        "no hardcoded umbrella subrepo_runtime path — resolution goes "
        "through the runtime inventory instead"
    )
    assert "subrepos.lock" not in content, (
        "no umbrella lock-file dependency — the inventory is the neutral "
        "per-host path map"
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


_STUB_CLI = """\
import os
import sys

print(os.environ.get("FAKE_STOPS_MSG", "OK: stub"), "argv=" + " ".join(sys.argv[1:]))
sys.exit(int(os.environ.get("FAKE_STOPS_EXIT", "0")))
"""

# Fake ``renquant_execution.software_stops_liveness`` module used by the
# install-guard tests (below).
#
# Round 7 (Codex CHANGES_REQUESTED, 2026-07-12T11:33:56Z): the install guard
# no longer imports ``_pipeline_stops_api``/``resolve_registry_path`` as
# in-process Python objects — a leading-underscore name is an
# implementation detail, not a versioned cross-repo contract. It now shells
# out to the pinned renquant-execution's PUBLIC
# ``--validate-registry`` CLI mode (renquant-execution#30), the same way
# ``_STUB_CLI`` above is invoked via ``python3 -m .../-m module`` /
# subprocess rather than imported. This stub therefore implements a
# minimal, argparse-driven ``main()`` mirroring the real
# ``validate_registry()``'s exit-code/message contract
# (0=VALID/1=MISSING/2=CORRUPT) against the same fake schema check
# (``version == 1`` and ``stops`` is a dict) the old stub used — only the
# MECHANISM changed (shell-out CLI vs. importable names), not the fake
# schema itself.
_STUB_REGISTRY_MODULE = """\
import argparse
import json
import sys
from pathlib import Path


def resolve_registry_path(*, registry=None, data_root=None, broker="alpaca"):
    if registry:
        return Path(registry)
    return Path(data_root) / f"{broker}.json"


def _validate_snapshot(raw):
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(
        raw.get("stops"), dict
    ):
        raise ValueError("fake registry schema violation")
    return raw


def validate_registry(registry_path):
    if not registry_path.exists():
        return 1, f"MISSING: no software-stop registry file at {registry_path}"
    try:
        _validate_snapshot(json.loads(registry_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return 2, (
            f"CORRUPT: {registry_path} unreadable or fails schema "
            f"validation ({type(exc).__name__}: {exc})"
        )
    return 0, f"VALID: {registry_path} is a well-formed software-stop registry"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate-registry", action="store_true")
    ap.add_argument("--registry", default=None)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--broker", default="alpaca")
    args = ap.parse_args(argv)

    path = resolve_registry_path(
        registry=args.registry, data_root=args.data_root, broker=args.broker,
    )
    if args.validate_registry:
        code, message = validate_registry(path)
        print(message)
        return code
    print("OK: stub check-mode not exercised by these tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def _fake_state_root(tmp_path: Path, *, exec_module_content: str = _STUB_CLI) -> Path:
    """A fake R-PIN state root whose runtime inventory (REAL schema v1,
    validated by the real reader) points at stub pinned checkouts. The stub
    execution checkout carries a fake ``renquant_execution.software_stops_liveness``
    module. Default content (``_STUB_CLI``) is a CLI-style script driven by
    env vars, used by the wrapper tests; the install-guard tests (below)
    pass ``exec_module_content=_STUB_REGISTRY_MODULE`` instead, since the
    guard imports real Python names rather than shelling out."""
    exec_pkg = tmp_path / "pin-exec" / "src" / "renquant_execution"
    exec_pkg.mkdir(parents=True)
    (exec_pkg / "__init__.py").write_text("", encoding="utf-8")
    (exec_pkg / "software_stops_liveness.py").write_text(exec_module_content, encoding="utf-8")
    stub_repos = {"renquant-execution": {"path": str(tmp_path / "pin-exec")}}
    # the wrapper resolves the checker's full first-party import closure
    for name in (
        "renquant-common", "renquant-base-data", "renquant-artifacts",
        "renquant-model", "renquant-pipeline",
    ):
        (tmp_path / name / "src").mkdir(parents=True)
        stub_repos[name] = {"path": str(tmp_path / name)}

    state_root = tmp_path / "deploy-state"
    state_root.mkdir()
    inventory = {
        "schema_version": 1,
        "kind": "runtime-inventory",
        "generated_at": "2026-07-11T00:00:00Z",
        "host": "test-host",
        "repos": stub_repos,
    }
    (state_root / "runtime-inventory.json").write_text(
        json.dumps(inventory), encoding="utf-8"
    )
    return state_root


def test_wrapper_resolves_pinned_checkouts_via_runtime_inventory(tmp_path, ntfy_server):
    """Real (non-fake) exercise of the production resolution path — no
    RENQUANT_STOPS_PAGER_CHECKER_CMD override. The wrapper reads a
    schema-valid runtime inventory through the REAL deployment_manifest
    reader, builds PYTHONPATH from the inventory's checkout paths, and
    invokes `python -m renquant_execution.software_stops_liveness` (a stub
    module in the fake pinned checkout) with the explicit --data-root."""
    base, requests = ntfy_server
    state_root = _fake_state_root(tmp_path)
    data_root = tmp_path / "data-root"
    data_root.mkdir()
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
        "RENQUANT_STOPS_PAGER_DATA_ROOT": str(data_root),
        "RENQUANT_DEPLOY_STATE_ROOT": str(state_root),
        "RENQUANT_STOPS_PAGER_NTFY_BASE": base,
        "RENQUANT_STOPS_PAGER_NTFY_TOPIC": "test-topic",
        "FAKE_STOPS_EXIT": "0",
        "FAKE_STOPS_MSG": "OK: stub registry fresh",
    }
    proc = subprocess.run(
        ["bash", str(WRAPPER)], env=env, text=True, capture_output=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert requests == []
    # the stub CLI received the explicit data root + broker args
    assert "--data-root" in proc.stdout
    assert str(data_root) in proc.stdout
    assert "--broker alpaca" in proc.stdout


def test_wrapper_warns_when_data_root_is_legacy_not_neutral(tmp_path, ntfy_server):
    """Codex round-3 review of PR #481 (2026-07-11): CODE resolution now
    goes through pins, but the DATA root is still an explicit, reviewed
    plist value naming the deprecated umbrella in production — a real
    dependency Codex said must be made observable, not silently accepted.
    A data root outside the neutral runtime-state-root contract
    (renquant_orchestrator.software_stops_registry_contract) must produce a
    CLEARLY LABELED warning on stderr every run, without changing the
    paging decision (still exit 0, still no page, for an OK checker)."""
    base, requests = ntfy_server
    state_root = _fake_state_root(tmp_path)
    legacy_data_root = tmp_path / "RenQuant"  # umbrella-shaped, not neutral
    legacy_data_root.mkdir()
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
        "RENQUANT_STOPS_PAGER_DATA_ROOT": str(legacy_data_root),
        "RENQUANT_DEPLOY_STATE_ROOT": str(state_root),
        "RENQUANT_STOPS_PAGER_NTFY_BASE": base,
        "RENQUANT_STOPS_PAGER_NTFY_TOPIC": "test-topic",
        "FAKE_STOPS_EXIT": "0",
        "FAKE_STOPS_MSG": "OK: stub registry fresh",
    }
    proc = subprocess.run(
        ["bash", str(WRAPPER)], env=env, text=True, capture_output=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert requests == [], "observability warning must not itself page"
    assert "WARNING: LEGACY/UNVERSIONED" in proc.stderr
    assert "R-PIN writer migration not yet landed" in proc.stderr


def test_wrapper_does_not_warn_when_data_root_is_under_neutral_runtime_root(tmp_path, ntfy_server):
    """The inverse of the above: a data root that IS under the neutral
    runtime-state root (the shape a migrated writer would use) must not
    trip the legacy warning — proving the check is a real classifier, not
    an always-on notice."""
    base, requests = ntfy_server
    state_root = _fake_state_root(tmp_path)
    neutral_root = tmp_path / ".renquant" / "runtime"
    neutral_data_root = neutral_root / "software-stops"
    neutral_data_root.mkdir(parents=True)
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
        "RENQUANT_STOPS_PAGER_DATA_ROOT": str(neutral_data_root),
        "RENQUANT_DEPLOY_STATE_ROOT": str(state_root),
        "RENQUANT_STOPS_PAGER_NTFY_BASE": base,
        "RENQUANT_STOPS_PAGER_NTFY_TOPIC": "test-topic",
        "FAKE_STOPS_EXIT": "0",
        "FAKE_STOPS_MSG": "OK: stub registry fresh",
    }
    proc = subprocess.run(
        ["bash", str(WRAPPER)], env=env, text=True, capture_output=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert requests == []
    assert "LEGACY/UNVERSIONED" not in proc.stderr


def test_wrapper_stale_pin_pages_resolution_failure_not_false_stale(tmp_path, ntfy_server):
    """Stale-pin guard (found by live smoke 2026-07-11): the host's pinned
    renquant-execution checkout predates renquant-execution#29, and
    `python -m <missing module>` exits 1 — which would masquerade as a
    STALE verdict and page a FALSE alarm. The resolver must classify a
    missing checker module as a resolution failure (crash-class page with
    the pin-not-advanced detail), never as STALE."""
    base, requests = ntfy_server
    state_root = _fake_state_root(tmp_path)
    module_file = (
        tmp_path / "pin-exec" / "src" / "renquant_execution"
        / "software_stops_liveness.py"
    )
    module_file.unlink()
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
        "RENQUANT_STOPS_PAGER_DATA_ROOT": str(tmp_path),
        "RENQUANT_DEPLOY_STATE_ROOT": str(state_root),
        "RENQUANT_STOPS_PAGER_NTFY_BASE": base,
        "RENQUANT_STOPS_PAGER_NTFY_TOPIC": "test-topic",
    }
    proc = subprocess.run(
        ["bash", str(WRAPPER)], env=env, text=True, capture_output=True, timeout=60,
    )
    assert proc.returncode not in (0, 1, 2), proc.stderr
    assert len(requests) == 1
    assert "PIN RESOLUTION FAILED" in requests[0]["body"]
    assert "STALE" not in requests[0]["body"], "must not page a false STALE"


def test_wrapper_missing_inventory_pages_resolution_failure(tmp_path, ntfy_server):
    """The reader API fail-closes on a missing/invalid runtime inventory;
    the wrapper must treat that exactly like a checker crash (page, don't
    die dark) rather than silently exiting clean."""
    base, requests = ntfy_server
    empty_state_root = tmp_path / "empty-state-root"
    empty_state_root.mkdir()
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path),
        "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
        "RENQUANT_STOPS_PAGER_DATA_ROOT": str(tmp_path),
        "RENQUANT_DEPLOY_STATE_ROOT": str(empty_state_root),
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


def _run_installer(
    tmp_path: Path, *args: str, env_extra: "dict | None" = None
) -> subprocess.CompletedProcess:
    env = _installer_env(tmp_path)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(INSTALLER), *args],
        env=env, text=True, capture_output=True, timeout=60,
    )


def _write_fake_plist(tmp_path: Path, *, env_vars: dict, name: str = "fake-stops-liveness.plist") -> Path:
    """A throwaway plist for the install --apply registry guard tests.

    Round 6 (Codex CHANGES_REQUESTED, 2026-07-12T10:57:11Z): the guard now
    derives RENQUANT_STOPS_PAGER_DATA_ROOT/_PYTHON EXCLUSIVELY from
    $PLIST_SRC's own EnvironmentVariables dict, never from ambient env —
    matching exactly what launchd would actually arm. These tests therefore
    point RENQUANT_STOPS_PAGER_PLIST_SRC at a controlled fake plist rather
    than the real committed one (whose DATA_ROOT is a real, machine-specific
    absolute path tests must not write into)."""
    plist_path = tmp_path / name
    with open(plist_path, "wb") as fh:
        plistlib.dump({"EnvironmentVariables": env_vars}, fh)
    return plist_path


def _valid_registry_install_env(tmp_path: Path, *, broker: str = "alpaca") -> dict:
    """The full env the install --apply fail-closed guard (Codex review,
    2026-07-12T04:32:57Z) needs to PASS: a fake R-PIN state root (schema-
    valid runtime inventory pointing at stub pinned renquant-execution /
    renquant-pipeline / ... checkouts — same machinery as
    ``_fake_state_root`` above, reused rather than reinvented), a fake plist
    (round 6: the guard reads data root/interpreter from THIS file only —
    see ``_write_fake_plist``) declaring a VALID registry's data root, and
    that VALID registry file actually present there."""
    state_root = _fake_state_root(tmp_path, exec_module_content=_STUB_REGISTRY_MODULE)
    data_root = tmp_path / "registry-data-root"
    data_root.mkdir()
    (data_root / f"{broker}.json").write_text(
        json.dumps({"version": 1, "stops": {}}), encoding="utf-8"
    )
    plist_path = _write_fake_plist(
        tmp_path,
        env_vars={
            "RENQUANT_STOPS_PAGER_DATA_ROOT": str(data_root),
            "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
            "RENQUANT_STOPS_PAGER_BROKER": broker,
        },
    )
    return {
        "RENQUANT_DEPLOY_STATE_ROOT": str(state_root),
        "RENQUANT_STOPS_PAGER_PLIST_SRC": str(plist_path),
    }


def test_install_dry_run_echoes_and_changes_nothing(tmp_path):
    proc = _run_installer(tmp_path, "install")
    assert proc.returncode == 0, proc.stderr
    assert "DRY-RUN" in proc.stdout
    assert "+ cp " in proc.stdout
    assert "bootstrap" in proc.stdout
    assert not (tmp_path / "LaunchAgents").exists(), "dry-run must not create files"
    assert not (tmp_path / "launchctl_calls.log").exists(), "dry-run must not call launchctl"


def test_install_apply_copies_plist_and_bootstraps(tmp_path):
    env_extra = _valid_registry_install_env(tmp_path)
    proc = _run_installer(tmp_path, "install", "--apply", env_extra=env_extra)
    assert proc.returncode == 0, proc.stderr
    dst = tmp_path / "LaunchAgents" / "com.renquant.stops-liveness.plist"
    # Round 6: PLIST_SRC is the fake plist _valid_registry_install_env wrote
    # (RENQUANT_STOPS_PAGER_PLIST_SRC) rather than the real committed one —
    # the real plist's DATA_ROOT is a genuine machine-specific absolute path
    # tests must not write a registry file into. The real committed plist's
    # own shape/content is separately covered by test_plist_* below, which
    # read it directly rather than through the installer.
    assert dst.read_bytes() == Path(env_extra["RENQUANT_STOPS_PAGER_PLIST_SRC"]).read_bytes()
    assert (tmp_path / "logs").is_dir(), "log dir must exist before launchd writes to it"
    calls = (tmp_path / "launchctl_calls.log").read_text().splitlines()
    assert any(c.startswith("bootout ") for c in calls)
    assert any(c.startswith("bootstrap gui/") for c in calls)
    # idempotent: a second apply converges without error
    again = _run_installer(tmp_path, "install", "--apply", env_extra=env_extra)
    assert again.returncode == 0, again.stderr
    assert "already in sync" in again.stdout


# ------------------------------------------ install --apply registry guard

def test_install_apply_refuses_when_registry_missing(tmp_path):
    """Codex CHANGES_REQUESTED on PR #481 (2026-07-12T04:32:57Z): darkness
    alone is not a runtime safety control -- an operator running --apply
    before the writer migration must be refused, not silently armed against
    a path with no migrated writer (which would later produce a false
    critical alarm). No registry file exists at the configured data root
    here, so the guard must refuse BEFORE any mkdir/cp/bootstrap step.
    Round 6: the data root comes from the fake plist (RENQUANT_STOPS_PAGER_
    PLIST_SRC), not ambient env -- see _write_fake_plist."""
    state_root = _fake_state_root(tmp_path, exec_module_content=_STUB_REGISTRY_MODULE)
    data_root = tmp_path / "registry-data-root"
    data_root.mkdir()  # directory exists, but no registry file inside it
    plist_path = _write_fake_plist(
        tmp_path,
        env_vars={
            "RENQUANT_STOPS_PAGER_DATA_ROOT": str(data_root),
            "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
        },
    )
    env_extra = {
        "RENQUANT_DEPLOY_STATE_ROOT": str(state_root),
        "RENQUANT_STOPS_PAGER_PLIST_SRC": str(plist_path),
    }
    proc = _run_installer(tmp_path, "install", "--apply", env_extra=env_extra)
    assert proc.returncode != 0
    assert "no software-stop registry file" in proc.stderr
    assert not (tmp_path / "LaunchAgents" / "com.renquant.stops-liveness.plist").exists(), (
        "must not copy the plist when the registry guard fails"
    )
    assert not (tmp_path / "launchctl_calls.log").exists(), (
        "must not invoke launchctl bootstrap when the registry guard fails"
    )


def test_install_apply_refuses_when_registry_corrupt(tmp_path):
    """Same guard, CORRUPT-file branch: a registry file exists at the
    configured data root but is not valid JSON / does not pass the real
    schema validator. Must refuse exactly like the missing-file case --
    an unreadable registry is not evidence the writer migration landed
    cleanly."""
    state_root = _fake_state_root(tmp_path, exec_module_content=_STUB_REGISTRY_MODULE)
    data_root = tmp_path / "registry-data-root"
    data_root.mkdir()
    (data_root / "alpaca.json").write_text("not json{{{", encoding="utf-8")
    plist_path = _write_fake_plist(
        tmp_path,
        env_vars={
            "RENQUANT_STOPS_PAGER_DATA_ROOT": str(data_root),
            "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
        },
    )
    env_extra = {
        "RENQUANT_DEPLOY_STATE_ROOT": str(state_root),
        "RENQUANT_STOPS_PAGER_PLIST_SRC": str(plist_path),
    }
    proc = _run_installer(tmp_path, "install", "--apply", env_extra=env_extra)
    assert proc.returncode != 0
    assert "CORRUPT" in proc.stderr
    assert not (tmp_path / "LaunchAgents" / "com.renquant.stops-liveness.plist").exists(), (
        "must not copy the plist when the registry guard fails"
    )
    assert not (tmp_path / "launchctl_calls.log").exists(), (
        "must not invoke launchctl bootstrap when the registry guard fails"
    )


def test_install_apply_ignores_ambient_env_and_uses_plist_value_only(tmp_path):
    """Codex CHANGES_REQUESTED round 6 (2026-07-12T10:57:11Z): "install
    --apply can validate a different runtime contract than the launchd job
    it installs" -- launchd never inherits the interactive shell
    environment, only the EnvironmentVariables baked into the copied plist.
    Here an ambient RENQUANT_STOPS_PAGER_DATA_ROOT/_PYTHON in the calling
    shell point at a VALID registry (a decoy an operator's leftover shell
    state might carry), but the plist that will actually be copied and
    armed declares a data root with NO registry at all. Install must refuse
    -- proving the guard derives its answer exclusively from the plist, not
    from ambient env -- and the refusal message must name the PLIST's data
    root, not the ambient decoy."""
    state_root = _fake_state_root(tmp_path, exec_module_content=_STUB_REGISTRY_MODULE)
    decoy_data_root = tmp_path / "decoy-ambient-data-root"
    decoy_data_root.mkdir()
    (decoy_data_root / "alpaca.json").write_text(
        json.dumps({"version": 1, "stops": {}}), encoding="utf-8"
    )
    plist_data_root = tmp_path / "plist-data-root-no-writer-yet"
    plist_path = _write_fake_plist(
        tmp_path,
        env_vars={
            "RENQUANT_STOPS_PAGER_DATA_ROOT": str(plist_data_root),
            "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
        },
    )
    env_extra = {
        "RENQUANT_DEPLOY_STATE_ROOT": str(state_root),
        "RENQUANT_STOPS_PAGER_PLIST_SRC": str(plist_path),
        # Ambient decoy -- must be ignored by the guard entirely.
        "RENQUANT_STOPS_PAGER_DATA_ROOT": str(decoy_data_root),
        "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
    }
    proc = _run_installer(tmp_path, "install", "--apply", env_extra=env_extra)
    assert proc.returncode != 0
    assert "no software-stop registry file" in proc.stderr
    assert str(plist_data_root) in proc.stderr
    assert str(decoy_data_root) not in proc.stderr, (
        "guard must report the PLIST's data root, not the ambient decoy -- "
        "if this fails, the guard is reading ambient env again"
    )
    assert not (tmp_path / "LaunchAgents" / "com.renquant.stops-liveness.plist").exists(), (
        "must not copy the plist when the ambient decoy is the only valid path"
    )
    assert not (tmp_path / "launchctl_calls.log").exists(), (
        "must not invoke launchctl bootstrap when the ambient decoy is the only valid path"
    )


def test_install_apply_passes_with_zero_armed_stops(tmp_path):
    """A registry that exists and parses cleanly but has zero armed stops
    is a legitimate empty-but-valid state (nothing has ever armed yet) and
    must PASS the guard -- the guard checks validity, not emptiness."""
    env_extra = _valid_registry_install_env(tmp_path)
    proc = _run_installer(tmp_path, "install", "--apply", env_extra=env_extra)
    assert proc.returncode == 0, proc.stderr
    assert "GUARD OK" in proc.stderr
    assert (tmp_path / "LaunchAgents" / "com.renquant.stops-liveness.plist").exists()


# ------------------------------- real-sibling integration (round 8, Part C)
#
# Codex review on renquant-execution#30 (2026-07-12T11:57:53Z): "The
# current tests validate only a fake injected adapter; the real-pipeline
# contract test is optional/skipped. Add a non-skipped integration
# compatibility check in the R-PIN/multirepo validation lane, exercising
# this exact CLI against a valid registry and malformed fixture with the
# pinned pipeline implementation."
#
# The tests below are that check. They exercise install_stops_pager.sh's
# registry guard end-to-end against the REAL renquant_execution
# --validate-registry CLI and the REAL renquant_pipeline schema validator
# (renquant-pipeline#192's public validate_software_stop_snapshot contract,
# round 8 Part A) -- not the hermetic _STUB_REGISTRY_MODULE fake the tests
# above use. They are the "non-skipped ... lane" Codex means: this repo's
# own existing "Full multirepo test" CI job, which checks out every sibling
# (including pipeline, with cvxpy installed) as a real directory next to
# this one -- not a new CI job to build. On an isolated worktree (no
# sibling directories at the resolved parent) they correctly SKIP; on a
# normal dev machine at .../git/github/ or in that CI job they run for
# real. See doc/progress/2026-07-11-stops-liveness-pager-package.md for
# the "Correction (round 8)" section documenting this ordering explicitly.

def _real_siblings_root() -> Path:
    """Directory expected to contain sibling repo checkouts alongside this
    one. This test file lives at ``renquant-orchestrator/tests/``, so
    ``parents[2]`` is the directory containing renquant-orchestrator
    itself -- e.g. ``/Users/renhao/git/github`` on the operator's normal
    dev machine (where real renquant-pipeline/renquant-execution/...
    siblings sit next to renquant-orchestrator) and this repo's own "Full
    multirepo test" CI job (which checks out every sibling as a real
    directory next to this one). In an ISOLATED WORKTREE (this test file's
    own worktree included -- there is no sibling directory at that parent)
    the real-sibling tests below skip rather than fail."""
    return Path(__file__).resolve().parents[2]


def _real_sibling_repo_paths() -> "dict[str, Path] | None":
    """Real absolute paths for every repo the install guard's own
    PYTHONPATH resolution needs (the exact ``needed`` tuple
    ``resolve_pinned_pythonpath()`` in install_stops_pager.sh reads out of
    the runtime inventory), or ``None`` if they are not all present as
    real checkouts (with a ``src/`` dir -- the guard's own inventory
    validity check) at the resolved siblings root."""
    root = _real_siblings_root()
    names = (
        "renquant-execution", "renquant-pipeline", "renquant-common",
        "renquant-base-data", "renquant-artifacts", "renquant-model",
    )
    paths = {name: root / name for name in names}
    if not all((p / "src").is_dir() for p in paths.values()):
        return None
    return paths


def _real_sibling_state_root(tmp_path: Path, paths: "dict[str, Path]") -> Path:
    """A REAL R-PIN state root (schema v1 runtime inventory) pointing at
    the REAL sibling checkouts resolved by ``_real_sibling_repo_paths``
    -- the non-fake counterpart of ``_fake_state_root`` above."""
    state_root = tmp_path / "real-deploy-state"
    state_root.mkdir()
    inventory = {
        "schema_version": 1,
        "kind": "runtime-inventory",
        "generated_at": "2026-07-12T00:00:00Z",
        "host": "test-host",
        "repos": {name: {"path": str(path)} for name, path in paths.items()},
    }
    (state_root / "runtime-inventory.json").write_text(
        json.dumps(inventory), encoding="utf-8"
    )
    return state_root


def test_install_apply_guard_against_real_pinned_execution_and_pipeline(tmp_path):
    """Non-skipped integration compatibility check (Codex review on
    execution#30, 2026-07-12T11:57:53Z): exercises install_stops_pager.sh's
    registry guard end-to-end against the REAL renquant_execution
    --validate-registry CLI and the REAL renquant_pipeline schema validator
    -- not the hermetic _STUB_REGISTRY_MODULE fake used by the tests above.
    Skips (does not fail) when the real sibling checkouts are not importable
    -- e.g. an isolated worktree with no sibling repos -- but runs for real
    in this repo's own "Full multirepo test" CI job and on a normal
    developer machine at .../git/github/, where pyproject.toml's pytest
    pythonpath already resolves both siblings. Proves the full chain
    orchestrator -> execution public CLI -> pipeline public schema API
    actually works with real code, closing the "only a fake adapter is
    tested" gap Codex flagged.

    VALID-registry case only -- see
    test_install_apply_guard_against_real_pinned_execution_and_pipeline_malformed
    below for the CORRUPT-registry counterpart (a separate test so each
    gets its own fresh ``tmp_path`` / LaunchAgents dir, matching the
    missing-vs-corrupt split of the hermetic guard tests above).

    Ordering note: this test's real value only lands once
    renquant-pipeline#192 (the validate_software_stop_snapshot public
    contract, round 8 Part A) and renquant-execution#30's Part-B follow-up
    commit (the sibling change to this repo's own consumer module) have
    both merged and the local checkouts reflect that. Two distinct
    "not ready yet" states are handled differently on purpose:
      * The real sibling checkout of renquant-execution predates
        renquant-execution#30 (round 7) entirely, so
        ``software_stops_liveness.validate_registry`` doesn't exist yet --
        SKIPPED (the feature under test doesn't exist in that checkout;
        see the dotted-path importorskip below).
      * ``validate_registry`` DOES exist (round 7 landed) but the pinned
        renquant-pipeline checkout predates renquant-pipeline#192 (Part A),
        so the CLI's deferred import of ``validate_software_stop_snapshot``
        raises inside the subprocess this test invokes -- the subprocess
        exits nonzero/crash-class and this test genuinely FAILS (not
        skips): a real, actionable "pipeline sibling is stale relative to
        this contract" signal, not an infra gap to paper over.
    """
    pytest.importorskip("renquant_pipeline")
    pytest.importorskip("renquant_execution")
    # Round-9 correction: the prior revision used
    # pytest.importorskip("renquant_execution.software_stops_liveness.validate_registry"),
    # reasoning that a dotted path would trigger submodule-import machinery
    # and skip cleanly if the name didn't exist. Verified empirically this
    # is WRONG: validate_registry is a function attribute, not a submodule,
    # so `importlib.import_module("...software_stops_liveness.validate_registry")`
    # fails with "'...software_stops_liveness' is not a package" REGARDLESS
    # of whether validate_registry exists -- this ALWAYS skipped, even
    # against a fully up-to-date sibling checkout with the real function
    # present (reproduced against a live sibling-worktree layout with
    # renquant-execution#30 round 7+8 checked out and cvxpy installed: still
    # skipped). That silently defeated the "non-skipped integration check"
    # Codex explicitly asked for. Fixed: a plain attribute import wrapped in
    # try/except ImportError -- this DOES correctly distinguish "name
    # doesn't exist yet" (ImportError, caught, real skip) from "name
    # exists" (import succeeds, no skip) -- verified empirically both ways.
    try:
        from renquant_execution.software_stops_liveness import (  # noqa: F401
            validate_registry,
        )
    except ImportError:
        pytest.skip(
            "renquant_execution.software_stops_liveness.validate_registry "
            "not present on the pinned sibling checkout -- expected before "
            "renquant-execution#30 (round 7) merges; this test runs for "
            "real once it does, in this repo's 'Full multirepo test' CI "
            "job and on a normal dev machine at .../git/github/"
        )

    paths = _real_sibling_repo_paths()
    if paths is None:
        pytest.skip(
            f"real sibling checkouts not found under {_real_siblings_root()} "
            "-- expected in an isolated worktree; this test runs for real "
            "in this repo's own 'Full multirepo test' CI job and on a "
            "normal dev machine at .../git/github/"
        )

    from renquant_pipeline.software_stops import (
        DEFAULT_REGISTRY_PATH,
        registry_path_for,
    )

    state_root = _real_sibling_state_root(tmp_path, paths)

    valid_data_root = tmp_path / "valid-data-root"
    valid_registry_path = registry_path_for(
        valid_data_root / DEFAULT_REGISTRY_PATH, "alpaca"
    )
    valid_registry_path.parent.mkdir(parents=True)
    valid_registry_path.write_text(
        json.dumps({"version": 1, "stops": {}}), encoding="utf-8"
    )

    plist_path = _write_fake_plist(
        tmp_path,
        env_vars={
            "RENQUANT_STOPS_PAGER_DATA_ROOT": str(valid_data_root),
            "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
        },
        name="fake-plist-real-valid.plist",
    )
    env_extra = {
        "RENQUANT_DEPLOY_STATE_ROOT": str(state_root),
        "RENQUANT_STOPS_PAGER_PLIST_SRC": str(plist_path),
    }
    proc = _run_installer(tmp_path, "install", "--apply", env_extra=env_extra)
    assert proc.returncode == 0, proc.stderr
    assert "GUARD OK" in proc.stderr
    assert "VALID" in proc.stderr
    assert (tmp_path / "LaunchAgents" / "com.renquant.stops-liveness.plist").exists()


def test_install_apply_guard_against_real_pinned_execution_and_pipeline_malformed(tmp_path):
    """Malformed-registry counterpart of the test above -- same REAL
    renquant_execution/renquant_pipeline chain, but the registry file at
    the resolved path fails the REAL pipeline schema validator (invalid
    JSON), so the guard must refuse: nonzero exit, no plist copied, no
    launchctl call. Proves real CORRUPT detection, not just real VALID
    detection. Skip rationale identical to the valid-case test above (see
    its round-9 correction comment for why this uses a plain attribute
    import wrapped in try/except ImportError rather than a dotted-path
    importorskip)."""
    pytest.importorskip("renquant_pipeline")
    pytest.importorskip("renquant_execution")
    try:
        from renquant_execution.software_stops_liveness import (  # noqa: F401
            validate_registry,
        )
    except ImportError:
        pytest.skip(
            "renquant_execution.software_stops_liveness.validate_registry "
            "not present on the pinned sibling checkout -- expected before "
            "renquant-execution#30 (round 7) merges; this test runs for "
            "real once it does, in this repo's 'Full multirepo test' CI "
            "job and on a normal dev machine at .../git/github/"
        )

    paths = _real_sibling_repo_paths()
    if paths is None:
        pytest.skip(
            f"real sibling checkouts not found under {_real_siblings_root()} "
            "-- expected in an isolated worktree; this test runs for real "
            "in this repo's own 'Full multirepo test' CI job and on a "
            "normal dev machine at .../git/github/"
        )

    from renquant_pipeline.software_stops import (
        DEFAULT_REGISTRY_PATH,
        registry_path_for,
    )

    state_root = _real_sibling_state_root(tmp_path, paths)

    malformed_data_root = tmp_path / "malformed-data-root"
    malformed_registry_path = registry_path_for(
        malformed_data_root / DEFAULT_REGISTRY_PATH, "alpaca"
    )
    malformed_registry_path.parent.mkdir(parents=True)
    malformed_registry_path.write_text("not json{{{", encoding="utf-8")

    plist_path = _write_fake_plist(
        tmp_path,
        env_vars={
            "RENQUANT_STOPS_PAGER_DATA_ROOT": str(malformed_data_root),
            "RENQUANT_STOPS_PAGER_PYTHON": sys.executable,
        },
        name="fake-plist-real-malformed.plist",
    )
    env_extra = {
        "RENQUANT_DEPLOY_STATE_ROOT": str(state_root),
        "RENQUANT_STOPS_PAGER_PLIST_SRC": str(plist_path),
    }
    proc = _run_installer(tmp_path, "install", "--apply", env_extra=env_extra)
    assert proc.returncode != 0
    assert "CORRUPT" in proc.stderr
    assert not (tmp_path / "LaunchAgents" / "com.renquant.stops-liveness.plist").exists(), (
        "must not copy the plist when the real guard fails"
    )
    assert not (tmp_path / "launchctl_calls.log").exists(), (
        "must not invoke launchctl bootstrap when the real guard fails"
    )


def test_install_dry_run_does_not_hard_fail_without_registry(tmp_path):
    """install (no --apply) must stay a pure echo-only dry-run even with no
    registry/inventory/env configured at all -- the guard only gates
    --apply."""
    proc = _run_installer(tmp_path, "install")
    assert proc.returncode == 0, proc.stderr
    assert "DRY-RUN" in proc.stdout
    assert not (tmp_path / "LaunchAgents").exists()
    assert not (tmp_path / "launchctl_calls.log").exists()


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
