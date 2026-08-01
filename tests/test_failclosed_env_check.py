"""Is the fail-closed guard armed in the deployed job?

The tests target the ways this check could report an armed guard that is not armed —
counting a READ of the flag as an assignment, treating an uninstalled job as a pass, and
an unparseable plist vanishing from the denominator.
"""

from __future__ import annotations

import importlib.util
import pathlib
import plistlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "ops" / "failclosed_env_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("fcec", MOD)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


F = _load()


def _plist(tmp_path, name="j.plist", env=None, program=None):
    body = {"Label": name}
    if env is not None:
        body["EnvironmentVariables"] = env
    if program is not None:
        body["ProgramArguments"] = program
    p = tmp_path / name
    with p.open("wb") as fh:
        plistlib.dump(body, fh)
    return str(p)


def _sh(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# --- reading a flag is NOT arming it ----------------------------------------

def test_a_READ_of_the_flag_does_not_count_as_arming_it(tmp_path):
    """The fail-open version of this check: every script that merely mentions the flag
    would report as having set it. `daily_104.sh` only ever reads it."""
    s = _sh(tmp_path, "r.sh",
            'if [ "${RENQUANT_OPS_FAIL_CLOSED:-0}" = "1" ]; then exit 1; fi\n')
    assert F.script_assigns(s, "RENQUANT_OPS_FAIL_CLOSED") is False


def test_an_ASSIGNMENT_counts(tmp_path):
    for line in ('RENQUANT_OPS_FAIL_CLOSED=1\n',
                 'export RENQUANT_OPS_FAIL_CLOSED=1\n',
                 '  export  RENQUANT_OPS_FAIL_CLOSED="1"\n'):
        s = _sh(tmp_path, "a.sh", line)
        assert F.script_assigns(s, "RENQUANT_OPS_FAIL_CLOSED") is True, line


def test_a_DEFAULTED_expansion_is_not_an_assignment(tmp_path):
    s = _sh(tmp_path, "d.sh", 'X="${RENQUANT_STRICT_SUBREPO_PATHS:-0}"\n')
    assert F.script_assigns(s, "RENQUANT_STRICT_SUBREPO_PATHS") is False


# --- the plist side ---------------------------------------------------------

def test_the_flag_set_to_1_in_the_plist_env_arms_it(tmp_path):
    j = _plist(tmp_path, env={"RENQUANT_OPS_FAIL_CLOSED": "1"})
    assert F.audit_job(j, [])["armed"] is True


def test_the_flag_set_to_0_does_NOT_arm_it(tmp_path):
    """`"0"` is present-but-off; treating presence as arming is the obvious trap."""
    j = _plist(tmp_path, env={"RENQUANT_OPS_FAIL_CLOSED": "0"})
    assert F.audit_job(j, [])["armed"] is False


def test_EITHER_flag_arms_it_because_the_shell_condition_is_an_OR(tmp_path):
    for flag in F.FAILCLOSED_FLAGS:
        j = _plist(tmp_path, name=f"{flag}.plist", env={flag: "1"})
        assert F.audit_job(j, [])["armed"] is True, flag


def test_an_UNINSTALLED_job_is_a_FAILURE_not_a_pass(tmp_path):
    """Otherwise uninstalling the job is the cheapest way to make this check green."""
    r = F.audit_job(str(tmp_path / "gone.plist"), [])
    assert r["status"] == "job_not_installed" and r["armed"] is False


def test_a_MALFORMED_environment_block_fails_closed(tmp_path):
    p = tmp_path / "m.plist"
    with p.open("wb") as fh:
        plistlib.dump({"Label": "m", "EnvironmentVariables": "n/a"}, fh)
    r = F.audit_job(str(p), [])
    assert r["status"] == "malformed_environment" and r["armed"] is False


def test_an_UNPARSEABLE_plist_does_not_vanish_from_the_denominator(tmp_path):
    p = tmp_path / "b.plist"
    p.write_bytes(b"not a plist at all")
    r = F.audit_job(str(p), [])
    assert r["armed"] is False
    rep = F.audit([str(p)], [])
    assert rep["n_jobs_declared"] == 1 and rep["n_armed"] == 0


# --- the script side and the exit code --------------------------------------

def test_an_EXTRA_sourced_script_can_arm_it(tmp_path):
    """The env helper is sourced, not exec'd, so it must be inspectable too — otherwise
    a legitimately armed job reports unarmed."""
    helper = _sh(tmp_path, "env.sh", "export RENQUANT_OPS_FAIL_CLOSED=1\n")
    j = _plist(tmp_path, env={"PATH": "/bin"})
    assert F.audit_job(j, [])["armed"] is False
    assert F.audit_job(j, [helper])["armed"] is True


def test_the_PROGRAM_script_is_inspected_too(tmp_path):
    s = _sh(tmp_path, "prog.sh", "export RENQUANT_STRICT_SUBREPO_PATHS=1\n")
    j = _plist(tmp_path, env={"PATH": "/bin"}, program=[s])
    assert F.audit_job(j, [])["armed"] is True


def test_main_EXITS_NONZERO_when_a_job_is_unarmed(tmp_path, capsys):
    j = _plist(tmp_path, env={"PATH": "/bin"})
    assert F.main(["--job", j]) == 1
    assert "NOT ARMED" in capsys.readouterr().out


def test_ANTI_VACUITY_main_exits_zero_when_every_job_is_armed(tmp_path, capsys):
    j = _plist(tmp_path, env={"RENQUANT_OPS_FAIL_CLOSED": "1"})
    assert F.main(["--job", j]) == 0
    assert "ARMED" in capsys.readouterr().out


def test_the_report_REFUSES_the_stronger_reading(tmp_path, capsys):
    """'The guard is off' must not be readable as 'the stale checkpoint is deciding the
    book today'. Those need different measurements and only one has been made."""
    F.main(["--job", _plist(tmp_path, env={"PATH": "/bin"})])
    out = capsys.readouterr().out
    assert "does not claim the resolver is currently failing" in out
