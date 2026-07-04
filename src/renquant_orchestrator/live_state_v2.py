"""LiveStateV2 (#108 S1) — one typed schema + one parse/serialize choke point.

Replaces the flat, untyped ``live_state.alpaca.json`` dict-of-dicts that the
runner mutates field-by-field. Measured cost of the status quo: adding ONE state
field touched 9 sites (#294). Here a new per-holding field is a single schema
line (``protection_breaches`` is the worked example).

Migration contract (strangler-fig — the runner adopts v2 internally while the
rest of the system keeps reading the v1 file):

  * ``parse(v1_dict)``      v1 flat dicts -> typed v2
  * ``to_v1_dict()``        typed v2 -> v1 flat dicts, **byte-for-byte lossless**
  * unknown top-level keys are preserved verbatim (``extra_quarantine``) and
    re-emitted on ``to_v1_dict`` — never silently dropped
  * per-holding source dicts (``sell_streaks`` / ``protection_breaches`` /
    ``position_hwm`` / ``entry_signals``) whose ticker is absent from
    ``entry_dates`` are an inconsistency: ``parse`` fails loud rather than lose
    them.

The lossless round-trip (``to_v1_dict(parse(s)) == s``) is the safety property
that lets the runner switch to the typed model without risking live state.
"""
from __future__ import annotations

import json
from typing import Any, Optional  # noqa: UP035 — Pydantic evaluates at runtime, needs 3.9 compat

from pydantic import BaseModel, ConfigDict

# Top-level v1 keys this schema models explicitly. Everything else is preserved
# verbatim through extra_quarantine (monitor_state, regime_state, stop_orders,
# recent_sell_orders, …) so the runner can migrate one field at a time.
_PER_HOLDING_KEYS = ("sell_streaks", "protection_breaches", "position_hwm",
                     "entry_signals")
_MODELLED_TOP_KEYS = frozenset({
    "regime", "regime_confidence", "high_water_mark", "skip_buys",
    "entry_dates", "last_sell_dates", "last_stop_exit_dates",
    *_PER_HOLDING_KEYS,
})


class HoldingV2(BaseModel):
    """One open position. Add a per-holding field here in ONE line."""

    model_config = ConfigDict(extra="forbid")

    entry_date: str
    sell_streak: int = 0
    protection_breaches: int = 0           # the one-line field (#294 example)
    position_hwm: Optional[float] = None  # noqa: UP007
    entry_signal: Optional[dict[str, Any]] = None  # noqa: UP007

    @property
    def entry_regime(self) -> str | None:
        """max_hold anchor (incident #5) — derived, not stored."""
        return (self.entry_signal or {}).get("regime")


class LiveStateV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 2
    regime: str = "UNKNOWN"
    regime_confidence: float = 0.0
    high_water_mark: Optional[float] = None  # noqa: UP007
    skip_buys: bool = False
    holdings: dict[str, HoldingV2] = {}
    last_sell_dates: dict[str, str] = {}
    last_stop_exit_dates: dict[str, str] = {}
    # Unmodelled v1 keys, kept verbatim and re-emitted on to_v1_dict().
    extra_quarantine: dict[str, Any] = {}

    @classmethod
    def parse(cls, raw: dict) -> "LiveStateV2":
        """v1 (flat per-ticker dicts) -> typed v2. The ONE migration site."""
        entry_dates = dict(raw.get("entry_dates") or {})
        tickers = set(entry_dates)

        # Fail loud on per-holding entries that have no entry_date — losing them
        # silently is how live state drifts. (parse-don't-validate.)
        for key in _PER_HOLDING_KEYS:
            orphans = set((raw.get(key) or {})) - tickers
            if orphans:
                raise ValueError(
                    f"live_state {key!r} has entries with no entry_date: "
                    f"{sorted(orphans)} — refusing to drop them"
                )

        sell_streaks = raw.get("sell_streaks") or {}
        breaches = raw.get("protection_breaches") or {}
        position_hwm = raw.get("position_hwm") or {}
        entry_signals = raw.get("entry_signals") or {}

        holdings = {
            t: HoldingV2(
                entry_date=str(d),
                sell_streak=int(sell_streaks.get(t, 0) or 0),
                protection_breaches=int(breaches.get(t, 0) or 0),
                position_hwm=position_hwm.get(t),
                entry_signal=entry_signals.get(t),
            )
            for t, d in entry_dates.items()
        }
        return cls(
            regime=raw.get("regime", "UNKNOWN"),
            regime_confidence=float(raw.get("regime_confidence") or 0.0),
            high_water_mark=raw.get("high_water_mark"),
            skip_buys=bool(raw.get("skip_buys", False)),
            holdings=holdings,
            last_sell_dates=dict(raw.get("last_sell_dates") or {}),
            last_stop_exit_dates=dict(raw.get("last_stop_exit_dates") or {}),
            extra_quarantine={k: v for k, v in raw.items()
                              if k not in _MODELLED_TOP_KEYS},
        )

    def to_v1_dict(self) -> dict:
        """Typed v2 -> v1 flat dicts. Lossless inverse of parse().

        Per-holding fields fan back out into the v1 ticker-keyed dicts;
        ``position_hwm`` and ``entry_signals`` are emitted only for holdings that
        carried them, matching v1 sparsity. Quarantined keys are merged back
        verbatim.
        """
        out: dict[str, Any] = {
            "regime": self.regime,
            "regime_confidence": self.regime_confidence,
            "high_water_mark": self.high_water_mark,
            "skip_buys": self.skip_buys,
            "entry_dates": {t: h.entry_date for t, h in self.holdings.items()},
            "sell_streaks": {t: h.sell_streak for t, h in self.holdings.items()},
            "protection_breaches": {t: h.protection_breaches
                                    for t, h in self.holdings.items()},
            "position_hwm": {t: h.position_hwm for t, h in self.holdings.items()
                             if h.position_hwm is not None},
            "entry_signals": {t: h.entry_signal for t, h in self.holdings.items()
                              if h.entry_signal is not None},
            "last_sell_dates": dict(self.last_sell_dates),
            "last_stop_exit_dates": dict(self.last_stop_exit_dates),
        }
        out.update(self.extra_quarantine)
        return out

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True, default=str)
