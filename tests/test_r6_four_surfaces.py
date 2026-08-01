"""R6 re-measured: four role-assignment surfaces, two internally-consistent pairs.

The registry recorded three files and "two of them are wrong". Measured 2026-08-01 there
are four, and the shape matters more than the count: they split 2-2 across the
pinned/umbrella boundary, and each pair AGREES INTERNALLY.

That is why R6's drift guard "reports clean forever" — it compares two members of the same
pair. The failure is not that it looks at the wrong files; it is that it never crosses the
boundary.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

REGISTRY = (pathlib.Path(__file__).resolve().parent.parent / "doc" / "arch"
            / "twin-implementation-registry.md")

PINNED = "/Users/renhao/git/github/renquant-strategy-104/configs"
UMBRELLA = "/Users/renhao/git/github/RenQuant/backtesting/renquant_104"

SURFACES = (
    ("pinned", f"{PINNED}/strategy_config.json", "xgb"),
    ("pinned_golden", f"{PINNED}/strategy_config.golden.json", "xgb"),
    ("umbrella", f"{UMBRELLA}/strategy_config.json", "hf_patchtst"),
    ("umbrella_golden", f"{UMBRELLA}/strategy_config.golden.json", "hf_patchtst"),
)


def _kind(path: str):
    with open(path, "rb") as fh:
        cfg = json.loads(fh.read())
    ranking = cfg.get("ranking")
    if not isinstance(ranking, dict):
        return None
    ps = ranking.get("panel_scoring")
    return ps.get("kind") if isinstance(ps, dict) else None


def _present():
    return [(n, p, k) for n, p, k in SURFACES if os.path.exists(p)]


def test_the_registry_records_FOUR_surfaces_not_three():
    """The document is the deliverable here; this runs everywhere, including CI."""
    text = REGISTRY.read_text(encoding="utf-8")
    assert "FOUR** surfaces, not three" in text
    assert "internally-consistent PAIRS" in text
    assert "strategy_config_primary_parity.py" in text, (
        "condition 3 must record that DETECTION exists even though a single SOURCE "
        "does not")


def test_each_PAIR_agrees_internally_which_is_why_the_guard_passes_forever():
    """The load-bearing shape. If the pairs did NOT agree internally, R6's guard would
    have caught the divergence and the row would not exist."""
    present = _present()
    if len(present) < 4:
        pytest.skip(f"only {len(present)} of 4 surfaces on this machine")
    kinds = {n: _kind(p) for n, p, _ in present}
    assert kinds["pinned"] == kinds["pinned_golden"], kinds
    assert kinds["umbrella"] == kinds["umbrella_golden"], kinds


def test_the_two_PAIRS_disagree_with_each_other():
    present = _present()
    if len(present) < 4:
        pytest.skip(f"only {len(present)} of 4 surfaces on this machine")
    kinds = {n: _kind(p) for n, p, _ in present}
    assert kinds["pinned"] != kinds["umbrella"], kinds


def test_each_surface_still_declares_the_kind_the_registry_records():
    """If a surface moves, this fails and the registry row must be re-measured rather
    than quietly inherited."""
    present = _present()
    if not present:
        pytest.skip("no config surface on this machine")
    for name, path, expected in present:
        assert _kind(path) == expected, (name, path, _kind(path), expected)


def test_a_MISSING_surface_SKIPS_rather_than_passing():
    """A machine with fewer checkouts must not read as agreement — the same rule the
    parity tool follows."""
    present = _present()
    assert len(present) <= 4
    if len(present) < 4:
        pytest.skip("fewer than four surfaces — recorded, not passed")


def test_the_registry_states_WHERE_a_guard_must_look():
    """The actionable half. 'Both are wrong' does not tell anyone what to build; 'a check
    must cross the pinned/umbrella boundary' does."""
    text = REGISTRY.read_text(encoding="utf-8")
    assert "passes forever" in text and "boundary" in text
