"""The kernel-surface census must not report a wrapper it failed to read as safe.

Every fixture here is synthetic and lives in tmp_path. An earlier probe in this
repo bound its anti-vacuity control to a live defect, so it could only pass while
the system was broken; these tests must stay green after the umbrella twin is
fixed, so none of them reads the real tree.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ops.renquant104.kernel_surface_census import (  # noqa: E402
    FALLBACK, NO_RUNNER, NO_WRAPPER, PINNED, UMBRELLA, UNREADABLE,
    ManifestUnreadable, census, classify_text, runner_env_is_set,
)

BRIDGE_SH = 'exec "$PY" -m renquant_orchestrator daily-bridge --repo-dir "$REPO"\n'
DIRECT_SH = 'exec "$PY" -m live.runner --preflight\n'
FALLBACK_SH = (
    'if [ "${RQ_DAILY_RUNNER:-multirepo}" = "umbrella" ]; then\n'
    '  RUNNER_ARGS=(-m live.runner)\n'
    'else\n'
    '  RUNNER_ARGS=(-m renquant_orchestrator daily-bridge --repo-dir "$REPO")\n'
    'fi\n'
)
INERT_SH = 'python3 "$REPO/scripts/some_report.py"\n'


def _manifest(tmp_path: pathlib.Path, jobs: dict) -> pathlib.Path:
    p = tmp_path / "launchd_manifest.json"
    p.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
    return p


def _wrapper(tmp_path: pathlib.Path, name: str, body: str) -> str:
    w = tmp_path / name
    w.write_text(body, encoding="utf-8")
    return str(w)


# --- classification -------------------------------------------------------

@pytest.mark.parametrize("body,expected", [
    (BRIDGE_SH, PINNED),
    (DIRECT_SH, UMBRELLA),
    (FALLBACK_SH, FALLBACK),
    (INERT_SH, NO_RUNNER),
])
def test_classify_each_surface(body, expected):
    assert classify_text(body) == expected


def test_embedded_python_list_form_is_detected():
    """daily_104.sh spells the direct call as a python list, not a shell word.
    A regex that only matched `-m live.runner` with a single space would miss
    every shadow lane in that file."""
    body = 'runner = [sys.executable, "-m", "live.runner"]\n'
    assert classify_text(body) == UMBRELLA


# --- the refusals ---------------------------------------------------------

def test_unreadable_wrapper_is_not_reported_as_no_runner(tmp_path):
    """The whole point: a wrapper nobody could read is the dangerous state."""
    m = _manifest(tmp_path, {
        "com.example.ghost": {"program_args": ["/bin/sh", str(tmp_path / "gone.sh")]},
    })
    c = census(m, launchagents=tmp_path / "no-agents")
    row = c["jobs"][0]
    assert row["surface"] == UNREADABLE
    assert row["surface"] != NO_RUNNER
    assert c["n_undetermined"] == 1


def test_undetermined_makes_the_cli_exit_nonzero(tmp_path):
    from ops.renquant104.kernel_surface_census import main
    m = _manifest(tmp_path, {
        "com.example.ghost": {"program_args": ["/bin/sh", str(tmp_path / "gone.sh")]},
    })
    assert main(["--manifest", str(m)]) == 1


def test_job_with_no_wrapper_is_flagged_not_skipped(tmp_path):
    m = _manifest(tmp_path, {"com.example.bare": {"program_args": ["/bin/echo", "hi"]}})
    c = census(m, launchagents=tmp_path / "no-agents")
    assert c["jobs"][0]["surface"] == NO_WRAPPER
    assert c["n_undetermined"] == 1


def test_unreadable_manifest_refuses_rather_than_returning_empty(tmp_path):
    bad = tmp_path / "m.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ManifestUnreadable):
        census(bad, launchagents=tmp_path)


# --- the fallback is dormant, not absent ----------------------------------

def test_fallback_job_is_not_counted_as_reaching_umbrella(tmp_path):
    m = _manifest(tmp_path, {
        "com.example.daily": {"program_args": [
            "/bin/sh", _wrapper(tmp_path, "daily.sh", FALLBACK_SH)]},
    })
    c = census(m, launchagents=tmp_path / "no-agents")
    assert c["jobs"][0]["surface"] == FALLBACK
    assert c["n_reaching_umbrella_kernel"] == 0
    assert c["n_with_dormant_umbrella_fallback"] == 1
    assert c["fallback_is_armed"] is False


def test_armed_fallback_is_reported_from_a_plist(tmp_path):
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    (agents / "com.example.daily.plist").write_text(
        "<plist><dict><key>RQ_DAILY_RUNNER</key><string>umbrella</string>"
        "</dict></plist>", encoding="utf-8")
    m = _manifest(tmp_path, {
        "com.example.daily": {"program_args": [
            "/bin/sh", _wrapper(tmp_path, "daily.sh", FALLBACK_SH)]},
    })
    c = census(m, launchagents=agents)
    assert c["fallback_is_armed"] is True
    assert c["runner_env"]["launchagent_plists_setting_it"] == [
        "com.example.daily.plist"]


def test_armed_fallback_is_also_read_from_the_manifest_env(tmp_path):
    """Two places can arm it. Reading only the plists would be true about the
    file read and wrong about the machine."""
    m = _manifest(tmp_path, {
        "com.example.daily": {
            "program_args": ["/bin/sh", _wrapper(tmp_path, "d.sh", FALLBACK_SH)],
            "environment": {"RQ_DAILY_RUNNER": "umbrella"},
        },
    })
    c = census(m, launchagents=tmp_path / "no-agents")
    assert c["fallback_is_armed"] is True
    assert c["runner_env"]["manifest_jobs_setting_it"] == ["com.example.daily"]


def test_env_probe_survives_a_missing_launchagents_dir(tmp_path):
    e = runner_env_is_set(tmp_path / "definitely-absent", {"jobs": {}})
    assert e["armed_anywhere"] is False


# --- a positive control ---------------------------------------------------

def test_a_direct_job_is_counted_and_a_bridge_job_is_not(tmp_path):
    """Anti-vacuity: the census must actually distinguish the two, on synthetic
    input, so this stays meaningful after the real tree is fixed."""
    m = _manifest(tmp_path, {
        "com.example.preflight": {"program_args": [
            "/bin/sh", _wrapper(tmp_path, "pre.sh", DIRECT_SH)]},
        "com.example.daily": {"program_args": [
            "/bin/sh", _wrapper(tmp_path, "daily.sh", BRIDGE_SH)]},
        "com.example.report": {"program_args": [
            "/bin/sh", _wrapper(tmp_path, "rep.sh", INERT_SH)]},
    })
    c = census(m, launchagents=tmp_path / "no-agents")
    assert c["n_reaching_umbrella_kernel"] == 1
    assert c["n_undetermined"] == 0
    by = {r["label"]: r["surface"] for r in c["jobs"]}
    assert by["com.example.preflight"] == UMBRELLA
    assert by["com.example.daily"] == PINNED
    assert by["com.example.report"] == NO_RUNNER
