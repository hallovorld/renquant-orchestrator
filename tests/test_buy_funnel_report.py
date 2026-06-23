"""Tests for the read-only buy-funnel diagnostic parser."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "buy_funnel_report.py"
_spec = importlib.util.spec_from_file_location("funnel", _SCRIPT)
funnel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(funnel)

# A real-shaped 2026-05-30 run: P-WF-GATE blocked it; VetoWeakBuys was the big in-pipeline cut.
BLOCKED_RUN = """
2026-05-30 16:12:01 [INFO] kernel.preflight: preflight ✗ P-WF-GATE  [HARD] active panel artifact carries failed WF gate
2026-05-30 16:12:22 [INFO] kernel.pipeline: Phase 2b (buy scan): 102 candidates from 107 tickers
2026-05-30 16:12:22 [INFO] kernel.pipeline.risk_gates: RealizedVolGateTask: dropped 11/102 candidates over 60% vol cap
2026-05-30 16:12:24 [INFO] kernel.panel_pipeline.scoring: VetoWeakBuysTask: dropped 81 candidate(s) below rank_score floor=0.526
2026-05-30 16:12:24 [INFO] kernel.panel_pipeline.scoring: ApplyKellySizingTask: fractional=0.50 max_conc=0.35  cands=10 non-zero (avg=4.7%)
2026-05-30 16:12:24 [INFO] kernel.pipeline.ranking: SortCandidatesTask: 10 ranked
"""

# A healthy run: not blocked; Kelly mu<edge is the dominant cut.
HEALTHY_RUN = """
Phase 2b (buy scan): 81 candidates from 90 tickers
RealizedVolGateTask: dropped 12/81 candidates over 60% vol cap
ApplyKellySizingTask: fractional=0.50 max_conc=0.35  cands=7 non-zero (avg=4.4%)
mu_le_min_edge=62
SortCandidatesTask: 69 ranked
"""


def test_blocked_run_binding_is_wf_gate():
    f = funnel.parse_funnel(BLOCKED_RUN)
    assert f["panel_candidates"] == 102
    assert f["after_vol_gate"] == 91
    assert f["veto_weak_dropped"] == 81
    assert f["after_veto_weak"] == 10
    assert f["kelly_sized"] == 10
    assert f["wf_gate_blocked"] is True
    assert f["actual_buys"] == 0  # HARD block -> 0 regardless of 10 sized candidates
    assert f["binding_constraint"].startswith("P-WF-GATE")


def test_healthy_run_binding_is_kelly_mu():
    f = funnel.parse_funnel(HEALTHY_RUN)
    assert f["panel_candidates"] == 81
    assert f["wf_gate_blocked"] is False
    assert f["actual_buys"] == 7
    assert f["kelly_mu_below_edge"] == 62
    assert f["binding_constraint"] == "Kelly mu<edge"


def test_missing_stages_degrade_gracefully():
    f = funnel.parse_funnel("nothing useful here")
    assert f["panel_candidates"] is None
    assert f["wf_gate_blocked"] is False
    assert f["binding_constraint"] == "unknown (incomplete log)"


def test_last_match_wins_on_retried_run():
    # a log with two buy-scan phases (retry); the LAST should win
    text = "Phase 2b (buy scan): 50 candidates\nPhase 2b (buy scan): 99 candidates\n"
    assert funnel.parse_funnel(text)["panel_candidates"] == 99


def test_report_aggregates_binding_frequency(tmp_path):
    (tmp_path / "a.log").write_text(BLOCKED_RUN)
    (tmp_path / "b.log").write_text(HEALTHY_RUN)
    res = funnel.report(tmp_path, last=10)
    assert res["n_runs"] == 2
    freq = res["binding_constraint_frequency"]
    assert any(k.startswith("P-WF-GATE") for k in freq)
    assert "Kelly mu<edge" in freq
