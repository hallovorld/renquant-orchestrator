"""orch#1016 — which renquant-common an rq105 job imports was a filesystem accident.

Six scheduled wrappers each carried:

    RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"
    [ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"

The drift scanner's own phrasing is the finding: *which copy executes is decided
by filesystem state, not by review*. `renquant-common-run` does not exist on this
machine, so all six imported the DEV working tree — a tree edited freely, on
whatever branch someone last used, governed by no pin. And the day anyone creates
that directory, six scheduled jobs change which code they run with no commit and
no alarm.

The load-bearing test here is
`test_a_fallback_hidden_in_a_sourced_file_is_still_found`. Consolidating the
idiom into a sourced helper is exactly the move that could make the scanner go
green while the defect stays live, and a scan that cannot see the thing it is
named for is worse than no scan.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OPS = ROOT / "ops"
RQ105 = OPS / "renquant105"
RESOLVER = RQ105 / "rq105_common_src.sh"
WRAPPERS = sorted(RQ105.glob("run_*.sh"))


def _load(path: Path, name: str):
    if str(OPS) not in sys.path:
        sys.path.insert(0, str(OPS))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# the idiom is gone
# ---------------------------------------------------------------------------

def test_no_rq105_wrapper_still_picks_a_checkout_by_filesystem_state():
    offenders = [
        w.name for w in WRAPPERS
        if "renquant-common-run" in w.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"these wrappers still carry the two-checkout fallback: {offenders}. "
        f"Which copy of the code runs must be a reviewed decision."
    )


def test_every_wrapper_that_needs_common_uses_the_shared_resolver():
    users = [w for w in WRAPPERS if "RQ_COMMON_SRC" in w.read_text(encoding="utf-8")]
    assert users, "no wrapper references RQ_COMMON_SRC — this test has lost its subject"
    for w in users:
        text = w.read_text(encoding="utf-8")
        assert "rq105_common_src.sh" in text, f"{w.name} does not source the resolver"
        assert "rq105_resolve_common_src" in text, f"{w.name} does not call it"


def test_the_python_side_names_the_same_checkout_as_the_shell_side():
    """Two languages, one decision. If they drift, a liveness check and the job
    it checks can import different copies — and the check would still pass."""
    lc = _load(OPS / "liveness_common.py", "lc_checkout")
    shell = RESOLVER.read_text(encoding="utf-8")
    assert f'RQ105_COMMON_CHECKOUT:-{lc.COMMON_CHECKOUT}' in shell, (
        f"python says {lc.COMMON_CHECKOUT!r}; the shell resolver disagrees"
    )


# ---------------------------------------------------------------------------
# it fails closed
# ---------------------------------------------------------------------------

def test_the_resolver_refuses_rather_than_choosing_another_copy(tmp_path):
    (tmp_path / "renquant-orchestrator-run").mkdir()
    (tmp_path / "renquant-common-run" / "src").mkdir(parents=True)  # the tempting one
    proc = subprocess.run(
        ["/bin/zsh", "-c",
         f'. "{RESOLVER}"; RQ105_ORCH_ROOT="{tmp_path}/renquant-orchestrator-run" '
         f'RQ105_COMMON_CHECKOUT=renquant-common rq105_resolve_common_src'],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0, "a missing checkout must not resolve"
    assert "not found" in proc.stderr
    assert "Refusing to fall back" in proc.stderr
    assert "renquant-common-run" not in proc.stdout, (
        "it reached for the other checkout — that is the defect"
    )


def test_the_resolver_exports_the_named_checkout_when_present(tmp_path):
    (tmp_path / "renquant-orchestrator-run").mkdir()
    (tmp_path / "renquant-common" / "src").mkdir(parents=True)
    proc = subprocess.run(
        ["/bin/zsh", "-c",
         f'. "{RESOLVER}"; RQ105_ORCH_ROOT="{tmp_path}/renquant-orchestrator-run" '
         f'rq105_resolve_common_src && echo "$RQ_COMMON_SRC"'],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(tmp_path / "renquant-common" / "src")


def test_the_python_resolver_raises_instead_of_falling_back(tmp_path):
    lc = _load(OPS / "liveness_common.py", "lc_raise")
    (tmp_path / "renquant-common-run" / "src").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="Refusing to fall back"):
        lc.resolve_common_src(str(tmp_path / "renquant-orchestrator-run"))


# ---------------------------------------------------------------------------
# THE BLIND SPOT — the reason this file exists
# ---------------------------------------------------------------------------

def test_a_fallback_hidden_in_a_sourced_file_is_still_found(tmp_path):
    """Moving the idiom into a sourced helper must not hide it from the scan.

    Consolidation is the right fix AND the perfect place to hide the defect:
    the scanner reads the wrapper, the wrapper is clean, the scan goes green,
    and the fallback runs anyway. Then the check is worse than absent, because
    it now certifies the thing it stopped looking at.
    """
    drift = _load(OPS / "run_surface_drift_check.py", "drift_sourced")
    helper = tmp_path / "shared.sh"
    helper.write_text(
        'RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"\n'
        '[ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"\n'
    )
    wrapper = tmp_path / "run_thing.sh"
    wrapper.write_text('#!/bin/zsh\n. "$(dirname "$0")/shared.sh"\nexport PYTHONPATH="$RQ_COMMON_SRC"\n')

    problems: list[str] = []
    infos: list[str] = []
    text = drift._with_sourced_text(str(wrapper), wrapper.read_text())
    drift._scan_wrapper_text("job", text, str(tmp_path), problems, infos)

    assert problems, (
        "the fallback moved into a sourced file and the scan reported CLEAN — "
        "the scanner has a blind spot exactly where consolidation puts the code"
    )
    assert "FALLBACK" in problems[0]


def test_the_real_wrappers_are_clean_through_the_same_path(tmp_path):
    """The control for the test above: with the fallback genuinely gone, the
    scan must go GREEN through the sourced-file path too. A check that cannot
    go green after the documented remediation is a ratchet, not a check."""
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
