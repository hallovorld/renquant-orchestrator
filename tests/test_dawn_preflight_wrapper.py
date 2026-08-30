"""Wrapper-command regression for the dawn preflight monitor (#968 r1, codex).

The PR's central safety property is the shell invocation itself: the scheduled
probe must run through the multirepo bridge (NOT direct `-m live.runner`),
forward the readonly/preflight flags + the pinned config, and gate on the
read-only pin-identity check BEFORE the bridge, fail-closed. These controls pin
that command + ordering so a later revert to `-m live.runner`, a dropped
`--preflight`, or a reordered pin check turns CI red — statically, no live run.
"""
from __future__ import annotations

from pathlib import Path

WRAPPER = (Path(__file__).resolve().parent.parent
           / "ops" / "renquant104" / "dawn_funnel_preflight.sh")


def _code_lines() -> list[tuple[int, str]]:
    """(index, line) for NON-comment, non-blank lines (comments may legitimately
    mention `-m live.runner` as the documented rollback)."""
    out = []
    for i, raw in enumerate(WRAPPER.read_text().splitlines()):
        s = raw.strip()
        if s and not s.startswith("#"):
            out.append((i, raw))
    return out


def _first_idx(token: str) -> int:
    for i, line in _code_lines():
        if token in line:
            return i
    return -1


def test_invokes_multirepo_bridge_not_direct_live_runner():
    code = "\n".join(l for _, l in _code_lines())
    assert "renquant_orchestrator daily-bridge --repo-dir" in code
    # the ACTUAL invocation must not be the direct umbrella runner (comments ok)
    assert "-m live.runner" not in code


def test_forwards_readonly_preflight_flags_and_derived_config():
    code = "\n".join(l for _, l in _code_lines())
    assert "--strategy renquant_104" in code
    assert "--broker readonly-alpaca" in code
    assert "--preflight" in code
    # the config path is the SUBREPO_ROOT-derived variable, not a hard-coded path
    assert '--strategy-config-path "$STRATEGY_CONFIG"' in code
    assert 'STRATEGY_CONFIG="$(renquant_strategy_config "$SUBREPO_ROOT")"' in code


def test_check_config_and_bridge_bind_the_same_resolved_subrepo_root():
    # codex #968 r1 P1: the pin check, the strategy config, and the bridge must all
    # bind the ONE resolved SUBREPO_ROOT (renquant_subrepo_root, which honors
    # RENQUANT_SUBREPO_ROOT / an assembly), never a hard-coded .subrepo_runtime.
    code = "\n".join(l for _, l in _code_lines())
    # the pin check verifies exactly that root
    assert '--runtime-root "$SUBREPO_ROOT"' in code
    # the strategy config derives from that same root
    assert 'renquant_strategy_config "$SUBREPO_ROOT"' in code
    # the bridge inherits that same root via the exported env
    assert 'export RENQUANT_SUBREPO_ROOT="$SUBREPO_ROOT"' in code
    # and no consumer hard-codes a divergent runtime path
    assert ".subrepo_runtime/repos" not in code


def test_pin_check_runs_before_the_bridge_and_fails_closed():
    pin_idx = _first_idx("dawn_pin_identity_check.py")
    bridge_idx = _first_idx("renquant_orchestrator daily-bridge")
    assert pin_idx != -1 and bridge_idx != -1
    # ordering: the read-only pin check gates the probe BEFORE the bridge runs
    assert pin_idx < bridge_idx
    # fail-closed: an `exit 1` sits between the pin check and the bridge
    exits = [i for i, line in _code_lines() if "exit 1" in line and pin_idx <= i < bridge_idx]
    assert exits, "pin-identity check must abort (exit 1) before the bridge"


def test_pin_check_distinguishes_mismatch_from_dirt_and_aborts_loudly():
    """2026-08-30: the check exits 0 (proceed; TREE_DIRTY in docs paths is a
    WARN the check prints itself), 1 (PIN_MISMATCH) or 2 (TREE_DIRTY_BLOCKING).
    The wrapper must map each code to its own message — never "not aligned"
    for a dirty tree — and must notify on either abort: from 08-19 to 08-27 it
    aborted seven sessions in silence."""
    code = "\n".join(l for _, l in _code_lines())
    assert "PIN_RC=$?" in code
    assert 'PIN_ABORT="PIN_MISMATCH:' in code and 'PIN_ABORT="TREE_DIRTY_BLOCKING:' in code
    assert "not aligned" not in code
    # the abort path is one block: echo + notify + exit 1, after a non-zero rc
    abort_idx = _first_idx('if [ "$PIN_RC" -ne 0 ]')
    notify_idx = _first_idx('rq_notify "rq104 dawn preflight ABORT')
    bridge_idx = _first_idx("renquant_orchestrator daily-bridge")
    assert -1 < abort_idx < notify_idx < bridge_idx
    # rc 0 proceeds: no `exit` on the 0 arm
    zero_arm = [l for _, l in _code_lines() if l.strip().startswith("0)")]
    assert zero_arm and all("exit" not in l for l in zero_arm)


def test_boot_catchup_guard_runs_after_the_pinned_pythonpath_and_before_the_pin_check():
    """RunAtLoad (deploy/ plist) + the shared guard: the calendar helper must
    import from the PINNED orchestrator (after `export PYTHONPATH=`), and a
    load-time skip must not re-run the pin check (before it)."""
    guard_idx = _first_idx("launchd_catchup_guard dawn-preflight")
    path_idx = _first_idx("export PYTHONPATH=")
    pin_idx = _first_idx("dawn_pin_identity_check.py")
    assert -1 < path_idx < guard_idx < pin_idx
    code = "\n".join(l for _, l in _code_lines())
    assert '. "$OPS_DIR/../catchup_guard.sh"' in code
    assert "0605 session" in code
