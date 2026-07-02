"""Deterministic fixture tests for scripts/poc_transfer_coefficient.py.

Covers the round-2 (Codex CHANGES_REQUESTED) fixes:
  1. admission-vs-sizing split (blocked_by breakdown, sizing-only population)
  2. undefined-correlation categorization (no_deployment / zero_dispersion /
     measured — never silently folded into 0.0)
  3. canonical one-run-per-day selection (last completed run wins same-day
     duplicates)
  4. full-book same-day-alignment flag

All fixtures are in-memory SQLite databases built with the exact schema
subset `poc_transfer_coefficient.py` reads (candidate_scores, trades,
pipeline_runs) — no dependency on the real runs.alpaca.db.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import poc_transfer_coefficient as poc  # noqa: E402


_SCHEMA = """
CREATE TABLE pipeline_runs (
    run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT, created_at TIMESTAMP
);
CREATE TABLE candidate_scores (
    run_id TEXT, ticker TEXT, role TEXT, mu REAL, sigma REAL,
    kelly_target_pct REAL, blocked_by TEXT
);
CREATE TABLE trades (
    run_id TEXT, ticker TEXT, action TEXT, target_pct REAL
);
"""


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    c.executescript(_SCHEMA)
    yield c
    c.close()


def _add_run(con, run_id, run_date, created_at, n_candidates=80):
    con.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, created_at) "
        "VALUES (?,?,?,?)",
        (run_id, run_date, "live", created_at),
    )
    # pad candidate_scores with filler rows so the run counts as "full"
    # (>= MIN_FULL_RUN_CANDIDATES) independent of the real fixtures added.
    for i in range(n_candidates):
        con.execute(
            "INSERT INTO candidate_scores (run_id, ticker, role, mu) "
            "VALUES (?,?,?,?)",
            (run_id, f"__FILLER_{i}", "holding", 0.0),
        )
    con.commit()


def _add_candidate(con, run_id, ticker, mu, kelly, blocked_by=None):
    con.execute(
        "INSERT INTO candidate_scores "
        "(run_id, ticker, role, mu, kelly_target_pct, blocked_by) "
        "VALUES (?,?,?,?,?,?)",
        (run_id, ticker, "candidate", mu, kelly, blocked_by),
    )
    con.commit()


def _add_buy(con, run_id, ticker, target_pct):
    con.execute(
        "INSERT INTO trades (run_id, ticker, action, target_pct) "
        "VALUES (?,?,?,?)",
        (run_id, ticker, "buy", target_pct),
    )
    con.commit()


class TestAdmissionVsSizingSplit:
    """Round-2 point 2 + round-3 correction: blocked_by breakdown separated
    from sizing TC, using the REAL pipeline-stage taxonomy (round 2's
    `blocked_by IS NULL` test misclassified selected/submitted and
    sizing-failure names as pre-selection blockers — see _classify_reason)."""

    def test_blocked_candidates_excluded_from_sizing_population(self, con):
        run_id = "2026-01-05-live-aaa"
        _add_run(con, run_id, "2026-01-05", "2026-01-05 21:00:00")
        # 3 TRUE pre-selection blockers (real run_selection_loop reasons)
        _add_candidate(con, run_id, "BLOCKED1", 0.05, 0.02, blocked_by="correlation")
        _add_candidate(con, run_id, "BLOCKED2", 0.06, 0.03, blocked_by="sector")
        _add_candidate(con, run_id, "BLOCKED3", 0.04, 0.01, blocked_by="candidate_not_selected")
        _add_candidate(con, run_id, "SURV1", 0.10, 0.05, blocked_by=None)
        _add_candidate(con, run_id, "SURV2", 0.08, 0.04, blocked_by=None)
        _add_candidate(con, run_id, "SURV3", 0.06, 0.02, blocked_by=None)
        _add_candidate(con, run_id, "SURV4", 0.04, 0.01, blocked_by=None)
        _add_buy(con, run_id, "SURV1", 0.05)
        _add_buy(con, run_id, "SURV2", 0.03)
        _add_buy(con, run_id, "SURV3", 0.015)
        # SURV4 not bought -> w_actual = 0

        result = poc.buy_side_decision_tc(con, run_id)
        assert result["n_eligible_by_mu"] == 7
        assert result["admission_breakdown"]["correlation"] == 1
        assert result["admission_breakdown"]["sector"] == 1
        assert result["admission_breakdown"]["candidate_not_selected"] == 1
        assert result["admission_breakdown"]["survived_admission"] == 4
        assert result["n_survived_admission"] == 4
        # the 3 blocked names must never enter the correlation calc
        assert result["category"] == "measured"
        assert result["buy_side_decision_tc"] is not None

    def test_insufficient_sizing_population_when_all_blocked(self, con):
        run_id = "2026-01-06-live-bbb"
        _add_run(con, run_id, "2026-01-06", "2026-01-06 21:00:00")
        for i in range(5):
            _add_candidate(con, run_id, f"BLK{i}", 0.05, 0.02, blocked_by="correlation")
        result = poc.buy_side_decision_tc(con, run_id)
        assert result["n_survived_admission"] == 0
        assert result["category"] == "insufficient_sizing_population"
        assert result["buy_side_decision_tc"] is None
        assert result["exposure_transfer_ratio"] is None

    def test_broker_pending_submitted_is_not_a_blocker(self, con):
        """Round-3 regression: this is the exact misclassification bug —
        `broker_pending_submitted` names WERE selected+submitted, they must
        reach the sizing population, never the pre-selection-blocked bucket."""
        run_id = "2026-01-13-live-ggg"
        _add_run(con, run_id, "2026-01-13", "2026-01-13 21:00:00")
        _add_candidate(con, run_id, "PENDING1", 0.10, 0.05, blocked_by="broker_pending_submitted")
        _add_candidate(con, run_id, "SURV1", 0.08, 0.04, blocked_by=None)
        _add_candidate(con, run_id, "SURV2", 0.06, 0.02, blocked_by=None)
        _add_candidate(con, run_id, "SURV3", 0.04, 0.01, blocked_by=None)
        _add_candidate(con, run_id, "SURV4", 0.05, 0.025, blocked_by=None)
        _add_buy(con, run_id, "SURV1", 0.04)
        _add_buy(con, run_id, "SURV2", 0.02)
        _add_buy(con, run_id, "SURV3", 0.01)
        _add_buy(con, run_id, "SURV4", 0.015)
        # PENDING1 has NO row in trades (fill unconfirmed at trace time)

        result = poc.buy_side_decision_tc(con, run_id)
        # the pending name reaches the sizing population...
        assert result["n_survived_admission"] == 5
        assert result["admission_breakdown_by_stage"]["selected_submitted"] == 1
        # ...but is excluded from the correlation itself (unknown, not zero)
        assert result["n_pending_unconfirmed"] == 1
        assert result["n_corr_population"] == 4
        assert result["category"] == "measured"

    def test_sizing_failure_reaches_sizing_population_as_a_zero(self, con):
        """A real sizing-stage failure (SizeAndEmitTask._block) DID reach
        sizing — it just failed there. It belongs in the population with a
        genuine w_actual=0, unlike a fill-unconfirmed pending submission."""
        run_id = "2026-01-14-live-hhh"
        _add_run(con, run_id, "2026-01-14", "2026-01-14 21:00:00")
        _add_candidate(con, run_id, "CASHBLOCK", 0.10, 0.05, blocked_by="size_insufficient_cash")
        _add_candidate(con, run_id, "SURV1", 0.08, 0.04, blocked_by=None)
        _add_candidate(con, run_id, "SURV2", 0.06, 0.02, blocked_by=None)
        _add_candidate(con, run_id, "SURV3", 0.04, 0.01, blocked_by=None)
        _add_buy(con, run_id, "SURV1", 0.04)
        _add_buy(con, run_id, "SURV2", 0.02)
        # SURV3 and CASHBLOCK both unbought -> genuine w_actual=0 for both

        result = poc.buy_side_decision_tc(con, run_id)
        assert result["n_survived_admission"] == 4
        assert result["admission_breakdown_by_stage"]["sizing_failed"] == 1
        assert result["n_pending_unconfirmed"] == 0
        assert result["n_corr_population"] == 4  # CASHBLOCK counted, real zero

    def test_unclassified_reason_excluded_from_both_buckets(self, con):
        run_id = "2026-01-15-live-iii"
        _add_run(con, run_id, "2026-01-15", "2026-01-15 21:00:00")
        _add_candidate(con, run_id, "MYSTERY", 0.10, 0.05, blocked_by="some_future_reason_v99")
        _add_candidate(con, run_id, "SURV1", 0.08, 0.04, blocked_by=None)
        _add_candidate(con, run_id, "SURV2", 0.06, 0.02, blocked_by=None)
        _add_candidate(con, run_id, "SURV3", 0.04, 0.01, blocked_by=None)
        _add_buy(con, run_id, "SURV1", 0.04)
        _add_buy(con, run_id, "SURV2", 0.02)

        result = poc.buy_side_decision_tc(con, run_id)
        assert result["n_unclassified"] == 1
        assert "some_future_reason_v99" not in {
            k for k in result["admission_breakdown_by_stage"]
        } or result["admission_breakdown_by_stage"].get("unclassified") == 1
        # MYSTERY is in neither the blocked count nor survived_admission
        assert result["n_survived_admission"] == 3


class TestUndefinedCorrelationCategorization:
    """Round-2 point 3: no_deployment / zero_dispersion never averaged as 0.0."""

    def test_no_buys_is_no_deployment_not_zero(self, con):
        run_id = "2026-01-07-live-ccc"
        _add_run(con, run_id, "2026-01-07", "2026-01-07 21:00:00")
        for i, (mu, kelly) in enumerate([(0.10, 0.05), (0.08, 0.04), (0.06, 0.02), (0.04, 0.01)]):
            _add_candidate(con, run_id, f"T{i}", mu, kelly, blocked_by=None)
        # no trades inserted at all
        result = poc.buy_side_decision_tc(con, run_id)
        assert result["n_bought"] == 0
        assert result["category"] == "no_deployment"
        assert result["buy_side_decision_tc"] is None  # never silently 0.0

    def test_uniform_sizing_is_zero_dispersion_not_zero_correlation(self, con):
        run_id = "2026-01-08-live-ddd"
        _add_run(con, run_id, "2026-01-08", "2026-01-08 21:00:00")
        for i, (mu, kelly) in enumerate([(0.10, 0.05), (0.08, 0.04), (0.06, 0.02), (0.04, 0.01)]):
            ticker = f"T{i}"
            _add_candidate(con, run_id, ticker, mu, kelly, blocked_by=None)
            _add_buy(con, run_id, ticker, 0.02)  # SAME target_pct for every name
        result = poc.buy_side_decision_tc(con, run_id)
        assert result["n_bought"] == 4
        assert result["category"] == "zero_dispersion"
        assert result["buy_side_decision_tc"] is None  # undefined, not 0.0
        # exposure_transfer_ratio IS computable here (desired has dispersion)
        assert result["exposure_transfer_ratio"] is not None

    def test_genuine_correlation_is_measured(self, con):
        run_id = "2026-01-09-live-eee"
        _add_run(con, run_id, "2026-01-09", "2026-01-09 21:00:00")
        rows = [("A", 0.10, 0.05, 0.05), ("B", 0.08, 0.04, 0.03),
                ("C", 0.06, 0.02, 0.01), ("D", 0.04, 0.01, 0.0)]
        for ticker, mu, kelly, actual in rows:
            _add_candidate(con, run_id, ticker, mu, kelly, blocked_by=None)
            if actual > 0:
                _add_buy(con, run_id, ticker, actual)
        result = poc.buy_side_decision_tc(con, run_id)
        assert result["category"] == "measured"
        assert result["buy_side_decision_tc"] is not None
        assert result["buy_side_decision_tc"] > 0.9  # near-perfect rank agreement by construction

    def test_mean_excludes_undefined_categories(self, con):
        """The series-level mean/SE must only ever average `measured` runs."""
        # one measured, one no_deployment, one zero_dispersion
        _add_run(con, "2026-01-10-live-f1", "2026-01-10", "2026-01-10 21:00:00")
        for ticker, mu, kelly, actual in [("A", 0.10, 0.05, 0.05), ("B", 0.08, 0.04, 0.02),
                                           ("C", 0.06, 0.02, 0.0), ("D", 0.04, 0.01, 0.0)]:
            _add_candidate(con, "2026-01-10-live-f1", ticker, mu, kelly, blocked_by=None)
            if actual > 0:
                _add_buy(con, "2026-01-10-live-f1", ticker, actual)

        _add_run(con, "2026-01-11-live-f2", "2026-01-11", "2026-01-11 21:00:00")
        for i in range(4):
            _add_candidate(con, "2026-01-11-live-f2", f"T{i}", 0.05, 0.02, blocked_by=None)
        # no buys -> no_deployment

        _add_run(con, "2026-01-12-live-f3", "2026-01-12", "2026-01-12 21:00:00")
        for i in range(4):
            ticker = f"U{i}"
            _add_candidate(con, "2026-01-12-live-f3", ticker, 0.05, 0.02, blocked_by=None)
            _add_buy(con, "2026-01-12-live-f3", ticker, 0.01)  # uniform -> zero_dispersion

        results = [
            poc.buy_side_decision_tc(con, rid)
            for rid in ("2026-01-10-live-f1", "2026-01-11-live-f2", "2026-01-12-live-f3")
        ]
        categories = {r["run_id"]: r["category"] for r in results}
        assert categories["2026-01-10-live-f1"] == "measured"
        assert categories["2026-01-11-live-f2"] == "no_deployment"
        assert categories["2026-01-12-live-f3"] == "zero_dispersion"
        measured_only = [r["buy_side_decision_tc"] for r in results if r["category"] == "measured"]
        assert len(measured_only) == 1  # only the genuinely measured run


class TestCanonicalDailyRunSelection:
    """Round-2 point 4: exactly one run per calendar day, last-completed wins."""

    def test_same_day_duplicate_picks_latest_created_at(self, con):
        _add_run(con, "2026-02-01-live-early", "2026-02-01", "2026-02-02 04:39:58")
        _add_run(con, "2026-02-01-live-late", "2026-02-01", "2026-02-02 04:58:11")
        _add_run(con, "2026-02-02-live-only", "2026-02-02", "2026-02-02 21:00:00")

        canonical = poc._canonical_daily_runs(con)
        assert canonical == ["2026-02-01-live-late", "2026-02-02-live-only"]
        assert "2026-02-01-live-early" not in canonical

    def test_sub_threshold_runs_excluded(self, con):
        # a run with fewer than MIN_FULL_RUN_CANDIDATES candidate_scores rows
        # must not be treated as a "full" run at all.
        _add_run(con, "2026-02-03-live-partial", "2026-02-03", "2026-02-03 21:00:00",
                  n_candidates=5)
        canonical = poc._canonical_daily_runs(con)
        assert canonical == []


class TestFullBookSameDayAlignment:
    """Round-2 point 1: cross-day pairing is explicitly flagged, never implied same-day."""

    def test_full_book_tc_flags_cross_day_pairing(self, con, monkeypatch):
        run_id = "2026-03-01-live-only"
        _add_run(con, run_id, "2026-03-01", "2026-03-01 21:00:00")
        _add_candidate(con, run_id, "A", 0.10, 0.05, blocked_by=None)
        _add_candidate(con, run_id, "B", 0.05, 0.02, blocked_by=None)

        class _FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def read(self):
                import json as _json
                return _json.dumps(self._payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, *a, **kw):
            url = req.full_url if hasattr(req, "full_url") else req
            if "/v2/positions" in str(url):
                return _FakeResponse([{"symbol": "A", "market_value": "50.0"}])
            return _FakeResponse({"equity": "1000.0"})

        monkeypatch.setenv("ALPACA_API_KEY", "test")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test")
        monkeypatch.setattr(poc.urllib.request, "urlopen", fake_urlopen)

        result = poc.full_book_tc(con)
        assert result["same_day_aligned"] is False
        assert "NOT" in result["caveat"] or "cross-day" in result["caveat"]
        assert "same_day_aligned=false" in result["caveat"]
