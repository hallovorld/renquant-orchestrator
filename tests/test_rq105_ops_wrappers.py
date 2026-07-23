"""Tests for rq105 launchd job shell wrappers and plists.

Every rq105 launchd job must go through a shell wrapper (not run python
directly) so that PYTHONPATH, logging, and ntfy notification are set up
consistently. These tests catch the class of bugs where a plist runs
python without the environment the script expects.
"""
from __future__ import annotations

import json
import plistlib
from pathlib import Path

OPS_DIR = Path(__file__).resolve().parent.parent / "ops" / "renquant105"
MANIFEST = Path(__file__).resolve().parent.parent / "ops" / "launchd_manifest.json"

WRAPPER_JOBS = [
    "batch-scores-export",
    "liveness",
    "postclose",
    "quote-logger",
    "session-scheduler",
    "shadow-serving",
]


def test_all_plists_use_shell_wrappers():
    """Every plist must call a shell wrapper, not python directly.

    Regression: batch-scores-export and liveness plists ran python
    directly, which meant no PYTHONPATH, no .env loading, and no
    subrepo paths — imports would fail silently."""
    for job in WRAPPER_JOBS:
        plist_path = OPS_DIR / f"com.renquant.rq105-{job}.plist"
        if not plist_path.exists():
            continue
        with open(plist_path, "rb") as fh:
            plist = plistlib.load(fh)
        args = plist["ProgramArguments"]
        assert args[0] in ("/bin/zsh", "/bin/bash"), (
            f"{plist_path.name}: ProgramArguments[0] is {args[0]!r}, "
            f"not a shell. Jobs must use a shell wrapper for PYTHONPATH setup."
        )
        assert args[-1].endswith(".sh"), (
            f"{plist_path.name}: ProgramArguments[-1] is {args[-1]!r}, "
            f"not a .sh wrapper. Direct python invocation skips PYTHONPATH."
        )


def test_all_wrappers_set_pythonpath():
    """Every shell wrapper must export PYTHONPATH."""
    for sh in OPS_DIR.glob("run_*.sh"):
        content = sh.read_text(encoding="utf-8")
        assert "PYTHONPATH" in content, (
            f"{sh.name} does not set PYTHONPATH — imports will fail "
            f"for anything outside the venv's installed packages."
        )


def test_all_wrappers_reference_pinned_checkout():
    """Wrappers must use the -run pinned checkout, not the working tree."""
    for sh in OPS_DIR.glob("run_*.sh"):
        content = sh.read_text(encoding="utf-8")
        assert "renquant-orchestrator-run" in content, (
            f"{sh.name} does not reference renquant-orchestrator-run. "
            f"Jobs must run from the pinned checkout."
        )


def test_all_wrappers_log_to_rq105_dir():
    """Wrappers must redirect output to logs/rq105/."""
    for sh in OPS_DIR.glob("run_*.sh"):
        content = sh.read_text(encoding="utf-8")
        assert "logs/rq105/" in content, (
            f"{sh.name} does not log to logs/rq105/. "
            f"Output will be lost."
        )


def test_batch_scores_export_wrapper_exists():
    wrapper = OPS_DIR / "run_batch_scores_export.sh"
    assert wrapper.exists(), "run_batch_scores_export.sh missing"
    content = wrapper.read_text(encoding="utf-8")
    assert "export_batch_scores.py" in content


def test_liveness_check_wrapper_exists():
    wrapper = OPS_DIR / "run_liveness_check.sh"
    assert wrapper.exists(), "run_liveness_check.sh missing"
    content = wrapper.read_text(encoding="utf-8")
    assert "rq105_liveness_check.py" in content


def _load_plist(path: Path) -> dict:
    """plistlib's expat rejects `--` inside XML comments (the annotated plists
    have them); fall back to plutil normalization like the drift scan does."""
    try:
        with open(path, "rb") as fh:
            return plistlib.load(fh)
    except Exception:
        import subprocess
        res = subprocess.run(
            ["plutil", "-convert", "xml1", "-o", "-", "--", str(path)],
            capture_output=True,
        )
        return plistlib.loads(res.stdout)


def test_quote_logger_plist_has_keepalive_for_auto_restart():
    """GOAL-5 Fix 3: the quote-logger job must auto-restart on a mid-session
    crash — KeepAlive={SuccessfulExit:false} (restart on non-zero/abnormal exit,
    NOT on a clean exit 0). Before this it fired once at 06:25 with no KeepAlive,
    so a ~08:37 death was fatal for the session."""
    plist = _load_plist(OPS_DIR / "com.renquant.rq105-quote-logger.plist")
    ka = plist.get("KeepAlive")
    assert isinstance(ka, dict), f"quote-logger plist must set KeepAlive dict, got {ka!r}"
    assert ka.get("SuccessfulExit") is False, (
        "KeepAlive must be SuccessfulExit=false: restart on crash, not on a clean exit"
    )


def test_quote_logger_manifest_records_keepalive_intent():
    """Containment protocol: the KeepAlive change must be recorded in the
    reviewed surface (launchd_manifest.json) in the same PR, not just the plist.
    ProgramArguments is unchanged, so program_args_sha256 stays valid."""
    jobs = json.loads(MANIFEST.read_text(encoding="utf-8"))["jobs"]
    entry = jobs["com.renquant.rq105-quote-logger"]
    assert entry["program_args"] == [
        "/bin/zsh",
        "/Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/run_quote_logger.sh",
    ], "ProgramArguments (the drift-tracked surface) must be unchanged"
    assert entry.get("keep_alive") == {"SuccessfulExit": False}, (
        "manifest must record the reviewed KeepAlive intent"
    )


def test_plists_are_weekday_only():
    """All rq105 jobs should only run Mon-Fri (weekday 1-5)."""
    for job in WRAPPER_JOBS:
        plist_path = OPS_DIR / f"com.renquant.rq105-{job}.plist"
        if not plist_path.exists():
            continue
        with open(plist_path, "rb") as fh:
            plist = plistlib.load(fh)
        intervals = plist.get("StartCalendarInterval", [])
        if not intervals:
            continue
        weekdays = {d["Weekday"] for d in intervals}
        assert weekdays <= {1, 2, 3, 4, 5}, (
            f"{plist_path.name} runs on weekends: {weekdays - {1,2,3,4,5}}"
        )
