"""Parking sleeve allocator — β-budgeted SPY/SGOV split (S7, shadow-only).

Computes the target parking-sleeve allocation from current book state using the
RS-1 β-budget formula. The SPY fraction is sized so that total book beta stays
within the planning budget (β_max = 0.6 by default). SGOV absorbs the rest.

    sleeve_spy_frac = clamp(0, 1, (β_max − β_positions) / (w_sleeve × β_spy))

where β_positions is the measured beta contribution from single-name holdings
(positions_value / portfolio_value × β_portfolio_ex_sleeve), w_sleeve is the
book weight available to the sleeve (1 − positions_weight − reserve_pct), and
β_spy ≈ 1.0.

This module is OBSERVE-ONLY: it logs shadow allocations to a JSONL file. It
never places orders, never modifies config, and never touches production state.
Arming requires the pre-registration gate per RS-1 §4 / #228 §1.3.

Module delivered; scheduler/session-tick integration (wiring this into the 105
session scheduler as a per-tick shadow computation) is NOT yet done — see the
progress doc's NEXT section.

Regime override: BEAR → sleeve_spy_frac = 0 (100% SGOV / cash).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from .runtime_paths import default_data_root, default_strategy_config_path

log = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class SleeveConfig:
    """Configuration for the parking sleeve (from strategy config `sleeve` section)."""

    enabled: bool = False
    beta_max: float = 0.6
    reserve_pct: float = 0.02
    spy_ticker: str = "SPY"
    sgov_ticker: str = "SGOV"
    beta_spy: float = 1.0
    regime_bear_override: bool = True

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "SleeveConfig":
        if not d:
            return cls()
        return cls(
            enabled=bool(d.get("enabled", False)),
            beta_max=float(d.get("beta_max", 0.6)),
            reserve_pct=float(d.get("reserve_pct", 0.02)),
            spy_ticker=str(d.get("spy_ticker", "SPY")),
            sgov_ticker=str(d.get("sgov_ticker", "SGOV")),
            beta_spy=float(d.get("beta_spy", 1.0)),
            regime_bear_override=bool(d.get("regime_bear_override", True)),
        )


@dataclasses.dataclass(frozen=True)
class BookState:
    """Current book state snapshot for sleeve computation (read-only inputs)."""

    portfolio_value: float
    positions_value: float
    cash_value: float
    beta_positions: float
    regime: str


@dataclasses.dataclass(frozen=True)
class SleeveAllocation:
    """Computed sleeve allocation (shadow output — not an order)."""

    as_of: str
    portfolio_value: float
    positions_weight: float
    sleeve_weight: float
    reserve_weight: float
    spy_frac: float
    sgov_frac: float
    spy_target_weight: float
    sgov_target_weight: float
    spy_target_notional: float
    sgov_target_notional: float
    beta_positions: float
    beta_book_estimate: float
    regime: str
    regime_override_active: bool
    enabled: bool

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        # ``risk_budget.beta_composition()`` consumes ``spy_notional`` from the
        # sleeve shadow log. Keep the target_* names (local clarity) and emit the
        # contract aliases as well so the monitor can read real sleeve beta.
        payload["spy_notional"] = self.spy_target_notional
        payload["sgov_notional"] = self.sgov_target_notional
        return payload


def default_runs_db_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else default_data_root()
    return root / "data" / "runs.alpaca.db"


def default_ohlcv_dir(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else default_data_root()
    return root / "data" / "ohlcv"


def default_shadow_log_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else default_data_root()
    return root / "backtesting" / "renquant_104" / "logs" / "parking_sleeve_shadow.jsonl"


def compute_sleeve_allocation(
    book: BookState,
    config: SleeveConfig,
) -> SleeveAllocation:
    """Compute the target sleeve allocation from current book state.

    Pure computation — no I/O, no side effects.
    """
    pv = book.portfolio_value
    if pv <= 0:
        return _zero_allocation(book, config, reason="zero_portfolio_value")

    w_pos = book.positions_value / pv
    reserve = config.reserve_pct
    w_sleeve = max(0.0, 1.0 - w_pos - reserve)

    regime_override = (
        config.regime_bear_override and book.regime == "BEAR"
    )

    if regime_override or w_sleeve <= 0:
        spy_frac = 0.0
    else:
        beta_headroom = config.beta_max - book.beta_positions
        if beta_headroom <= 0 or config.beta_spy <= 0:
            spy_frac = 0.0
        else:
            spy_frac = min(1.0, beta_headroom / (w_sleeve * config.beta_spy))

    sgov_frac = 1.0 - spy_frac

    spy_target_w = w_sleeve * spy_frac
    sgov_target_w = w_sleeve * sgov_frac

    beta_book = book.beta_positions + spy_target_w * config.beta_spy

    return SleeveAllocation(
        as_of=dt.date.today().isoformat(),
        portfolio_value=pv,
        positions_weight=w_pos,
        sleeve_weight=w_sleeve,
        reserve_weight=reserve,
        spy_frac=spy_frac,
        sgov_frac=sgov_frac,
        spy_target_weight=spy_target_w,
        sgov_target_weight=sgov_target_w,
        spy_target_notional=spy_target_w * pv,
        sgov_target_notional=sgov_target_w * pv,
        beta_positions=book.beta_positions,
        beta_book_estimate=beta_book,
        regime=book.regime,
        regime_override_active=regime_override,
        enabled=config.enabled,
    )


def write_shadow_log(
    allocation: SleeveAllocation,
    log_path: Path,
    *,
    record_extras: dict[str, Any] | None = None,
) -> None:
    """Append a shadow allocation record to JSONL (observe-only)."""
    record = allocation.to_dict()
    if record_extras:
        record.update(record_extras)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    log.info(
        "sleeve shadow: spy_frac=%.3f sgov_frac=%.3f β_book=%.3f regime=%s override=%s",
        allocation.spy_frac,
        allocation.sgov_frac,
        allocation.beta_book_estimate,
        allocation.regime,
        allocation.regime_override_active,
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {path}")
    return payload


def _load_sleeve_config(path: Path) -> SleeveConfig:
    raw = _load_json_object(path)
    section = raw.get("sleeve")
    if isinstance(section, dict):
        return SleeveConfig.from_dict(section)
    return SleeveConfig.from_dict(raw)


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"runs DB not found: {db_path}")
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _build_runtime_book_state(
    *,
    db_path: Path,
    ohlcv_dir: Path,
    run_type: str = "live",
) -> tuple[BookState, dict[str, Any]]:
    """Derive the sleeve book-state inputs from the live run DB + OHLCV store.

    This keeps the scheduled-job entrypoint observe-only and repo-local: it reuses
    the orchestrator's existing read-only position/beta primitives instead of
    inventing a second source of truth for book weights or beta composition.
    """
    from .risk_budget import budget as bd

    with _connect_ro(db_path) as conn:
        positions = bd.latest_positions(conn, run_type=run_type)
        if positions.get("censored"):
            raise ValueError(str(positions["censored"]))

        pv = positions.get("portfolio_value")
        if not isinstance(pv, (int, float)) or float(pv) <= 0:
            raise ValueError("latest live run missing positive portfolio_value")

        tickers = [
            str(p["ticker"])
            for p in (positions.get("positions") or [])
            if p.get("ticker") and p.get("weight")
        ]
        close_by_ticker = {
            ticker: bd.load_close_series(ohlcv_dir, ticker)
            for ticker in sorted(set(tickers + [bd.BENCHMARK_TICKER]))
        }
        betas = bd.per_name_betas(close_by_ticker)
        beta_comp = bd.beta_composition(positions, betas, sleeve_reading=None)

    if tickers:
        beta_positions = beta_comp.get("book_beta_measured_names")
        unmeasured_weight = float(beta_comp.get("unmeasured_weight") or 0.0)
        if beta_positions is None:
            raise ValueError("book beta unavailable for current held positions")
        if unmeasured_weight > 0:
            raise ValueError(
                "book beta censored for current positions; refusing to size sleeve on partial beta"
            )
        beta_positions_value = float(beta_positions)
    else:
        beta_positions_value = 0.0

    invested_weight = float(positions.get("invested_weight") or 0.0)
    cash_weight = float(positions.get("cash_weight") or 0.0)
    book = BookState(
        portfolio_value=float(pv),
        positions_value=invested_weight * float(pv),
        cash_value=cash_weight * float(pv),
        beta_positions=beta_positions_value,
        regime=str(positions.get("regime") or "UNKNOWN"),
    )
    meta = {
        "positions": positions,
        "beta_composition": beta_comp,
        "beta_censored_names": beta_comp.get("censored_names") or {},
        "db_path": str(db_path),
        "ohlcv_dir": str(ohlcv_dir),
        "run_type": run_type,
    }
    return book, meta


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for shadow parking-sleeve computation."""
    import argparse
    import sys as _sys

    parser = argparse.ArgumentParser(
        prog="renquant-orchestrator parking-sleeve",
        description="Compute shadow parking-sleeve allocation (observe-only)",
    )
    parser.add_argument(
        "--book-state-json", default=None,
        help="JSON file with book state: portfolio_value, positions_value, "
        "cash_value, beta_positions, regime. When omitted, derive book state "
        "read-only from the latest live run + OHLCV store.",
    )
    parser.add_argument(
        "--config-json", default=None,
        help="JSON file with the sleeve section or full strategy config "
        "(default: auto-resolved strategy_config.json)",
    )
    parser.add_argument(
        "--db", default=None,
        help="runs.alpaca.db path for auto book-state mode (default: auto-resolved)",
    )
    parser.add_argument(
        "--ohlcv-dir", default=None,
        help="daily OHLCV store for auto book-state mode (default: auto-resolved)",
    )
    parser.add_argument(
        "--data-root", default=None,
        help="operator data root (default: RENQUANT_DATA_ROOT or repo-root fallback)",
    )
    parser.add_argument(
        "--run-type", default="live",
        help="pipeline_runs.run_type to inspect in auto book-state mode (default: live)",
    )
    parser.add_argument(
        "--shadow-log", default=None,
        help="path to append shadow allocation JSONL record "
        "(default: auto-resolved parking_sleeve_shadow.jsonl in data root)",
    )

    args = parser.parse_args(argv)

    data_root = Path(args.data_root) if args.data_root else default_data_root()
    config_path = Path(args.config_json) if args.config_json else default_strategy_config_path()
    config = _load_sleeve_config(config_path)

    runtime_meta: dict[str, Any] = {
        "config_path": str(config_path),
        "data_root": str(data_root),
    }

    if args.book_state_json:
        book_data = _load_json_object(Path(args.book_state_json))
        book = BookState(
            portfolio_value=float(book_data["portfolio_value"]),
            positions_value=float(book_data["positions_value"]),
            cash_value=float(book_data["cash_value"]),
            beta_positions=float(book_data["beta_positions"]),
            regime=str(book_data["regime"]),
        )
        runtime_meta["book_state_source"] = str(Path(args.book_state_json))
    else:
        db_path = Path(args.db) if args.db else default_runs_db_path(data_root)
        ohlcv_dir = Path(args.ohlcv_dir) if args.ohlcv_dir else default_ohlcv_dir(data_root)
        book, derived_meta = _build_runtime_book_state(
            db_path=db_path,
            ohlcv_dir=ohlcv_dir,
            run_type=str(args.run_type),
        )
        runtime_meta.update(derived_meta)
        runtime_meta["book_state_source"] = "latest_live_run"

    allocation = compute_sleeve_allocation(book, config)

    shadow_log: Path | None
    if args.shadow_log:
        shadow_log = Path(args.shadow_log)
    elif args.book_state_json:
        shadow_log = None
    else:
        shadow_log = default_shadow_log_path(data_root)

    if shadow_log is not None:
        record_extras = {
            "book_state": {
                **allocation.to_dict(),
                "sleeve_contribution_pct": None,
                "dd_budget_pct": None,
                "dd_budget_consumption_pct": None,
                "max_dd_budget_consumption_pct": None,
            },
            "input_book_state": dataclasses.asdict(book),
            "runtime": runtime_meta,
        }
        write_shadow_log(
            allocation,
            shadow_log,
            record_extras=record_extras,
        )

    _sys.stdout.write(json.dumps(allocation.to_dict(), indent=2, sort_keys=True) + "\n")
    return 0


def _zero_allocation(
    book: BookState, config: SleeveConfig, *, reason: str
) -> SleeveAllocation:
    """Return a zeroed-out allocation when computation is impossible."""
    return SleeveAllocation(
        as_of=dt.date.today().isoformat(),
        portfolio_value=book.portfolio_value,
        positions_weight=0.0,
        sleeve_weight=0.0,
        reserve_weight=config.reserve_pct,
        spy_frac=0.0,
        sgov_frac=1.0,
        spy_target_weight=0.0,
        sgov_target_weight=0.0,
        spy_target_notional=0.0,
        sgov_target_notional=0.0,
        beta_positions=0.0,
        beta_book_estimate=0.0,
        regime=book.regime,
        regime_override_active=False,
        enabled=config.enabled,
    )
