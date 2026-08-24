"""orch#1016 — which renquant-common an rq105 job imports must be a REVIEWED fact.

Six scheduled wrappers each carried:

    RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"
    [ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"

so which copy executed was decided by filesystem state, not by review, and since
`renquant-common-run` is absent every job imported the mutable dev working tree.

The FIRST fix consolidated that onto one *named sibling*, and was still wrong
(codex): a directory name is not a revision. Worse,
`run_session_scheduler.sh` already had `$SUBREPO/renquant-common/src` — the
PINNED runtime copy — on PYTHONPATH, positioned AFTER the mutable sibling, so the
pin was present and losing.

Resolution is now the pinned runtime, verified against the umbrella's
`subrepos.lock.json` before import, with no fallback and no env override of the
checkout.

These tests run under whatever shell exists (production is zsh, CI is ubuntu with
none) because a resolver the CI cannot execute is a resolver the CI does not
check — see `_SHELL`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OPS = ROOT / "ops"
RQ105 = OPS / "renquant105"
RESOLVER = RQ105 / "rq105_common_src.sh"
WRAPPERS = sorted(RQ105.glob("run_*.sh"))

#: Production runs zsh; ubuntu CI has neither zsh nor a reason to. The resolver
#: is deliberately free of zsh-only syntax (an earlier draft used `${0:A:h}`,
#: which expands to EMPTY under bash — the tests would have had to skip on CI,
#: and a skipped test covers nothing).
_SHELL = shutil.which("zsh") or shutil.which("bash") or "/bin/sh"


def _load(path: Path, name: str):
    for d in (str(OPS), str(RQ105)):
        if d not in sys.path:
            sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fake_umbrella(tmp_path: Path, *, commit: str | None = None,
                   head: str | None = None, make_src: bool = True) -> Path:
    """An RQ_ROOT with a pinned runtime checkout that is a real git repo."""
    rq = tmp_path / "RenQuant"
    checkout = rq / ".subrepo_runtime" / "repos" / "renquant-common"
    if make_src:
        (checkout / "src").mkdir(parents=True)
    else:
        checkout.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    subprocess.run(["git", "-C", str(checkout), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(checkout), "config", "user.name", "t"], check=True)
    (checkout / "marker").write_text(head or "x")
    subprocess.run(["git", "-C", str(checkout), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(checkout), "commit", "-qm", "init"], check=True)
    real = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    (rq / "subrepos.lock.json").write_text(json.dumps({
        "schema_version": 1,
        "subrepos": [{"name": "renquant-common", "commit": commit or real}],
    }))
    return rq


# ---------------------------------------------------------------------------
# the idiom is gone, and the pin is what replaced it
# ---------------------------------------------------------------------------

def test_no_rq105_wrapper_still_picks_a_checkout_by_filesystem_state():
    offenders = [w.name for w in WRAPPERS
                 if "renquant-common-run" in w.read_text(encoding="utf-8")]
    assert not offenders, offenders


def test_no_wrapper_names_a_mutable_sibling_checkout():
    """The first fix's mistake: a NAME instead of a revision."""
    for w in WRAPPERS:
        text = w.read_text(encoding="utf-8")
        assert '/renquant-common/src' not in text.replace(
            "$SUBREPO/renquant-common/src", ""), w.name


def test_every_wrapper_that_needs_common_uses_the_shared_resolver():
    users = [w for w in WRAPPERS if "RQ_COMMON_SRC" in w.read_text(encoding="utf-8")]
    assert users, "no wrapper references RQ_COMMON_SRC — this test lost its subject"
    for w in users:
        text = w.read_text(encoding="utf-8")
        assert "rq105_common_src.sh" in text, w.name
        assert "rq105_resolve_common_src" in text, w.name
        assert "RQ105_OPS_DIR=" in text, f"{w.name} does not pass its own dir"


def test_the_session_scheduler_no_longer_shadows_the_pinned_copy():
    """It listed the mutable sibling BEFORE $SUBREPO/renquant-common/src, so the
    pinned copy was on PYTHONPATH and losing to an unpinned one."""
    text = (RQ105 / "run_session_scheduler.sh").read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("export PYTHONPATH="))
    assert line.count("renquant-common") == 0, (
        f"a literal renquant-common entry is back on the PYTHONPATH line: {line}"
    )


# ---------------------------------------------------------------------------
# the pin is VERIFIED, not assumed
# ---------------------------------------------------------------------------

def test_a_checkout_at_the_wrong_commit_is_refused(tmp_path):
    mod = _load(RQ105 / "rq105_pinned_common.py", "pinned_wrong")
    rq = _fake_umbrella(tmp_path, commit="0" * 40)
    with pytest.raises(mod.PinRefusal, match="pins"):
        mod.resolve_pinned_common_src(str(rq))


def test_a_matching_checkout_resolves(tmp_path):
    mod = _load(RQ105 / "rq105_pinned_common.py", "pinned_ok")
    rq = _fake_umbrella(tmp_path)
    src = mod.resolve_pinned_common_src(str(rq))
    assert src == str(rq / ".subrepo_runtime" / "repos" / "renquant-common" / "src")


def test_a_lock_with_no_entry_is_refused(tmp_path):
    mod = _load(RQ105 / "rq105_pinned_common.py", "pinned_noentry")
    rq = _fake_umbrella(tmp_path)
    (rq / "subrepos.lock.json").write_text(json.dumps({"subrepos": []}))
    with pytest.raises(mod.PinRefusal, match="no renquant-common entry"):
        mod.resolve_pinned_common_src(str(rq))


def test_a_pin_with_no_commit_pins_nothing_and_is_refused(tmp_path):
    mod = _load(RQ105 / "rq105_pinned_common.py", "pinned_nocommit")
    rq = _fake_umbrella(tmp_path)
    (rq / "subrepos.lock.json").write_text(json.dumps(
        {"subrepos": [{"name": "renquant-common", "commit": ""}]}))
    with pytest.raises(mod.PinRefusal, match="pins nothing"):
        mod.resolve_pinned_common_src(str(rq))


def test_a_missing_runtime_checkout_is_refused_not_substituted(tmp_path):
    mod = _load(RQ105 / "rq105_pinned_common.py", "pinned_missing")
    rq = _fake_umbrella(tmp_path, make_src=False)
    # A tempting sibling sits right there. It must not be reached for.
    (tmp_path / "renquant-common" / "src").mkdir(parents=True)
    with pytest.raises(mod.PinRefusal, match="Refusing to fall back"):
        mod.resolve_pinned_common_src(str(rq))


def test_an_unrelated_sibling_checkout_never_wins(tmp_path):
    """Precedence: the pinned copy is the answer even when siblings exist and
    look plausible — including one named exactly what the old code preferred."""
    mod = _load(RQ105 / "rq105_pinned_common.py", "pinned_prec")
    rq = _fake_umbrella(tmp_path)
    for name in ("renquant-common", "renquant-common-run"):
        (tmp_path / name / "src").mkdir(parents=True)
    src = mod.resolve_pinned_common_src(str(rq))
    assert ".subrepo_runtime" in src, src
    assert src != str(tmp_path / "renquant-common" / "src")
    assert src != str(tmp_path / "renquant-common-run" / "src")


# ---------------------------------------------------------------------------
# ambient environment cannot redirect a scheduled job
# ---------------------------------------------------------------------------

def test_no_env_var_selects_the_checkout(tmp_path, monkeypatch):
    """The first fix read RQ105_COMMON_CHECKOUT from the environment, so an
    unreviewed process env could still choose the code while the drift scan
    reported the choice as reviewed (codex)."""
    mod = _load(RQ105 / "rq105_pinned_common.py", "pinned_env")
    rq = _fake_umbrella(tmp_path)
    (tmp_path / "evil" / "src").mkdir(parents=True)
    for var in ("RQ105_COMMON_CHECKOUT", "RQ_COMMON_SRC", "PYTHONPATH"):
        monkeypatch.setenv(var, str(tmp_path / "evil" / "src"))
    src = mod.resolve_pinned_common_src(str(rq))
    assert "evil" not in src, src


def test_the_source_carries_no_env_override_of_the_checkout():
    """Belt and braces: the value must not be readable from the environment at
    all, in either language. A test that only checks behaviour would pass if a
    new override were added on a path the test does not exercise."""
    py = (RQ105 / "rq105_pinned_common.py").read_text(encoding="utf-8")
    sh = RESOLVER.read_text(encoding="utf-8")
    assert "RQ105_COMMON_CHECKOUT" not in py
    assert "RQ105_COMMON_CHECKOUT" not in sh
    assert 'RUNTIME_RELPATH = os.path.join(".subrepo_runtime"' in py


# ---------------------------------------------------------------------------
# the shell entrypoint, exercised for real
# ---------------------------------------------------------------------------

def _run_resolver(rq_root: Path, extra: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        # `VAR=x cmd` prefixes only the ONE command, so the exports have to be
        # their own statements — the function runs after the `.` returns.
        [_SHELL, "-c",
         f'export RQ105_OPS_DIR="{RQ105}"; export RQ_ROOT="{rq_root}"; {extra} '
         f'. "{RESOLVER}"; rq105_resolve_common_src && echo "$RQ_COMMON_SRC"'],
        capture_output=True, text=True)


def test_the_shell_resolver_exports_the_pinned_path(tmp_path):
    rq = _fake_umbrella(tmp_path)
    proc = _run_resolver(rq)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith(
        os.path.join(".subrepo_runtime", "repos", "renquant-common", "src"))


def test_the_shell_resolver_refuses_a_wrong_pin(tmp_path):
    rq = _fake_umbrella(tmp_path, commit="0" * 40)
    proc = _run_resolver(rq)
    assert proc.returncode != 0, proc.stdout
    assert "pins" in proc.stderr


def test_the_shell_resolver_is_not_zsh_only():
    """An earlier draft used ${0:A:h}, empty under bash — CI could not have run
    the resolver at all, so every shell test would have skipped."""
    proc = subprocess.run(
        ["/bin/sh", "-c", f'. "{RESOLVER}"; type rq105_resolve_common_src'],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# THE BLIND SPOT — consolidation is also the perfect hiding place
# ---------------------------------------------------------------------------

def test_a_fallback_hidden_in_a_sourced_file_is_still_found(tmp_path):
    drift = _load(OPS / "run_surface_drift_check.py", "drift_sourced")
    helper = tmp_path / "shared.sh"
    helper.write_text(
        'RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"\n'
        '[ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"\n')
    wrapper = tmp_path / "run_thing.sh"
    wrapper.write_text('#!/bin/zsh\n. "$(dirname "$0")/shared.sh"\nexport PYTHONPATH="$RQ_COMMON_SRC"\n')
    problems: list[str] = []
    infos: list[str] = []
    text = drift._with_sourced_text(str(wrapper), wrapper.read_text())
    drift._scan_wrapper_text("job", text, str(tmp_path), problems, infos)
    assert problems, (
        "the fallback moved into a sourced file and the scan reported CLEAN")
    assert "FALLBACK" in problems[0]


def test_the_real_wrappers_are_clean_through_the_same_path():
    """Control: with the fallback genuinely gone the scan must go GREEN through
    the sourced-file path too — a check that cannot go green after the
    documented remediation is a ratchet, not a check."""
    drift = _load(OPS / "run_surface_drift_check.py", "drift_clean")
    for w in [x for x in WRAPPERS if "RQ_COMMON_SRC" in x.read_text()]:
        problems: list[str] = []
        infos: list[str] = []
        text = drift._with_sourced_text(str(w), w.read_text(encoding="utf-8"))
        drift._scan_wrapper_text(w.name, text, str(ROOT.parent), problems, infos)
        assert not problems, f"{w.name}: {problems}"


def test_an_unreadable_source_target_is_recorded_not_swallowed(tmp_path):
    drift = _load(OPS / "run_surface_drift_check.py", "drift_missing")
    wrapper = tmp_path / "run_x.sh"
    wrapper.write_text('#!/bin/zsh\n. "$(dirname "$0")/nope.sh"\n')
    text = drift._with_sourced_text(str(wrapper), wrapper.read_text())
    assert "unreadable source target" in text
