"""Tests for M5 tournament shadow admission logger + delta report."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pytest

from renquant_orchestrator.tournament_shadow_admission import (
    SCHEMA_VERSION,
    DeltaReport,
    SessionRecord,
    TickerAdmission,
    append_record,
    evaluate_session,
    format_delta_report,
    generate_delta_report,
    log_shadow_admission,
    read_records,
)

RUN_DATE = date(2026, 7, 5)
WATCHLIST = ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA", "NFLX"]
MIN_MODEL_SCORE = 0.10


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_scores(
    tickers: list[str],
    *,
    buy_signal: set[str] | None = None,
    high_rank: set[str] | None = None,
) -> dict[str, dict]:
    """Build a ticker_scores mapping.

    - ``buy_signal`` tickers get signal="buy"; others get "hold".
    - ``high_rank`` tickers get rank_score=0.5; others get 0.05.
    """
    buy_signal = buy_signal or set()
    high_rank = high_rank or set()
    out: dict[str, dict] = {}
    for t in tickers:
        out[t] = {
            "signal": "buy" if t in buy_signal else "hold",
            "raw_score": 0.3 if t in buy_signal else -0.1,
            "rank_score": 0.5 if t in high_rank else 0.05,
        }
    return out


# ---------------------------------------------------------------------------
# TickerAdmission dataclass
# ---------------------------------------------------------------------------

class TestTickerAdmission:
    def test_admitted(self):
        ta = TickerAdmission(ticker="AAPL", admitted=True)
        assert ta.admitted
        assert ta.blocked_by is None

    def test_rejected(self):
        ta = TickerAdmission(ticker="AAPL", admitted=False, blocked_by="wash_sale")
        assert not ta.admitted
        assert ta.blocked_by == "wash_sale"


# ---------------------------------------------------------------------------
# Tournament gate replay
# ---------------------------------------------------------------------------

class TestTournamentGateReplay:
    def test_buy_signal_high_rank_admitted(self):
        """Tournament admits: signal=buy AND rank >= min_model_score."""
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.5}},
            panel_candidates=["AAPL"],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert "AAPL" in record.tournament_admitted

    def test_hold_signal_rejected(self):
        """Tournament rejects: signal != buy."""
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={"AAPL": {"signal": "hold", "raw_score": -0.1, "rank_score": 0.5}},
            panel_candidates=["AAPL"],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert "AAPL" in record.tournament_rejected
        detail = record.tournament_details[0]
        assert detail["blocked_by"] == "model_signal:hold"

    def test_low_rank_rejected(self):
        """Tournament rejects: buy signal but rank < min_model_score."""
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.05}},
            panel_candidates=["AAPL"],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert "AAPL" in record.tournament_rejected
        detail = record.tournament_details[0]
        assert detail["blocked_by"] == "rank_below_min"

    def test_nan_rank_rejected(self):
        """Tournament rejects: NaN rank_score."""
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": float("nan")}},
            panel_candidates=["AAPL"],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert "AAPL" in record.tournament_rejected
        detail = record.tournament_details[0]
        assert detail["blocked_by"] == "rank_below_min"

    def test_none_signal_rejected(self):
        """Tournament rejects: None signal (no model)."""
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={"AAPL": {"signal": None, "raw_score": None, "rank_score": None}},
            panel_candidates=[],
            panel_blocked={"AAPL": "no_model"},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert "AAPL" in record.tournament_rejected
        detail = record.tournament_details[0]
        assert detail["blocked_by"] == "no_model_signal"

    def test_missing_from_scores(self):
        """Ticker in watchlist but not in ticker_scores -> blocked."""
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL", "MSFT"],
            ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.5}},
            panel_candidates=["AAPL"],
            panel_blocked={"MSFT": "missing_features"},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert "MSFT" in record.tournament_rejected
        msft_detail = [d for d in record.tournament_details if d["ticker"] == "MSFT"][0]
        assert msft_detail["blocked_by"] == "no_model_data"


# ---------------------------------------------------------------------------
# Panel path observation
# ---------------------------------------------------------------------------

class TestPanelPathObservation:
    def test_panel_admits_candidate(self):
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.5}},
            panel_candidates=["AAPL"],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert "AAPL" in record.panel_admitted

    def test_panel_rejects_blocked(self):
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.5}},
            panel_candidates=[],
            panel_blocked={"AAPL": "veto:rank_score_below_floor"},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert "AAPL" in record.panel_rejected
        detail = record.panel_details[0]
        assert detail["blocked_by"] == "veto:rank_score_below_floor"


# ---------------------------------------------------------------------------
# Session-level agreement / disagreement
# ---------------------------------------------------------------------------

class TestSessionAgreement:
    def test_full_agreement(self):
        """When both paths agree on every ticker, agreement_rate=1.0."""
        # Both admit AAPL, MSFT; both reject GOOG, AMZN
        scores = _make_scores(
            ["AAPL", "MSFT", "GOOG", "AMZN"],
            buy_signal={"AAPL", "MSFT"},
            high_rank={"AAPL", "MSFT"},
        )
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL", "MSFT", "GOOG", "AMZN"],
            ticker_scores=scores,
            panel_candidates=["AAPL", "MSFT"],
            panel_blocked={"GOOG": "veto:low", "AMZN": "veto:low"},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert record.agreement_rate == 1.0
        assert record.tournament_only == []
        assert record.panel_only == []
        assert sorted(record.agreed_admit) == ["AAPL", "MSFT"]
        assert sorted(record.agreed_reject) == ["AMZN", "GOOG"]

    def test_partial_disagreement(self):
        """Tournament admits GOOG but panel rejects it -> tournament_only."""
        scores = _make_scores(
            ["AAPL", "GOOG"],
            buy_signal={"AAPL", "GOOG"},
            high_rank={"AAPL", "GOOG"},
        )
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL", "GOOG"],
            ticker_scores=scores,
            panel_candidates=["AAPL"],
            panel_blocked={"GOOG": "regime_admission:failed"},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert record.tournament_only == ["GOOG"]
        assert record.panel_only == []
        assert record.agreement_rate == 0.5

    def test_panel_only_disagreement(self):
        """Panel admits GOOG but tournament rejects it -> panel_only."""
        scores = _make_scores(
            ["AAPL", "GOOG"],
            buy_signal={"AAPL"},
            high_rank={"AAPL"},
        )
        # Panel admits both, tournament only admits AAPL
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL", "GOOG"],
            ticker_scores=scores,
            panel_candidates=["AAPL", "GOOG"],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert record.panel_only == ["GOOG"]
        assert record.tournament_only == []
        assert record.agreement_rate == 0.5

    def test_schema_version(self):
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.5}},
            panel_candidates=["AAPL"],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert record.schema_version == SCHEMA_VERSION

    def test_regime_stored(self):
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.5}},
            panel_candidates=["AAPL"],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
            regime="BULL_CALM",
        )
        assert record.regime == "BULL_CALM"


# ---------------------------------------------------------------------------
# Conditional (admission-relevant) agreement — codex review fix
# ---------------------------------------------------------------------------

class TestConditionalAgreement:
    def test_whole_watchlist_metric_hides_admission_relevant_disagreement(self):
        """Reproduces the exact bug: 18 trivial both-reject names plus 2
        admission-relevant names in TOTAL disagreement. The old whole-
        watchlist ``agreement_rate`` reports a comforting 90% (dominated by
        the 18 both-reject names) while ``conditional_agreement_rate`` — the
        metric restricted to the admission-relevant subset — correctly
        reports 0% (the two paths agree on NOTHING that either path would
        actually admit)."""
        rejects = [f"REJ{i}" for i in range(18)]
        watchlist = rejects + ["TOURN_ONLY", "PANEL_ONLY"]
        scores = _make_scores(
            watchlist, buy_signal={"TOURN_ONLY"}, high_rank={"TOURN_ONLY"},
        )
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=watchlist,
            ticker_scores=scores,
            panel_candidates=["PANEL_ONLY"],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        # The old metric: comforting and WRONG for the retirement decision.
        assert record.agreement_rate == 0.9
        # The new metric: correctly surfaces total disagreement on the
        # names that actually matter.
        assert record.conditional_agreement_rate == 0.0
        assert record.admission_precision == 0.0
        assert record.admission_recall == 0.0

    def test_conditional_agreement_full_overlap(self):
        """Both paths admit exactly the same names -> conditional agreement
        is 1.0 regardless of how many trivial both-reject names surround it."""
        scores = _make_scores(
            ["AAPL", "MSFT", "GOOG"],
            buy_signal={"AAPL", "MSFT"}, high_rank={"AAPL", "MSFT"},
        )
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL", "MSFT", "GOOG"],
            ticker_scores=scores,
            panel_candidates=["AAPL", "MSFT"],
            panel_blocked={"GOOG": "veto:low"},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert record.conditional_agreement_rate == 1.0
        assert record.admission_precision == 1.0
        assert record.admission_recall == 1.0

    def test_conditional_agreement_none_when_no_admission_relevant_subset(self):
        """When neither path admits anything, there is no admission-relevant
        subset — conditional_agreement_rate (and precision/recall) must be
        None, not a default that could be misread as agreement."""
        scores = _make_scores(["AAPL", "MSFT"])  # no buy_signal -> both reject
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL", "MSFT"],
            ticker_scores=scores,
            panel_candidates=[],
            panel_blocked={"AAPL": "veto:low", "MSFT": "veto:low"},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert record.conditional_agreement_rate is None
        assert record.admission_precision is None
        assert record.admission_recall is None
        # Whole-watchlist agreement is still 1.0 (both trivially reject) —
        # exactly the comforting-but-uninformative number this fix guards
        # against being mistaken for the decision signal.
        assert record.agreement_rate == 1.0

    def test_asymmetric_admission_precision_recall(self):
        """Tournament admits a superset of what panel admits -> precision
        < 1.0 (tournament over-admits relative to panel), recall == 1.0
        (every panel-admitted name is also tournament-admitted)."""
        scores = _make_scores(
            ["AAPL", "MSFT", "GOOG"],
            buy_signal={"AAPL", "MSFT", "GOOG"}, high_rank={"AAPL", "MSFT", "GOOG"},
        )
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL", "MSFT", "GOOG"],
            ticker_scores=scores,
            panel_candidates=["AAPL"],
            panel_blocked={"MSFT": "veto:low", "GOOG": "veto:low"},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert record.admission_precision == pytest.approx(1 / 3, abs=1e-4)
        assert record.admission_recall == 1.0
        assert record.conditional_agreement_rate == pytest.approx(1 / 3, abs=1e-4)


# ---------------------------------------------------------------------------
# Persistence (JSONL)
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_append_and_read(self, tmp_path: Path):
        log_path = tmp_path / "shadow" / "test.jsonl"
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL", "MSFT"],
            ticker_scores=_make_scores(
                ["AAPL", "MSFT"],
                buy_signal={"AAPL"},
                high_rank={"AAPL"},
            ),
            panel_candidates=["AAPL"],
            panel_blocked={"MSFT": "veto"},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        append_record(record, log_path)
        assert log_path.exists()

        records = read_records(log_path)
        assert len(records) == 1
        assert records[0]["run_date"] == "2026-07-05"
        assert records[0]["schema_version"] == SCHEMA_VERSION

    def test_multiple_appends(self, tmp_path: Path):
        log_path = tmp_path / "test.jsonl"
        for i in range(3):
            record = evaluate_session(
                run_date=date(2026, 7, 5 + i),
                watchlist=["AAPL"],
                ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.5}},
                panel_candidates=["AAPL"],
                panel_blocked={},
                min_model_score=MIN_MODEL_SCORE,
                bypass_ticker_gate=True,
            )
            append_record(record, log_path)

        records = read_records(log_path)
        assert len(records) == 3

    def test_read_empty(self, tmp_path: Path):
        log_path = tmp_path / "nonexistent.jsonl"
        assert read_records(log_path) == []

    def test_read_with_malformed_lines(self, tmp_path: Path):
        log_path = tmp_path / "test.jsonl"
        log_path.write_text('{"valid": true}\nnot json\n{"also_valid": true}\n')
        records = read_records(log_path)
        assert len(records) == 2


# ---------------------------------------------------------------------------
# Fail-open entry point
# ---------------------------------------------------------------------------

class TestLogShadowAdmission:
    def test_disabled_by_default(self):
        result = log_shadow_admission(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={},
            panel_candidates=[],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        assert result is None

    def test_enabled_writes(self, tmp_path: Path):
        result = log_shadow_admission(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.5}},
            panel_candidates=["AAPL"],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
            enabled=True,
            shadow_dir=tmp_path,
        )
        assert result is not None
        assert result.agreement_rate == 1.0
        log_path = tmp_path / "tournament_vs_panel_admission.jsonl"
        assert log_path.exists()


# ---------------------------------------------------------------------------
# Delta report
# ---------------------------------------------------------------------------

class TestDeltaReport:
    @staticmethod
    def _build_records(
        n: int,
        agreement_rate: float = 1.0,
        conditional_agreement_rate: float | None = None,
    ) -> list[dict]:
        """Build n synthetic session records.

        ``conditional_agreement_rate`` defaults to ``agreement_rate`` so
        existing threshold tests (written against the pre-fix whole-watchlist
        metric) continue to exercise the same READY/LIKELY READY/NOT READY
        branches, now via the corrected admission-relevant metric that
        actually drives ``recommendation``.
        """
        if conditional_agreement_rate is None:
            conditional_agreement_rate = agreement_rate
        records = []
        for i in range(n):
            d = date(2026, 7, 1 + i)
            # Build a small 4-ticker example
            if agreement_rate >= 1.0:
                tourn_admitted = ["AAPL", "MSFT"]
                panel_admitted = ["AAPL", "MSFT"]
                tourn_only = []
                panel_only = []
            else:
                tourn_admitted = ["AAPL", "MSFT"]
                panel_admitted = ["AAPL", "GOOG"]
                tourn_only = ["MSFT"]
                panel_only = ["GOOG"]

            records.append({
                "schema_version": SCHEMA_VERSION,
                "run_date": d.isoformat(),
                "n_watchlist": 4,
                "agreement_rate": agreement_rate,
                "conditional_agreement_rate": conditional_agreement_rate,
                "admission_precision": conditional_agreement_rate,
                "admission_recall": conditional_agreement_rate,
                "tournament_admitted": tourn_admitted,
                "panel_admitted": panel_admitted,
                "tournament_rejected": [],
                "panel_rejected": [],
                "agreed_admit": ["AAPL"],
                "agreed_reject": [],
                "tournament_only": tourn_only,
                "panel_only": panel_only,
                "regime": "BULL_CALM",
            })
        return records

    def test_empty_records(self):
        report = generate_delta_report([])
        assert report.n_sessions == 0
        assert "Insufficient" in report.recommendation

    def test_insufficient_sessions(self):
        records = self._build_records(5)
        report = generate_delta_report(records)
        assert report.n_sessions == 5
        assert "Insufficient" in report.recommendation

    def test_high_agreement_ready(self):
        records = self._build_records(25, agreement_rate=0.97)
        report = generate_delta_report(records)
        assert report.n_sessions == 25
        assert "READY" in report.recommendation
        assert report.mean_agreement_rate == 0.97

    def test_medium_agreement_likely_ready(self):
        records = self._build_records(25, agreement_rate=0.90)
        report = generate_delta_report(records)
        assert "LIKELY READY" in report.recommendation

    def test_low_agreement_not_ready(self):
        records = self._build_records(25, agreement_rate=0.70)
        report = generate_delta_report(records)
        assert "NOT READY" in report.recommendation

    def test_chronic_disagreements_tracked(self):
        records = self._build_records(25, agreement_rate=0.75)
        report = generate_delta_report(records)
        assert "MSFT" in report.chronic_tournament_only
        assert report.chronic_tournament_only["MSFT"] == 25
        assert "GOOG" in report.chronic_panel_only
        assert report.chronic_panel_only["GOOG"] == 25

    def test_format_report_produces_text(self):
        records = self._build_records(5)
        report = generate_delta_report(records)
        text = format_delta_report(report)
        assert "Delta Report" in text
        assert "RECOMMENDATION" in text
        assert "Insufficient" in text

    def test_date_range(self):
        records = self._build_records(5)
        report = generate_delta_report(records)
        assert report.date_range == ("2026-07-01", "2026-07-05")

    def test_total_tickers_evaluated(self):
        records = self._build_records(5)
        report = generate_delta_report(records)
        assert report.total_tickers_evaluated == 20  # 5 sessions * 4 tickers

    def test_recommendation_driven_by_conditional_not_whole_watchlist(self):
        """The exact bug this fix closes at the aggregate level: a dataset
        where whole-watchlist agreement looks READY (>=95%) but the
        admission-relevant subset is in material disagreement (<85%) must
        recommend NOT READY, not READY."""
        records = self._build_records(
            25, agreement_rate=0.97, conditional_agreement_rate=0.40,
        )
        report = generate_delta_report(records)
        assert report.mean_agreement_rate == 0.97
        assert report.mean_conditional_agreement_rate == 0.40
        assert "NOT READY" in report.recommendation
        assert "READY" not in report.recommendation.split("NOT READY")[0]

    def test_cannot_assess_when_no_admission_relevant_sessions(self):
        records = self._build_records(
            25, agreement_rate=1.0, conditional_agreement_rate=None,
        )
        # Explicitly strip the field to simulate zero admission-relevant
        # sessions (both paths reject everything, every session).
        for r in records:
            r["conditional_agreement_rate"] = None
            r["admission_precision"] = None
            r["admission_recall"] = None
        report = generate_delta_report(records)
        assert report.n_sessions_admission_relevant == 0
        assert report.mean_conditional_agreement_rate is None
        assert "CANNOT ASSESS" in report.recommendation

    def test_insufficient_admission_relevant_sample_despite_25_total_sessions(self):
        """The exact bug codex flagged: 25 total sessions (>= 20) but only 2
        have any admission activity, and those 2 happen to agree perfectly
        (conditional_agreement_rate=1.0). Pre-fix, this would report READY
        off an effective sample size of 2. Must report insufficient sample
        instead, regardless of the total session count."""
        records = self._build_records(
            25, agreement_rate=1.0, conditional_agreement_rate=None,
        )
        # Strip admission activity from all but 2 sessions, which agree
        # perfectly -- would trip the >=0.95 READY branch under the old,
        # total-session-only minimum-N gate.
        for r in records:
            r["conditional_agreement_rate"] = None
            r["admission_precision"] = None
            r["admission_recall"] = None
        for r in records[:2]:
            r["conditional_agreement_rate"] = 1.0
            r["admission_precision"] = 1.0
            r["admission_recall"] = 1.0

        report = generate_delta_report(records)
        assert report.n_sessions == 25
        assert report.n_sessions_admission_relevant == 2
        assert report.mean_conditional_agreement_rate == 1.0
        assert "INSUFFICIENT ADMISSION-RELEVANT SAMPLE" in report.recommendation
        assert "READY" not in report.recommendation


# ---------------------------------------------------------------------------
# Delta report CLI
# ---------------------------------------------------------------------------

class TestDeltaReportCLI:
    def test_nonexistent_file(self):
        from scripts.tournament_delta_report import main
        rc = main(["nonexistent.jsonl"])
        assert rc == 1

    def test_json_output(self, tmp_path: Path):
        from scripts.tournament_delta_report import main
        log_path = tmp_path / "test.jsonl"
        # Write a valid record
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=["AAPL"],
            ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.5}},
            panel_candidates=["AAPL"],
            panel_blocked={},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
        )
        append_record(record, log_path)
        rc = main([str(log_path), "--json"])
        # Insufficient sessions -> exit 1
        assert rc == 1

    def test_last_n_filter(self, tmp_path: Path):
        from scripts.tournament_delta_report import main
        log_path = tmp_path / "test.jsonl"
        for i in range(5):
            record = evaluate_session(
                run_date=date(2026, 7, 1 + i),
                watchlist=["AAPL"],
                ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.5}},
                panel_candidates=["AAPL"],
                panel_blocked={},
                min_model_score=MIN_MODEL_SCORE,
                bypass_ticker_gate=True,
            )
            append_record(record, log_path)

        rc = main([str(log_path), "--last", "3"])
        assert rc == 1  # only 3 sessions < 20

    def test_exit_code_insufficient_despite_25_total_sessions(self, tmp_path: Path):
        """The same aggregate bug, exercised through the real exit-code path:
        25 total sessions (>= 20) but only 2 with any admission activity,
        which agree perfectly. Pre-fix, this would return 0 (ready) off an
        effective sample size of 2. Must return 1 (insufficient), not 0."""
        from scripts.tournament_delta_report import main

        log_path = tmp_path / "test.jsonl"
        for i in range(23):
            # Both paths reject: no admission activity this session.
            record = evaluate_session(
                run_date=date(2026, 7, 1 + i),
                watchlist=["AAPL"],
                ticker_scores={"AAPL": {"signal": "hold", "raw_score": -0.1, "rank_score": 0.01}},
                panel_candidates=[],
                panel_blocked={"AAPL": "veto_weak_buy"},
                min_model_score=MIN_MODEL_SCORE,
                bypass_ticker_gate=True,
            )
            append_record(record, log_path)
        for i in range(23, 25):
            # Both paths admit: perfect agreement, but only 2 such sessions.
            record = evaluate_session(
                run_date=date(2026, 7, 1 + i),
                watchlist=["AAPL"],
                ticker_scores={"AAPL": {"signal": "buy", "raw_score": 0.3, "rank_score": 0.5}},
                panel_candidates=["AAPL"],
                panel_blocked={},
                min_model_score=MIN_MODEL_SCORE,
                bypass_ticker_gate=True,
            )
            append_record(record, log_path)

        records = read_records(log_path)
        report = generate_delta_report(records)
        assert report.n_sessions == 25
        assert report.n_sessions_admission_relevant == 2
        assert report.mean_conditional_agreement_rate == 1.0

        rc = main([str(log_path)])
        assert rc == 1  # insufficient admission-relevant sample, not 0 (ready)


# ---------------------------------------------------------------------------
# SessionRecord serialization round-trip
# ---------------------------------------------------------------------------

class TestSerializationRoundTrip:
    def test_asdict_json_round_trip(self):
        record = evaluate_session(
            run_date=RUN_DATE,
            watchlist=WATCHLIST,
            ticker_scores=_make_scores(
                WATCHLIST,
                buy_signal={"AAPL", "MSFT", "GOOG"},
                high_rank={"AAPL", "MSFT"},
            ),
            panel_candidates=["AAPL", "MSFT", "AMZN"],
            panel_blocked={"GOOG": "regime_block", "META": "veto", "NVDA": "veto",
                           "TSLA": "veto", "NFLX": "veto"},
            min_model_score=MIN_MODEL_SCORE,
            bypass_ticker_gate=True,
            regime="BULL_CALM",
        )
        d = asdict(record)
        text = json.dumps(d, default=str)
        parsed = json.loads(text)
        assert parsed["schema_version"] == SCHEMA_VERSION
        assert parsed["run_date"] == "2026-07-05"
        assert parsed["regime"] == "BULL_CALM"
        # AAPL + MSFT have buy signal AND high rank -> tournament admits
        assert "AAPL" in parsed["tournament_admitted"]
        assert "MSFT" in parsed["tournament_admitted"]
        # GOOG has buy signal but low rank -> tournament rejects
        assert "GOOG" in parsed["tournament_rejected"]
