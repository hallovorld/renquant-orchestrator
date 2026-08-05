"""GOAL-7: Arm B is calendar-blocked to ~2027 — and nothing checked it was coming.

The frozen registration says Arm B, the only arm that may CERTIFY, needs ≥30
matured BULL_CALM dates. A date that far out is exactly the promise nothing
verifies: if the weekly training job stops, the ledger never grows, Arm B never
arrives, and **no alarm distinguishes that from waiting**.

These tests hold the probe to the three answers it must keep apart, and to
refusing the fourth (a projection) when it has no rate to project from.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops" / "renquant104"))
import goal7_arm_b_accrual_probe as P  # noqa: E402


def _ledger(tmp_path, *cutoffs, name="l.jsonl"):
    p = tmp_path / name
    p.write_text("".join(
        json.dumps({"cutoff_date": c, "kind": "momentum_residual_v0"}) + "\n"
        for c in cutoffs), encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _no_live_regime_chain(monkeypatch):
    """Regimes come from an injected stub, so these tests never depend on the
    umbrella being present — a probe test that only passes on the box that
    wrote it is not a test of the probe."""
    monkeypatch.setattr(P, "regimes_for", lambda dates: {
        "by_date": {d: "BULL_CALM" for d in dates},
        "unavailable_because": None})


class TestUnavailableEvidenceIsAnOBSERVABLEState:
    """[codex on orch#836] LEDGER_ABSENT and LEDGER_UNREADABLE were declared
    states that `probe()` could never return — it raised instead, and `--json`
    emitted nothing. A declared state a caller cannot observe is not a state,
    and a daily report needs to tell unavailable evidence from an ordinary
    not-yet-eligible result."""

    def test_an_ABSENT_ledger_is_a_structured_result(self, tmp_path):
        r = P.probe_result(dt.date(2026, 8, 5), path=tmp_path / "nope.jsonl")
        assert r["state"] == P.STATE_NO_LEDGER
        assert "no ledger at" in r["unavailable_because"]

    def test_an_UNPARSEABLE_ledger_is_a_structured_result(self, tmp_path):
        p = tmp_path / "l.jsonl"
        p.write_text("{not json\n", encoding="utf-8")
        r = P.probe_result(dt.date(2026, 8, 5), path=p)
        assert r["state"] == P.STATE_UNREADABLE

    def test_the_counts_are_NONE_not_zero(self, tmp_path):
        """Zero would read like a measurement of an empty ledger."""
        r = P.probe_result(dt.date(2026, 8, 5), path=tmp_path / "nope.jsonl")
        assert r["n_rows"] is None and r["n_primary_matured"] is None
        assert "NOT 'nothing accrued'" in P.render(r)

    def test_the_CLI_exits_2_on_unavailable_evidence(self, tmp_path, monkeypatch,
                                                    capsys):
        monkeypatch.setattr(P, "LEDGER", tmp_path / "nope.jsonl")
        assert P.main(["--as-of", "2026-08-05", "--json"]) == 2
        assert json.loads(capsys.readouterr().out)["state"] == P.STATE_NO_LEDGER

    def test_the_exception_still_exists_for_callers_that_want_it(self, tmp_path):
        with pytest.raises(P.LedgerUnreadable):
            P.probe(dt.date(2026, 8, 5), path=tmp_path / "nope.jsonl")


class TestABrokenPRODUCERIsNotAnEmptyLedger:
    """A row the accrual cannot count must not read as 'nothing accrued yet' —
    that is the exact state this probe exists to tell apart from 'it stopped'."""

    def test_a_row_with_NO_cutoff_date_is_UNREADABLE_not_skipped(self, tmp_path):
        p = tmp_path / "l.jsonl"
        p.write_text(json.dumps({"kind": "momentum_residual_v0"}) + "\n",
                     encoding="utf-8")
        r = P.probe_result(dt.date(2026, 8, 5), path=p)
        assert r["state"] == P.STATE_UNREADABLE
        assert "no cutoff_date" in r["unavailable_because"]

    def test_a_MALFORMED_cutoff_date_is_UNREADABLE_not_a_raw_ValueError(
            self, tmp_path):
        p = tmp_path / "l.jsonl"
        p.write_text(json.dumps({"cutoff_date": "not-a-date"}) + "\n",
                     encoding="utf-8")
        r = P.probe_result(dt.date(2026, 8, 5), path=p)
        assert r["state"] == P.STATE_UNREADABLE
        assert "is not a date" in r["unavailable_because"]

    def test_a_NON_OBJECT_row_is_UNREADABLE(self, tmp_path):
        p = tmp_path / "l.jsonl"
        p.write_text("[]\n", encoding="utf-8")
        assert P.probe_result(dt.date(2026, 8, 5), path=p)["state"] == \
            P.STATE_UNREADABLE


class TestTheThreeQuestionsStayApart:

    def test_a_ledger_that_STOPPED_growing_is_its_own_state(self, tmp_path):
        """The failure the probe exists for: the job died and the wait looks
        identical to progress."""
        led = _ledger(tmp_path, "2026-01-05", "2026-01-12", "2026-01-19")
        r = P.probe(dt.date(2026, 3, 1), path=led)
        assert r["state"] == P.STATE_STOPPED
        assert r["missed_firings"] >= P.STALE_AFTER_MISSED

    def test_ONE_late_firing_is_NOT_stopped(self, tmp_path):
        """Anti-false-positive: an operator rebooting a machine is not an
        incident, and crying one teaches the reader to ignore the next."""
        led = _ledger(tmp_path, "2026-01-05", "2026-01-12", "2026-01-19")
        r = P.probe(dt.date(2026, 1, 29), path=led)   # 10 days = 1 missed
        assert r["missed_firings"] == 1
        assert r["state"] != P.STATE_STOPPED


class TestItRefusesToProjectFromNothing:
    def test_a_SINGLE_cutoff_projects_nothing(self, tmp_path):
        led = _ledger(tmp_path, "2026-08-02")
        r = P.probe(dt.date(2026, 8, 5), path=led)
        assert r["state"] == P.STATE_GENESIS_ONLY
        assert r["projection"]["projected"] is False
        assert "cannot be OBSERVED" in r["projection"]["refused_because"]
        assert "projected_eligible_on_or_after" not in r["projection"]

    def test_an_ELIGIBLE_arm_projects_NOTHING(self, tmp_path):
        """[codex on orch#836] `need` went <= 0 and the arithmetic produced a
        'projected eligibility' date in the PAST. A reached threshold is not a
        forecast."""
        cutoffs = [(dt.date(2025, 1, 6) + dt.timedelta(days=7 * i)).isoformat()
                   for i in range(40)]
        led = _ledger(tmp_path, *cutoffs)
        r = P.probe(dt.date(2026, 8, 5), path=led)
        assert r["state"] == P.STATE_ELIGIBLE
        assert r["n_primary_matured"] >= P.MIN_DATES_PRIMARY
        assert r["projection"]["projected"] is False
        assert "already eligible" in r["projection"]["refused_because"]
        assert "projected_eligible_on_or_after" not in r["projection"]

    def test_enough_cutoffs_project_from_the_OBSERVED_rate(self, tmp_path):
        led = _ledger(tmp_path, "2026-01-05", "2026-01-12", "2026-01-19",
                      "2026-01-26")
        r = P.probe(dt.date(2026, 1, 27), path=led)
        p = r["projection"]
        assert p["projected"] is True
        assert p["observed_cutoffs_per_day"] == pytest.approx(3 / 21)
        assert p["observed_primary_share"] == 1.0
        assert p["projected_eligible_on_or_after"] > "2026-01-27"


class TestMaturityIsTheEARLIESTPossible:
    def test_a_cutoff_matures_60_BUSINESS_days_later(self, tmp_path):
        led = _ledger(tmp_path, "2026-08-02")
        r = P.probe(dt.date(2026, 8, 5), path=led)
        d = r["per_cutoff"][0]
        assert d["label_matures_on_or_after"] == "2026-10-23"
        assert d["matured"] is False

    def test_the_render_says_holidays_are_not_modelled(self, tmp_path):
        led = _ledger(tmp_path, "2026-08-02")
        text = P.render(P.probe(dt.date(2026, 8, 5), path=led))
        assert "EARLIEST possible" in text


class TestAnUnknownRegimeIsNotThePrimaryOne:
    def test_an_unavailable_regime_chain_counts_NOTHING_as_primary(
            self, tmp_path, monkeypatch):
        """Assuming the primary regime would inflate the only number that
        decides eligibility."""
        monkeypatch.setattr(P, "regimes_for", lambda dates: {
            "by_date": {}, "unavailable_because": "chain unavailable here"})
        led = _ledger(tmp_path, *[f"2026-01-{d:02d}" for d in range(5, 26, 7)])
        r = P.probe(dt.date(2026, 6, 1), path=led)
        assert r["n_primary_matured"] == 0
        assert all(d["regime"] is None and d["regime_known"] is False
                   for d in r["per_cutoff"])
        assert "UNKNOWN, not zero" in P.render(r)

    def test_a_NON_primary_regime_does_not_count(self, tmp_path, monkeypatch):
        monkeypatch.setattr(P, "regimes_for", lambda dates: {
            "by_date": {d: "BEAR" for d in dates}, "unavailable_because": None})
        led = _ledger(tmp_path, *[f"2026-01-{d:02d}" for d in range(5, 26, 7)])
        r = P.probe(dt.date(2026, 6, 1), path=led)
        assert r["n_primary_matured"] == 0


def test_the_LIVE_ledger_is_what_the_GOAL7_record_describes():
    """Bound to reality: genesis only, one cutoff, nothing matured."""
    if not P.LEDGER.is_file():
        pytest.skip("umbrella ledger absent — the unit tests above still ran")
    r = P.probe(dt.date(2026, 8, 5))
    assert r["n_rows"] == 1 and r["newest_cutoff"] == "2026-08-02", r
    assert r["n_primary_matured"] == 0, (
        "Arm B has started maturing — the registration's ~2027 estimate should "
        "be replaced by the probe's projection", r)
    assert r["projection"]["projected"] is False
