"""Decision-level P&L attribution (#108 III.6, self-discovered gap #6).

The complement to the decision ledger (``gate_registry`` + ``decision_ledger``):
the ledger records *what* each gate decided; this module measures *what that
decision earned or cost*. It answers a question no one could answer before —
"what did each GATE/VETO decision actually pay?" — by joining the historical
``candidate_scores`` rows (selected vs blocked, with the ``blocked_by`` reason)
to realized forward returns from ``ticker_forward_returns``.

Design (matches the prior graduations — artifact_resolver / gate_registry /
config_schema): pure functions over DataFrames plus a thin sqlite reader whose
DB path is **parameterized** (never hard-codes the live ``runs.alpaca.db``). The
attribution logic takes plain DataFrames so it is testable without any DB, and
the loader is read-only.

Pipeline
--------
1. ``load_decision_outcomes(conn)`` reads candidate decisions + forward returns
   and joins them on (date, ticker) into one decision-outcome frame.
2. ``classify_decisions(df)`` labels each row with a decision class
   (``SELECTED`` / ``veto:<reason>`` / ``passed-not-selected``).
3. ``attribute_by_class(df, ret_col)`` aggregates realized outcome per class.
4. ``selection_edge(df, ret_col)`` is the headline: mean(SELECTED) −
   mean(VETOED), i.e. the per-decision edge the selection logic captured.

Production wiring (future): once orders carry a ``decision_id`` and realized
P&L is written back on close, this stops being a backfilled join and becomes a
continuous, per-gate, queryable attribution table.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

# The live run DB. Exposed only as a default for ad-hoc/CLI use — every public
# function takes the path/connection explicitly so nothing is hard-coded into
# the logic and tests never touch live state.
DEFAULT_DB = Path.home() / "git/github/RenQuant/data/runs.alpaca.db"

# Class labels (kept as constants so callers/tests don't string-match by hand).
SELECTED = "SELECTED"
PASSED_NOT_SELECTED = "passed-not-selected"
VETO_PREFIX = "veto:"


def _first_date_column(columns: list[str]) -> str:
    """Forward-returns tables name their key column variously (``date``,
    ``as_of_date``, ...). Pick the first column whose name mentions 'date'."""
    for col in columns:
        if "date" in col.lower():
            return col
    raise ValueError(f"no date-like column found in forward returns: {columns}")


def return_columns(columns: list[str]) -> list[str]:
    """Forward-return metric columns: ``fwd_*`` horizons or any ``*ret*`` column.
    The ticker join key (``ticker``) and date column are never returns."""
    return [
        c for c in columns
        if (c.startswith("fwd_") or "ret" in c.lower()) and c.lower() != "ticker"
    ]


def join_decisions_to_returns(
    decisions: pd.DataFrame,
    forward_returns: pd.DataFrame,
) -> pd.DataFrame:
    """Join candidate decisions to realized forward returns on (date, ticker).

    ``decisions`` carries ``run_id`` (whose first 10 chars are the ISO date),
    ``ticker``, ``selected``, ``blocked_by``, ``rank_score``. ``forward_returns``
    carries a date-like column, ``ticker``, and one or more return columns. The
    result is an inner join with a derived ``date`` column; no rows are dropped
    for NaN returns here (the caller decides per metric).
    """
    date_col = _first_date_column(list(forward_returns.columns))
    dec = decisions.copy()
    dec["date"] = dec["run_id"].str.slice(0, 10)
    return dec.merge(
        forward_returns,
        left_on=["date", "ticker"],
        right_on=[date_col, "ticker"],
        how="inner",
    )


def load_decision_outcomes(
    conn: sqlite3.Connection,
) -> tuple[pd.DataFrame, str]:
    """Read decisions + forward returns from an (already-open) sqlite connection
    and return ``(joined_frame, return_column)``. Read-only.

    The connection is passed in so the live DB path stays the *caller's* choice
    (use :func:`connect` or hand in an in-memory connection in tests). The chosen
    return column is the first forward-return metric discovered.
    """
    decisions = pd.read_sql(
        "SELECT run_id, ticker, selected, blocked_by, rank_score "
        "FROM candidate_scores WHERE rank_score IS NOT NULL",
        conn,
    )
    forward_returns = pd.read_sql("SELECT * FROM ticker_forward_returns", conn)
    ret_cols = return_columns(list(forward_returns.columns))
    if not ret_cols:
        raise ValueError(
            f"no forward-return column in ticker_forward_returns: "
            f"{list(forward_returns.columns)}"
        )
    joined = join_decisions_to_returns(decisions, forward_returns)
    return joined, ret_cols[0]


def _classify_row(selected: object, blocked_by: object) -> str:
    """SELECTED if chosen; else ``veto:<reason-head>`` when a block reason is
    present; else ``passed-not-selected``. The veto reason is split on ``:`` so
    ``"kelly:capped_zero"`` and ``"kelly:nan"`` both roll up to ``veto:kelly``."""
    if bool(selected):
        return SELECTED
    if blocked_by is not None and not (isinstance(blocked_by, float) and pd.isna(blocked_by)):
        text = str(blocked_by)
        if text and text.lower() != "nan":
            return VETO_PREFIX + text.split(":")[0]
    return PASSED_NOT_SELECTED


def classify_decisions(df: pd.DataFrame) -> pd.DataFrame:
    """Add a ``cls`` column labelling each decision (SELECTED / veto:* /
    passed-not-selected). Returns a copy; the input frame is not mutated."""
    out = df.copy()
    out["cls"] = [
        _classify_row(s, b) for s, b in zip(out["selected"], out["blocked_by"])
    ]
    return out


def attribute_by_class(df: pd.DataFrame, ret_col: str) -> pd.DataFrame:
    """Realized-outcome attribution per decision class.

    Drops rows with a NaN return for ``ret_col``, then groups by ``cls`` and
    reports ``count``/``mean``/``median``, ordered by population (largest first).
    ``df`` must already carry a ``cls`` column (call :func:`classify_decisions`).
    """
    if "cls" not in df.columns:
        df = classify_decisions(df)
    scored = df.dropna(subset=[ret_col])
    agg = (
        scored.groupby("cls")[ret_col]
        .agg(["count", "mean", "median"])
        .sort_values("count", ascending=False)
    )
    return agg


def selection_edge(df: pd.DataFrame, ret_col: str) -> dict:
    """Headline metric: mean realized return of SELECTED minus mean of VETOED.

    Returns a dict with ``selected_mean``, ``vetoed_mean``, ``edge`` (the
    difference), and the two sample sizes. A positive ``edge`` means the gates
    kept the better names and blocked the worse ones — the whole point of the
    attribution. NaN means/edge when a side is empty.
    """
    if "cls" not in df.columns:
        df = classify_decisions(df)
    scored = df.dropna(subset=[ret_col])
    sel = scored.loc[scored["cls"] == SELECTED, ret_col]
    vetoed = scored.loc[scored["cls"].str.startswith(VETO_PREFIX), ret_col]
    sel_mean = float(sel.mean()) if len(sel) else float("nan")
    veto_mean = float(vetoed.mean()) if len(vetoed) else float("nan")
    return {
        "selected_mean": sel_mean,
        "vetoed_mean": veto_mean,
        "edge": sel_mean - veto_mean,
        "n_selected": int(len(sel)),
        "n_vetoed": int(len(vetoed)),
    }


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the run DB **read-only** for attribution queries. Defaults to
    :data:`DEFAULT_DB`; pass an explicit path (or an in-memory DB) in tests.

    Uses a ``file:...?mode=ro`` URI so this module can never write to the live
    run DB — attribution is a pure read over recorded decisions and outcomes.
    """
    if db_path is None:
        db_path = DEFAULT_DB
    uri = f"file:{Path(db_path)}?mode=ro"
    return sqlite3.connect(uri, uri=True)
