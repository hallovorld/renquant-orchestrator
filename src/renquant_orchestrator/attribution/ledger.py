"""Unified per-decision read model for attribution (107 sprint D3).

Joins the run DB's ``candidate_scores`` (mu / rank / blocked_by per run),
``trades`` (entry/exit events), ``pipeline_runs`` (date, run_type, regime,
portfolio value) and ``ticker_forward_returns`` (reference closes + forward
returns, own and SPY) into per-DECISION records, then pairs entries to exits
into round trips for :mod:`renquant_orchestrator.attribution.decompose`.

Data-contract facts this module encodes (measured on the live DB, 2026-07-03;
see the design note ``doc/design/2026-07-03-attribution-engine.md``):

- **Fill-confirmation censoring (#253).** The live pipeline stopped writing
  ``action='buy'`` fill-confirmation rows after 2026-05-22; entries since
  2026-06-09 are ``action='buy_pending'`` whose ``price`` is a *submit-time
  reference, never a fill* (the order can be canceled pre-open — OXY
  2026-07-02 was). The same applies to ``sell_pending`` exits since 06-02.
  Such rows are represented with ``entry_fill_confirmed=False`` /
  ``exit_fill_confirmed=False`` and their reference price kept in a separate
  ``*_px_reference`` field — it is NEVER copied into the fill-price field.
- **Reference price = decision-session close.** ``ticker_forward_returns``
  persists only ``close_price``; open/VWAP benchmark prices are not persisted
  anywhere in this DB, so the TIMING leg's reference is the decision-session
  close (``ref_px_kind='close'``). Weekend/holiday-dated live rows exist via
  the S5 as-of backfill (backtesting#60 session_resolution semantics), so the
  exact (run_date, ticker) join is the session-correct one.
- **Duplicate event rows.** Live runs re-record the same broker event across
  every same-day run_id (e.g. the TSM 2026-04-23 fill appears under two
  run_ids with identical price/shares); events are deduplicated on
  (ticker, date, action, price, shares).
- **Cross-day re-records.** The early live era also re-records the SAME fill
  on subsequent days (e.g. one NET fill at 207.07 echoed over 2026-04-25/26/27,
  with share counts varying 2/3/39 across echoes). Same-price runs of events
  with no opposite-side event in between are collapsed to the first-dated row;
  when the echoes DISAGREE on share count the realized notional is ambiguous
  and is explicitly censored (``shares_conflict=True``) — never guessed.
- **Round-trip matching is a live-stream tool.** ``run_type='sim'`` commingles
  thousands of parallel simulated streams (37,647 sim runs), so FIFO pairing
  across them is unreliable; class-level sim attribution stays with
  ``decision_pnl_attribution`` (#145). ``build_round_trips`` therefore
  defaults to the live stream and refuses sim unless explicitly forced.

Everything here is read-only over the run DB (``mode=ro`` URI).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from renquant_orchestrator.runtime_paths import default_data_root

# The live run DB — a default for ad-hoc/CLI use only; every public function
# takes the connection/path explicitly (same convention as
# decision_pnl_attribution / decision_ledger).
DEFAULT_DB = default_data_root() / "data" / "runs.alpaca.db"

BENCHMARK_TICKER = "SPY"
REF_PX_KIND = "close"  # the only persisted reference price (see module doc)

ENTRY_ACTIONS_CONFIRMED = ("buy",)
ENTRY_ACTIONS_PENDING = ("buy_pending",)
EXIT_ACTIONS_CONFIRMED = ("sell",)
EXIT_ACTIONS_PENDING = ("sell_pending",)

FWD_COLS = ("fwd_1d", "fwd_5d", "fwd_10d", "fwd_20d", "fwd_60d")


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the run DB **read-only** (``file:...?mode=ro`` URI): the
    attribution engine can never write to the live run DB by construction."""
    if db_path is None:
        db_path = DEFAULT_DB
    uri = f"file:{Path(db_path)}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _event_date(df: pd.DataFrame) -> pd.Series:
    """Event date: ``trade_date`` when stamped, else the run_id's leading ISO
    date (run_ids are ``YYYY-MM-DD-<type>-<hash>``; #145 uses the same rule).
    Recorded data only — no imputation."""
    fallback = df["run_id"].str.slice(0, 10)
    if "trade_date" not in df.columns:
        return fallback
    td = df["trade_date"].astype("string")
    return td.fillna(fallback).astype(str)


def _read_events(conn: sqlite3.Connection, actions: tuple[str, ...], run_type: str) -> pd.DataFrame:
    placeholders = ",".join("?" for _ in actions)
    q = f"""
        SELECT t.run_id, t.ticker, t.action, t.shares, t.price, t.invest,
               t.target_pct, t.exit_reason, t.pnl_pct, t.hold_days,
               t.trade_date, t.order_type, t.kelly_target_pct AS trade_kelly_target_pct,
               pr.run_date, pr.run_type, pr.regime, pr.portfolio_value
        FROM trades t
        JOIN pipeline_runs pr ON pr.run_id = t.run_id
        WHERE t.action IN ({placeholders}) AND pr.run_type = ?
    """
    df = pd.read_sql(q, conn, params=(*actions, run_type))
    if df.empty:
        df["date"] = pd.Series(dtype=str)
        return df
    df["date"] = _event_date(df)
    return df


def _dedupe_events(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse the same broker event re-recorded across same-day run_ids.
    Key = (ticker, date, action, price, shares); keeps the first run_id and
    counts the multiplicity in ``n_duplicate_rows``."""
    if df.empty:
        df["n_duplicate_rows"] = pd.Series(dtype=int)
        return df
    key = ["ticker", "date", "action", "price", "shares"]
    df = df.sort_values(["date", "run_id"]).copy()
    df["n_duplicate_rows"] = df.groupby(key, dropna=False)["run_id"].transform("size")
    return df.drop_duplicates(subset=key, keep="first").reset_index(drop=True)


def _collapse_re_records(
    df: pd.DataFrame,
    opposite_dates_by_ticker: dict[str, set[str]],
) -> pd.DataFrame:
    """Collapse cross-day re-records of one broker event (see module doc).

    A group = same (ticker, action, price) at distinct dates. It is collapsed
    to its first-dated row ONLY when no opposite-side event (an exit for entry
    groups, an entry for exit groups) falls strictly inside the group's date
    span — a genuine re-entry at an identical price after a round trip stays
    separate. When the echoes disagree on share count, ``shares`` (and any
    realized notional derived from it) is censored via ``shares_conflict``.
    """
    for col, default in (("n_re_record_days", 1), ("shares_conflict", False)):
        df[col] = default
    if df.empty:
        return df
    df = df.sort_values(["date", "run_id"]).reset_index(drop=True)
    out_rows: list[pd.Series] = []
    for (ticker, _action, price), g in df.groupby(
        ["ticker", "action", "price"], dropna=False, sort=False
    ):
        if len(g) == 1 or pd.isna(price):
            out_rows.extend(row for _, row in g.iterrows())
            continue
        dates = sorted(g["date"])
        first, last = dates[0], dates[-1]
        opposite = opposite_dates_by_ticker.get(ticker, set())
        if any(first < d <= last for d in opposite):
            # an opposite-side event inside the span: genuine separate events
            out_rows.extend(row for _, row in g.iterrows())
            continue
        row = g.iloc[0].copy()
        row["n_re_record_days"] = int(g["date"].nunique())
        row["n_duplicate_rows"] = int(g["n_duplicate_rows"].sum())
        if g["shares"].nunique(dropna=False) > 1:
            row["shares_conflict"] = True
            row["shares"] = float("nan")
            for derived in ("invest", "realized_notional"):
                if derived in row.index:
                    row[derived] = float("nan")
        out_rows.append(row)
    return pd.DataFrame(out_rows).sort_values(["date", "run_id"]).reset_index(drop=True)


def _attach_decision_fields(conn: sqlite3.Connection, entries: pd.DataFrame) -> pd.DataFrame:
    """Join candidate_scores decision fields (mu / rank / blocked_by /
    kelly_target_pct / selected) onto entry events by (run_id, ticker)."""
    if entries.empty:
        for c in ("mu", "sigma", "rank_score", "blocked_by", "selected", "kelly_target_pct"):
            entries[c] = pd.Series(dtype=float)
        return entries
    cs = pd.read_sql(
        "SELECT run_id, ticker, mu, sigma, rank_score, blocked_by, selected,"
        " kelly_target_pct FROM candidate_scores",
        conn,
    )
    merged = entries.merge(cs, on=["run_id", "ticker"], how="left")
    # trades carries its own kelly_target_pct copy on newer rows — recorded
    # fallback (not imputation) when candidate_scores lacks the column value.
    merged["kelly_target_pct"] = pd.to_numeric(
        merged["kelly_target_pct"], errors="coerce"
    ).fillna(pd.to_numeric(merged["trade_kelly_target_pct"], errors="coerce"))
    return merged


def _reference_prices(conn: sqlite3.Connection) -> pd.DataFrame:
    """(as_of_date, ticker) -> decision-session close + forward returns."""
    cols = ", ".join(FWD_COLS)
    return pd.read_sql(
        f"SELECT as_of_date, ticker, close_price, {cols} FROM ticker_forward_returns",
        conn,
    )


def _attach_reference(df: pd.DataFrame, refs: pd.DataFrame, when: str) -> pd.DataFrame:
    """Attach own + SPY reference closes (and, for entries, forward returns)
    at the event's decision date. Exact (date, ticker) join — the S5 as-of
    backfill already gives weekend/holiday run_dates their session row."""
    own = refs.rename(columns={"as_of_date": "date", "close_price": f"ref_{when}_px"})
    spy = refs.loc[refs["ticker"] == BENCHMARK_TICKER, ["as_of_date", "close_price"]].rename(
        columns={"as_of_date": "date", "close_price": f"spy_{when}_px"}
    )
    keep = ["date", "ticker", f"ref_{when}_px"] + (list(FWD_COLS) if when == "entry" else [])
    df = df.merge(own[keep], on=["date", "ticker"], how="left")
    return df.merge(spy, on="date", how="left")


def load_decision_ledger(
    conn: sqlite3.Connection,
    run_type: str = "live",
) -> pd.DataFrame:
    """The per-decision read model: one row per deduplicated ENTRY decision
    event (confirmed fill or pending submission), carrying:

    decision_id, date, ticker, action, mu, sigma, rank_score, blocked_by,
    regime, intended_notional (kelly_target_pct x portfolio_value),
    realized_notional (shares x fill price — only when the fill is
    confirmed), entry_px (confirmed fills only), entry_px_reference
    (submit-time reference, pending rows), entry_fill_confirmed,
    ref_entry_px / spy_entry_px (decision-session closes), fwd_* forward
    returns and rel_fwd_* benchmark-relative forward returns.

    Censored quantities are left as NaN/None and flagged via the
    ``entry_fill_confirmed`` boolean — never imputed (#253).
    """
    entries = _read_events(
        conn, ENTRY_ACTIONS_CONFIRMED + ENTRY_ACTIONS_PENDING, run_type
    )
    # Fill-confirmation is derived from the recorded action kind: 'buy' rows
    # are confirmations, 'buy_pending' rows are submissions only (#253).
    entries["entry_fill_confirmed"] = entries["action"].isin(ENTRY_ACTIONS_CONFIRMED)
    entries = _dedupe_events(entries)
    entries = _attach_decision_fields(conn, entries)
    refs = _reference_prices(conn)
    entries = _attach_reference(entries, refs, "entry")

    if entries.empty:
        return entries

    entries["decision_id"] = entries["run_id"] + ":" + entries["ticker"]
    # Fill price vs submit-time reference are DIFFERENT fields by contract.
    entries["entry_px"] = entries["price"].where(entries["entry_fill_confirmed"])
    entries["entry_px_reference"] = entries["price"].where(~entries["entry_fill_confirmed"])
    entries["intended_notional"] = entries["kelly_target_pct"] * entries["portfolio_value"]
    entries["realized_notional"] = (entries["shares"] * entries["entry_px"]).where(
        entries["entry_fill_confirmed"]
    )
    for col in FWD_COLS:
        spy_fwd = entries[["date"]].merge(
            refs.loc[refs["ticker"] == BENCHMARK_TICKER, ["as_of_date", col]].rename(
                columns={"as_of_date": "date"}
            ),
            on="date",
            how="left",
        )[col]
        entries[f"rel_{col}"] = entries[col] - spy_fwd.values
    entries["ref_px_kind"] = REF_PX_KIND
    return entries


def load_exit_events(conn: sqlite3.Connection, run_type: str = "live") -> pd.DataFrame:
    """Deduplicated exit events (confirmed ``sell`` + pending ``sell_pending``)
    with reference closes attached. ``exit_px`` is populated only for
    confirmed exits; pending submissions keep their reference price in
    ``exit_px_reference`` (same censoring contract as entries)."""
    exits = _read_events(
        conn, EXIT_ACTIONS_CONFIRMED + EXIT_ACTIONS_PENDING, run_type
    )
    exits["exit_fill_confirmed"] = exits["action"].isin(EXIT_ACTIONS_CONFIRMED)
    exits = _dedupe_events(exits)
    exits = _attach_reference(exits, _reference_prices(conn), "exit")
    if exits.empty:
        return exits
    exits["exit_px"] = exits["price"].where(exits["exit_fill_confirmed"])
    exits["exit_px_reference"] = exits["price"].where(~exits["exit_fill_confirmed"])
    return exits


def _latest_marks(conn: sqlite3.Connection) -> dict[str, tuple[str, float]]:
    """ticker -> (latest as_of_date, close_price) for open-position
    mark-to-market. Recorded closes only."""
    df = pd.read_sql(
        "SELECT t.ticker, t.as_of_date, t.close_price FROM ticker_forward_returns t"
        " JOIN (SELECT ticker, MAX(as_of_date) AS d FROM ticker_forward_returns"
        "       WHERE close_price IS NOT NULL GROUP BY ticker) m"
        " ON m.ticker = t.ticker AND m.d = t.as_of_date",
        conn,
    )
    return {r.ticker: (r.as_of_date, r.close_price) for r in df.itertuples()}


def build_round_trips(
    conn: sqlite3.Connection,
    run_type: str = "live",
    allow_sim: bool = False,
) -> list[dict[str, Any]]:
    """FIFO-pair entry decisions to exit events per ticker into round-trip
    records for decomposition. Open positions become mark-to-market records
    (``status='open_mtm'``) marked at the latest recorded close.

    Sim streams are refused by default (commingled parallel runs make FIFO
    pairing unreliable — see module doc); pass ``allow_sim=True`` only for
    controlled fixtures.
    """
    if run_type == "sim" and not allow_sim:
        raise ValueError(
            "round-trip FIFO matching is unreliable across commingled sim "
            "streams; use decision_pnl_attribution (#145) for sim class-level "
            "attribution, or pass allow_sim=True for controlled fixtures"
        )
    entries = load_decision_ledger(conn, run_type)
    exits = load_exit_events(conn, run_type)
    entry_dates = (
        {} if entries.empty
        else {t: set(g) for t, g in entries.groupby("ticker")["date"]}
    )
    exit_dates = (
        {} if exits.empty
        else {t: set(g) for t, g in exits.groupby("ticker")["date"]}
    )
    entries = _collapse_re_records(entries, exit_dates)
    exits = _collapse_re_records(exits, entry_dates)
    marks = _latest_marks(conn)

    trips: list[dict[str, Any]] = []
    exit_pool: dict[str, list[dict]] = {}
    if not exits.empty:
        for _, row in exits.sort_values("date").iterrows():
            exit_pool.setdefault(row["ticker"], []).append(row.to_dict())

    entry_iter = [] if entries.empty else list(entries.sort_values("date").iterrows())
    for _, e in entry_iter:
        rec: dict[str, Any] = {
            "decision_id": e["decision_id"],
            "run_id": e["run_id"],
            "date": e["date"],
            "ticker": e["ticker"],
            "action": e["action"],
            "run_type": e["run_type"],
            "regime": _s(e.get("regime")),
            "mu": _f(e.get("mu")),
            "sigma": _f(e.get("sigma")),
            "rank_score": _f(e.get("rank_score")),
            "blocked_by": _s(e.get("blocked_by")),
            "shares": _f(e.get("shares")),
            "shares_conflict": bool(e.get("shares_conflict", False)),
            "n_re_record_days": int(e.get("n_re_record_days", 1)),
            "intended_notional": _f(e.get("intended_notional")),
            "realized_notional": _f(e.get("realized_notional")),
            "entry_px": _f(e.get("entry_px")),
            "entry_px_reference": _f(e.get("entry_px_reference")),
            "entry_fill_confirmed": bool(e["entry_fill_confirmed"]),
            "ref_entry_px": _f(e.get("ref_entry_px")),
            "spy_entry_px": _f(e.get("spy_entry_px")),
            "ref_px_kind": REF_PX_KIND,
            "fwd": {c: _f(e.get(c)) for c in FWD_COLS},
            "rel_fwd": {c: _f(e.get(f"rel_{c}")) for c in FWD_COLS},
        }
        pool = exit_pool.get(e["ticker"], [])
        matched = None
        for i, x in enumerate(pool):
            if x["date"] >= e["date"]:
                matched = pool.pop(i)
                break
        if matched is not None:
            rec.update(
                status="closed",
                exit_date=matched["date"],
                exit_px=_f(matched.get("exit_px")),
                exit_px_reference=_f(matched.get("exit_px_reference")),
                exit_fill_confirmed=bool(matched["exit_fill_confirmed"]),
                exit_reason=_s(matched.get("exit_reason")),
                pnl_pct_recorded=_f(matched.get("pnl_pct")),
                hold_days_recorded=_f(matched.get("hold_days")),
                ref_exit_px=_f(matched.get("ref_exit_px")),
                spy_exit_px=_f(matched.get("spy_exit_px")),
            )
        else:
            mark = marks.get(e["ticker"])
            rec.update(
                status="open_mtm",
                exit_date=mark[0] if mark else None,
                # Open positions are marked at the latest recorded close: the
                # mark is BOTH the "real" and the reference exit price, so the
                # TIMING leg carries entry timing only (exit sides cancel).
                exit_px=_f(mark[1]) if mark else None,
                exit_px_reference=None,
                exit_fill_confirmed=None,  # not applicable — nothing filled
                exit_reason=None,
                pnl_pct_recorded=None,
                hold_days_recorded=None,
                ref_exit_px=_f(mark[1]) if mark else None,
                spy_exit_px=_spy_mark(marks),
            )
        trips.append(rec)

    # Exits that never matched an in-window entry (positions opened before the
    # ledger's first entry row, reconciliation sells, ...) — surfaced, never
    # silently dropped.
    unmatched = [x for pool in exit_pool.values() for x in pool]
    for x in unmatched:
        trips.append(
            {
                "decision_id": f"{x['run_id']}:{x['ticker']}:exit-unmatched",
                "run_id": x["run_id"],
                "date": x["date"],
                "ticker": x["ticker"],
                "action": x["action"],
                "run_type": x["run_type"],
                "regime": _s(x.get("regime")),
                "status": "exit_unmatched",
                "exit_px": _f(x.get("exit_px")),
                "exit_px_reference": _f(x.get("exit_px_reference")),
                "exit_fill_confirmed": bool(x["exit_fill_confirmed"]),
                "exit_reason": _s(x.get("exit_reason")),
                "pnl_pct_recorded": _f(x.get("pnl_pct")),
                "hold_days_recorded": _f(x.get("hold_days")),
            }
        )
    return trips


def _f(v) -> float | None:
    """NaN-safe float coercion: pandas NaN/NA -> None (explicit absence)."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _s(v) -> str | None:
    """NaN-safe string coercion: pandas NaN/None -> None, else str."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def _spy_mark(marks: dict[str, tuple[str, float]]) -> float | None:
    m = marks.get(BENCHMARK_TICKER)
    return _f(m[1]) if m else None
