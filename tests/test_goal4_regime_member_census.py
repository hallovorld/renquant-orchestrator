"""GOAL-4 Phase-0 census: the axis that decides, per ensemble member.

MEASURED 2026-08-05 (orch#805): the primary panel recipe's genuine IC is +0.335
in BEAR — where the strategy places ZERO buys — and NEGATIVE in BULL_CALM, where
136 of its 154 buys land. The pooled +0.0089 every decision was read off is a
regime-mix artifact. An ensemble is a weighting over members, so GOAL-4's prior
question is whether ANY member is positively informative in the regime the book
trades. This census makes that question cheap to ask, and honest to answer.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.goal4_regime_member_census import (  # noqa: E402
    MEMBERS,
    SHIFT,
    census,
    render,
)


def _artifact(dirpath: Path, name: str, profile, *, run_at="2026-08-04",
              fp="sha256:cfdd6cb8e950da0f"):
    dirpath.mkdir(parents=True, exist_ok=True)
    payload = {"metadata": {"wf_gate_metadata": {
        "run_at": run_at, "candidate_recipe_fingerprint": fp,
        "model_placebo_profile": profile}}}
    (dirpath / name).write_text(json.dumps(payload), encoding="utf-8")


def _profile(**per_regime):
    return {"pooled": {SHIFT: {"genuine_ic": 0.0089}},
            "per_regime": {r: {SHIFT: {"genuine_ic": v}}
                           for r, v in per_regime.items()}}


class TestItReadsTheRightThing:
    def test_it_reports_the_2x_shift_the_ENFORCED_leg_uses(self, tmp_path):
        """A census on another shift describes a different experiment than the
        verdicts it sits beside."""
        _artifact(tmp_path, "panel-ltr.alpha158_fund.json",
                  {"per_regime": {"BULL_CALM": {"1x": {"genuine_ic": 0.5},
                                                "2x": {"genuine_ic": -0.03}}}})
        got = census(tmp_path)["members"][0]["vintages"][0]
        assert got["BULL_CALM"] == pytest.approx(-0.03)

    def test_byte_copies_of_one_verdict_are_ONE_vintage(self, tmp_path):
        """The corpus holds many copies of the same verdict (one artifact has 23).
        Counting them as separate vintages would inflate any claim made here."""
        prof = _profile(BULL_CALM=-0.03, BEAR=0.33)
        for i in range(5):
            _artifact(tmp_path, f"panel-ltr.alpha158_fund.copy{i}.json", prof)
        assert census(tmp_path)["members"][0]["n_vintages"] == 1

    def test_two_genuinely_different_profiles_are_TWO_vintages(self, tmp_path):
        _artifact(tmp_path, "panel-ltr.alpha158_fund.a.json",
                  _profile(BULL_CALM=-0.03), run_at="2026-07-05")
        _artifact(tmp_path, "panel-ltr.alpha158_fund.b.json",
                  _profile(BULL_CALM=-0.04), run_at="2026-08-04")
        v = census(tmp_path)["members"][0]["vintages"]
        assert [x["run_at"] for x in v] == ["2026-07-05", "2026-08-04"]


class TestAbsenceReadsAsAbsence:
    def test_a_member_with_NO_evidence_is_a_ROW_not_a_silence(self, tmp_path):
        """The load-bearing property. An unmeasured member that simply did not
        appear would read as 'nothing to report'; it must read as 'unmeasured on
        the axis that decides'."""
        _artifact(tmp_path, "panel-ltr.alpha158_fund.json", _profile(BULL_CALM=-0.03))
        result = census(tmp_path)
        assert [m["member"] for m in result["members"]] == [m[0] for m in MEMBERS]
        unmeasured = [m for m in result["members"] if m["n_vintages"] == 0]
        assert len(unmeasured) == 2
        assert "NO per-regime evidence" in render(result)
        assert "unmeasured on the axis that decides" in render(result)

    def test_a_regime_missing_from_a_profile_is_None_not_zero(self, tmp_path):
        """A zero would read as 'measured, and it is zero'."""
        _artifact(tmp_path, "panel-ltr.alpha158_fund.json", _profile(BEAR=0.33))
        v = census(tmp_path)["members"][0]["vintages"][0]
        assert v["BEAR"] == pytest.approx(0.33)
        assert v["BULL_CALM"] is None
        assert "n/a" in render(census(tmp_path))

    def test_an_absent_artifacts_dir_yields_an_empty_census_not_a_crash(self, tmp_path):
        result = census(tmp_path / "nope")
        assert all(m["n_vintages"] == 0 for m in result["members"])

    def test_unreadable_json_is_skipped_not_counted(self, tmp_path):
        (tmp_path / "panel-ltr.alpha158_fund.broken.json").write_text("{not json",
                                                                     encoding="utf-8")
        assert census(tmp_path)["members"][0]["n_vintages"] == 0


class TestTheVerdictLine:
    def test_all_negative_reads_NEGATIVE_with_the_range(self, tmp_path):
        for i, v in enumerate((-0.029, -0.034)):
            _artifact(tmp_path, f"panel-ltr.alpha158_fund.{i}.json",
                      _profile(BULL_CALM=v), run_at=f"2026-07-0{i+5}")
        text = render(census(tmp_path))
        assert "BULL_CALM: NEGATIVE in 2/2 vintages" in text
        assert "min -0.0340" in text and "max -0.0290" in text

    def test_a_sign_change_reads_MIXED_not_a_summary_statistic(self, tmp_path):
        """A member that flipped sign must NOT be summarised into one direction —
        that is the regime-mix error one level down."""
        for i, v in enumerate((-0.03, +0.02)):
            _artifact(tmp_path, f"panel-ltr.alpha158_fund.{i}.json",
                      _profile(BULL_CALM=v), run_at=f"2026-07-0{i+5}")
        assert "BULL_CALM: MIXED" in render(census(tmp_path))


def test_the_LIVE_census_still_says_what_the_issue_says():
    """Bound to reality, skips loudly off-machine. If the live corpus ever stops
    showing this, orch#805 and the GOAL-4 re-scope must be revisited — which is
    the point of pinning it."""
    live = Path("/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts")
    if not live.exists():
        pytest.skip("umbrella artifacts absent — the unit tests above still ran")
    result = census(live)
    primary = result["members"][0]
    assert primary["n_vintages"] >= 8, primary["n_vintages"]
    bull = [v["BULL_CALM"] for v in primary["vintages"] if v["BULL_CALM"] is not None]
    bear = [v["BEAR"] for v in primary["vintages"] if v["BEAR"] is not None]
    assert bull and max(bull) < 0, ("BULL_CALM is no longer negative in every "
                                    "vintage — revisit orch#805", bull)
    assert bear and min(bear) > 0.3, bear
    others = [m for m in result["members"][1:]]
    assert all(m["n_vintages"] == 0 for m in others), (
        "a fleet member gained per-regime evidence — update the GOAL-4 record",
        [(m["member"], m["n_vintages"]) for m in others])
