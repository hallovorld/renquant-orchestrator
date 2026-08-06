"""P0 orch#851: the umbrella's sizing twin allocates 25 % of the book when the
reviewed one allocates nothing.

PROVEN 2026-08-05. `compute_position_size` exists twice. Both carry an
"oversize fallback" — target buys <1 share → try `0.25 * portfolio_value`. The
**pipeline** copy then clamps back under the cap (`cap_shares`, added
2026-07-03). The **umbrella** copy, which `live.runner` sizes with, does not.

Reproduced 7/7 against the umbrella copy with the inputs recorded on the orders
themselves — including the two live-money buys of 2026-07-28.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops" / "renquant104"))
import sizing_twin_conformance as C  # noqa: E402


def _twins():
    if not C.UMBRELLA.is_file() or not C.PINNED.is_file():
        pytest.skip("umbrella and/or pinned pipeline absent on this box")
    return C._load(C.UMBRELLA, "u_test"), C._load(C.PINNED, "p_test")


class TestTheOrdersThatWereActuallyPlaced:
    """Each case is an order the live book or the dry-run funnel really made."""

    @pytest.mark.parametrize("name,max_pct,cash,price,placed", [
        # 2026-07-28 — LIVE MONEY, PV $10,565.46
        ("TSLA", 0.02322927996719378, 9162.85, 309.2200012207031, 8),
        ("EME", 0.024377563527212456, 6689.089990234375, 742.72998046875, 3),
        ("SPG", 0.023124971215604678, 4460.90, 231.70, 1),
    ])
    def test_the_UMBRELLA_copy_reproduces_the_live_order(
            self, name, max_pct, cash, price, placed):
        u, _ = _twins()
        _, shares = u.compute_position_size(10565.46, cash, max_pct, 0.0, price)
        assert shares == placed, (
            f"{name}: the umbrella twin must reproduce the order that was "
            f"actually filled; if it no longer does, the twin changed and this "
            f"record must be re-derived")

    @pytest.mark.parametrize("name,max_pct,cash,price,placed", [
        ("TSLA", 0.02322927996719378, 9162.85, 309.2200012207031, 8),
        ("EME", 0.024377563527212456, 6689.089990234375, 742.72998046875, 3),
    ])
    def test_the_PINNED_copy_would_have_placed_NOTHING(
            self, name, max_pct, cash, price, placed):
        """The whole finding: the reviewed implementation refuses these."""
        _, p = _twins()
        _, shares = p.compute_position_size(10565.46, cash, max_pct, 0.0, price)
        assert shares == 0, (
            f"{name}: the pinned copy is supposed to clamp the sub-one-share "
            f"fallback back to zero")

    def test_the_one_order_BOTH_agree_on_is_the_one_that_was_correct(self):
        """SPG's target bought a whole share, so the fallback never fired and
        the twins agree — which is why only two of the three were oversized."""
        u, p = _twins()
        args = (10565.46, 4460.90, 0.023124971215604678, 0.0, 231.70)
        assert u.compute_position_size(*args)[1] == 1
        assert p.compute_position_size(*args)[1] == 1


class TestTheDivergenceIsSystematicNotAnEdgeCase:
    def test_the_grid_finds_many_divergences_and_they_are_LARGE(self):
        u, p = _twins()
        r = C.compare(umbrella=u, pinned=p)
        assert r["n_divergent"] > 0, (
            "the twins agree — if the umbrella copy has been fixed, this "
            "record must be re-derived rather than inherited")
        assert r["max_umbrella_pct_of_pv"] > 0.20, (
            "the divergence should reach ~25 % of the portfolio", r)

    def test_the_umbrella_NEVER_sizes_SMALLER_than_the_pinned_copy(self):
        """The defect has a direction: the twin only ever OVER-allocates.
        A divergence the other way would be a different bug and must not be
        silently folded into this record."""
        u, p = _twins()
        for d in C.compare(umbrella=u, pinned=p)["divergences"]:
            assert d["umbrella_shares"] > d["pinned_shares"], d

    def test_the_pinned_copy_carries_the_clamp_and_the_umbrella_does_not(self):
        """The mechanism, asserted on the source rather than inferred."""
        if not C.UMBRELLA.is_file() or not C.PINNED.is_file():
            pytest.skip("twins absent")
        umb = C.UMBRELLA.read_text(encoding="utf-8")
        pin = C.PINNED.read_text(encoding="utf-8")
        assert "0.25 * portfolio_value" in umb and "0.25 * portfolio_value" in pin, (
            "both copies are supposed to carry the oversize fallback")
        assert "cap_shares" in pin, "the pinned copy must carry the clamp"
        assert "cap_shares" not in umb, (
            "the umbrella copy has gained the clamp — the P0 is fixed and this "
            "record must be re-derived rather than inherited")


class TestUnreadableIsNotAgreeing:
    def test_a_missing_twin_REFUSES(self, tmp_path):
        with pytest.raises(C.TwinUnreadable):
            C._load(tmp_path / "nope.py", "x")

    def test_a_module_without_the_function_REFUSES(self, tmp_path):
        p = tmp_path / "s.py"
        p.write_text("x = 1\n", encoding="utf-8")
        with pytest.raises(C.TwinUnreadable) as exc:
            C._load(p, "y")
        assert "compute_position_size" in str(exc.value)
