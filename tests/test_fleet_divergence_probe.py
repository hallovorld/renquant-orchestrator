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


class TestTheReferenceIsValidatedBEFOREAnythingIsComparedToIt:
    """[codex on orch#826] Without this the probe kept going: every lane
    compared against an EMPTY prod score set, landed in TOO_FEW_COMMON_NAMES,
    and the summary reported the whole fleet as producing "no separating
    evidence". A missing control would have been published as a finding."""

    def test_NO_prod_run_refuses_the_whole_probe(self, tmp_path):
        _lane(tmp_path, "alpaca", "2026-08-03", {_n(i): float(i) for i in range(20)})
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04",
              {_n(i): float(i) for i in range(20)})
        with pytest.raises(F.ProdBaselineUnavailable) as exc:
            F.probe("2026-08-04", data=tmp_path)
        assert "nothing to compare" in str(exc.value)

    def test_a_prod_run_that_scored_NOTHING_refuses_too(self, tmp_path):
        _lane(tmp_path, "alpaca", "2026-08-04", {})
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04",
              {_n(i): float(i) for i in range(20)})
        with pytest.raises(F.ProdBaselineUnavailable):
            F.probe("2026-08-04", data=tmp_path)

    def test_too_few_prod_names_to_define_the_TOP_K_refuses(self, tmp_path):
        """The reference must be able to support the comparison ASKED FOR —
        a top-20 cannot be defined from 12 names."""
        _lane(tmp_path, "alpaca", "2026-08-04", {_n(i): float(i) for i in range(12)})
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04",
              {_n(i): float(i) for i in range(20)})
        assert F.probe("2026-08-04", top_k=10, data=tmp_path)["lanes"]
        with pytest.raises(F.ProdBaselineUnavailable) as exc:
            F.probe("2026-08-04", top_k=20, data=tmp_path)
        assert "top-20" in str(exc.value)

    def test_the_refusal_says_HOW_MANY_prod_runs_it_saw(self, tmp_path):
        """Without the run count, "scored 0 names" is missing the one fact that
        lets a reader tell a quiet morning from a broken funnel."""
        for i in range(3):
            _lane(tmp_path, "alpaca", "2026-08-04", {},
                  run_id=f"r{i}", created_at=f"2026-08-04T1{i}:00:00")
        with pytest.raises(F.ProdBaselineUnavailable) as exc:
            F.probe("2026-08-04", data=tmp_path)
        # The message now names the BASELINE LANE rather than the word "prod",
        # because the baseline is choosable.
        assert "3 alpaca run(s) recorded" in str(exc.value)
        assert "stale baseline" in str(exc.value)

    def test_the_refusal_DIAGNOSES_NOTHING(self, tmp_path):
        """[codex on orch#831] A run count cannot establish that those runs are
        intraday passes, nor that the funnel's scheduled time has not arrived.
        On a historical date, or after a FAILED funnel, calling the zero-score
        state 'expected' would convert an unknown empty baseline into a
        non-incident by implication — the exact move this probe exists to
        prevent, appearing in the probe's own error text."""
        _lane(tmp_path, "alpaca", "2026-08-04", {})
        with pytest.raises(F.ProdBaselineUnavailable) as exc:
            F.probe("2026-08-04", data=tmp_path)
        msg = str(exc.value).lower()
        for word in ("expected", "intraday", "once daily", "not yet", "13:55"):
            assert word not in msg, (word, msg)

    def test_a_NON_POSITIVE_top_k_is_refused(self, tmp_path):
        """An empty top-K set makes EVERY lane read SAME_TOP_K_AS_PROD — the
        strongest verdict this file can emit, from a parameter that asked for
        nothing [codex on orch#826]."""
        _lane(tmp_path, "alpaca", "2026-08-04", {_n(i): float(i) for i in range(20)})
        for bad in (0, -1):
            with pytest.raises(ValueError) as exc:
                F.probe("2026-08-04", top_k=bad, data=tmp_path)
            assert "positive" in str(exc.value)

    def test_the_CLI_exits_3_rather_than_printing_a_fleet_conclusion(
            self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(F, "DATA", tmp_path)
        _lane(tmp_path, "alpaca", "2026-08-03", {_n(i): float(i) for i in range(20)})
        rc = F.main(["--date", "2026-08-04"])
        assert rc == 3
        err = capsys.readouterr()
        assert "REFUSED" in err.err
        assert "no separating evidence" not in err.out


class TestWhatWasComparedIsHashed:
    """The probe reads MUTABLE sqlite. A record naming only a run id cannot
    prove the rows behind it are the rows compared [codex on orch#826]."""

    def test_every_row_carries_the_hash_of_what_was_read(self, tmp_path):
        prod = {_n(i): float(i) for i in range(20)}
        _lane(tmp_path, "alpaca", "2026-08-04", prod)
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04", prod)
        r = F.probe("2026-08-04", data=tmp_path)
        assert r["baseline_score_set_sha256"].startswith("sha256:")
        assert r["lanes"][0]["score_set_sha256"] == r["baseline_score_set_sha256"]

    def test_the_hash_is_ORDER_independent_but_VALUE_sensitive(self):
        a = {"AAA": 1.0, "BBB": 2.0}
        assert F.score_set_sha256(a) == F.score_set_sha256({"BBB": 2.0, "AAA": 1.0})
        assert F.score_set_sha256(a) != F.score_set_sha256({"AAA": 1.0, "BBB": 2.5})
        assert F.score_set_sha256(a) != F.score_set_sha256({"AAA": 1.0})


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
        assert row["baseline_score_sd"] > 0
        assert "base_sd" in F.render(r)

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


BUNDLE = (REPO / "doc" / "progress" / "data" /
          "2026-08-05-fleet-divergence-2026-08-04.json")


class TestTheRecordThisProbeStands_On:
    """Bound to the COMMITTED bundle, not to mutable sqlite.

    [codex on orch#826] These assertions used to re-query the live DB, so they
    could pass long after the reported evidence had changed underneath the
    document citing it. The bundle is the immutable thing the write-up cites;
    the live check below is a SEPARATE test that fails loudly on divergence
    rather than quietly re-deriving.
    """

    @pytest.fixture(scope="class")
    def bundle(self):
        import json as _json

        return _json.loads(BUNDLE.read_text())

    def _row(self, bundle, lane):
        return next(x for x in bundle["lanes"] if x["lane"] == lane)

    def test_the_bundle_names_what_it_compared(self, bundle):
        assert bundle["date"] == "2026-08-04" and bundle["top_k"] == 10
        assert bundle["baseline_run_id"] == "2026-08-04-live-a199b993"
        assert bundle["baseline_score_set_sha256"].startswith("sha256:")
        for row in bundle["lanes"]:
            if row["state"] not in (F.STATE_NO_RUN, F.STATE_NO_DB):
                assert row["run_id"], row

    def test_the_momentum_lane_picked_prods_entire_top_10(self, bundle):
        row = self._row(bundle, "alpaca_shadow_blend_mom")
        assert row["top_k_overlap"] == 10, row
        assert row["state"] == F.STATE_SAME_TOP
        assert row["affine_residual_ratio"] < 0.05, row

    def test_two_lanes_ran_and_scored_nothing(self, bundle):
        silent = sorted(x["lane"] for x in bundle["lanes"]
                        if x["state"] == F.STATE_NO_SCORES)
        assert silent == ["alpaca_shadow_blend_mom_fast",
                          "alpaca_shadow_blend_rb_fast"], silent

    def test_three_of_five_lanes_gave_no_separating_evidence(self, bundle):
        assert bundle["n_lanes"] == 5
        assert bundle["n_lanes_with_no_separating_evidence"] == 3


def test_the_LIVE_evidence_still_reproduces_the_committed_bundle():
    """If the DB behind the record moves, this FAILS — it does not skip and it
    does not silently re-derive. A record that quietly re-computes itself is
    not a record."""
    import json as _json

    if not (F.DATA / "runs.alpaca.db").is_file():
        pytest.skip("umbrella data absent — the bundle tests above still ran")
    bundle = _json.loads(BUNDLE.read_text())
    live = F.probe(bundle["date"], top_k=bundle["top_k"])
    assert live["baseline_score_set_sha256"] == bundle["baseline_score_set_sha256"], (
        "prod's scored set changed under the GOAL-4 record — re-derive it "
        "rather than inheriting it")
    for want in bundle["lanes"]:
        got = next(x for x in live["lanes"] if x["lane"] == want["lane"])
        assert got["state"] == want["state"], (want["lane"], got, want)
        assert got.get("score_set_sha256") == want.get("score_set_sha256"), (
            want["lane"], "the lane's scored set changed under the record")


RANGE_BUNDLE = (REPO / "doc" / "progress" / "data" /
                "2026-08-05-fleet-divergence-blend-range.json")


class TestTheRangeClaimHasItsOwnRecord:
    """[codex on orch#826] The six-date statement was asserted from a test that
    re-queried mutable sqlite and skipped when absent, while the committed
    bundle held ONE date. A claim about a range needs a record of the range."""

    @pytest.fixture(scope="class")
    def rng(self):
        import json as _json

        return _json.loads(RANGE_BUNDLE.read_text())

    def test_the_bundle_holds_all_six_dates(self, rng):
        assert rng["dates"] == ["2026-07-28", "2026-07-29", "2026-07-30",
                                "2026-07-31", "2026-08-03", "2026-08-04"]
        assert len(rng["runs"]) == 6
        assert rng["top_k"] == 10

    def test_blend_never_once_matched_prods_top_10(self, rng):
        overlaps = []
        for run in rng["runs"]:
            row = next(x for x in run["lanes"]
                       if x["lane"] == "alpaca_shadow_blend")
            overlaps.append(row["top_k_overlap"])
        assert overlaps == [7, 7, 7, 6, 6, 5], overlaps
        assert max(overlaps) < 10

    def test_each_date_names_the_runs_and_hashes_it_compared(self, rng):
        for run in rng["runs"]:
            assert run["baseline_run_id"], run["date"]
            assert run["baseline_score_set_sha256"].startswith("sha256:"), run["date"]
            row = next(x for x in run["lanes"]
                       if x["lane"] == "alpaca_shadow_blend")
            assert row["run_id"] and row["score_set_sha256"].startswith("sha256:")

    def test_an_unavailable_baseline_is_RECORDED_in_the_range_not_dropped(
            self, tmp_path):
        """A range that quietly shrinks is a different range."""
        _lane(tmp_path, "alpaca", "2026-08-04", {_n(i): float(i) for i in range(20)})
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04",
              {_n(i): float(i) for i in range(20)})
        out = F.probe_range(["2026-08-03", "2026-08-04"], data=tmp_path)
        assert [r["date"] for r in out["runs"]] == ["2026-08-03", "2026-08-04"]
        assert out["runs"][0]["state"] == F.STATE_PROD_UNAVAILABLE
        assert out["runs"][0]["lanes"] == []


class TestTheBaselineIsChoosableButStillValidated:
    """[measured 2026-08-05] prod scores its buy funnel ONCE a day. Before that
    the reference does not exist and the probe refuses — but the fleet may
    already have run, and "do the candidates disagree with EACH OTHER" is the
    ensemble question regardless. A choosable reference must not become an
    unchecked one."""

    def _fleet(self, tmp_path):
        prod = {_n(i): float(i) for i in range(20)}
        _lane(tmp_path, "alpaca", "2026-08-04", prod)
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04", prod)
        _lane(tmp_path, "alpaca_shadow_blend_mom", "2026-08-04",
              {t: -v for t, v in prod.items()})
        return prod

    def test_a_NON_PROD_baseline_compares_the_others_to_it(self, tmp_path):
        self._fleet(tmp_path)
        r = F.probe("2026-08-04", data=tmp_path,
                    baseline="alpaca_shadow_blend")
        assert r["baseline_lane"] == "alpaca_shadow_blend"
        lanes = {x["lane"]: x for x in r["lanes"]}
        # PROD is now one of the compared lanes, and the baseline is not.
        assert "alpaca" in lanes and "alpaca_shadow_blend" not in lanes
        assert lanes["alpaca"]["state"] == F.STATE_SAME_TOP
        assert lanes["alpaca_shadow_blend_mom"]["top_k_overlap"] == 0

    def test_a_CHOSEN_baseline_that_scored_nothing_still_REFUSES(self, tmp_path):
        """The validation is on the baseline, whichever lane it is."""
        _lane(tmp_path, "alpaca", "2026-08-04", {_n(i): float(i) for i in range(20)})
        _lane(tmp_path, "alpaca_shadow_blend", "2026-08-04", {})
        with pytest.raises(F.ProdBaselineUnavailable) as exc:
            F.probe("2026-08-04", data=tmp_path, baseline="alpaca_shadow_blend")
        assert "alpaca_shadow_blend" in str(exc.value)

    def test_the_default_baseline_is_still_PROD(self, tmp_path):
        self._fleet(tmp_path)
        r = F.probe("2026-08-04", data=tmp_path)
        assert r["baseline_lane"] == "alpaca"
        assert all(x["lane"] != "alpaca" for x in r["lanes"])

    def test_the_render_names_which_baseline_was_used(self, tmp_path):
        self._fleet(tmp_path)
        text = F.render(F.probe("2026-08-04", data=tmp_path,
                                baseline="alpaca_shadow_blend"))
        assert "vs alpaca_shadow_blend" in text


# --- persisted names must be baseline-scoped (codex on orch#844) --------------

def test_no_persisted_key_claims_prod_when_the_baseline_is_choosable():
    """The committed bundle is a review surface. With `--baseline` choosable, a
    key named `prod_*` asserts a comparison that did not happen: the shipped
    bundle had `baseline_lane = alpaca_shadow_blend` while its keys still said
    `prod_run_id` / `prod_n_scored` / `prod_score_set_sha256`.

    Pinned as "no persisted key starts with prod_" rather than as a rename of
    three known names, so a FOURTH prod-scoped key cannot be added later and
    reintroduce the same misleading record."""
    import json as _json
    for p in sorted((REPO / "doc" / "progress" / "data").glob("*fleet-divergence*.json")):
        bundle = _json.loads(p.read_text())

        def walk(node, path="$"):
            if isinstance(node, dict):
                for k, v in node.items():
                    assert not k.startswith("prod_"), (
                        f"{p.name}{path}: persisted key {k!r} is prod-scoped while "
                        f"baseline_lane={node.get('baseline_lane', '?')!r}")
                    walk(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")

        walk(bundle)


def test_the_blendbase_bundle_records_a_NON_prod_baseline():
    """Anti-vacuity for the test above: it must be checking a bundle whose
    baseline really is not prod, otherwise prod-scoped keys would be harmless
    and the assertion vacuous."""
    import json as _json
    p = REPO / "doc" / "progress" / "data" / "2026-08-05-fleet-divergence-2026-08-05-blendbase.json"
    bundle = _json.loads(p.read_text())
    assert bundle["baseline_lane"] != "alpaca"
    assert bundle["baseline_run_id"]
