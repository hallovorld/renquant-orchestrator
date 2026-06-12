#!/usr/bin/env python3
"""StrategyConfig schema prototype (#108 S1-PR6) — typed top level, warn-only.

Strategy: don't boil the 841-key ocean. Type the DANGEROUS top level
(regime thresholds, risk caps, sizing) with extra-key telemetry, so typos
fail at load. Run against the REAL production config + golden, and against
mutated configs to prove typos are caught.
"""
from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, ValidationError, confloat, conint

R = "/Users/renhao/git/github/renquant-strategy-104/configs"


class RegimeCfg(BaseModel):
    model_config = ConfigDict(extra="allow")
    bear_vol_threshold: confloat(gt=0, lt=2)
    bear_return_threshold: confloat(gt=-1, lt=0)
    bear_vol_threshold_5d: confloat(gt=0, lt=2)
    bear_return_threshold_5d: confloat(gt=-1, lt=0)
    transition_uncertainty_bars: conint(ge=0, le=30)
    bear_short_route_require_both: bool


class StrategyConfigTop(BaseModel):
    model_config = ConfigDict(extra="allow")
    model_name: str
    watchlist: list[str]
    benchmark: str
    wash_sale_days: conint(ge=0, le=61)
    min_hold_days: conint(ge=0, le=120)
    max_hold_days: conint(ge=0, le=2000)
    max_concurrent_positions: conint(ge=1, le=50)
    regime: RegimeCfg

    def extra_key_count(self) -> int:
        return len(self.model_extra or {})


if __name__ == "__main__":
    for name in ("strategy_config.json", "strategy_config.golden.json"):
        raw = json.load(open(f"{R}/{name}"))
        cfg = StrategyConfigTop(**raw)
        print(f"P1 {name}: typed OK — watchlist={len(cfg.watchlist)}, "
              f"max_pos={cfg.max_concurrent_positions}, "
              f"untyped-extra-top-keys={cfg.extra_key_count()} (telemetry for gradual typing)")
    # P2: classic typo classes are caught at load, not mid-trade
    raw = json.load(open(f"{R}/strategy_config.json"))
    bad1 = json.loads(json.dumps(raw))
    bad1["wash_sale_days"] = 3000
    bad2 = json.loads(json.dumps(raw))
    bad2["regime"]["bear_return_threshold_5d"] = 0.04   # sign flip!
    bad3 = json.loads(json.dumps(raw))
    bad3["max_concurrent_positions"] = 0
    caught = 0
    for i, bad in enumerate((bad1, bad2, bad3), 1):
        try:
            StrategyConfigTop(**bad)
            print(f"P2.{i} MISSED")
        except ValidationError as e:
            caught += 1
            print(f"P2.{i} caught at load: {e.errors()[0]['loc']} -> {e.errors()[0]['msg'][:40]}")
    assert caught == 3
    print("ALL PROOFS PASS — incl. the sign-flip class (a positive bear_return_threshold_5d "
          "would have silently disabled the acute-loss BEAR route)")
