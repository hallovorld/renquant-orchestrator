"""GOAL-6 — qualifying my own orch#677 claim that "the criterion IS satisfiable".

#677 established that `BEAR` clears the placebo leg on 11 of 11 artifacts and
concluded the regime sanity criterion is satisfiable. Re-measured 2026-08-01, that
conclusion rests on a regime whose statistics are not those of a normal alpha:

    regime          n_dates   n_rows   mean_ic   hit_rate
    BULL_CALM           444   127092    0.0220     0.508
    BEAR                 55    15320    0.3346     0.982
    BULL_VOLATILE        41     8716    0.1116     0.732
    CHOPPY               41    11972    0.0129     0.707

A per-date IC positive on **98.2%** of dates, at 15x the IC of the regime carrying
**8x** the rows, is the signature of a cross-section moving as one — not of ranking
skill. So "satisfiable" is demonstrated only in a degenerate corner.
"""

from __future__ import annotations

import csv
import pathlib

CSV = (pathlib.Path(__file__).resolve().parent.parent
       / "doc/research/evidence/2026-08-01-regime-statistics/regime_profile.csv")


def _by_name():
    with CSV.open() as fh:
        return {r["regime"]: r for r in csv.DictReader(fh)}


def test_the_only_passing_regime_has_an_implausible_hit_rate():
    """THE qualification. 0.982 is not what an alpha's per-date IC looks like."""
    bear = _by_name()["BEAR"]
    assert int(bear["n_passed"]) == 11
    assert float(bear["median_hit_rate"]) > 0.98


def test_the_regime_carrying_the_panel_is_a_coin_flip():
    """BULL_CALM: 444 dates, 127k rows, hit rate 0.508 — and it never passes."""
    bc = _by_name()["BULL_CALM"]
    assert int(bc["n_passed"]) == 0
    assert 0.50 < float(bc["median_hit_rate"]) < 0.52
    assert int(bc["median_n_rows"]) > 8 * int(_by_name()["BEAR"]["median_n_rows"])


def test_the_passing_regime_is_the_smallest_by_dates():
    """The one example of satisfiability is the thinnest slice in the panel."""
    rows = _by_name()
    assert int(rows["BEAR"]["median_n_dates"]) == 55
    assert int(rows["BEAR"]["median_n_dates"]) < int(rows["BULL_CALM"]["median_n_dates"]) / 8


def test_bear_ic_is_an_order_of_magnitude_above_every_other_regime():
    rows = _by_name()
    bear = float(rows["BEAR"]["median_mean_ic"])
    others = [float(r["median_mean_ic"]) for k, r in rows.items() if k != "BEAR"]
    assert bear / max(others) > 2.9
    assert bear / float(rows["BULL_CALM"]["median_mean_ic"]) > 15


def test_the_qualification_does_not_overturn_the_placebo_finding():
    """CONTROL. #677's other claim — that BULL_CALM fails the PLACEBO leg with a
    positive mean_ic, not the skill floor — is untouched and still holds."""
    bc = _by_name()["BULL_CALM"]
    assert float(bc["median_mean_ic"]) > 0
    assert float(bc["median_placebo_ic"]) > 2 * float(bc["median_mean_ic"])
