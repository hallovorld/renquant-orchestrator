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


def test_forwards_readonly_preflight_flags_and_pinned_config():
    code = "\n".join(l for _, l in _code_lines())
    assert "--strategy renquant_104" in code
    assert "--broker readonly-alpaca" in code
    assert "--preflight" in code
    assert ".subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json" in code


def test_pin_check_runs_before_the_bridge_and_fails_closed():
    pin_idx = _first_idx("dawn_pin_identity_check.py")
    bridge_idx = _first_idx("renquant_orchestrator daily-bridge")
    assert pin_idx != -1 and bridge_idx != -1
    # ordering: the read-only pin check gates the probe BEFORE the bridge runs
    assert pin_idx < bridge_idx
    # fail-closed: an `exit 1` sits between the pin check and the bridge
    exits = [i for i, line in _code_lines() if "exit 1" in line and pin_idx <= i < bridge_idx]
    assert exits, "pin-identity check must abort (exit 1) before the bridge"
