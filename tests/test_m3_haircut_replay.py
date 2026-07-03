"""Deterministic fixture tests for scripts/m3_haircut_replay.py (M3 study).

In-memory SQLite only - no dependency on the real runs.alpaca.db.
"""
from __future__ import annotations

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import m3_haircut_replay as m3  # noqa: E402


def _mkdb() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript(
        """
        CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT,
            regime TEXT, created_at TIMESTAMP);
        CREATE TABLE candidate_scores (
            run_id TEXT, ticker TEXT, role TEXT, mu REAL,
            model_type TEXT, blocked_by TEXT);
        CREATE TABLE ticker_forward_returns (
            as_of_date DATE, ticker TEXT, fwd_5d REAL, fwd_10d REAL,
            fwd_20d REAL);
        """
    )
    return con


def _add_run(con, run_id, run_date, regime="BULL_CALM", created="2026-01-01 10:00:00",
             n_cands=None, run_type="live"):
    con.execute(
        "INSERT INTO pipeline_runs VALUES (?,?,?,?,?)",
        (run_id, run_date, run_type, regime, created),
    )
    n = m3.MIN_FULL_RUN_CANDIDATES if n_cands is None else n_cands
    for i in range(n):
        con.execute(
            "INSERT INTO candidate_scores VALUES (?,?,?,?,?,?)",
            (run_id, f"FILL{i}", "candidate", 0.0, None, None),
        )


# ------------------------------------------------------- canonical selection
def test_canonical_selects_latest_full_run_per_date():
    con = _mkdb()
    _add_run(con, "r-early", "2026-06-01", created="2026-06-01 09:00:00")
    _add_run(con, "r-late", "2026-06-01", created="2026-06-01 16:00:00")
    _add_run(con, "r-thin", "2026-06-02", n_cands=5)          # sub-threshold
    _add_run(con, "r-sim", "2026-06-03", run_type="sim")       # not live
    runs = m3.canonical_daily_runs(con)
    assert [r["run_id"] for r in runs] == ["r-late"]


# --------------------------------------------------------------- era + SE(a)
def test_classify_era_buckets():
    assert m3.classify_era(None) == "pre_tournament_null"
    assert m3.classify_era("") == "pre_tournament_null"
    for t in ("Classification", "Manual", "QLearning", "XGBoost"):
        assert m3.classify_era(t) == "legacy_tournament"
    assert m3.classify_era("panel_ltr_xgboost") == "panel_ltr_xgboost"


def test_trailing_se_requires_min_obs():
    assert m3.trailing_se([0.03]) is None
    assert m3.trailing_se([0.03, 0.04]) is None
    assert m3.trailing_se([0.03, 0.04, 0.05]) == pytest.approx(0.01)


def test_attach_se_never_mixes_scorer_eras():
    # 3 obs in era A then 2 in era B: the era-B row must NOT reach MIN_OBS
    # by borrowing era-A history.
    cands = []
    for i, (d, era_mt) in enumerate(
        [("2026-06-01", None), ("2026-06-02", None), ("2026-06-03", None),
         ("2026-06-04", "panel_ltr_xgboost"), ("2026-06-05", "panel_ltr_xgboost")]
    ):
        cands.append({
            "run_date": d, "run_id": f"r{i}", "regime": "BULL_CALM",
            "ticker": "AAA", "mu": 0.03 + 0.01 * i,
            "era": m3.classify_era(era_mt), "blocked_by": None,
        })
    m3.attach_se(cands)
    assert cands[2]["se"] is not None and cands[2]["n_obs"] == 3
    assert cands[3]["se"] is None and cands[3]["n_obs"] == 1   # era reset
    assert cands[4]["se"] is None and cands[4]["n_obs"] == 2


def test_attach_se_window_caps_at_window_obs():
    cands = [
        {"run_date": f"2026-06-{d:02d}", "run_id": f"r{d}", "regime": "B",
         "ticker": "AAA", "mu": 0.01 * d, "era": "e", "blocked_by": None}
        for d in range(1, 15)
    ]
    m3.attach_se(cands)
    assert cands[-1]["n_obs"] == m3.WINDOW_OBS


# ------------------------------------------------------------ rule + outcome
def test_haircut_admit_boundary():
    # mu - k*se must be STRICTLY above the floor (binary-exact fixture values)
    assert m3.haircut_admits(0.5, 0.25, 1.0, floor=0.25) is False   # == floor
    assert m3.haircut_admits(0.5, 0.25, 0.5, floor=0.25) is True    # 0.375
    assert m3.haircut_admits(0.5625, 0.25, 1.0, floor=0.25) is True # 0.3125
    assert m3.haircut_admits(0.02, 0.001, 0.5) is False   # below default floor


def test_winner_threshold_is_cost_proxy():
    assert m3.is_winner(0.00111) is True
    assert m3.is_winner(0.0011) is False
    assert m3.is_winner(-0.02) is False


def test_effective_outcome_date_maps_weekend_to_prior_trading_day():
    con = _mkdb()
    con.execute(
        "INSERT INTO ticker_forward_returns VALUES ('2026-05-08','SPY',0,0,0)")
    cache = {}
    assert m3.effective_outcome_date(con, "2026-05-09", cache) == "2026-05-08"
    # beyond MAX_EFFDATE_LAG_DAYS -> unresolvable
    assert m3.effective_outcome_date(con, "2026-05-20", cache) is None


# ------------------------------------------------------------------- replay
def _universe_fixture():
    """4 floor-clearing SE-defined names on one date: two stable (kept), one
    high-dispersion winner and one high-dispersion loser (both removed at
    k=1.0)."""
    base = {"run_date": "2026-06-01", "run_id": "r", "regime": "BULL_CALM",
            "era": "e", "blocked_by": None}
    rows = [
        dict(base, ticker="KEEPW", mu=0.05, se=0.001, excess_fwd_20d=0.02),
        dict(base, ticker="KEEPL", mu=0.05, se=0.001, excess_fwd_20d=-0.02),
        dict(base, ticker="CUTW", mu=0.04, se=0.02, excess_fwd_20d=0.10),
        dict(base, ticker="CUTL", mu=0.04, se=0.02, excess_fwd_20d=-0.10),
        # non-clearing and unresolved rows must be excluded from the universe
        dict(base, ticker="BELOW", mu=0.01, se=0.001, excess_fwd_20d=0.5),
        dict(base, ticker="NOFWD", mu=0.06, se=0.001, excess_fwd_20d=None),
    ]
    for r in rows:
        r.setdefault("excess_fwd_10d", None)
        r.setdefault("excess_fwd_5d", None)
    return rows


def test_replay_counts_winners_and_losers_removed():
    r = m3.replay(_universe_fixture(), "fwd_20d", 1.0)
    assert r["current"]["n"] == 4
    assert r["haircut"]["n"] == 2
    assert r["winners_removed"] == 1 and r["losers_removed"] == 1
    assert r["expectancy_delta_haircut_minus_current"] == pytest.approx(0.0)
    assert set(r["per_regime"]) == {"BULL_CALM"}


def test_passthrough_keeps_undefined_se_names():
    rows = _universe_fixture()
    rows.append({
        "run_date": "2026-06-01", "run_id": "r", "regime": "BULL_CALM",
        "era": "e", "blocked_by": None, "ticker": "FRESH", "mu": 0.035,
        "se": None, "excess_fwd_20d": 0.01,
        "excess_fwd_10d": None, "excess_fwd_5d": None,
    })
    s = m3.passthrough_sensitivity(rows, "fwd_20d", 1.0)
    assert s["n_undefined_se_passed"] == 1
    assert s["current"]["n"] == 5          # NOFWD excluded, FRESH included
    assert s["haircut"]["n"] == 3          # KEEPW, KEEPL, FRESH


def test_block_bootstrap_flags_degenerate_when_block_exceeds_dates():
    rows = _universe_fixture()
    out = m3.block_bootstrap_delta(rows, "fwd_20d", 1.0, block_len=13,
                                   n_boot=50, seed=1)
    assert out["degenerate"] is True
    assert out["n_dates"] == 1
    lo, hi = out["ci95"]
    assert lo == pytest.approx(hi)         # zero-width CI, honestly flagged


def test_thin_margin_band():
    assert m3.is_thin_margin(0.031) is True
    assert m3.is_thin_margin(0.0375) is False
    assert m3.is_thin_margin(0.03) is False
