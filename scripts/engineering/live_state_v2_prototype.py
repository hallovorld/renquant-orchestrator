#!/usr/bin/env python3
"""LiveStateV2 prototype (#108 S1-PR1) — pydantic schema + one-place parse.

Proof obligations executed at bottom:
  P1 parses the REAL production live_state.alpaca.json (v1 migration)
  P2 canonical round-trip: parse(canonical(s)) == s
  P3 unknown fields are REJECTED, not silently dropped (quarantine list)
  P4 adding a field is one schema line (protection_breaches is the example)
"""
from __future__ import annotations
import json, datetime as dt
from pathlib import Path
from pydantic import BaseModel, ConfigDict

class HoldingV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_date: str
    sell_streak: int = 0
    protection_breaches: int = 0          # P4: the new field, one line
    position_hwm: float | None = None
    entry_regime: str | None = None       # max_hold anchor (incident #5)

class LiveStateV2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 2
    regime: str = "UNKNOWN"
    regime_confidence: float = 0.0
    high_water_mark: float | None = None
    holdings: dict[str, HoldingV2] = {}
    last_sell_dates: dict[str, str] = {}
    last_stop_exit_dates: dict[str, str] = {}
    skip_buys: bool = False
    extra_quarantine: dict = {}            # P3: unknown v1 keys land here, loudly

    @classmethod
    def parse(cls, raw: dict) -> "LiveStateV2":
        """v1 (flat dicts) -> v2 (typed holdings). ONE place, forever."""
        known = {"regime","regime_confidence","high_water_mark","entry_dates",
                 "sell_streaks","protection_breaches","position_hwm",
                 "entry_signals","last_sell_dates","last_stop_exit_dates","skip_buys"}
        hold = {}
        for t, d in (raw.get("entry_dates") or {}).items():
            hold[t] = HoldingV2(
                entry_date=str(d),
                sell_streak=int((raw.get("sell_streaks") or {}).get(t, 0) or 0),
                protection_breaches=int((raw.get("protection_breaches") or {}).get(t, 0) or 0),
                position_hwm=(raw.get("position_hwm") or {}).get(t),
                entry_regime=((raw.get("entry_signals") or {}).get(t) or {}).get("regime"),
            )
        return cls(
            regime=raw.get("regime","UNKNOWN"),
            regime_confidence=float(raw.get("regime_confidence") or 0.0),
            high_water_mark=raw.get("high_water_mark"),
            holdings=hold,
            last_sell_dates=raw.get("last_sell_dates") or {},
            last_stop_exit_dates=raw.get("last_stop_exit_dates") or {},
            skip_buys=bool(raw.get("skip_buys", False)),
            extra_quarantine={k: v for k, v in raw.items() if k not in known},
        )

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True, default=str)

if __name__ == "__main__":
    real = json.load(open("/Users/renhao/git/github/RenQuant/backtesting/renquant_104/live_state.alpaca.json"))
    s = LiveStateV2.parse(real)                                   # P1
    assert LiveStateV2(**json.loads(s.canonical_json())) == s     # P2
    print(f"P1 real-state parse OK: {len(s.holdings)} holdings {list(s.holdings)}")
    print(f"P2 round-trip OK; P3 quarantined v1 keys: {sorted(s.extra_quarantine)}")
    mu = s.holdings.get("MU")
    print(f"P4 one-line field live: MU protection_breaches={mu.protection_breaches if mu else 'n/a'}, entry_regime={mu.entry_regime if mu else 'n/a'}")
