"""Same-recipe boosters on the REAL panel — and the correction to orch#698.

orch#698 measured booster divergence on a SYNTHETIC probe and reported ~60% top-decile
disagreement, saying in its own title that it licensed no production inference. Measured
on the live panel over 20 sessions: the median is **35.7%**. The direction survives; the
magnitude does not, and the synthetic headline is withdrawn as a description of production.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops" / "renquant104"
sys.path.insert(0, str(OPS))

import booster_real_panel_divergence as D  # noqa: E402

DATA = (pathlib.Path(__file__).resolve().parent.parent / "doc" / "research" / "data"
        / "2026-08-01-booster-divergence-real-panel")


@pytest.fixture(scope="module")
def rep():
    return json.loads((DATA / "divergence.json").read_text())


# -------------------------------------------------------------- the measured result --
def test_twelve_distinct_boosters_share_one_config_fingerprint(rep):
    """The collapse being measured: 12 functions, one fingerprint."""
    assert rep["n_distinct_boosters"] == 12
    fps = {b["config_fingerprint"] for b in rep["boosters"].values()}
    assert len(fps) == 1, fps
    assert {b["n_features"] for b in rep["boosters"].values()} == {172}


def test_the_real_panel_median_disagreement_is_357_percent(rep):
    assert rep["n_dates_scored"] == 20
    assert rep["median_top_decile_disagreement"] == pytest.approx(0.357, abs=0.005)


def test_the_worst_pair_replaced_two_thirds_of_the_top_decile(rep):
    assert rep["worst_pair_overlap"] == pytest.approx(1 / 3, abs=0.005)


def test_the_synthetic_headline_is_NOT_reproduced_on_real_data(rep):
    """orch#698's ~60% is well outside the real median. If a later edit made this test
    pass at 0.60 again, the correction would have been silently undone."""
    assert rep["median_top_decile_disagreement"] < 0.50


def test_every_date_is_accounted_for_scored_or_skipped(rep):
    """A thin date dropped without a trace would make the rest look more representative
    than they are."""
    assert len(rep["per_date"]) == rep["n_dates_scored"] + rep["n_dates_skipped_thin"]
    assert all(r["status"] in ("scored", "SKIPPED_THIN") for r in rep["per_date"])


def test_the_assumption_about_source_space_is_recorded_not_buried(rep):
    """`feature_source_contract` is a documentation dict, not a selector, so 'panel' is
    my choice and has to travel with the number."""
    joined = " ".join(rep["assumptions"])
    assert "source_space='panel' is MY choice" in joined
    assert "documentation dict" in joined
    assert any("imported" in a for a in rep["assumptions"])


def test_what_is_not_claimed_travels_with_the_report(rep):
    joined = " ".join(rep["not_claimed"])
    assert "no label or forward return is touched" in joined
    assert "not a history" in joined
    assert "disagreement is a precondition" in joined


# ------------------------------------------------------------------------- the method --
def test_boosters_are_keyed_on_the_FUNCTION_not_the_fingerprint(tmp_path):
    """Keying on config_fingerprint would collapse all 12 into 1 — and that collapse is
    the defect under measurement, so it must not also be the method."""
    for i, raw in enumerate(["AAA", "BBB", "AAA"]):
        (tmp_path / f"a{i}.json").write_text(json.dumps(
            {"booster_raw_json": raw, "config_fingerprint": "same", "feature_cols": []}))
    got = D.distinct_boosters(str(tmp_path / "*.json"))
    assert len(got) == 2


def test_an_artifact_with_no_booster_is_skipped_not_counted(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"config_fingerprint": "x"}))
    (tmp_path / "b.json").write_text(json.dumps({"booster_raw_json": ""}))
    (tmp_path / "c.json").write_text("not json")
    assert D.distinct_boosters(str(tmp_path / "*.json")) == {}


def test_overlap_is_a_FRACTION_OF_K_not_jaccard():
    """The operational question is how much of the traded top decile changes; Jaccard's
    union denominator answers a different one."""
    a = pd.Series([5, 4, 3, 2, 1], index=list("abcde"))
    b = pd.Series([5, 4, 1, 2, 3], index=list("abcde"))
    st = D.pair_stats({"a": a, "b": b}, k=2)
    assert st["overlap_median"] == 1.0          # both top-2 are {a,b}
    st3 = D.pair_stats({"a": a, "b": b}, k=3)
    assert st3["overlap_median"] == pytest.approx(2 / 3)


def test_a_single_booster_yields_no_pairs_rather_than_a_fake_agreement():
    st = D.pair_stats({"only": pd.Series([1.0, 2.0])}, k=1)
    assert st["n_pairs"] == 0
    assert st["overlap_median"] is None and st["spearman_median"] is None
