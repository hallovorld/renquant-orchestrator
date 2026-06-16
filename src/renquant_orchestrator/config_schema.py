"""StrategyConfig schema (#108 S1) — type the DANGEROUS top level, warn-only.

Don't boil the 800+-key ocean. Type the keys whose typos are catastrophic —
regime thresholds, risk caps, sizing/hold limits — with ``extra="allow"`` so the
hundreds of untyped keys pass through untouched (and are counted as telemetry for
gradual typing). The payoff: a sign-flipped ``bear_return_threshold_5d`` or an
out-of-range ``wash_sale_days`` fails at config load, not mid-trade.

``validate_strategy_config(raw)`` is the one gate; ``load_strategy_config(path)``
reads + validates a config file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class RegimeCfg(BaseModel):
    """Regime-detection thresholds. Sign and magnitude both matter: a positive
    ``bear_return_threshold`` silently disables the acute-loss BEAR route."""

    model_config = ConfigDict(extra="allow")

    bear_vol_threshold: Annotated[float, Field(gt=0, lt=2)]
    bear_return_threshold: Annotated[float, Field(gt=-1, lt=0)]
    bear_vol_threshold_5d: Annotated[float, Field(gt=0, lt=2)]
    bear_return_threshold_5d: Annotated[float, Field(gt=-1, lt=0)]
    transition_uncertainty_bars: Annotated[int, Field(ge=0, le=30)]
    bear_short_route_require_both: bool


class StrategyConfigTop(BaseModel):
    """Typed top level of the strategy config. ``extra="allow"`` keeps every
    untyped key; ``extra_key_count`` reports how many remain untyped."""

    model_config = ConfigDict(extra="allow")

    model_name: str
    watchlist: list[str]
    benchmark: str
    wash_sale_days: Annotated[int, Field(ge=0, le=61)]
    min_hold_days: Annotated[int, Field(ge=0, le=120)]
    max_hold_days: Annotated[int, Field(ge=0, le=2000)]
    max_concurrent_positions: Annotated[int, Field(ge=1, le=50)]
    regime: RegimeCfg

    def extra_key_count(self) -> int:
        return len(self.model_extra or {})


def validate_strategy_config(raw: dict[str, Any]) -> StrategyConfigTop:
    """Validate a raw config dict. Raises pydantic ValidationError on a typed-key
    typo (out-of-range, sign flip, wrong type); untyped keys pass through."""
    return StrategyConfigTop(**raw)


def load_strategy_config(path: str | Path) -> StrategyConfigTop:
    """Read + validate a strategy config JSON file."""
    return validate_strategy_config(json.loads(Path(path).read_text()))
