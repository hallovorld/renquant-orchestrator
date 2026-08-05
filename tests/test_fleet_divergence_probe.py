"""GOAL-4: a shadow lane that ranks like prod produces no separating evidence.

The fleet exists to accumulate evidence distinguishing candidate scorers from
the deployed one. These tests hold the probe to saying only what it measured:
agreement on ONE date, never a verdict on a model, and never a threshold
invented after seeing the numbers.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops" / "renquant104"))
import fleet_divergence_probe as F  # noqa: E402

_SCHEMA = """
CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT, run_bundle_json TEXT,
                            created_at TEXT);
CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, role TEXT,
                               panel_score REAL);
"""


def _lane(tmp_path, lane, date, scores, *, run_id=None, bundle="{}",
          created_at="2026-08-04T13:55:00"):
    p = tmp_path / f"runs.{lane}.db"
    con = sqlite3.connect(p)
    if not p.stat().st_size:
        pass
    try:
        con.executescript(_SCHEMA)
    except sqlite3.OperationalError:
        pass                                   # already created
    rid = run_id or f"{date}-live-{lane[:6]}"
    con.execute("insert into pipeline_runs values (?,?,?,?)",
                (rid, date, bundle, created_at))
    for t, s in (scores or {}).items():
        con.execute("insert into candidate_scores values (?,?,?,?)",
                    (rid, t, "candidate", s))
    con.commit()
    con.close()
    return rid


def _n(i):
    return f"T{i:03d}"


class TestTheThreeWaysALaneGivesNoEvidence:
    """They are three different facts and must not collapse into one."""

    def test_an_ABSENT_lane_db_is_its_own_state(self, tmp_path):
        _lane(tmp_path, "alpaca", "2026-08-04", {_n(i): i for i in range(20)})
        r = F.probe("2026-08-04", data=tmp_path)
        assert all(x["state"] == F.STATE_NO_DB for x in r["lanes"])
        assert r["n_lanes_with_no_separating_evidence"] == r["n_lanes"]

    def test_a_lane_that_DID_NOT_RUN_is_not_a_lane_that_scored_nothing(
            self, tmp_path):
        _lane(tmp_path, "alpaca", "2026-08-04", {_n(i): i for i in range(20)})
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-03", {_n(0): 1.0})
        row = next(x for x in F.probe("2026-08-04", data=tmp_path)["lanes"]
                   if x["lane"] == "alpaca_shadow_blend")
        assert row["state"] == F.STATE_NO_RUN
        assert "run_id" not in row

    def test_a_run_with_NO_SCORES_keeps_its_run_id(self, tmp_path):
        """The run happened. Reporting it as 'did not run' would hide a lane
        that is failing closed every day."""
        _lane(tmp_path, "alpaca", "2026-08-04", {_n(i): i for i in range(20)})
        rid = _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04", {})
        row = next(x for x in F.probe("2026-08-04", data=tmp_path)["lanes"]
                   if x["lane"] == "alpaca_shadow_blend")
        assert row["state"] == F.STATE_NO_SCORES
        assert row["run_id"] == rid


class TestAgreementIsMeasuredNotThresholded:
    def test_an_IDENTICAL_top_k_reads_as_SAME_TOP_K(self, tmp_path):
        prod = {_n(i): float(i) for i in range(20)}
        # A strictly increasing transform: same order, different values.
        lane = {t: v * 2.0 + 5.0 for t, v in prod.items()}
        _lane(tmp_path, "alpaca", "2026-08-04", prod)
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04", lane)
        row = F.probe("2026-08-04", data=tmp_path)["lanes"][0]
        assert row["state"] == F.STATE_SAME_TOP
        assert row["top_k_overlap"] == 10
        assert row["affine_residual_ratio"] == pytest.approx(0.0, abs=1e-9)

    def test_a_REORDERING_lane_reads_as_DIVERGED(self, tmp_path):
        prod = {_n(i): float(i) for i in range(20)}
        lane = {t: -v for t, v in prod.items()}          # exactly reversed
        _lane(tmp_path, "alpaca", "2026-08-04", prod)
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04", lane)
        row = F.probe("2026-08-04", data=tmp_path)["lanes"][0]
        assert row["state"] == F.STATE_DIVERGED
        assert row["top_k_overlap"] == 0
        assert row["spearman_vs_prod"] == pytest.approx(-1.0)

    def test_the_ratio_is_reported_WITH_its_denominator(self, tmp_path):
        """A ratio whose denominator is invisible cannot be compared across
        dates — and prod's own score sd moved 8x on 2026-08-04."""
        prod = {_n(i): float(i) for i in range(20)}
        _lane(tmp_path, "alpaca", "2026-08-04", prod)
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04",
              {t: v * 2 for t, v in prod.items()})
        r = F.probe("2026-08-04", data=tmp_path)
        row = r["lanes"][0]
        assert row["prod_score_sd"] > 0
        assert "prod_sd" in F.render(r)

    def test_NO_cutoff_is_applied_to_the_ratio(self, tmp_path):
        """A NON-zero residual with an identical top-K still reads SAME_TOP_K.
        The verdict is the definitional fact — the lane would have bought the
        same names — never the magnitude. Reordering below the cut is real
        disagreement and is reported, but it is not what the state answers."""
        prod = {_n(i): float(i) for i in range(10)}
        prod.update({_n(i): 100.0 + i for i in range(10, 20)})
        lane = dict(prod)
        for i in range(0, 10):        # scramble strictly BELOW the top-10 cut
            lane[_n(i)] = float(9 - i)
        _lane(tmp_path, "alpaca", "2026-08-04", prod)
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04", lane)
        row = F.probe("2026-08-04", data=tmp_path)["lanes"][0]
        assert row["state"] == F.STATE_SAME_TOP
        assert row["top_k_overlap"] == 10
        assert row["affine_residual_ratio"] > 0, (
            "the lane really does disagree below the cut — the state answers a "
            "different question and must not be read as 'identical'")
        assert row["spearman_vs_prod"] < 1.0

    def test_too_few_common_names_REFUSES_a_correlation(self, tmp_path):
        _lane(tmp_path, "alpaca", "2026-08-04", {_n(i): float(i) for i in range(20)})
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04",
              {_n(i): float(i) for i in range(3)})
        row = F.probe("2026-08-04", data=tmp_path)["lanes"][0]
        assert row["state"] == F.STATE_TOO_FEW
        assert "spearman_vs_prod" not in row


class TestTheRecordThisProbeStands_On:
    """Bound to the live evidence. If it moves, the GOAL-4 record must be
    re-derived rather than inherited."""

    def _live(self, top_k=10):
        if not (F.DATA / "runs.alpaca.db").is_file():
            pytest.skip("umbrella data absent — the unit tests above still ran")
        return F.probe("2026-08-04", top_k=top_k)

    def test_the_momentum_lane_picked_prods_entire_top_10(self):
        r = self._live()
        row = next(x for x in r["lanes"]
                   if x["lane"] == "alpaca_shadow_blend_mom")
        if row["state"] in (F.STATE_NO_RUN, F.STATE_NO_DB):
            pytest.skip("lane absent on this box")
        assert row["top_k_overlap"] == 10, row
        assert row["state"] == F.STATE_SAME_TOP
        assert row["affine_residual_ratio"] < 0.05, row

    def test_two_lanes_ran_and_scored_nothing(self):
        r = self._live()
        silent = sorted(x["lane"] for x in r["lanes"]
                        if x["state"] == F.STATE_NO_SCORES)
        assert silent == ["alpaca_shadow_blend_mom_fast",
                          "alpaca_shadow_blend_rb_fast"], silent

    def test_the_ONE_lane_with_a_history_diverges(self):
        """`blend` is the only lane with more than one date. Six dates,
        never once matching prod's top 10."""
        overlaps = []
        for d in ("2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31",
                  "2026-08-03", "2026-08-04"):
            if not (F.DATA / "runs.alpaca.db").is_file():
                pytest.skip("umbrella data absent")
            row = next(x for x in F.probe(d)["lanes"]
                       if x["lane"] == "alpaca_shadow_blend")
            if "top_k_overlap" in row:
                overlaps.append(row["top_k_overlap"])
        assert len(overlaps) >= 5, overlaps
        assert max(overlaps) < 10, overlaps
