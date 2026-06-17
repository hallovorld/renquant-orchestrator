"""Tests for ``decision_pnl_attribution`` (#108 III.6) — decision P&L.

Fully hermetic: pure-DataFrame cases for the attribution logic, plus a small
in-memory sqlite DB that mimics ``candidate_scores`` / ``ticker_forward_returns``
for the loader. Never touches the live run DB.
"""
from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from renquant_orchestrator.decision_pnl_attribution import (
    PASSED_NOT_SELECTED,
    SELECTED,
    attribute_by_class,
    classify_decisions,
    connect,
    join_decisions_to_returns,
    load_decision_outcomes,
    return_columns,
    selection_edge,
)


def _decisions() -> pd.DataFrame:
    """Four decisions on 2026-06-11: one selected, two vetoed (kelly + bear),
    one passed-but-not-selected."""
    return pd.DataFrame(
        {
            "run_id": ["2026-06-11-live-abc"] * 4,
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "selected": [1, 0, 0, 0],
            "blocked_by": [None, "kelly:capped_zero", "bear_override:5d_vol", None],
            "rank_score": [0.9, 0.4, 0.3, 0.5],
        }
    )


def _forward_returns() -> pd.DataFrame:
    """Realized 5-day forward returns; selected name wins, vetoed names lose."""
    return pd.DataFrame(
        {
            "as_of_date": ["2026-06-11"] * 4,
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "fwd_ret_5d": [0.030, -0.020, -0.015, 0.005],
        }
    )


# ---------------------------------------------------------------------------
# column discovery
# ---------------------------------------------------------------------------
def test_return_columns_picks_fwd_and_ret_not_ticker():
    cols = ["as_of_date", "ticker", "fwd_ret_5d", "fwd_ret_1d", "realized_return"]
    assert return_columns(cols) == ["fwd_ret_5d", "fwd_ret_1d", "realized_return"]
    # 'ticker' contains no return signal and must never be treated as a metric
    assert "ticker" not in return_columns(["ticker", "fwd_ret_5d"])


# ---------------------------------------------------------------------------
# join
# ---------------------------------------------------------------------------
def test_join_derives_date_and_inner_joins():
    joined = join_decisions_to_returns(_decisions(), _forward_returns())
    assert len(joined) == 4
    assert (joined["date"] == "2026-06-11").all()
    assert set(joined["ticker"]) == {"AAA", "BBB", "CCC", "DDD"}
    assert "fwd_ret_5d" in joined.columns


def test_join_is_inner_drops_unmatched():
    fr = _forward_returns().iloc[:2]  # only AAA, BBB have realized returns
    joined = join_decisions_to_returns(_decisions(), fr)
    assert set(joined["ticker"]) == {"AAA", "BBB"}


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------
def test_classify_labels_each_class():
    out = classify_decisions(join_decisions_to_returns(_decisions(), _forward_returns()))
    by_ticker = dict(zip(out["ticker"], out["cls"]))
    assert by_ticker["AAA"] == SELECTED
    assert by_ticker["BBB"] == "veto:kelly"          # rolled up from kelly:capped_zero
    assert by_ticker["CCC"] == "veto:bear_override"
    assert by_ticker["DDD"] == PASSED_NOT_SELECTED


def test_classify_rolls_up_veto_reason_head():
    df = pd.DataFrame(
        {
            "selected": [0, 0],
            "blocked_by": ["kelly:capped_zero", "kelly:nan_score"],
        }
    )
    assert list(classify_decisions(df)["cls"]) == ["veto:kelly", "veto:kelly"]


def test_classify_does_not_mutate_input():
    df = join_decisions_to_returns(_decisions(), _forward_returns())
    classify_decisions(df)
    assert "cls" not in df.columns


# ---------------------------------------------------------------------------
# attribution
# ---------------------------------------------------------------------------
def test_attribute_by_class_counts_and_means():
    joined = join_decisions_to_returns(_decisions(), _forward_returns())
    agg = attribute_by_class(joined, "fwd_ret_5d")
    assert set(agg.index) == {SELECTED, "veto:kelly", "veto:bear_override",
                              PASSED_NOT_SELECTED}
    assert agg.loc[SELECTED, "count"] == 1
    assert agg.loc[SELECTED, "mean"] == pytest.approx(0.030)
    assert agg.loc["veto:kelly", "mean"] == pytest.approx(-0.020)


def test_attribute_drops_nan_returns():
    joined = join_decisions_to_returns(_decisions(), _forward_returns())
    joined.loc[joined["ticker"] == "AAA", "fwd_ret_5d"] = float("nan")
    agg = attribute_by_class(joined, "fwd_ret_5d")
    # SELECTED row had the only AAA outcome → drops out entirely
    assert SELECTED not in agg.index


def test_attribute_classifies_if_missing_cls_column():
    joined = join_decisions_to_returns(_decisions(), _forward_returns())
    assert "cls" not in joined.columns
    agg = attribute_by_class(joined, "fwd_ret_5d")  # must not raise
    assert agg.loc[SELECTED, "count"] == 1


# ---------------------------------------------------------------------------
# headline selection edge
# ---------------------------------------------------------------------------
def test_selection_edge_positive_when_gates_help():
    joined = join_decisions_to_returns(_decisions(), _forward_returns())
    edge = selection_edge(joined, "fwd_ret_5d")
    assert edge["n_selected"] == 1
    assert edge["n_vetoed"] == 2
    assert edge["selected_mean"] == pytest.approx(0.030)
    assert edge["vetoed_mean"] == pytest.approx((-0.020 + -0.015) / 2)
    # selected name beat the average vetoed name → positive edge
    assert edge["edge"] > 0


def test_selection_edge_nan_when_no_vetoes():
    df = pd.DataFrame(
        {
            "selected": [1, 1],
            "blocked_by": [None, None],
            "fwd_ret_5d": [0.01, 0.02],
        }
    )
    edge = selection_edge(df, "fwd_ret_5d")
    assert edge["n_vetoed"] == 0
    assert pd.isna(edge["vetoed_mean"])
    assert pd.isna(edge["edge"])


# ---------------------------------------------------------------------------
# sqlite loader (hermetic in-memory DB)
# ---------------------------------------------------------------------------
@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    _decisions().to_sql("candidate_scores", conn, index=False)
    _forward_returns().to_sql("ticker_forward_returns", conn, index=False)
    yield conn
    conn.close()


def test_load_decision_outcomes_end_to_end(db):
    joined, ret_col = load_decision_outcomes(db)
    assert ret_col == "fwd_ret_5d"
    assert len(joined) == 4
    edge = selection_edge(joined, ret_col)
    assert edge["n_selected"] == 1 and edge["n_vetoed"] == 2
    assert edge["edge"] > 0


def test_load_skips_null_rank_score(db):
    # a NULL rank_score row must be excluded by the loader's WHERE clause
    db.execute(
        "INSERT INTO candidate_scores (run_id, ticker, selected, blocked_by, "
        "rank_score) VALUES ('2026-06-11-live-abc', 'EEE', 0, NULL, NULL)"
    )
    db.commit()
    joined, _ = load_decision_outcomes(db)
    assert "EEE" not in set(joined["ticker"])


def test_load_raises_when_no_return_column():
    conn = sqlite3.connect(":memory:")
    _decisions().to_sql("candidate_scores", conn, index=False)
    pd.DataFrame({"as_of_date": ["2026-06-11"], "ticker": ["AAA"]}).to_sql(
        "ticker_forward_returns", conn, index=False
    )
    with pytest.raises(ValueError, match="no forward-return column"):
        load_decision_outcomes(conn)
    conn.close()


def test_connect_opens_read_only(tmp_path):
    """``connect`` must open the DB read-only so attribution can never write to
    the live run DB."""
    path = tmp_path / "runs.db"
    seed = sqlite3.connect(path)
    _decisions().to_sql("candidate_scores", seed, index=False)
    _forward_returns().to_sql("ticker_forward_returns", seed, index=False)
    seed.close()

    ro = connect(path)
    joined, ret_col = load_decision_outcomes(ro)
    assert len(joined) == 4
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM candidate_scores")
    ro.close()
