"""Parking sleeve allocator — β-budgeted SPY/SGOV split (S7, shadow-only).

Computes the target parking-sleeve allocation from current book state using the
RS-1 β-budget formula. The SPY fraction is sized so that total book beta stays
within the planning budget (β_max = 0.6 by default). SGOV absorbs the rest.

    sleeve_spy_frac = clamp(0, 1, (β_max − β_positions) / β_spy)

where β_positions is the measured beta contribution from single-name holdings
(positions_value / portfolio_value × β_portfolio_ex_sleeve) and β_spy ≈ 1.0.

This module is OBSERVE-ONLY: it logs shadow allocations to a JSONL file. It
never places orders, never modifies config, and never touches production state.
Arming requires the pre-registration gate per RS-1 §4 / #228 §1.3.

Regime override: BEAR → sleeve_spy_frac = 0 (100% SGOV / cash).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

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
        return dataclasses.asdict(self)


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
) -> None:
    """Append a shadow allocation record to JSONL (observe-only)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(allocation.to_dict(), sort_keys=True) + "\n")
    log.info(
        "sleeve shadow: spy_frac=%.3f sgov_frac=%.3f β_book=%.3f regime=%s override=%s",
        allocation.spy_frac,
        allocation.sgov_frac,
        allocation.beta_book_estimate,
        allocation.regime,
        allocation.regime_override_active,
    )


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
