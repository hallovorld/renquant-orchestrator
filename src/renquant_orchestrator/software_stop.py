"""Per-position intraday software stops for renquant105 sessions.

Complements the existing stop layers:
- ``gtc_catastrophe_planner.py`` — broker-resident GTC stops at −20% (survives host death)
- ``CanaryEnvelopeTracker`` — session-level cumulative loss budget (§9.3a)

This module adds per-position INTRADAY stops evaluated each tick:
- **Hard stop**: exit if unrealized loss exceeds a fixed % of entry price
- **Trailing stop**: exit if price drops a fixed % below the session high-water mark

Shadow-only by default. Generates ``StopSignal`` records logged to the
shadow decision log; actual order submission requires the Stage-2 quintuple
gate + prereg authorization (§9.3a). The stop evaluator is wired into the
session runner's tick loop as an observe+signal layer — it never talks to a
broker directly.

Integration: the session runner calls ``evaluate_tick`` with current quotes
each tick. Stop signals are returned as exit intents the runner may fold
into the decision payload (when armed) or log as shadow observations.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

log = logging.getLogger("renquant.software_stop")

DEFAULT_HARD_STOP_PCT = 0.05
DEFAULT_TRAILING_STOP_PCT = 0.03
SCHEMA_VERSION = "rq105-software-stop-v1"


@dataclass(frozen=True)
class StopConfig:
    """Per-position stop parameters, loaded from the authorization payload."""

    hard_stop_pct: float = DEFAULT_HARD_STOP_PCT
    trailing_stop_pct: float = DEFAULT_TRAILING_STOP_PCT
    enabled: bool = False

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "StopConfig":
        if payload is None:
            return cls()
        return cls(
            hard_stop_pct=float(payload.get("hard_stop_pct", DEFAULT_HARD_STOP_PCT)),
            trailing_stop_pct=float(payload.get("trailing_stop_pct", DEFAULT_TRAILING_STOP_PCT)),
            enabled=bool(payload.get("enabled", False)),
        )


@dataclass(frozen=True)
class StopSignal:
    """A stop-triggered exit signal for one position."""

    symbol: str
    stop_type: str  # "hard_stop" | "trailing_stop"
    entry_price: float
    current_price: float
    session_hwm: float
    loss_pct: float
    threshold_pct: float
    timestamp: str

    def to_intent(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": "SELL",
            "kind": "exit",
            "reason": self.stop_type,
            "price": self.current_price,
            "stop_detail": asdict(self),
        }


@dataclass
class _PositionState:
    symbol: str
    entry_price: float
    session_hwm: float
    stopped: bool = False
    stop_type: str | None = None


@dataclass
class SoftwareStopEvaluator:
    """Evaluates per-position stops each tick. Stateful within a session."""

    config: StopConfig
    positions: dict[str, _PositionState] = field(default_factory=dict)
    signals_emitted: list[StopSignal] = field(default_factory=list)

    def load_positions(self, holdings: Mapping[str, Mapping[str, Any]]) -> None:
        """Initialize position tracking from the session-start book state.

        ``holdings``: ``{symbol: {entry_price: float, ...}}``.
        Only positions with a known entry price can be stop-tracked.
        """
        for symbol, info in holdings.items():
            entry = info.get("entry_price") or info.get("avg_entry_price")
            if entry is None:
                continue
            entry = float(entry)
            if entry <= 0:
                continue
            sym = str(symbol).upper()
            if sym not in self.positions:
                self.positions[sym] = _PositionState(
                    symbol=sym,
                    entry_price=entry,
                    session_hwm=entry,
                )

    def evaluate_tick(
        self,
        quotes: Mapping[str, float],
        *,
        now: datetime | None = None,
    ) -> list[StopSignal]:
        """Evaluate stops for all tracked positions against current quotes.

        Returns a list of newly-triggered stop signals (each position fires
        at most once per session — the stop is sticky).
        """
        if not self.config.enabled:
            return []
        ts = (now or datetime.now(timezone.utc)).isoformat()
        signals: list[StopSignal] = []
        for sym, pos in self.positions.items():
            if pos.stopped:
                continue
            price_raw = quotes.get(sym)
            if price_raw is None:
                continue
            try:
                price = float(price_raw)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            if price > pos.session_hwm:
                pos.session_hwm = price

            hard_loss = (pos.entry_price - price) / pos.entry_price
            if hard_loss >= self.config.hard_stop_pct:
                signal = StopSignal(
                    symbol=sym,
                    stop_type="hard_stop",
                    entry_price=pos.entry_price,
                    current_price=price,
                    session_hwm=pos.session_hwm,
                    loss_pct=hard_loss,
                    threshold_pct=self.config.hard_stop_pct,
                    timestamp=ts,
                )
                pos.stopped = True
                pos.stop_type = "hard_stop"
                signals.append(signal)
                self.signals_emitted.append(signal)
                continue

            trailing_loss = (pos.session_hwm - price) / pos.session_hwm
            if trailing_loss >= self.config.trailing_stop_pct:
                signal = StopSignal(
                    symbol=sym,
                    stop_type="trailing_stop",
                    entry_price=pos.entry_price,
                    current_price=price,
                    session_hwm=pos.session_hwm,
                    loss_pct=trailing_loss,
                    threshold_pct=self.config.trailing_stop_pct,
                    timestamp=ts,
                )
                pos.stopped = True
                pos.stop_type = "trailing_stop"
                signals.append(signal)
                self.signals_emitted.append(signal)
        return signals

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "config": asdict(self.config),
            "positions_tracked": len(self.positions),
            "positions_stopped": sum(1 for p in self.positions.values() if p.stopped),
            "signals_emitted": len(self.signals_emitted),
            "positions": {
                sym: {
                    "entry_price": p.entry_price,
                    "session_hwm": p.session_hwm,
                    "stopped": p.stopped,
                    "stop_type": p.stop_type,
                }
                for sym, p in sorted(self.positions.items())
            },
        }


class SoftwareStopShadowLog:
    """Append-only shadow log for stop signals (observe-only, no execution)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.records_written = 0

    def append(self, signal: StopSignal, *, session_date: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "schema_version": SCHEMA_VERSION,
            "kind": "software_stop_signal",
            "session_date": session_date,
            **asdict(signal),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        self.records_written += 1


def default_stop_log_path(data_root: Path | None = None) -> Path:
    if data_root is None:
        from .runtime_paths import default_data_root
        data_root = default_data_root()
    return Path(data_root) / "logs" / "renquant105_pilot" / "software_stop_shadow.jsonl"
