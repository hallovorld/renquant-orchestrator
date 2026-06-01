"""Market-anomaly retrain trigger pipeline.

The scheduled umbrella wrapper uses this module to decide whether a SPY/VIX
shock should launch the weekly WF trust-boundary chain.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
import json
import logging
import math
import sys

from renquant_common import Job, Pipeline, Task


log = logging.getLogger("renquant-orchestrator.anomaly-triggers")
PctChangeFetcher = Callable[[str], float | None]


def pct_change_from_closes(closes: Sequence[float]) -> float | None:
    """Return latest/prior close change for a close series."""
    values = [float(v) for v in closes if math.isfinite(float(v))]
    if len(values) < 2:
        return None
    prior = values[-2]
    if prior <= 0:
        return None
    return (values[-1] / prior) - 1.0


def fetch_yfinance_pct_change(symbol: str) -> float | None:
    """Fetch a 5-day close window from yfinance and return daily pct change."""
    import yfinance as yf  # noqa: PLC0415

    try:
        hist = yf.Ticker(symbol).history(period="5d", auto_adjust=False, actions=False)
    except Exception as exc:  # pragma: no cover - network/provider dependent
        log.warning("yfinance fetch failed for %s: %s", symbol, exc)
        return None
    if hist is None or "Close" not in hist:
        log.warning("No close history returned for %s", symbol)
        return None
    closes = hist["Close"].dropna().tolist()
    change = pct_change_from_closes(closes)
    if change is None:
        log.warning("Insufficient valid closes for %s", symbol)
    return change


def _threshold_tag(prefix: str, threshold: float, default: float, default_tag: str) -> str:
    if math.isclose(threshold, default, rel_tol=0.0, abs_tol=1e-12):
        return default_tag
    return f"anomaly_{prefix}_{int(threshold * 1000)}bp"


def evaluate_triggers(
    *,
    spy_change: float | None,
    vix_change: float | None,
    spy_pct: float,
    vix_pct: float,
) -> list[str]:
    """Evaluate configured anomaly thresholds and return trigger tags."""
    triggers: list[str] = []
    if spy_change is not None and abs(spy_change) > spy_pct:
        triggers.append(_threshold_tag("spy", spy_pct, 0.02, "anomaly_spy_2pct"))
    if vix_change is not None and abs(vix_change) > vix_pct:
        triggers.append(_threshold_tag("vix", vix_pct, 0.05, "anomaly_vix_5pct"))
    return triggers


@dataclass
class AnomalyTriggerContext:
    spy_pct: float = 0.02
    vix_pct: float = 0.05
    fetch_pct_change: PctChangeFetcher = field(default_factory=lambda: fetch_yfinance_pct_change)
    dry_run: bool = False
    changes: dict[str, float | None] = field(default_factory=dict)
    triggers: list[str] = field(default_factory=list)


class FetchMarketMovesTask(Task):
    def run(self, ctx: AnomalyTriggerContext) -> bool | None:
        spy_change = ctx.fetch_pct_change("^SPY")
        if spy_change is None:
            spy_change = ctx.fetch_pct_change("SPY")
        vix_change = ctx.fetch_pct_change("^VIX")
        ctx.changes = {"SPY": spy_change, "VIX": vix_change}
        return True


class EvaluateAnomalyTriggersTask(Task):
    def run(self, ctx: AnomalyTriggerContext) -> bool | None:
        spy_change = ctx.changes.get("SPY")
        vix_change = ctx.changes.get("VIX")
        if spy_change is not None:
            log.info("SPY daily change: %+.2f%% (threshold +/-%.2f%%)", spy_change * 100, ctx.spy_pct * 100)
        if vix_change is not None:
            log.info("VIX daily change: %+.2f%% (threshold +/-%.2f%%)", vix_change * 100, ctx.vix_pct * 100)
        ctx.triggers = evaluate_triggers(
            spy_change=spy_change,
            vix_change=vix_change,
            spy_pct=ctx.spy_pct,
            vix_pct=ctx.vix_pct,
        )
        return True


class MarketMoveJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [FetchMarketMovesTask(), EvaluateAnomalyTriggersTask()]


def build_pipeline() -> Pipeline:
    return Pipeline([MarketMoveJob()], name="market-anomaly-retrain-triggers")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--spy-pct", type=float, default=0.02)
    parser.add_argument("--vix-pct", type=float, default=0.05)
    parser.add_argument("--dry-run", action="store_true", help="print triggers but always exit 0")
    parser.add_argument("--json", action="store_true", help="emit structured JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    args = parse_args(argv)
    ctx = AnomalyTriggerContext(spy_pct=args.spy_pct, vix_pct=args.vix_pct, dry_run=args.dry_run)
    build_pipeline().run(ctx)
    if args.json:
        print(json.dumps({"changes": ctx.changes, "triggers": ctx.triggers}, sort_keys=True))
    else:
        for trigger in ctx.triggers:
            print(trigger)
    if ctx.triggers and args.dry_run:
        log.info("[dry-run] Would have exited 1 to fire retrain(s): %s", ctx.triggers)
    elif ctx.triggers:
        log.info("Firing retrain triggers: %s", ctx.triggers)
        return 1
    else:
        log.info("No anomaly triggers fired; no retrain needed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
