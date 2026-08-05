"""orch#817: I set a P0 severity from a row fraction without measuring the effect.

53 % of `fwd_60d_excess` rows exceed |0.5| and clipping collapses 726,100
distinct values to 340,527. Both true. Neither implies the IC moves: `clip` is
MONOTONE and Spearman is invariant to monotone transforms except through the
ties they create. Measured on the gate's own corpus the mean per-date IC moves
by at most ~0.005.
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from goal4_label_clip_sensitivity import CLIP, render, sensitivity  # noqa: E402


def _panel(tmp_path, label_values, pred_values, n_dates=3):
    rows = []
    for d in range(n_dates):
        for y, x in zip(label_values, pred_values):
            rows.append({"date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=d),
                         "fwd_60d_excess": y, "PRED": x})
    p = tmp_path / "panel.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return p


class TestTheMonotoneProperty:
    def test_a_clip_that_binds_NOTHING_moves_the_IC_by_zero(self, tmp_path):
        y = np.linspace(-0.4, 0.4, 40)
        p = _panel(tmp_path, y, np.arange(40.0))
        r = sensitivity(p, ("PRED",), since="2024-01-01")["predictors"]["PRED"]
        assert r["mean_delta"] == pytest.approx(0.0, abs=1e-12)

    def test_TWO_tie_groups_keeps_most_of_the_IC(self, tmp_path):
        """Calibration, NOT a ceiling [codex on orch#822]. EVERY value is
        clipped and only two tie groups survive; the rank correlation falls from
        1.000 to 0.866 because the two blocks keep their relative order.

        An earlier version called 0.134 "the worst this transform can do" — and
        the very next test in this class contradicts it, because one tie group
        loses everything. The cost depends on how the values sit against the
        bound; no ceiling is claimed. (An earlier guess of ">0.9" here was also
        wrong; the measured value is pinned instead.)"""
        y = np.concatenate([np.linspace(-5, -0.6, 20), np.linspace(0.6, 5, 20)])
        p = _panel(tmp_path, y, np.arange(40.0))
        r = sensitivity(p, ("PRED",), since="2024-01-01")["predictors"]["PRED"]
        assert r["mean_ic_unclipped"] == pytest.approx(1.0, abs=1e-9)
        assert r["mean_ic_clipped"] == pytest.approx(0.8663, abs=1e-3), r
        assert r["mean_delta"] == pytest.approx(-0.1337, abs=1e-3), r

    def test_ONE_tie_group_destroys_the_IC_ENTIRELY(self, tmp_path):
        """The refutation of any ceiling claim: when the clip leaves ONE tie
        group there is no order left to correlate with, and the loss is 1.0."""
        y = np.full(40, 9.0)
        y[:20] = 8.0                      # both sides clip to +0.5 -> all tied
        p = _panel(tmp_path, y, np.arange(40.0))
        r = sensitivity(p, ("PRED",), since="2024-01-01")["predictors"]["PRED"]
        assert np.isnan(r["mean_ic_clipped"]) or abs(r["mean_ic_clipped"]) < 1e-9


class TestItSaysWhatItMeasured:
    def test_the_render_names_the_monotone_reason(self, tmp_path):
        p = _panel(tmp_path, np.linspace(-1, 1, 40), np.arange(40.0))
        text = render(sensitivity(p, ("PRED",), since="2024-01-01"))
        assert "MONOTONE" in text and "invariant to monotone transforms" in text

    def test_the_render_CLAIMS_NO_CEILING(self, tmp_path):
        """[codex on orch#822] An earlier version claimed 0.134 was the worst
        case, contradicted by its own next test."""
        p = _panel(tmp_path, np.linspace(-1, 1, 40), np.arange(40.0))
        text = render(sensitivity(p, ("PRED",), since="2024-01-01"))
        assert "NO CEILING IS CLAIMED" in text
        assert "the worst case is 1.0" in text

    def test_the_render_says_it_cannot_settle_a_severity_question(self, tmp_path):
        p = _panel(tmp_path, np.linspace(-1, 1, 40), np.arange(40.0))
        text = render(sensitivity(p, ("PRED",), since="2024-01-01"))
        assert "cannot settle a severity question" in text

    def test_the_render_states_it_is_NOT_about_a_model(self, tmp_path):
        p = _panel(tmp_path, np.linspace(-1, 1, 40), np.arange(40.0))
        text = render(sensitivity(p, ("PRED",), since="2024-01-01"))
        assert "NOT a served scorer's mu" in text
        assert "they describe three named probes" in text

    def test_a_date_below_the_name_floor_is_skipped_not_counted(self, tmp_path):
        p = _panel(tmp_path, np.linspace(-1, 1, 5), np.arange(5.0), n_dates=4)
        r = sensitivity(p, ("PRED",), since="2024-01-01")["predictors"]["PRED"]
        assert r["n_dates"] == 0 and "no eligible dates" in r["note"]


def test_the_LIVE_measurement_behind_the_severity_downgrade():
    """Bound to reality: if the clip ever DOES move the live corpus materially,
    orch#817's downgrade must be revisited rather than inherited."""
    from goal4_label_clip_sensitivity import DEFAULT_PANEL

    if not DEFAULT_PANEL.exists():
        pytest.skip("gate corpus absent — the unit tests above still ran")
    r = sensitivity()
    assert r["n_dates"] >= 400, r["n_dates"]
    for pred, cell in r["predictors"].items():
        if not cell.get("n_dates"):
            continue
        assert abs(cell["mean_delta"]) < 0.02, (
            "the clip now moves mean per-date IC materially — revisit the "
            "orch#817 severity downgrade", pred, cell)


# ── [codex on orch#822] the only measurement that speaks to SCORER evidence ──

def test_the_served_mode_reports_the_level_gap_it_cannot_explain():
    """The measurement that settled orch#817's severity, and the caveat that
    must travel with it: 591 dates matches the stamp exactly, the absolute level
    does not, and the DELTA is a paired within-slice difference that survives a
    constant offset but not a materially different row set."""
    import pathlib

    from goal4_label_clip_sensitivity import render_served

    art = pathlib.Path("/Users/renhao/git/github/RenQuant/backtesting/"
                       "renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json")
    if not art.exists():
        pytest.skip("served artifact absent — the unit tests above still ran")
    # render only; scoring the panel is a minutes-long job and belongs in the
    # tool, not in the suite.
    fake = {"artifact": str(art), "window": ["2023-12-26", "2026-05-05"],
            "n_rows": 164869, "n_dates": 591, "stamped_real_ic": 0.04655813988989114,
            "stamped_n_oos_dates": 591, "mean_ic_unclipped": 0.06106,
            "mean_ic_clipped": 0.06627, "paired_mean_delta": 0.00521}
    text = render_served(fake)
    assert "PAIRED mean delta" in text
    assert "need NOT match the stamp" in text
    assert "materially different ROW SET would move" in text
    assert "stamped real_ic" in text


def test_the_served_mode_is_reachable_from_the_CLI():
    """Anti-inert-scaffolding: the mode that settles the question must be
    runnable, not just importable."""
    src = Path(__file__).resolve().parent.parent / "scripts" / \
        "goal4_label_clip_sensitivity.py"
    text = src.read_text(encoding="utf-8")
    assert "--served-artifact" in text
    assert "served_sensitivity(args.served_artifact" in text
