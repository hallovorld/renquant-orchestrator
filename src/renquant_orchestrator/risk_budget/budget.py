"""Risk budgets as data + current consumption from read-only sources (107 sprint D3).

OBSERVE-ONLY. This module defines the book's risk budgets as *data with
provenance* and measures their CURRENT consumption from already-persisted
sources. It enforces nothing, gates nothing, and changes no trading behavior
— the enforcement layer stays where it already lives (the pinned strategy
config's regime caps / per-name caps / vol-gated regime detector, consumed
here as definitions, never reimplemented).

The budgets (each entry cites its source — nothing here is invented):

- ``max_drawdown`` — **15% HARD**. The G* bar (#230 §4 "Max drawdown
  discipline ≤ 15%", restated in the unified 107 master plan §0). The one
  budget in this ledger with a hard mandate behind it.
- ``book_beta`` — **0.6 PLANNING**. RS-1 §2's planning heuristic
  ``β_max = DD_bar / stress = 0.15 / 0.25 = 0.6`` (mirrored by the pinned
  strategy config's ``sleeve.beta_max``). RS-1 itself flags this as "planning
  heuristic only, not a hard budget" with four uncorrected weaknesses — the
  first being that β_pos = 1.0 was ASSUMED, never measured. This module
  closes exactly that gap: it MEASURES realized book beta and the per-name
  beta composition instead of assuming it.
- ``per_name_concentration`` — per-regime ``max_position_pct`` from the
  pinned strategy config (BULL_CALM 0.12 / BULL_VOLATILE 0.20 / CHOPPY 0.15 /
  BEAR 0.0 as of 2026-07-03). Consumed, not redefined.
- ``sleeve_dd_sub_budget`` — the parking sleeve's DD sub-budget
  (``sleeve.dd_budget_pct``, pipeline #157 ``ParkingSleeveShadowTask``).
  Consumption is read from the sleeve shadow JSONL when present; the sleeve
  is default-OFF, so "absent" is an explicit, reported state — never imputed.

Context controls reported but NOT given breach semantics (they are existing
enforcement, not budgets this ledger owns): per-regime ``cash_reserve_pct``,
``max_positions_per_sector``, per-regime ``max_sector_weight_pct``, and the
regime detector's vol gate thresholds (``regime.bear_vol_threshold`` etc.).

Everything is read-only: the run DB is opened ``mode=ro``, config / sleeve
log / ohlcv parquets are only ever read.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from renquant_orchestrator.runtime_paths import default_data_root

# --- default read-only sources (every public function takes them explicitly) ---
_DATA_ROOT = default_data_root()
DEFAULT_DB = _DATA_ROOT / "data/runs.alpaca.db"
DEFAULT_OHLCV_DIR = _DATA_ROOT / "data/ohlcv"
DEFAULT_SLEEVE_LOG = (
    _DATA_ROOT / "backtesting/renquant_104/logs/parking_sleeve_shadow.jsonl"
)
# Pinned runtime copy first (what the live run actually reads — "merged is not
# deployed"), sibling working checkout as fallback for research use.
STRATEGY_CONFIG_CANDIDATES = (
    _DATA_ROOT / ".subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json",
    Path.home() / "git/github/renquant-strategy-104/configs/strategy_config.json",
)

BENCHMARK_TICKER = "SPY"

# Budget constants (sources documented in the module doc + build_budgets)
DD_BUDGET_HARD = 0.15
BETA_BUDGET_PLANNING = 0.6

CENSOR_NO_EQUITY = "no_equity_curve(portfolio_daily_metrics empty for run_type)"
CENSOR_SHORT_CURVE = "curve_too_short(<2 sessions)"
CENSOR_NOT_BURNING = "not_burning(drawdown flat or recovering over window)"
CENSOR_NO_SPY = "no_benchmark_series(SPY closes missing)"
CENSOR_BETA_N_OBS = "beta_unmeasurable(<{min_obs} paired daily returns)"
CENSOR_SLEEVE_ABSENT = "sleeve_log_absent(flag default-OFF; shadow never ran)"
CENSOR_DB_BETA_NULL = "db_beta_spy_252d_null(all live rows NULL — computed here instead)"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the run DB **read-only** (``file:...?mode=ro`` URI) — same
    convention as the attribution engine: this ledger can never write to the
    live run DB by construction."""
    if db_path is None:
        db_path = DEFAULT_DB
    return sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)


# ---------------------------------------------------------------------------
# Budget definitions (as data, with provenance)
# ---------------------------------------------------------------------------

def resolve_strategy_config(path: str | Path | None = None) -> Path | None:
    """The pinned runtime strategy config if present, else the sibling
    checkout copy; explicit path wins. Returns None when nothing exists."""
    if path is not None:
        p = Path(path)
        return p if p.exists() else None
    for cand in STRATEGY_CONFIG_CANDIDATES:
        if cand.exists():
            return cand
    return None


def load_strategy_risk_controls(path: str | Path | None = None) -> dict[str, Any]:
    """Read the EXISTING risk controls out of the pinned strategy config —
    consumed as budget definitions, never reimplemented or enforced here."""
    resolved = resolve_strategy_config(path)
    if resolved is None:
        return {
            "config_path": None,
            "pinned": False,
            "regime_params": {},
            "max_positions_per_sector": None,
            "vol_gate": {},
            "sleeve": {},
            "censored": ["strategy_config_missing(no pinned or sibling copy found)"],
        }
    cfg = json.loads(resolved.read_text())
    regime_params: dict[str, dict[str, Any]] = {}
    for regime, params in (cfg.get("regime_params") or {}).items():
        if not isinstance(params, dict):
            continue
        regime_params[regime] = {
            key: params.get(key)
            for key in (
                "max_position_pct",
                "cash_reserve_pct",
                "max_sector_weight_pct",
                "stop_loss_pct",
                "max_single_day_loss_pct",
            )
            if key in params
        }
    regime_cfg = cfg.get("regime") or {}
    vol_gate = {
        key: regime_cfg.get(key)
        for key in (
            "bear_vol_threshold",
            "vol_realized_window",
            "bear_vol_threshold_5d",
            "vol_realized_window_5d",
            "choppy_vol_baseline_window",
            "choppy_vol_ratio_threshold",
        )
        if key in regime_cfg
    }
    sleeve = cfg.get("sleeve") or {}
    return {
        "config_path": str(resolved),
        "pinned": ".subrepo_runtime" in str(resolved),
        "regime_params": regime_params,
        "position_sizing": cfg.get("position_sizing") or {},
        "max_positions_per_sector": cfg.get("max_positions_per_sector"),
        "vol_gate": vol_gate,
        "sleeve": {
            key: sleeve.get(key)
            for key in ("enabled", "mode", "beta_max", "beta_pos", "dd_budget_pct", "log_path")
        },
        "censored": [],
    }


def build_budgets(controls: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The budget ledger: limit + kind + provenance, as data."""
    sleeve = controls.get("sleeve") or {}
    sleeve_dd = sleeve.get("dd_budget_pct")
    return {
        "max_drawdown": {
            "limit": DD_BUDGET_HARD,
            "kind": "hard",
            "unit": "fraction of book, peak-to-trough",
            "source": "G* bar: #230 §4 / unified 107 master plan §0 (DD ≤ 15% HARD)",
        },
        "book_beta": {
            "limit": BETA_BUDGET_PLANNING,
            "kind": "planning",
            "unit": "book beta vs SPY",
            "source": (
                "RS-1 §2 planning heuristic β_max = 0.15/0.25 = 0.6 "
                "(PROVISIONAL per RS-1; strategy config sleeve.beta_max mirrors it)"
            ),
        },
        "per_name_concentration": {
            "limit": None,  # regime-dependent; resolved against the live regime
            "kind": "hard",
            "unit": "max single-name weight vs regime max_position_pct",
            "per_regime": {
                regime: params.get("max_position_pct")
                for regime, params in (controls.get("regime_params") or {}).items()
            },
            "source": "pinned strategy config regime_params[*].max_position_pct (consumed)",
        },
        "sleeve_dd_sub_budget": {
            "limit": sleeve_dd if sleeve_dd is not None else DD_BUDGET_HARD,
            "kind": "sub-budget",
            "unit": "sleeve drawdown vs sleeve.dd_budget_pct",
            "source": "pipeline #157 ParkingSleeveShadowTask / strategy config sleeve.dd_budget_pct",
        },
    }


# ---------------------------------------------------------------------------
# Equity curve → running max-DD + burn rate / runway
# ---------------------------------------------------------------------------

def load_equity_curve(
    conn: sqlite3.Connection,
    run_type: str = "live",
    strategy: str | None = None,
) -> pd.DataFrame:
    """Book equity history from ``portfolio_daily_metrics`` (one row per
    session), columns ``date / portfolio_value / daily_return``."""
    q = (
        "SELECT as_of_date AS date, portfolio_value, daily_return, strategy "
        "FROM portfolio_daily_metrics WHERE run_type = ?"
    )
    params: list[Any] = [run_type]
    if strategy is not None:
        q += " AND strategy = ?"
        params.append(strategy)
    q += " ORDER BY as_of_date"
    df = pd.read_sql(q, conn, params=params)
    return df.dropna(subset=["portfolio_value"]).reset_index(drop=True)


def stamped_high_water_mark(conn: sqlite3.Connection) -> float | None:
    """The pipeline's own stamped high-water mark (latest
    ``live_state_snapshots`` row) — a cross-check for the measured peak: the
    stamped HWM can predate the measurable curve. Missing table → None."""
    try:
        row = pd.read_sql(
            "SELECT high_water_mark FROM live_state_snapshots "
            "ORDER BY run_date DESC, created_at DESC LIMIT 1",
            conn,
        )
    except Exception:
        return None
    if row.empty or row["high_water_mark"].iloc[0] is None:
        return None
    return float(row["high_water_mark"].iloc[0])


def running_drawdown(curve: pd.DataFrame, stamped_hwm: float | None = None) -> dict[str, Any]:
    """Running max drawdown over the full recorded history: the running peak,
    the worst peak-to-trough drawdown to date, and the current drawdown.
    Recorded sessions only — calendar gaps are reported, never interpolated.

    The series is END-OF-DAY only (intraday troughs are invisible) and starts
    at the first recorded session (earlier drawdowns are unknowable). When the
    pipeline's stamped HWM exceeds the measured peak, the drawdown against it
    is ALSO computed and the conservative (deeper) figure drives consumption
    — two recorded sources that disagree are both reported, never resolved by
    guessing."""
    if curve.empty:
        return {"censored": CENSOR_NO_EQUITY}
    pv = curve["portfolio_value"].astype(float)
    peak = pv.cummax()
    dd = 1.0 - pv / peak
    worst_idx = int(dd.idxmax())
    out = {
        "as_of": str(curve["date"].iloc[-1]),
        "n_sessions": int(len(curve)),
        "start_date": str(curve["date"].iloc[0]),
        "portfolio_value": float(pv.iloc[-1]),
        "peak_value": float(peak.iloc[-1]),
        "peak_date": str(curve["date"].iloc[int(pv.idxmax())]),
        "max_drawdown": float(dd.max()),
        "max_drawdown_date": str(curve["date"].iloc[worst_idx]),
        # the peak the worst drawdown fell from (start of the DD window)
        "max_drawdown_peak_date": str(
            curve["date"].iloc[int(pv.iloc[: worst_idx + 1].idxmax())]
        ),
        "current_drawdown": float(dd.iloc[-1]),
        "censored": None,
    }
    out["stamped_hwm"] = stamped_hwm
    out["max_drawdown_conservative"] = out["max_drawdown"]
    if stamped_hwm is not None and stamped_hwm > out["peak_value"]:
        dd_vs_hwm = 1.0 - float(pv.iloc[-1]) / stamped_hwm
        out["current_drawdown_vs_stamped_hwm"] = dd_vs_hwm
        out["max_drawdown_conservative"] = max(out["max_drawdown"], dd_vs_hwm)
    return out


def dd_budget_consumption(drawdown: dict[str, Any], limit: float) -> dict[str, Any]:
    """Consumption fractions of the DD budget. The breach driver is the
    RUNNING max drawdown (a drawdown budget is spent by the worst realized
    excursion, not just today's — conservative vs the stamped HWM when that
    is higher); the current drawdown is reported alongside."""
    if drawdown.get("censored"):
        return {"censored": drawdown["censored"], "limit": limit}
    driver = drawdown.get("max_drawdown_conservative", drawdown["max_drawdown"])
    return {
        "limit": limit,
        "max_consumption": driver / limit,
        "current_consumption": drawdown["current_drawdown"] / limit,
        "remaining_fraction": max(0.0, 1.0 - driver / limit),
        "censored": None,
    }


def burn_rate(
    curve: pd.DataFrame,
    limit: float = DD_BUDGET_HARD,
    window: int = 21,
) -> dict[str, Any]:
    """Runway arithmetic on the CURRENT drawdown: over the trailing
    ``window`` sessions, how fast is budget consumption growing, and — if it
    keeps growing at that pace — how many sessions until the budget is gone?

    burn = (consumption_now − consumption_{now−k}) / k   [budget-fractions/session]
    runway_sessions = (1 − consumption_now) / burn        [only when burn > 0]

    A flat or recovering book has no finite runway; that is reported as an
    explicit not-burning state, never as a number."""
    if len(curve) < 2:
        return {"censored": CENSOR_SHORT_CURVE, "window": window}
    pv = curve["portfolio_value"].astype(float)
    dd = 1.0 - pv / pv.cummax()
    consumption = dd / limit
    k = min(window, len(curve) - 1)
    c_now = float(consumption.iloc[-1])
    c_then = float(consumption.iloc[-1 - k])
    burn = (c_now - c_then) / k
    out: dict[str, Any] = {
        "window": k,
        "consumption_now": c_now,
        "consumption_window_start": c_then,
        "burn_per_session": burn,
        "censored": None,
    }
    if burn > 0:
        out["runway_sessions"] = (1.0 - c_now) / burn
    else:
        out["runway_sessions"] = None
        out["censored"] = CENSOR_NOT_BURNING
    return out


# ---------------------------------------------------------------------------
# Positions → concentration (HHI, top-name, per-name cap consumption)
# ---------------------------------------------------------------------------

def latest_positions(conn: sqlite3.Connection, run_type: str = "live") -> dict[str, Any]:
    """The latest run's held positions (weights of book) from
    ``ticker_daily_state``, plus the run's regime and cash weight."""
    run = pd.read_sql(
        "SELECT run_id, run_date, regime, portfolio_value, cash FROM pipeline_runs "
        "WHERE run_type = ? ORDER BY run_date DESC, created_at DESC LIMIT 1",
        conn,
        params=(run_type,),
    )
    if run.empty:
        return {"censored": "no_runs(run DB has no rows for run_type)", "positions": []}
    run_id = run["run_id"].iloc[0]
    pos = pd.read_sql(
        "SELECT ticker, position_pct, sector FROM ticker_daily_state "
        "WHERE run_id = ? AND has_position = 1 ORDER BY position_pct DESC",
        conn,
        params=(run_id,),
    )
    invested = float(pos["position_pct"].fillna(0.0).sum())
    pv = run["portfolio_value"].iloc[0]
    cash = run["cash"].iloc[0]
    # The recorded cash column is NOT trusted for weights: on the live DB it
    # is inconsistent with PV − Σ position notionals (2026-07-02: cash 8313.5
    # vs PV−invested 6922.6 — a ~13%-of-book identity gap, likely a snapshot-
    # moment/pending-settlement artifact). Cash weight is DERIVED from the
    # position weights, and the identity gap is surfaced, never papered over.
    recorded_cash_weight = (float(cash) / float(pv)) if pv and cash is not None else None
    identity_gap = (
        recorded_cash_weight + invested - 1.0 if recorded_cash_weight is not None else None
    )
    return {
        "run_id": str(run_id),
        "date": str(run["run_date"].iloc[0]),
        "regime": run["regime"].iloc[0],
        "portfolio_value": float(pv) if pv is not None else None,
        "cash_weight": 1.0 - invested,
        "recorded_cash_weight": recorded_cash_weight,
        "cash_identity_gap": identity_gap,
        "invested_weight": invested,
        "positions": [
            {
                "ticker": r["ticker"],
                "weight": float(r["position_pct"]) if r["position_pct"] is not None else None,
                "sector": r["sector"],
            }
            for _, r in pos.iterrows()
        ],
        "censored": None,
    }


def concentration(
    positions: dict[str, Any],
    regime_caps: dict[str, float | None],
) -> dict[str, Any]:
    """HHI (book and invested-normalized), top-name weight, and per-name
    consumption against the LIVE regime's max_position_pct cap."""
    rows = [p for p in positions.get("positions", []) if p.get("weight")]
    regime = positions.get("regime")
    cap = regime_caps.get(regime) if regime is not None else None
    if not rows:
        return {
            "censored": positions.get("censored") or "no_positions(book is all cash)",
            "regime": regime,
            "cap": cap,
            "n_names": 0,
        }
    weights = [p["weight"] for p in rows]
    invested = sum(weights)
    hhi_book = sum(w * w for w in weights)
    hhi_invested = sum((w / invested) ** 2 for w in weights)
    top = max(rows, key=lambda p: p["weight"])
    sector_weights: dict[str, float] = {}
    for p in rows:
        sector_weights[p["sector"] or "unknown"] = (
            sector_weights.get(p["sector"] or "unknown", 0.0) + p["weight"]
        )
    out = {
        "regime": regime,
        "cap": cap,
        "n_names": len(rows),
        "hhi_book": hhi_book,
        "hhi_invested": hhi_invested,
        "effective_n_invested": 1.0 / hhi_invested,
        "top_name": top["ticker"],
        "top_name_weight": top["weight"],
        "sector_weights": sector_weights,
        "censored": None,
    }
    if cap:
        out["consumption"] = top["weight"] / cap
        out["per_name_consumption"] = {
            p["ticker"]: p["weight"] / cap for p in rows
        }
    else:
        out["consumption"] = None
        out["censored"] = (
            f"no_cap_for_regime({regime}: cap={cap!r} — BEAR cap 0 means any "
            "position is over-cap; reported, not divided by zero)"
            if cap == 0
            else f"no_cap_for_regime({regime})"
        )
        if cap == 0 and rows:
            # cap 0 with live positions IS a full breach, representable without /0
            out["consumption"] = float("inf")
    return out


# ---------------------------------------------------------------------------
# Beta: realized book beta (measured) + per-name composition incl. sleeve leg
# ---------------------------------------------------------------------------

def spy_return_series(conn: sqlite3.Connection) -> pd.Series:
    """SPY daily simple returns from the run DB's persisted closes
    (``ticker_forward_returns.close_price``), indexed by date string. The
    return dated t is close[t]/close[t_prev] − 1 — same-day alignment with
    ``portfolio_daily_metrics.daily_return``."""
    spy = pd.read_sql(
        "SELECT as_of_date AS date, close_price FROM ticker_forward_returns "
        "WHERE ticker = ? AND close_price IS NOT NULL ORDER BY as_of_date",
        conn,
        params=(BENCHMARK_TICKER,),
    )
    if spy.empty:
        return pd.Series(dtype=float)
    ret = spy.set_index("date")["close_price"].pct_change().dropna()
    ret.name = "spy_return"
    return ret


def realized_beta(
    book_returns: pd.Series,
    bench_returns: pd.Series,
    min_obs: int = 20,
) -> dict[str, Any]:
    """OLS beta of book daily returns on benchmark daily returns over the
    dates both series recorded. Pure arithmetic — unit-testable."""
    joined = pd.concat([book_returns, bench_returns], axis=1, join="inner").dropna()
    n = len(joined)
    if n < min_obs:
        return {"censored": CENSOR_BETA_N_OBS.format(min_obs=min_obs), "n_obs": n}
    b = joined.iloc[:, 0].astype(float)
    m = joined.iloc[:, 1].astype(float)
    var_m = float(m.var(ddof=1))
    if var_m <= 0:
        return {"censored": "benchmark_variance_zero", "n_obs": n}
    beta = float(m.cov(b) / var_m)
    corr = float(m.corr(b))
    return {"beta": beta, "n_obs": n, "r2": corr * corr, "censored": None}


def load_close_series(ohlcv_dir: str | Path, ticker: str) -> pd.Series | None:
    """Daily close series from the umbrella ohlcv store (read-only). None
    when the ticker has no parquet — the caller censors, never imputes."""
    path = Path(ohlcv_dir) / ticker / "1d.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path, columns=["close"])
    s = df["close"].astype(float)
    s.index = pd.to_datetime(s.index).strftime("%Y-%m-%d")
    return s


def per_name_betas(
    close_by_ticker: dict[str, pd.Series | None],
    bench_ticker: str = BENCHMARK_TICKER,
    window: int = 63,
    min_obs: int = 40,
) -> dict[str, dict[str, Any]]:
    """Per-name beta vs the benchmark over the trailing ``window`` sessions
    of daily returns. Names without enough paired observations are censored
    (RS-1 §2 weakness #1 is an *assumed* β_pos — this module measures or
    says it cannot)."""
    bench = close_by_ticker.get(bench_ticker)
    out: dict[str, dict[str, Any]] = {}
    if bench is None or bench.empty:
        for t in close_by_ticker:
            if t != bench_ticker:
                out[t] = {"censored": CENSOR_NO_SPY, "n_obs": 0}
        return out
    bench_ret = bench.pct_change().dropna().iloc[-window:]
    for ticker, closes in close_by_ticker.items():
        if ticker == bench_ticker:
            continue
        if closes is None or closes.empty:
            out[ticker] = {"censored": "no_price_series(ohlcv parquet missing)", "n_obs": 0}
            continue
        ret = closes.pct_change().dropna().iloc[-window:]
        out[ticker] = realized_beta(ret, bench_ret, min_obs=min_obs)
    return out


def beta_composition(
    positions: dict[str, Any],
    betas: dict[str, dict[str, Any]],
    sleeve_reading: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Point-in-time book beta = Σ w_i·β_i over measured names, with the
    unmeasured weight reported as censored — plus the sleeve leg
    (w_SPY·1.0 + w_SGOV·0.0, SGOV≈0 stated per RS-1 §2) when a sleeve
    shadow state is present. Never fills β=1 for an unmeasured name."""
    rows = [p for p in positions.get("positions", []) if p.get("weight")]
    measured_sum = 0.0
    measured_weight = 0.0
    censored_names: dict[str, str] = {}
    per_name: dict[str, dict[str, Any]] = {}
    for p in rows:
        info = betas.get(p["ticker"], {"censored": "no_beta_computed", "n_obs": 0})
        if info.get("censored"):
            censored_names[p["ticker"]] = info["censored"]
        else:
            measured_sum += p["weight"] * info["beta"]
            measured_weight += p["weight"]
        per_name[p["ticker"]] = {"weight": p["weight"], **info}
    sleeve_leg = None
    if sleeve_reading and sleeve_reading.get("present"):
        last = sleeve_reading.get("last") or {}
        pv = positions.get("portfolio_value")
        spy_notional = last.get("spy_notional")
        if pv and spy_notional is not None:
            w_spy = float(spy_notional) / float(pv)
            # SPY β = 1.0 by definition of the benchmark; SGOV β treated as 0
            # — an explicit simplification (RS-1 §2 weakness #2), stated here.
            sleeve_leg = {
                "spy_weight": w_spy,
                "beta_contribution": w_spy * 1.0,
                "sgov_beta_assumed_zero": True,
            }
            measured_sum += w_spy
            measured_weight += w_spy
    return {
        "book_beta_measured_names": measured_sum if measured_weight > 0 else None,
        "measured_weight": measured_weight,
        "unmeasured_weight": sum(
            p["weight"] for p in rows if p["ticker"] in censored_names
        ),
        "per_name": per_name,
        "censored_names": censored_names,
        "sleeve_leg": sleeve_leg,
        "censored": None if measured_weight > 0 else "no_measurable_names",
    }


# ---------------------------------------------------------------------------
# Sleeve shadow log (pipeline #157) — sub-budget + reversal metrics
# ---------------------------------------------------------------------------

def read_sleeve_shadow(
    path: str | Path | None = None,
    reversal_sessions: int = 63,
    reversal_dd_threshold: float = 0.5,
) -> dict[str, Any]:
    """Read the parking-sleeve shadow JSONL (schema: pipeline #157
    ``ParkingSleeveShadowTask``) and evaluate the RS-1 reversal-metric
    inputs: trailing ~3-month (63-session) sleeve contribution and the
    running max DD-sub-budget consumption. The reversal rule (negative
    3-month contribution AND >50% sub-budget consumption ⇒ drop to the SGOV
    floor) is a MONITORING readout here — observe-only, no action."""
    p = Path(path) if path is not None else DEFAULT_SLEEVE_LOG
    if not p.exists():
        return {"present": False, "path": str(p), "censored": CENSOR_SLEEVE_ABSENT}
    records: list[dict[str, Any]] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # partial trailing writes tolerated; counted below
        if isinstance(rec, dict):
            records.append(rec)
    if not records:
        return {"present": False, "path": str(p), "censored": "sleeve_log_empty"}

    def _book_state(rec: dict[str, Any]) -> dict[str, Any]:
        bs = rec.get("book_state")
        return bs if isinstance(bs, dict) else rec

    last = _book_state(records[-1])
    tail = [_book_state(r) for r in records[-reversal_sessions:]]
    contributions = [
        float(bs["sleeve_contribution_pct"])
        for bs in tail
        if isinstance(bs.get("sleeve_contribution_pct"), (int, float))
    ]
    contribution_sum = sum(contributions) if contributions else None
    max_dd_consumption = last.get("max_dd_budget_consumption_pct")
    reversal = None
    if contribution_sum is not None and isinstance(max_dd_consumption, (int, float)):
        reversal = bool(
            contribution_sum < 0 and float(max_dd_consumption) > reversal_dd_threshold
        )
    return {
        "present": True,
        "path": str(p),
        "n_records": len(records),
        "last": last,
        "dd_budget_pct": last.get("dd_budget_pct"),
        "dd_budget_consumption_pct": last.get("dd_budget_consumption_pct"),
        "max_dd_budget_consumption_pct": max_dd_consumption,
        "reversal_metrics": {
            "window_sessions": min(reversal_sessions, len(records)),
            "contribution_sum_pct": contribution_sum,
            "max_dd_budget_consumption_pct": max_dd_consumption,
            "triggered": reversal,
            "rule": (
                "negative trailing-3-month sleeve contribution AND >50% "
                "DD-sub-budget consumption => drop to SGOV floor (#157 monitoring rule)"
            ),
        },
        "censored": None,
    }
