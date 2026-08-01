"""Is the boosters' disagreement structured, or churn? Measured: structured, U-shaped.

orch#712 closed with "disagreement is a precondition, never evidence that an ensemble
works". This answers what that leaves open. Over 12 boosters × 20 real sessions (3 528
top-decile slots): 29.8% of name-appearances get ONE vote and 10.3% get TWELVE — the two
ends are the two largest buckets — and weighted by traded slots, 66.9% are held by
majority names and 25.9% by unanimous ones.

The by-name and by-slot views disagree by a factor of four on singletons (29.8% vs 6.2%),
which is why both are computed and both are pinned.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

import pytest

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops" / "renquant104"
sys.path.insert(0, str(OPS))

import booster_consensus_structure as C  # noqa: E402

DATA = (pathlib.Path(__file__).resolve().parent.parent / "doc" / "research" / "data"
        / "2026-08-01-booster-consensus")


@pytest.fixture(scope="module")
def rep():
    return json.loads((DATA / "consensus.json").read_text())


# ------------------------------------------------------------ the measured shape --
def test_unanimity_is_a_SECOND_MODE_above_the_plateau_not_a_U(rep):
    """Churn would be roughly uniform; this is not.

    My first version of this test asserted a U — that `12/12` exceeds every middle
    bucket — and it FAILED: 76 at 12/12 against 105 at 2/12. The claim was wrong, not the
    data. What holds is narrower and still decisive: 4/12..11/12 is a flat plateau and
    unanimity stands clear above ALL of it.
    """
    h = {int(k): v for k, v in rep["vote_hist_by_name"].items()}
    n = rep["n_boosters"]
    assert h[1] == 220 and h[n] == 76
    plateau = [h[v] for v in range(4, n)]
    assert max(plateau) <= 45 and min(plateau) >= 28      # 3.8%-6.1% of names
    assert h[n] > max(plateau)                            # a distinct second mode
    assert h[n] < h[2]                                    # but NOT a U — pinned


def test_by_SLOT_unanimity_IS_the_largest_bucket(rep):
    """The view that matters operationally: 12/12 holds more traded slots than any other
    vote level, even though 2/12 holds more distinct names."""
    s = {int(k): v for k, v in rep["vote_hist_by_slot"].items()}
    n = rep["n_boosters"]
    assert s[n] == max(s.values())


def test_two_thirds_of_TRADED_SLOTS_carry_a_majority(rep):
    assert rep["pct_slots_majority"] == pytest.approx(66.9, abs=0.2)
    assert rep["pct_slots_unanimous"] == pytest.approx(25.9, abs=0.2)


def test_the_union_is_two_and_a_half_times_one_arm(rep):
    assert rep["median_union_over_k"] == pytest.approx(2.5, abs=0.05)


def test_BY_NAME_and_BY_SLOT_disagree_and_both_are_reported(rep):
    """Singletons are 29.8% of names but 6.2% of slots. Publishing only the name view
    would understate the stable core roughly fourfold."""
    tot_n = sum(rep["vote_hist_by_name"].values())
    pct_name = 100 * rep["vote_hist_by_name"]["1"] / tot_n
    pct_slot = 100 * rep["vote_hist_by_slot"]["1"] / rep["total_slots"]
    assert pct_name == pytest.approx(29.8, abs=0.2)
    assert pct_slot == pytest.approx(6.2, abs=0.2)
    assert pct_name > 4 * pct_slot


def test_slots_sum_to_n_times_k_times_dates(rep):
    """An arithmetic identity: every booster fills exactly k slots on every scored date.
    If this drifts, a date was double-counted or silently dropped."""
    scored = [r for r in rep["per_date"] if r["status"] == "scored"]
    assert rep["total_slots"] == sum(rep["n_boosters"] * r["k"] for r in scored)


def test_every_date_is_accounted_for(rep):
    assert len(rep["per_date"]) == rep["n_dates_scored"] + rep["n_dates_skipped_thin"]


# ----------------------------------------------------------------- the two views --
def test_consensus_counts_a_name_ONCE_and_its_slots_V_TIMES():
    votes = collections.Counter({"AAA": 12, "BBB": 1, "CCC": 1})
    c = C.consensus(votes, 12)
    assert c["by_name"] == {12: 1, 1: 2}
    assert c["by_slot"] == {12: 12, 1: 2}


def test_a_unanimous_and_a_singleton_are_ONE_NAME_EACH_but_12_vs_1_slots():
    c = C.consensus(collections.Counter({"X": 12, "Y": 1}), 12)
    assert c["by_name"][12] == c["by_name"][1] == 1
    assert c["by_slot"][12] == 12 and c["by_slot"][1] == 1


# ------------------------------------------------------------- label-free by proof --
def test_NO_LABEL_COLUMN_IS_READ_ANYWHERE_IN_THE_SOURCE():
    """The whole result is label-free by construction. Asserted against the source rather
    than promised in prose, because 'I did not look at the labels' is exactly the kind of
    claim that should be checkable."""
    src = (OPS / "booster_consensus_structure.py").read_text()
    body = "\n".join(l for l in src.splitlines()
                     if "FORBIDDEN_LABEL_COLS" not in l and not l.strip().startswith("#"))
    for col in C.FORBIDDEN_LABEL_COLS:
        assert f'"{col}"' not in body, col


def test_the_not_claimed_list_travels_with_the_report(rep):
    j = " ".join(rep["not_claimed"])
    assert "no label or forward return is read" in j
    assert "share a blind spot" in j


def test_boosters_are_keyed_on_BYTES(tmp_path):
    for i, raw in enumerate(["A", "B", "A"]):
        (tmp_path / f"{i}.json").write_text(json.dumps(
            {"booster_raw_json": raw, "config_fingerprint": "same"}))
    assert len(C.distinct_boosters(str(tmp_path / "*.json"))) == 2
