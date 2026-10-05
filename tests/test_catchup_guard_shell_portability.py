"""ops/catchup_guard.sh must behave IDENTICALLY under zsh, bash and POSIX sh.

Regression after orch#1098: the shared guard is SOURCED by the two rq105
wrappers (run_batch_scores_export.sh / run_session_scheduler.sh) whose shebang
AND plist ProgramArguments are /bin/zsh, with `set -u` active. #1098's guard
did `for req in $required; do eval "val=\\${$req:-}"` — zsh does not word-split
an unquoted `$var`, so the loop ran once over the whole name list, the eval
became `${RQ_ROOT CATCHUP_CUTOFF_HELPER PYTHONPATH:-}` ("bad substitution"),
`val` was never assigned and `set -u` killed the wrapper:

    (eval):1: bad substitution
    launchd_catchup_guard:25: val: parameter not set

→ both rq105 jobs exit 1; the Monday 06:15 batch export and the 06:25 session
scheduler would have failed (serving loop dark). #1098's tests only ever ran
the guard under bash.

Every test here runs the guard's decision matrix under EACH shell of
{/bin/zsh, /bin/bash, /bin/sh} that exists on the host (a shell that is absent
is skipped, never silently passed — the CI runner has bash + dash, the
operator's Mac has all three) and asserts identical rc / stdout / stderr /
guard-log lines across shells, plus the expected verdict. A stub
catchup_cutoff.py sits on PATH and is named by CATCHUP_CUTOFF_HELPER; nothing
reads the operator's disk.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OPS = ROOT / "ops"
GUARD = OPS / "catchup_guard.sh"
RQ105_EXPORT = OPS / "renquant105" / "run_batch_scores_export.sh"

SHELLS = ["/bin/zsh", "/bin/bash", "/bin/sh"]
TESTED_SHELL_NAMES = {"zsh", "bash", "sh"}


def _shell_param(path: str):
    return pytest.param(path, id=Path(path).name,
                        marks=[] if shutil.which(path) or Path(path).exists()
                        else pytest.mark.skip(reason=f"{path} absent on this host"))


def _available_shells() -> list[str]:
    return [s for s in SHELLS if Path(s).exists()]


def _fixture_root(tmp_path: Path, helper_stdout: str = "1300", helper_rc: int = 0) -> dict:
    """RQ_ROOT with a .venv python shim + a stub catchup_cutoff.py on PATH."""
    rq = tmp_path / "rq"
    (rq / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    py = rq / ".venv" / "bin" / "python"
    py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    py.chmod(0o755)
    stubdir = tmp_path / "stubbin"
    stubdir.mkdir(exist_ok=True)
    helper = stubdir / "catchup_cutoff.py"
    helper.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path({str(tmp_path / 'helper_called.txt')!r}).write_text(' '.join(sys.argv[1:]))\n"
        f"print({helper_stdout!r})\nsys.exit({helper_rc})\n")
    (rq / "data").mkdir(exist_ok=True)
    return {
        "RQ_ROOT": str(rq),
        "CATCHUP_CUTOFF_HELPER": str(helper),
        "PYTHONPATH": str(tmp_path / "pinned_src"),
        "PATH": f"{stubdir}:/usr/bin:/bin",
    }


def _hermetic_env(overrides: dict) -> dict:
    ambient = {k: v for k, v in os.environ.items()
               if k not in ("RQ_ROOT", "CATCHUP_CUTOFF_HELPER", "PYTHONPATH", "PATH")}
    return {**ambient, **overrides}


_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z ")


def _run_guard(shell: str, tmp_path: Path, env: dict, args: str, set_u: bool = True):
    """`<shell> -c '. ops/catchup_guard.sh; launchd_catchup_guard …'` — the way
    every wrapper consumes the guard; returns the observable tuple with the
    guard-log timestamps stripped so shells can be compared."""
    log = tmp_path / f"guard_{Path(shell).name}.log"
    if log.exists():
        log.unlink()
    prelude = "set -u; " if set_u else ""
    cmd = f'{prelude}. "{GUARD}"; launchd_catchup_guard {args.replace("{LOG}", str(log))}'
    res = subprocess.run([shell, "-c", cmd], capture_output=True, text=True, env=env)
    lines = [_TS.sub("", ln) for ln in log.read_text().splitlines()] if log.exists() else []
    return res.returncode, res.stdout, res.stderr, tuple(lines)


# --- the decision matrix, one case per row, every shell per case --------------

MATRIX = [
    # id, helper (stdout, rc), env-drop, args, expected rc, expected log/stderr marker
    ("session_run_missing_output", ("1300", 0), None,
     'batch-scores-export 2026-08-31 0620 0615 session "{LOG}" "{OUT}/a.json" "{OUT}/a.meta.json"',
     0, "RUN local 0620 in [0615,1300)"),
    ("session_run_at_exact_slot", ("1300", 0), None,
     'batch-scores-export 2026-08-31 0615 0615 session "{LOG}" "{OUT}/a.json"',
     0, "RUN local 0615 in [0615,1300)"),
    ("session_skip_before_slot", ("1300", 0), None,
     'session-scheduler 2026-08-31 0624 0625 session "{LOG}" "{OUT}/a.json"',
     1, "SKIP local 0624 is before the 0625 slot"),
    ("session_skip_at_cutoff", ("1300", 0), None,
     'batch-scores-export 2026-08-31 1300 0615 session "{LOG}" "{OUT}/a.json"',
     1, "SKIP local 1300 is at/after the 1300 cutoff"),
    ("session_early_close_cutoff", ("1000", 0), None,
     'batch-scores-export 2026-11-27 1005 0615 session "{LOG}" "{OUT}/a.json"',
     1, "SKIP local 1005 is at/after the 1000 cutoff"),
    ("session_refused_non_session_day", ("", 1), None,
     'batch-scores-export 2026-09-07 0620 0615 session "{LOG}" "{OUT}/a.json"',
     1, "SKIP calendar refused catch-up for 2026-09-07 (helper rc=1: no output)"),
    ("session_refused_helper_garbage", ("13:00", 0), None,
     'batch-scores-export 2026-08-31 0620 0615 session "{LOG}" "{OUT}/a.json"',
     1, "helper rc=0: 13:00"),
    ("session_idempotent_all_present", ("1300", 0), None,
     'batch-scores-export 2026-08-31 0620 0615 session "{LOG}" "{PRESENT}" "{PRESENT}"',
     1, "SKIP today's output already present (idempotent)"),
    ("literal_run_late_evening", ("1300", 0), "CATCHUP_CUTOFF_HELPER",
     'run-surface-drift 2026-09-06 2359 0700 2400 "{LOG}" "{OUT}/drift.log"',
     0, "RUN local 2359 in [0700,2400) (literal cutoff 2400 local, calendar-day job)"),
    ("literal_skip_before_slot", ("1300", 0), "PYTHONPATH",
     'run-surface-drift 2026-09-06 0659 0700 2400 "{LOG}" "{OUT}/drift.log"',
     1, "SKIP local 0659 is before the 0700 slot"),
    ("fatal_missing_helper_env_in_session_mode", ("1300", 0), "CATCHUP_CUTOFF_HELPER",
     'batch-scores-export 2026-08-31 0620 0615 session "{LOG}" "{OUT}/a.json"',
     2, "CATCHUP_CUTOFF_HELPER must be set by the sourcing wrapper"),
    ("fatal_missing_pythonpath_in_session_mode", ("1300", 0), "PYTHONPATH",
     'batch-scores-export 2026-08-31 0620 0615 session "{LOG}" "{OUT}/a.json"',
     2, "PYTHONPATH must be set by the sourcing wrapper"),
    ("fatal_missing_rq_root_even_in_literal_mode", ("1300", 0), "RQ_ROOT",
     'run-surface-drift 2026-09-06 0705 0700 2400 "{LOG}" "{OUT}/drift.log"',
     2, "RQ_ROOT must be set by the sourcing wrapper"),
    ("fatal_usage_six_args", ("1300", 0), None,
     'batch-scores-export 2026-08-31 0620 0615 session "{LOG}"',
     2, "usage: launchd_catchup_guard"),
    ("fatal_bad_cutoff_spec", ("1300", 0), None,
     'batch-scores-export 2026-08-31 0620 0615 13pm "{LOG}" "{OUT}/a.json"',
     2, "cutoff must be 'session' or a literal HHMM"),
    ("fatal_bad_date", ("1300", 0), None,
     'batch-scores-export 20260831 0620 0615 session "{LOG}" "{OUT}/a.json"',
     2, "date must be YYYY-MM-DD"),
    ("fatal_non_numeric_hhmm", ("1300", 0), None,
     'batch-scores-export 2026-08-31 06h20 0615 session "{LOG}" "{OUT}/a.json"',
     2, "non-numeric HHMM"),
]


@pytest.mark.parametrize("case_id,helper,drop,args,expect_rc,marker", MATRIX,
                         ids=[m[0] for m in MATRIX])
def test_decision_matrix_is_identical_under_every_shell(tmp_path, case_id, helper, drop, args,
                                                        expect_rc, marker):
    shells = _available_shells()
    assert "/bin/bash" in shells, "bash is the CI baseline and must exist"
    env_over = _fixture_root(tmp_path, *helper)
    if drop:
        env_over.pop(drop)
    present = tmp_path / "present.json"
    present.write_text("{}")
    out = Path(env_over.get("RQ_ROOT", str(tmp_path / "rq"))) / "data"
    out.mkdir(parents=True, exist_ok=True)
    args = args.replace("{OUT}", str(out)).replace("{PRESENT}", str(present))
    results = {}
    for shell in shells:
        results[shell] = _run_guard(shell, tmp_path, _hermetic_env(env_over), args)
    # 1. the verdict is the expected one, and the marker names it
    for shell, (rc, stdout, stderr, lines) in results.items():
        assert rc == expect_rc, (case_id, shell, rc, stderr, lines)
        assert stdout == "", (case_id, shell, stdout)
        haystack = "\n".join(lines) + "\n" + stderr
        assert marker in haystack, (case_id, shell, haystack)
        if expect_rc == 2:
            assert lines == (), "a usage/env error must not stamp the guard log"
        else:
            assert len(lines) == 1, "exactly ONE stamped line per invocation"
        # no shell-generated diagnostics ever (that is the #1098 failure mode)
        assert "parameter not set" not in stderr and "bad substitution" not in stderr \
            and "unbound variable" not in stderr, (shell, stderr)
    # 2. every shell observes the SAME thing (rc, stdout, stderr, log lines)
    distinct = {v for v in results.values()}
    assert len(distinct) == 1, {s: v for s, v in results.items()}


@pytest.mark.parametrize("shell", [_shell_param(s) for s in SHELLS])
def test_set_u_is_safe_with_nothing_but_the_required_env(tmp_path, shell):
    """Under `set -u` with ONLY the wrapper's env (no leftovers from a previous
    call: `val`, `required`, `cutoff` … must never be read before assignment)."""
    env_over = _fixture_root(tmp_path)
    out = Path(env_over["RQ_ROOT"]) / "data"
    rc, stdout, stderr, lines = _run_guard(
        shell, tmp_path, _hermetic_env(env_over),
        f'batch-scores-export 2026-08-31 0620 0615 session "{{LOG}}" "{out}/a.json"', set_u=True)
    assert (rc, stdout, stderr) == (0, "", ""), (shell, rc, stderr)
    assert len(lines) == 1 and lines[0].startswith("[catch-up guard batch-scores-export] RUN")


@pytest.mark.parametrize("shell", [_shell_param(s) for s in SHELLS])
def test_two_calls_in_one_shell_do_not_leak_state_between_them(tmp_path, shell):
    """A literal-mode call after a session-mode call must not inherit the
    earlier cutoff (the guard uses shell-global variables — reassignment,
    never a stale read)."""
    env_over = _fixture_root(tmp_path, "1000", 0)
    out = Path(env_over["RQ_ROOT"]) / "data"
    log = tmp_path / "two.log"
    cmd = (f'set -u; . "{GUARD}"; '
           f'launchd_catchup_guard a 2026-08-31 1005 0615 session "{log}" "{out}/a.json"; r1=$?; '
           f'launchd_catchup_guard b 2026-08-31 1005 0700 2400 "{log}" "{out}/b.json"; r2=$?; '
           f'printf "%s %s" "$r1" "$r2"')
    res = subprocess.run([shell, "-c", cmd], capture_output=True, text=True,
                         env=_hermetic_env(env_over))
    assert res.stderr == "", (shell, res.stderr)
    assert res.stdout == "1 0", (shell, res.stdout)
    lines = [_TS.sub("", ln) for ln in log.read_text().splitlines()]
    assert lines[0].startswith("[catch-up guard a] SKIP local 1005 is at/after the 1000 cutoff")
    assert lines[1].startswith("[catch-up guard b] RUN local 1005 in [0700,2400)")


# --- sourced EXACTLY the way run_batch_scores_export.sh does, under zsh --------

def _rq105_export_guard_block() -> str:
    """The literal lines of run_batch_scores_export.sh from `set -u` through the
    guard's rc dispatch, with the pin resolver + export replaced by stubs, so
    the test executes the wrapper's OWN sourcing + argument shape verbatim."""
    src = RQ105_EXPORT.read_text()
    assert src.startswith("#!/bin/zsh\n"), "the rq105 export wrapper runs /bin/zsh"
    assert "\nset -u\n" in src, "the wrapper runs under set -u; the guard must survive it"
    start = src.index("CATCHUP_CUTOFF_HELPER=")
    end = src.index("esac\n", start) + len("esac\n")
    block = src[start:end]
    assert '. "$RQ105_OPS_DIR/../catchup_guard.sh"' in block
    assert "launchd_catchup_guard batch-scores-export \"$TS\" \"$(date +%H%M)\" 0615 session" in block
    return block


@pytest.mark.parametrize("shell", [_shell_param("/bin/zsh")])
def test_rq105_export_wrapper_sourcing_shape_survives_zsh_set_u(tmp_path, shell):
    """Replays the wrapper's exact `set -u` + `. "$RQ105_OPS_DIR/../catchup_guard.sh"`
    + argument shape under /bin/zsh (RQ105_OPS_DIR = a copy of ops/renquant105
    whose parent holds the REAL guard + a STUB cutoff helper). Before the fix
    this exits 1 with `val: parameter not set`; after it, the guard RUNs (rc 0
    → wrapper proceeds) on a session day with today's bundle missing, and SKIPs
    (exit 0) when the bundle is present."""
    ops = tmp_path / "ops"
    (ops / "renquant105").mkdir(parents=True)
    shutil.copy(GUARD, ops / "catchup_guard.sh")
    (ops / "catchup_cutoff.py").write_text("import sys\nprint('1300')\nsys.exit(0)\n")
    env_over = _fixture_root(tmp_path)
    rq_root = Path(env_over["RQ_ROOT"])
    (rq_root / "data" / "rq105").mkdir(parents=True)
    (rq_root / "logs" / "rq105").mkdir(parents=True)
    block = _rq105_export_guard_block()
    script = ops / "renquant105" / "replay.sh"
    script.write_text(
        "#!/bin/zsh\nset -u\n"
        'RQ_ROOT="${RQ_ROOT:?}"\nLOG_DIR="$RQ_ROOT/logs/rq105"\n'
        'TS="2026-08-31"\nRQ105_OPS_DIR="$(dirname "$0")"\n'
        'export PYTHONPATH="/pinned/src"\n'
        + block +
        'echo "GUARD_RC=$GUARD_RC PROCEED"\n')
    env = _hermetic_env({"RQ_ROOT": str(rq_root), "PATH": "/usr/bin:/bin"})
    env.pop("CATCHUP_CUTOFF_HELPER", None)
    # the wrapper's own `date +%H%M` decides the window, so drive the clock
    # inside the wrapper by faking `date` on PATH (the guard never calls it
    # for the decision; only the stamp uses `date -u`).
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    (fake_bin / "date").write_text(
        '#!/bin/sh\ncase "$*" in +%H%M) echo 0620 ;; *) exec /bin/date "$@" ;; esac\n')
    (fake_bin / "date").chmod(0o755)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    res = subprocess.run([shell, str(script)], capture_output=True, text=True, env=env)
    assert res.stderr == "", res.stderr
    assert res.returncode == 0 and res.stdout.strip() == "GUARD_RC=0 PROCEED", res
    guard_log = rq_root / "logs" / "rq105" / "catchup_guard_batch-scores-export_2026-08-31.log"
    assert guard_log.exists()
    assert "RUN local 0620 in [0615,1300)" in guard_log.read_text()
    assert not (rq_root / "logs" / "rq105" / "batch_scores_export_2026-08-31.log").exists(), \
        "no FATAL line must be written on the wrapper's evidence log"

    # idempotent: both outputs present → guard 1 → wrapper `exit 0` before PROCEED
    for name in ("batch_scores_2026-08-31.json", "batch_scores_2026-08-31.meta.json"):
        (rq_root / "data" / "rq105" / name).write_text("{}")
    res2 = subprocess.run([shell, str(script)], capture_output=True, text=True, env=env)
    assert (res2.returncode, res2.stdout, res2.stderr) == (0, "", ""), res2
    assert "SKIP today's output already present" in guard_log.read_text()


# --- every wrapper that sources the guard runs a shell the matrix covers ------

def _guard_sourcers() -> list[Path]:
    found = []
    for p in OPS.rglob("*.sh"):
        if p == GUARD:
            continue
        if re.search(r'^\s*\.\s+"?[^\n]*catchup_guard\.sh', p.read_text(), re.M):
            found.append(p)
    return sorted(found)


def test_every_wrapper_that_sources_the_guard_runs_a_tested_shell():
    sourcers = _guard_sourcers()
    names = {p.relative_to(ROOT).as_posix() for p in sourcers}
    assert names == {
        "ops/renquant104/dawn_funnel_preflight.sh",
        "ops/renquant105/run_batch_scores_export.sh",
        "ops/renquant105/run_session_scheduler.sh",
        "ops/run_surface_drift_scan.sh",
    }, names
    for p in sourcers:
        shebang = p.read_text().splitlines()[0]
        assert shebang.startswith("#!"), (p, shebang)
        exe = shebang[2:].split()
        shell = Path(exe[1]).name if exe[0].endswith("/env") else Path(exe[0]).name
        assert shell in TESTED_SHELL_NAMES, (p, shebang)


def test_the_guard_contains_no_shell_specific_constructs():
    src = GUARD.read_text()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    for bad in (r"\beval\b", r"\$\{!", r"\blocal -n\b", r"\[\[", r"\$'", r"\bread -a\b",
                r"\bdeclare\b", r"\btypeset\b", r"\bsetopt\b", r"\bshopt\b"):
        assert not re.search(bad, code), f"non-portable construct {bad!r} in {GUARD}"
    # the #1098 pattern: an unquoted `$name_list` driving a for-loop
    assert not re.search(r"^\s*for\s+\w+\s+in\s+\$\w+\s*;", code, re.M), \
        "for-in over an unquoted $var word-splits in bash and NOT in zsh"
