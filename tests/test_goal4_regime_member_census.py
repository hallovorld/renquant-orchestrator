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
    DEFAULT_CONFIG,
    SHIFT,
    census,
    members_from_config,
    render,
)


def _config(tmp_path: Path, *artifact_paths) -> Path:
    """A strategy config whose blend declares exactly these components."""
    path = tmp_path / "strategy_config.json"
    path.write_text(json.dumps({"ranking": {"panel_scoring": {
        "kind": "blend",
        "components": [{"artifact_path": a} for a in artifact_paths]}}}),
        encoding="utf-8")
    return path


PROD_LIKE = ("artifacts/prod/panel-ltr.alpha158_fund.json",
             "artifacts/momentum/momentum_artifact_ledger.jsonl")


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
        got = census(tmp_path, _config(tmp_path, *PROD_LIKE))["members"][0]["vintages"][0]
        assert got["BULL_CALM"] == pytest.approx(-0.03)

    def test_byte_copies_of_one_verdict_are_ONE_vintage(self, tmp_path):
        """The corpus holds many copies of the same verdict (one artifact has 23).
        Counting them as separate vintages would inflate any claim made here."""
        prof = _profile(BULL_CALM=-0.03, BEAR=0.33)
        for i in range(5):
            _artifact(tmp_path, f"panel-ltr.alpha158_fund.copy{i}.json", prof)
        assert census(tmp_path, _config(tmp_path, *PROD_LIKE))["members"][0]["n_vintages"] == 1

    def test_two_genuinely_different_profiles_are_TWO_vintages(self, tmp_path):
        _artifact(tmp_path, "panel-ltr.alpha158_fund.a.json",
                  _profile(BULL_CALM=-0.03), run_at="2026-07-05")
        _artifact(tmp_path, "panel-ltr.alpha158_fund.b.json",
                  _profile(BULL_CALM=-0.04), run_at="2026-08-04")
        v = census(tmp_path, _config(tmp_path, *PROD_LIKE))["members"][0]["vintages"]
        assert [x["run_at"] for x in v] == ["2026-07-05", "2026-08-04"]


class TestAbsenceReadsAsAbsence:
    def test_a_member_with_NO_evidence_is_a_ROW_not_a_silence(self, tmp_path):
        """The load-bearing property. An unmeasured member that simply did not
        appear would read as 'nothing to report'; it must read as 'unmeasured on
        the axis that decides'."""
        _artifact(tmp_path, "panel-ltr.alpha158_fund.json", _profile(BULL_CALM=-0.03))
        result = census(tmp_path, _config(tmp_path, *PROD_LIKE))
        assert len(result["members"]) == 2
        unmeasured = [m for m in result["members"] if m["n_vintages"] == 0]
        assert len(unmeasured) == 1
        assert "NO per-regime evidence" in render(result)
        assert "unmeasured on the axis that decides" in render(result)

    def test_a_regime_missing_from_a_profile_is_None_not_zero(self, tmp_path):
        """A zero would read as 'measured, and it is zero'."""
        _artifact(tmp_path, "panel-ltr.alpha158_fund.json", _profile(BEAR=0.33))
        v = census(tmp_path, _config(tmp_path, *PROD_LIKE))["members"][0]["vintages"][0]
        assert v["BEAR"] == pytest.approx(0.33)
        assert v["BULL_CALM"] is None
        assert "n/a" in render(census(tmp_path, _config(tmp_path, *PROD_LIKE)))

    def test_an_absent_artifacts_dir_yields_an_empty_census_not_a_crash(self, tmp_path):
        result = census(tmp_path / "nope", _config(tmp_path, *PROD_LIKE))
        assert all(m["n_vintages"] == 0 for m in result["members"])

    def test_unreadable_json_is_skipped_not_counted(self, tmp_path):
        (tmp_path / "panel-ltr.alpha158_fund.broken.json").write_text("{not json",
                                                                     encoding="utf-8")
        assert census(tmp_path, _config(tmp_path, *PROD_LIKE))["members"][0]["n_vintages"] == 0


class TestTheVerdictLine:
    def test_all_negative_reads_NEGATIVE_with_the_range(self, tmp_path):
        for i, v in enumerate((-0.029, -0.034)):
            _artifact(tmp_path, f"panel-ltr.alpha158_fund.{i}.json",
                      _profile(BULL_CALM=v), run_at=f"2026-07-0{i+5}")
        text = render(census(tmp_path, _config(tmp_path, *PROD_LIKE)))
        assert "BULL_CALM: NEGATIVE in 2/2 readings" in text
        assert "min -0.0340" in text and "max -0.0290" in text

    def test_a_sign_change_reads_MIXED_not_a_summary_statistic(self, tmp_path):
        """A member that flipped sign must NOT be summarised into one direction —
        that is the regime-mix error one level down."""
        for i, v in enumerate((-0.03, +0.02)):
            _artifact(tmp_path, f"panel-ltr.alpha158_fund.{i}.json",
                      _profile(BULL_CALM=v), run_at=f"2026-07-0{i+5}")
        assert "BULL_CALM: MIXED" in render(census(tmp_path, _config(tmp_path, *PROD_LIKE)))


class TestTheMemberListIsDERIVED:
    """[codex on orch#807] The first version froze panel + clf + momentum in code
    and called it "the live blend". It was not: PROD is panel + slow momentum;
    the clf leg belongs to the SHADOW profiles. Freezing a member list is the
    same error one level up from the one this census exists to find."""

    def test_the_members_come_from_the_config_not_from_code(self, tmp_path):
        only_panel = _config(tmp_path, "artifacts/prod/panel-ltr.alpha158_fund.json")
        assert [m[0] for m in members_from_config(only_panel)] == [
            "panel primary (XGB recipe)"]
        three = _config(tmp_path, *PROD_LIKE,
                        "artifacts/shadow/panel-clf.top-decile.fwd60.json")
        assert len(members_from_config(three)) == 3

    def test_an_UNRECOGNISED_component_is_a_ROW_not_a_drop(self, tmp_path):
        """A new member must never vanish from the census silently."""
        cfg = _config(tmp_path, "artifacts/prod/panel-ltr.alpha158_fund.json",
                      "artifacts/prod/some-new-leg.json")
        labels = [m[0] for m in members_from_config(cfg)]
        assert any("UNRECOGNISED" in x for x in labels), labels

    def test_a_config_with_no_components_REFUSES(self, tmp_path):
        """An empty member list would read as 'nothing to measure' instead of
        'the config could not be read'."""
        path = tmp_path / "c.json"
        path.write_text(json.dumps({"ranking": {"panel_scoring": {"kind": "xgb"}}}),
                        encoding="utf-8")
        with pytest.raises(SystemExit, match="no blend components"):
            members_from_config(path)


def test_the_LIVE_PINNED_config_is_what_the_record_describes():
    """Bound to the pinned PROD config, so MEMBERSHIP drift fails here — not
    only evidence drift. If a leg is added or removed, this test names it and
    the GOAL-4 record has to be rewritten rather than quietly inherited."""
    if not DEFAULT_CONFIG.exists():
        pytest.skip("pinned strategy config absent — unit tests above still ran")
    labels = [m[0] for m in members_from_config(DEFAULT_CONFIG)]
    assert labels == ["panel primary (XGB recipe)",
                      "momentum residual v0 (ledger-served)"], (
        "the pinned PROD blend membership changed — re-derive the GOAL-4 census "
        "claim before trusting it", labels)


def test_the_LIVE_census_still_says_what_the_record_says():
    """Bound to reality, skips loudly off-machine. If the live corpus ever stops
    showing this, orch#805 and the GOAL-4 re-scope must be revisited — which is
    the point of pinning it."""
    live = Path("/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts")
    if not live.exists() or not DEFAULT_CONFIG.exists():
        pytest.skip("umbrella artifacts/config absent — unit tests above still ran")
    result = census(live, DEFAULT_CONFIG)
    primary = result["members"][0]
    assert primary["member"] == "panel primary (XGB recipe)"
    assert primary["n_vintages"] >= 8, primary["n_vintages"]
    bull = [v["BULL_CALM"] for v in primary["vintages"] if v["BULL_CALM"] is not None]
    bear = [v["BEAR"] for v in primary["vintages"] if v["BEAR"] is not None]
    assert bull and max(bull) < 0, ("BULL_CALM is no longer negative in every "
                                    "vintage — revisit orch#805", bull)
    assert bear and min(bear) > 0.3, bear
    others = result["members"][1:]
    assert others and all(m["n_vintages"] == 0 for m in others), (
        "a PROD blend member gained per-regime evidence — update the GOAL-4 record",
        [(m["member"], m["n_vintages"]) for m in others])


class TestProvenanceAndSampleSize:
    """[codex on orch#807] A number with no file behind it cannot be re-checked,
    and a -0.03 on 11 dates reads the same as a -0.03 on 363 without n_dates."""

    def test_each_vintage_names_its_source_artifact(self, tmp_path):
        _artifact(tmp_path, "panel-ltr.alpha158_fund.json", _profile(BULL_CALM=-0.03))
        v = census(tmp_path, _config(tmp_path, *PROD_LIKE))["members"][0]["vintages"][0]
        assert v["source_artifact"].endswith("panel-ltr.alpha158_fund.json")
        assert v["profile_digest"]

    def test_n_dates_is_carried_per_regime_and_rendered(self, tmp_path):
        prof = {"per_regime": {"BULL_CALM": {SHIFT: {"genuine_ic": -0.03,
                                                     "n_dates": 363}},
                               "BULL_VOLATILE": {SHIFT: {"genuine_ic": -0.08,
                                                         "n_dates": 11}}}}
        _artifact(tmp_path, "panel-ltr.alpha158_fund.json", prof)
        result = census(tmp_path, _config(tmp_path, *PROD_LIKE))
        assert result["members"][0]["vintages"][0]["n_dates"]["BULL_CALM"] == 363
        text = render(result)
        assert "n_dates [363]" in text and "n_dates [11]" in text

    def test_an_unstamped_n_dates_reads_as_unstamped_not_zero(self, tmp_path):
        _artifact(tmp_path, "panel-ltr.alpha158_fund.json", _profile(BULL_CALM=-0.03))
        text = render(census(tmp_path, _config(tmp_path, *PROD_LIKE)))
        assert "n_dates unstamped" in text

    def test_the_NON_INDEPENDENCE_caveat_is_printed_with_every_member(self, tmp_path):
        """Agreement across overlapping windows is not a significance statement,
        and the census must say so where the numbers are, not only in a doc."""
        _artifact(tmp_path, "panel-ltr.alpha158_fund.json", _profile(BULL_CALM=-0.03))
        text = render(census(tmp_path, _config(tmp_path, *PROD_LIKE)))
        assert "OVERLAPPING evaluation windows" in text
        assert "not independent samples" in text


def test_the_WITHDRAWN_claims_do_not_come_back():
    """orch#807 withdrew 'not noise', 'degrading' and 'property of the RECIPE' as
    unsupported. This fails if any is reintroduced into the record."""
    doc = (Path(__file__).resolve().parent.parent / "doc" / "progress"
           / "2026-08-05-goal4-regime-member-census.md").read_text()
    body = doc[:doc.index("### What these 8 readings are NOT")]
    for withdrawn in ("not noise", "degrading", "property of the RECIPE"):
        assert withdrawn not in body, withdrawn


def test_the_record_never_states_a_member_count_the_config_contradicts():
    """[codex on orch#807, twice] I wrote 'the other two members' and left it in
    place after correcting PROD to TWO members — so the doc contradicted itself.
    A member count asserted in prose is a number like any other: it has to match
    the source. This derives it instead of trusting the prose."""
    doc_path = (Path(__file__).resolve().parent.parent / "doc" / "progress"
                / "2026-08-05-goal4-regime-member-census.md")
    doc = " ".join(doc_path.read_text().split())
    if DEFAULT_CONFIG.exists():
        n_prod = len(members_from_config(DEFAULT_CONFIG))
        assert n_prod == 2, n_prod
        assert "the one other PROD member" in doc
    # [codex on orch#807] The first guard listed one exact phrasing, so the
    # variant actually present ("two thirds of the SHADOW ensembles") sailed
    # through. Guard the PATTERN, not one spelling.
    for contradiction in ("the other two members", "two thirds"):
        assert contradiction not in doc, contradiction


def test_the_record_claims_NO_shadow_ensemble_result():
    """This PR derives, tests and asserts PROD only. The shadow profiles are
    censusable with --config, but nothing here binds a shadow result, so the
    record must not state one."""
    doc = " ".join((Path(__file__).resolve().parent.parent / "doc" / "progress"
                    / "2026-08-05-goal4-regime-member-census.md").read_text().split())
    assert "does not bind or claim a shadow-ensemble result" in doc
