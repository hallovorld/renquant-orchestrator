"""expkit.verdict — the GO/KILL/NULL/INCONCLUSIVE/NON-VOTING taxonomy."""
from __future__ import annotations

from statistics import NormalDist

import pytest

from renquant_orchestrator.expkit.stats import exact_sign_test
from renquant_orchestrator.expkit.verdict import (
    Outcome,
    decide,
    mde_one_sided,
    verdicts_md_row,
)

ALPHA = 0.05 / 3
BAR = 0.015


def _boot_result(lbs, ubs, ses, n_dates=700):
    by_seed = {
        str(42 + i): {
            "boot_se": ses[i],
            "ci95_two_sided": [lbs[i], ubs[i]],
            "lb_one_sided": lbs[i],
            "ub_one_sided": ubs[i],
            "alpha_one_sided": ALPHA,
            "n_boot_effective": 2000,
        }
        for i in range(len(lbs))
    }
    return {
        "method": "block_bootstrap",
        "n_dates": n_dates,
        "block": 60,
        "usable_blocks": n_dates // 60,
        "by_seed": by_seed,
        "requires_null_control": False,
    }


def _decide(res, controls_ok=True, **kw):
    return decide(
        res,
        threshold=BAR,
        min_decision_dates=600,
        alpha_one_sided=ALPHA,
        controls_ok=controls_ok,
        **kw,
    )


def test_mde_formula():
    z = NormalDist().inv_cdf(1 - ALPHA)
    assert mde_one_sided(0.02, threshold=BAR, alpha_one_sided=ALPHA) == pytest.approx(
        BAR + z * 0.02
    )


# ---------------------------------------------------------------------------
# mechanical outcomes, bootstrap branch
# ---------------------------------------------------------------------------
def test_go_requires_unanimity_and_floor():
    d = _decide(_boot_result([0.02, 0.021, 0.019], [0.05, 0.05, 0.05], [0.005] * 3))
    assert d.mechanical_outcome is Outcome.GO and d.outcome is Outcome.GO
    # one seed below the bar -> split -> not GO
    d = _decide(_boot_result([0.02, 0.01, 0.019], [0.05, 0.05, 0.05], [0.005] * 3))
    assert d.mechanical_outcome is not Outcome.GO
    assert d.unanimity_go["split"]
    # floor unmet -> never GO
    d = _decide(
        _boot_result([0.02, 0.021, 0.019], [0.05, 0.05, 0.05], [0.005] * 3, n_dates=100)
    )
    assert d.mechanical_outcome is Outcome.INCONCLUSIVE
    assert not d.floor_met


def test_kill_is_unanimous_ub_below_bar():
    d = _decide(_boot_result([-0.05, -0.05, -0.05], [0.01, 0.012, 0.014], [0.005] * 3))
    assert d.mechanical_outcome is Outcome.KILL


def test_null_vs_inconclusive_is_mechanical_power():
    z = NormalDist().inv_cdf(1 - ALPHA)
    powered_se = BAR / z * 0.9  # z*SE < bar -> powered
    unpowered_se = BAR / z * 1.1
    d = _decide(_boot_result([-0.01, -0.01, -0.01], [0.02, 0.02, 0.02], [powered_se] * 3))
    assert d.mechanical_outcome is Outcome.NULL
    assert d.power["powered_at_decision_scale"]
    d = _decide(
        _boot_result([-0.01, -0.01, -0.01], [0.02, 0.02, 0.02], [unpowered_se] * 3)
    )
    assert d.mechanical_outcome is Outcome.INCONCLUSIVE
    assert not d.power["powered_at_decision_scale"]
    # the MDE is reported next to the observed effect either way
    assert d.mde == pytest.approx(BAR + z * unpowered_se)


# ---------------------------------------------------------------------------
# NON-VOTING overlay
# ---------------------------------------------------------------------------
def test_controls_not_run_forces_non_voting():
    res = _boot_result([0.02, 0.021, 0.019], [0.05, 0.05, 0.05], [0.005] * 3)
    d = _decide(res, controls_ok=None)
    assert d.outcome is Outcome.NON_VOTING
    assert d.mechanical_outcome is Outcome.GO  # still computed and recorded
    assert any("controls_not_run" in r for r in d.non_voting_reasons)


def test_controls_failed_forces_non_voting():
    res = _boot_result([-0.05] * 3, [0.01] * 3, [0.005] * 3)
    d = _decide(res, controls_ok=False)
    assert d.outcome is Outcome.NON_VOTING
    assert any("controls_failed" in r for r in d.non_voting_reasons)


def test_declared_disqualifier_forces_non_voting():
    res = _boot_result([0.02, 0.021, 0.019], [0.05, 0.05, 0.05], [0.005] * 3)
    d = _decide(res, non_voting_reasons=("survivorship substrate",))
    assert d.outcome is Outcome.NON_VOTING
    assert d.mechanical_outcome is Outcome.GO


# ---------------------------------------------------------------------------
# small-n exact branch mapping
# ---------------------------------------------------------------------------
def _exact_result(vals, threshold=BAR):
    import numpy as np

    exact = exact_sign_test(np.asarray(vals, dtype=float), threshold=threshold)
    return {
        "method": "exact",
        "n_dates": len(vals),
        "block": 13,
        "usable_blocks": 0,
        "refusal": "toy",
        "exact": exact,
        "requires_null_control": True,
    }


def test_exact_branch_never_null():
    # 12 dates all above the bar: strong exact evidence -> GO allowed
    d = _decide(_exact_result([0.2] * 12))
    assert d.mechanical_outcome is Outcome.GO
    # mixed evidence -> INCONCLUSIVE, never NULL (V3: small n is never powered)
    d = _decide(_exact_result([0.2, -0.2] * 5))
    assert d.mechanical_outcome is Outcome.INCONCLUSIVE
    assert not d.power["powered_at_decision_scale"]
    assert d.requires_null_control


def test_exact_branch_kill():
    d = _decide(_exact_result([-0.2] * 12))
    assert d.mechanical_outcome is Outcome.KILL


# ---------------------------------------------------------------------------
# ledger row emitter
# ---------------------------------------------------------------------------
def test_verdicts_md_row_matches_ledger_format():
    row = verdicts_md_row(
        date="2026-07-03",
        id_source="toy — `memo.md` (#1)",
        verdict="NULL",
        rationale="clean IC -0.0005, CI spans the bar",
        evidence_boundary="2,241 dates; survivorship panel",
        verification="PROVISIONAL",
        verification_note="(R1 default)",
        reopening_condition="PIT substrate lands",
    )
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert len(cells) == 6  # Date | ID | Verdict | Boundary | Verification | Reopening
    assert cells[0] == "2026-07-03"
    assert cells[2].startswith("**NULL** — ")
    assert cells[4].startswith("**PROVISIONAL**")


def test_verdicts_md_row_escapes_pipes_and_newlines():
    row = verdicts_md_row(
        date="2026-07-03",
        id_source="a|b",
        verdict="GO",
        rationale="x\ny",
        evidence_boundary="n/a",
        reopening_condition="c|d",
    )
    assert "a\\|b" in row and "c\\|d" in row
    assert "\n" not in row
    import re

    cells = [c for c in re.split(r"(?<!\\)\|", row) if c.strip()]
    assert len(cells) == 6  # escaped pipes never break the table
