"""Crypto sleeve scheduling coordination (G2 S1-S4 + S9).

Orchestrates the daily/weekly crypto pipeline DAG via file-based signaling.
Each step writes a completion marker; downstream steps check upstream markers
before proceeding.

    S1 (ingest, 00:05) → S2 (universe, Sun 00:10) → S3 (signal, 00:15)
    → S4 (sizing, 00:20) → S5 (tick loop, continuous)

S5 (session tick loop) is handled by crypto_session.py.
S8 (liveness) and S9 (report) are independent observers.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("renquant_orchestrator.crypto_scheduling")

CRYPTO_STATE_DIR_NAME = "crypto_state"
COMPLETION_SUFFIX = "_done.json"

DEFAULT_WATCHLIST = [
    "BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "ADA-USD",
    "NEAR-USD", "DOGE-USD", "MATIC-USD", "LINK-USD", "LTC-USD",
    "AAVE-USD", "DOT-USD", "ATOM-USD", "BCH-USD", "APT-USD", "OP-USD",
]

EXCLUDED_PAIRS = ["XRP-USD", "UNI-USD", "FIL-USD", "ARB-USD"]


@dataclass(frozen=True)
class CryptoScheduleConfig:
    state_dir: Path = Path("data") / CRYPTO_STATE_DIR_NAME
    watchlist: tuple[str, ...] = tuple(DEFAULT_WATCHLIST)
    excluded_pairs: tuple[str, ...] = tuple(EXCLUDED_PAIRS)
    universe_top_n: int = 5
    min_sharpe_90d: float = 0.0
    sma_period: int = 50
    sleeve_budget_usd: float = 5350.0
    mode: str = "paper"


@dataclass
class CompletionMarker:
    step: str
    session_date: str
    completed_at_utc: str
    status: str
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _state_dir(cfg: CryptoScheduleConfig) -> Path:
    d = cfg.state_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_completion_marker(cfg: CryptoScheduleConfig, marker: CompletionMarker) -> Path:
    d = _state_dir(cfg)
    fname = f"{marker.step}_{marker.session_date}{COMPLETION_SUFFIX}"
    path = d / fname
    path.write_text(json.dumps(marker.to_dict(), indent=2, sort_keys=True) + "\n")
    log.info("wrote completion marker: %s", path)
    return path


def read_completion_marker(
    cfg: CryptoScheduleConfig, step: str, session_date: str,
) -> CompletionMarker | None:
    d = _state_dir(cfg)
    fname = f"{step}_{session_date}{COMPLETION_SUFFIX}"
    path = d / fname
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return CompletionMarker(**data)


def check_upstream(
    cfg: CryptoScheduleConfig, step: str, session_date: str,
) -> bool:
    marker = read_completion_marker(cfg, step, session_date)
    return marker is not None and marker.status == "ok"


def run_universe_rotation(
    cfg: CryptoScheduleConfig,
    session_date: str | None = None,
    prices_90d: dict[str, list[float]] | None = None,
) -> dict:
    """S2: weekly universe rotation — rank by trailing 90d Sharpe.

    prices_90d: {pair: [daily_returns_last_90d]}. If not provided,
    returns an empty selection (caller must supply data).
    """
    import numpy as np

    if session_date is None:
        session_date = str(date.today())

    if prices_90d is None:
        log.warning("S2 universe rotation: no price data supplied")
        return {"pairs": [], "session_date": session_date}

    rankings: list[tuple[str, float]] = []
    exclude_set = set(cfg.excluded_pairs)

    for pair, returns in prices_90d.items():
        if pair in exclude_set:
            continue
        if len(returns) < 60:
            continue
        arr = np.array(returns, dtype=float)
        arr = arr[np.isfinite(arr)]
        if len(arr) < 60:
            continue
        mean_r = float(np.mean(arr))
        std_r = float(np.std(arr, ddof=1))
        if std_r <= 0:
            continue
        sharpe = (mean_r / std_r) * np.sqrt(365.0)
        if sharpe > cfg.min_sharpe_90d:
            rankings.append((pair, round(sharpe, 4)))

    rankings.sort(key=lambda x: x[1], reverse=True)
    selected = rankings[:cfg.universe_top_n]

    result = {
        "session_date": session_date,
        "rankings": [{"pair": p, "sharpe_90d": s} for p, s in rankings],
        "selected": [p for p, _ in selected],
        "n_scored": len(rankings),
        "n_selected": len(selected),
    }

    path = _state_dir(cfg) / f"universe_selection_{session_date}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")

    write_completion_marker(cfg, CompletionMarker(
        step="s2_universe",
        session_date=session_date,
        completed_at_utc=datetime.now(timezone.utc).isoformat(),
        status="ok",
        detail={"n_selected": len(selected), "pairs": [p for p, _ in selected]},
    ))

    log.info("S2 universe rotation: %d scored, %d selected: %s",
             len(rankings), len(selected), [p for p, _ in selected])
    return result


def load_latest_universe(cfg: CryptoScheduleConfig) -> list[str]:
    """Load the most recent universe selection."""
    d = _state_dir(cfg)
    files = sorted(d.glob("universe_selection_*.json"), reverse=True)
    if not files:
        return list(cfg.watchlist)
    data = json.loads(files[0].read_text())
    return data.get("selected", list(cfg.watchlist))


def run_signal_computation(
    cfg: CryptoScheduleConfig,
    session_date: str | None = None,
    universe: list[str] | None = None,
) -> dict:
    """S3: daily signal computation — compute SMA50 for each pair in universe."""
    try:
        from renquant_base_data.crypto_trend_signal import (
            TrendSignalConfig,
            compute_signals,
        )
    except ImportError:
        log.error("renquant_base_data.crypto_trend_signal not available")
        return {"error": "signal module not importable"}

    if session_date is None:
        session_date = str(date.today())
    if universe is None:
        universe = load_latest_universe(cfg)

    signal_cfg = TrendSignalConfig(
        sma_period=cfg.sma_period,
        crypto_ohlcv_dir=cfg.state_dir.parent / "crypto_ohlcv" if cfg.state_dir else None,
    )

    snapshot = compute_signals(universe, signal_cfg, as_of=date.fromisoformat(session_date))
    result = snapshot.to_dict()

    path = _state_dir(cfg) / f"signal_snapshot_{session_date}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")

    write_completion_marker(cfg, CompletionMarker(
        step="s3_signal",
        session_date=session_date,
        completed_at_utc=datetime.now(timezone.utc).isoformat(),
        status="ok",
        detail={"n_long": snapshot.n_long, "n_cash": snapshot.n_cash, "digest": snapshot.digest},
    ))

    log.info("S3 signal: %d LONG, %d CASH, digest=%s",
             snapshot.n_long, snapshot.n_cash, snapshot.digest[:24])
    return result


def load_latest_signals(cfg: CryptoScheduleConfig) -> dict | None:
    """Load the most recent signal snapshot."""
    d = _state_dir(cfg)
    files = sorted(d.glob("signal_snapshot_*.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text())


def run_portfolio_sizing(
    cfg: CryptoScheduleConfig,
    session_date: str | None = None,
    current_positions: dict[str, dict] | None = None,
    current_prices: dict[str, float] | None = None,
) -> dict:
    """S4: daily portfolio sizing — translate signals into actions."""
    try:
        from renquant_pipeline.kernel.crypto_portfolio import (
            CryptoPortfolioConfig,
            SleeveState,
            Position,
            compute_portfolio_actions,
        )
    except ImportError:
        log.error("renquant_pipeline.kernel.crypto_portfolio not available")
        return {"error": "portfolio module not importable"}

    if session_date is None:
        session_date = str(date.today())

    signals_data = load_latest_signals(cfg)
    if signals_data is None:
        log.warning("S4: no signal snapshot available")
        return {"error": "no signal snapshot", "session_date": session_date}

    signal_map = {
        s["pair"]: s["signal"]
        for s in signals_data.get("signals", [])
    }
    if current_prices is None:
        current_prices = {
            s["pair"]: s["close"]
            for s in signals_data.get("signals", [])
        }

    state = SleeveState()
    if current_positions:
        for pair, pos_data in current_positions.items():
            state.positions[pair] = Position(
                pair=pair,
                qty=pos_data.get("qty", 0),
                entry_price=pos_data.get("entry_price", 0),
                entry_date=date.fromisoformat(pos_data.get("entry_date", session_date)),
                current_price=current_prices.get(pair, 0),
            )

    port_cfg = CryptoPortfolioConfig(sleeve_budget_usd=cfg.sleeve_budget_usd)
    actions = compute_portfolio_actions(
        signal_map, current_prices, state, port_cfg,
        today=date.fromisoformat(session_date),
    )

    result = {
        "session_date": session_date,
        "actions": [
            {
                "pair": a.pair,
                "action": a.action.value,
                "target_notional": round(a.target_notional, 2),
                "current_notional": round(a.current_notional, 2),
                "reason": a.reason,
            }
            for a in actions
        ],
        "n_actions": len(actions),
        "signal_digest": signals_data.get("digest", ""),
    }

    path = _state_dir(cfg) / f"portfolio_actions_{session_date}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")

    write_completion_marker(cfg, CompletionMarker(
        step="s4_sizing",
        session_date=session_date,
        completed_at_utc=datetime.now(timezone.utc).isoformat(),
        status="ok",
        detail={"n_actions": len(actions)},
    ))

    log.info("S4 sizing: %d actions", len(actions))
    return result


def crypto_status(cfg: CryptoScheduleConfig) -> dict:
    """Summary of the crypto sleeve's current state."""
    d = _state_dir(cfg)

    universe_files = sorted(d.glob("universe_selection_*.json"), reverse=True)
    signal_files = sorted(d.glob("signal_snapshot_*.json"), reverse=True)
    action_files = sorted(d.glob("portfolio_actions_*.json"), reverse=True)

    universe = json.loads(universe_files[0].read_text()) if universe_files else None
    signals = json.loads(signal_files[0].read_text()) if signal_files else None
    actions = json.loads(action_files[0].read_text()) if action_files else None

    return {
        "mode": cfg.mode,
        "sleeve_budget_usd": cfg.sleeve_budget_usd,
        "sma_period": cfg.sma_period,
        "universe": {
            "file": str(universe_files[0]) if universe_files else None,
            "selected": universe.get("selected") if universe else None,
            "n_scored": universe.get("n_scored") if universe else None,
        },
        "signals": {
            "file": str(signal_files[0]) if signal_files else None,
            "n_long": signals.get("n_long") if signals else None,
            "n_cash": signals.get("n_cash") if signals else None,
            "digest": signals.get("digest") if signals else None,
        },
        "actions": {
            "file": str(action_files[0]) if action_files else None,
            "n_actions": actions.get("n_actions") if actions else None,
        },
        "watchlist_size": len(cfg.watchlist),
        "excluded_pairs": list(cfg.excluded_pairs),
    }
