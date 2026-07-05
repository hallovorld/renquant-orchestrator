#!/usr/bin/env python3
"""S10: Retrospective open-auction implementation shortfall (IS) measurement.

Sizes the 105 prize — how much entry leak exists from filling at/near the open
vs better intraday prices. Read-only study over all historical live buys in
runs.alpaca.db.

Benchmarks:
  - Fill vs same-day OPEN   (are we filling AT the open?)
  - Fill vs same-day VWAP   (intraday execution quality)
  - Fill vs same-day CLOSE  (full-day drift)
  - Fill vs next-day CLOSE  (overnight + next-session opportunity cost)

IS_bps = (fill_price - benchmark_price) / benchmark_price * 10000
Positive = overpaid (filled above benchmark = leak).

Usage:
    # Needs FMP_API_KEY in environment or .env file
    set -a && source /path/to/.env && set +a
    python scripts/s10_open_auction_is.py --db /path/to/runs.alpaca.db --json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import requests

log = logging.getLogger("s10_open_auction_is")

FMP_STABLE = "https://financialmodelingprep.com/stable"
THROTTLE_S = 0.25
BOOTSTRAP_N = 10_000
CI_ALPHA = 0.05


@dataclass
class Trade:
    date: str
    ticker: str
    shares: float
    fill_price: float
    invest: float


@dataclass
class OHLCVDay:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float


@dataclass
class ISResult:
    trade: Trade
    open_price: float | None = None
    vwap_price: float | None = None
    close_price: float | None = None
    next_close_price: float | None = None
    is_vs_open_bps: float | None = None
    is_vs_vwap_bps: float | None = None
    is_vs_close_bps: float | None = None
    is_vs_next_close_bps: float | None = None
    matched: bool = False


def _is_bps(fill: float, benchmark: float) -> float:
    if benchmark <= 0:
        return float("nan")
    return (fill - benchmark) / benchmark * 10_000


def load_live_buys(db_path: str | Path) -> list[Trade]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("""
        SELECT DISTINCT r.run_date, t.ticker, t.shares, t.price, t.invest
        FROM trades t
        JOIN pipeline_runs r ON t.run_id = r.run_id
        WHERE r.run_type = 'live' AND t.action = 'buy'
        ORDER BY r.run_date, t.ticker
    """).fetchall()
    conn.close()
    return [Trade(date=r[0], ticker=r[1], shares=r[2],
                  fill_price=r[3], invest=r[4]) for r in rows]


def remap_weekend_run_dates(trades: list[Trade]) -> list[Trade]:
    """Remap a trade's ``run_date`` to the nearest PRIOR weekday when it
    falls on a Saturday/Sunday.

    Codex review (PR #333): 30/67 trades are unmatched purely because
    ``run_date`` landed on a weekend — these are duplicate pipeline
    invocations where the actual fill occurred on the adjacent (prior)
    weekday, not a genuine same-day execution on a day markets were
    closed. This is a data-alignment fix, not an outlier exclusion: it
    does not drop any trade, it corrects the join key so weekend-stamped
    trades can be matched to the OHLCV day they were actually filled on.
    """
    from datetime import datetime, timedelta

    out = []
    for t in trades:
        d = datetime.strptime(t.date, "%Y-%m-%d")
        # Monday=0 ... Sunday=6. Saturday(5) -> back 1 day to Friday.
        # Sunday(6) -> back 2 days to Friday.
        if d.weekday() == 5:
            d = d - timedelta(days=1)
        elif d.weekday() == 6:
            d = d - timedelta(days=2)
        out.append(Trade(
            date=d.strftime("%Y-%m-%d"), ticker=t.ticker, shares=t.shares,
            fill_price=t.fill_price, invest=t.invest,
        ))
    return out


def apply_outlier_exclusion(
    results: list[ISResult], *, threshold_bps: float | None
) -> tuple[list[ISResult], list[ISResult]]:
    """Split ``results`` into (kept, excluded) by an EX ANTE absolute
    IS-vs-open threshold.

    ``threshold_bps=None`` excludes nothing (kept == results). The
    threshold is a parameter, not a post-hoc per-trade judgment call —
    Codex review (PR #333) flagged that HON's exclusion in the prior memo
    was decided after looking at the result, not declared in advance.
    """
    if threshold_bps is None:
        return list(results), []
    kept, excluded = [], []
    for r in results:
        if r.matched and r.is_vs_open_bps is not None and abs(r.is_vs_open_bps) > threshold_bps:
            excluded.append(r)
        else:
            kept.append(r)
    return kept, excluded


def fetch_ohlcv(
    tickers: list[str],
    from_date: str,
    to_date: str,
    api_key: str,
) -> dict[str, list[OHLCVDay]]:
    result: dict[str, list[OHLCVDay]] = {}
    for i, ticker in enumerate(tickers, 1):
        url = (
            f"{FMP_STABLE}/historical-price-eod/full"
            f"?symbol={ticker}&from={from_date}&to={to_date}&apikey={api_key}"
        )
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                days = []
                for d in data:
                    days.append(OHLCVDay(
                        date=d["date"],
                        open=d["open"],
                        high=d["high"],
                        low=d["low"],
                        close=d["close"],
                        volume=int(d.get("volume", 0)),
                        vwap=d.get("vwap", (d["open"] + d["high"] + d["low"] + d["close"]) / 4),
                    ))
                result[ticker] = sorted(days, key=lambda x: x.date)
                log.debug("%d/%d %s: %d days", i, len(tickers), ticker, len(days))
        except Exception as exc:
            log.warning("%d/%d %s: fetch error: %s", i, len(tickers), ticker, exc)
        if i < len(tickers):
            time.sleep(THROTTLE_S)
    return result


def compute_is(
    trades: list[Trade],
    ohlcv: dict[str, list[OHLCVDay]],
) -> list[ISResult]:
    results = []
    for t in trades:
        r = ISResult(trade=t)
        ticker_days = ohlcv.get(t.ticker, [])
        day_map = {d.date: d for d in ticker_days}

        same_day = day_map.get(t.date)
        if same_day:
            r.open_price = same_day.open
            r.vwap_price = same_day.vwap
            r.close_price = same_day.close
            r.is_vs_open_bps = _is_bps(t.fill_price, same_day.open)
            r.is_vs_vwap_bps = _is_bps(t.fill_price, same_day.vwap)
            r.is_vs_close_bps = _is_bps(t.fill_price, same_day.close)
            r.matched = True

        sorted_dates = sorted(day_map.keys())
        trade_idx = None
        for idx, d in enumerate(sorted_dates):
            if d == t.date:
                trade_idx = idx
                break
        if trade_idx is not None and trade_idx + 1 < len(sorted_dates):
            next_day = day_map[sorted_dates[trade_idx + 1]]
            r.next_close_price = next_day.close
            r.is_vs_next_close_bps = _is_bps(t.fill_price, next_day.close)

        results.append(r)
    return results


def _bootstrap_ci(
    values: np.ndarray, n_boot: int = BOOTSTRAP_N, alpha: float = CI_ALPHA
) -> tuple[float, float, float]:
    if len(values) < 2:
        m = float(np.mean(values)) if len(values) else 0.0
        return m, m, m
    rng = np.random.default_rng(42)
    means = np.array([
        np.mean(rng.choice(values, size=len(values), replace=True))
        for _ in range(n_boot)
    ])
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return float(np.mean(values)), lo, hi


def _size_bucket(invest: float) -> str:
    if invest < 500:
        return "small (<$500)"
    elif invest < 2000:
        return "medium ($500-$2k)"
    else:
        return "large (>$2k)"


def build_report(results: list[ISResult]) -> dict[str, Any]:
    matched = [r for r in results if r.matched]
    if not matched:
        return {"error": "no trades matched to OHLCV data", "n_trades": len(results)}

    def _summarize(values: list[float], label: str) -> dict[str, Any]:
        arr = np.array([v for v in values if not np.isnan(v)])
        if len(arr) == 0:
            return {"label": label, "n": 0}
        mean, ci_lo, ci_hi = _bootstrap_ci(arr)
        return {
            "label": label,
            "n": int(len(arr)),
            "mean_bps": round(mean, 2),
            "median_bps": round(float(np.median(arr)), 2),
            "std_bps": round(float(np.std(arr, ddof=1)), 2) if len(arr) > 1 else 0.0,
            "ci_95_lo": round(ci_lo, 2),
            "ci_95_hi": round(ci_hi, 2),
            "min_bps": round(float(np.min(arr)), 2),
            "max_bps": round(float(np.max(arr)), 2),
            "pct_overpaid": round(float(np.mean(arr > 0) * 100), 1),
        }

    report: dict[str, Any] = {
        "n_trades_total": len(results),
        "n_trades_matched": len(matched),
        "date_range": [
            min(r.trade.date for r in matched),
            max(r.trade.date for r in matched),
        ],
        "total_invested_usd": round(sum(r.trade.invest for r in matched), 2),
    }

    # Overall IS
    report["overall"] = {
        "vs_open": _summarize([r.is_vs_open_bps for r in matched if r.is_vs_open_bps is not None], "fill vs open"),
        "vs_vwap": _summarize([r.is_vs_vwap_bps for r in matched if r.is_vs_vwap_bps is not None], "fill vs VWAP"),
        "vs_close": _summarize([r.is_vs_close_bps for r in matched if r.is_vs_close_bps is not None], "fill vs close"),
        "vs_next_close": _summarize([r.is_vs_next_close_bps for r in matched if r.is_vs_next_close_bps is not None], "fill vs next-day close"),
    }

    # Per-ticker
    by_ticker: dict[str, list[ISResult]] = {}
    for r in matched:
        by_ticker.setdefault(r.trade.ticker, []).append(r)
    ticker_summary = {}
    for ticker, trs in sorted(by_ticker.items()):
        vs_open = [r.is_vs_open_bps for r in trs if r.is_vs_open_bps is not None]
        vs_vwap = [r.is_vs_vwap_bps for r in trs if r.is_vs_vwap_bps is not None]
        ticker_summary[ticker] = {
            "n_buys": len(trs),
            "total_invested": round(sum(r.trade.invest for r in trs), 2),
            "avg_is_vs_open_bps": round(float(np.mean(vs_open)), 2) if vs_open else None,
            "avg_is_vs_vwap_bps": round(float(np.mean(vs_vwap)), 2) if vs_vwap else None,
        }
    report["by_ticker"] = ticker_summary

    # By size bucket
    by_size: dict[str, list[ISResult]] = {}
    for r in matched:
        bucket = _size_bucket(r.trade.invest)
        by_size.setdefault(bucket, []).append(r)
    size_summary = {}
    for bucket, trs in sorted(by_size.items()):
        vs_vwap = [r.is_vs_vwap_bps for r in trs if r.is_vs_vwap_bps is not None]
        size_summary[bucket] = _summarize(vs_vwap, f"fill vs VWAP ({bucket})")
    report["by_size_bucket"] = size_summary

    # Dollar-weighted IS (weight by invest amount)
    invest_arr = np.array([r.trade.invest for r in matched if r.is_vs_vwap_bps is not None])
    vwap_arr = np.array([r.is_vs_vwap_bps for r in matched if r.is_vs_vwap_bps is not None])
    if len(invest_arr) > 0 and invest_arr.sum() > 0:
        dollar_weighted_is = float(np.average(vwap_arr, weights=invest_arr))
        report["dollar_weighted_is_vs_vwap_bps"] = round(dollar_weighted_is, 2)

    return report


def render_text(report: dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append("S10: Open-Auction Implementation Shortfall (IS) Measurement")
    lines.append("=" * 72)
    lines.append(f"Trades: {report['n_trades_matched']}/{report['n_trades_total']} matched to OHLCV")
    lines.append(f"Period: {report['date_range'][0]} -> {report['date_range'][1]}")
    lines.append(f"Total invested: ${report['total_invested_usd']:,.2f}")
    lines.append("")

    lines.append("OVERALL IS (bps, positive = overpaid)")
    lines.append("-" * 60)
    for key in ["vs_open", "vs_vwap", "vs_close", "vs_next_close"]:
        s = report["overall"][key]
        if s.get("n", 0) == 0:
            continue
        lines.append(
            f"  {s['label']:25s}  mean={s['mean_bps']:+7.1f}  "
            f"median={s['median_bps']:+7.1f}  "
            f"95%CI=[{s['ci_95_lo']:+.1f}, {s['ci_95_hi']:+.1f}]  "
            f"n={s['n']}  overpaid={s['pct_overpaid']:.0f}%"
        )

    if "dollar_weighted_is_vs_vwap_bps" in report:
        lines.append(f"\n  Dollar-weighted IS (vs VWAP): {report['dollar_weighted_is_vs_vwap_bps']:+.1f} bps")

    lines.append("\nPER-TICKER (top 10 by total invested)")
    lines.append("-" * 60)
    sorted_tickers = sorted(
        report["by_ticker"].items(),
        key=lambda x: x[1]["total_invested"],
        reverse=True,
    )
    for ticker, ts in sorted_tickers[:10]:
        vs_open = f"{ts['avg_is_vs_open_bps']:+.1f}" if ts["avg_is_vs_open_bps"] is not None else "N/A"
        vs_vwap = f"{ts['avg_is_vs_vwap_bps']:+.1f}" if ts["avg_is_vs_vwap_bps"] is not None else "N/A"
        lines.append(
            f"  {ticker:6s}  n={ts['n_buys']}  invested=${ts['total_invested']:>9,.2f}  "
            f"IS_open={vs_open:>7s}  IS_vwap={vs_vwap:>7s}"
        )

    lines.append("\nBY ORDER SIZE")
    lines.append("-" * 60)
    for bucket, s in sorted(report["by_size_bucket"].items()):
        if s.get("n", 0) == 0:
            continue
        lines.append(
            f"  {bucket:20s}  mean={s['mean_bps']:+7.1f}  "
            f"95%CI=[{s['ci_95_lo']:+.1f}, {s['ci_95_hi']:+.1f}]  n={s['n']}"
        )

    return "\n".join(lines)


def render_memo(report: dict[str, Any]) -> str:
    overall = report["overall"]
    vs_vwap = overall["vs_vwap"]
    vs_open = overall["vs_open"]
    vs_close = overall["vs_close"]
    vs_next = overall["vs_next_close"]
    dw = report.get("dollar_weighted_is_vs_vwap_bps")

    lines = [
        "# S10: Open-auction implementation shortfall — measurement memo",
        "",
        f"**Date:** {report['date_range'][1]} (study as of)",
        f"**Period:** {report['date_range'][0]} to {report['date_range'][1]}",
        f"**Sample:** {report['n_trades_matched']} unique live buys, "
        f"${report['total_invested_usd']:,.0f} total invested",
        "",
        "## Summary",
        "",
    ]

    if vs_vwap.get("n", 0) > 0:
        material = abs(vs_vwap["mean_bps"]) > 10
        direction = "overpaid" if vs_vwap["mean_bps"] > 0 else "underpaid"
        lines.append(
            f"Average implementation shortfall vs VWAP: **{vs_vwap['mean_bps']:+.1f} bps** "
            f"(95% CI [{vs_vwap['ci_95_lo']:+.1f}, {vs_vwap['ci_95_hi']:+.1f}]), "
            f"n={vs_vwap['n']}. "
            f"We {direction} relative to same-day VWAP on average."
        )
        if dw is not None:
            lines.append(
                f"Dollar-weighted IS vs VWAP: **{dw:+.1f} bps** "
                f"(weights larger orders more heavily)."
            )
        lines.append("")

    if vs_open.get("n", 0) > 0:
        near_open = abs(vs_open["mean_bps"]) < 20
        lines.append(
            f"Fill vs same-day open: **{vs_open['mean_bps']:+.1f} bps** "
            f"(95% CI [{vs_open['ci_95_lo']:+.1f}, {vs_open['ci_95_hi']:+.1f}]). "
            + ("Fills are very close to the open price — consistent with MOO/early-session execution. "
               if near_open else
               f"Fills deviate meaningfully from the open. ")
        )

    if vs_close.get("n", 0) > 0:
        lines.append(
            f"Fill vs same-day close: **{vs_close['mean_bps']:+.1f} bps** "
            f"(95% CI [{vs_close['ci_95_lo']:+.1f}, {vs_close['ci_95_hi']:+.1f}]). "
        )

    if vs_next.get("n", 0) > 0:
        lines.append(
            f"Fill vs next-day close: **{vs_next['mean_bps']:+.1f} bps** "
            f"(95% CI [{vs_next['ci_95_lo']:+.1f}, {vs_next['ci_95_hi']:+.1f}]). "
        )

    lines.append("")
    lines.append("## Interpretation for 105 §9.4 prereg")
    lines.append("")

    if vs_vwap.get("n", 0) > 0:
        if vs_vwap["mean_bps"] > 10 and vs_vwap["ci_95_lo"] > 0:
            lines.append(
                "The IS vs VWAP is significantly positive — we consistently fill above "
                "the intraday average. This represents a measurable execution leak that "
                "105's entry-timing optimization could partially recover. At current order "
                f"sizes (${report['total_invested_usd']:,.0f} total), "
                f"the aggregate dollar impact is ~${report['total_invested_usd'] * abs(vs_vwap['mean_bps']) / 10000:,.2f}. "
                "The prize is **material** for the §9.4 prereg — an intraday timing "
                "strategy that captures even half the IS would pay for the engineering cost."
            )
        elif vs_vwap["mean_bps"] > 0 and vs_vwap["ci_95_lo"] < 0:
            lines.append(
                "The IS vs VWAP is positive on average but the 95% CI includes zero. "
                "The leak may exist but is not statistically significant at this sample size. "
                "For the §9.4 prereg: the signal is directionally supportive but inconclusive — "
                "more data or a larger book would tighten the CI. "
                f"Point estimate of total leak: ~${report['total_invested_usd'] * abs(vs_vwap['mean_bps']) / 10000:,.2f}."
            )
        elif vs_vwap["mean_bps"] <= 0:
            lines.append(
                "The IS vs VWAP is negative or zero — we are NOT systematically overpaying "
                "relative to VWAP. This suggests the current execution is already competitive "
                "with or better than intraday average. For the §9.4 prereg: the execution-leak "
                "rationale for 105 is **not supported** by this data. The prize from entry-timing "
                "optimization may be smaller than the ~40bps previously assumed."
            )
    lines.append("")
    lines.append("## Data and method")
    lines.append("")
    lines.append("- Source: `runs.alpaca.db` live buys joined to FMP `historical-price-eod/full`")
    lines.append("- Deduplication: `DISTINCT (run_date, ticker, shares, price, invest)`")
    lines.append(f"- OHLCV source: FMP Starter (includes true volume-weighted VWAP)")
    lines.append(f"- Bootstrap: {BOOTSTRAP_N} resamples, 95% CI (seed=42)")
    lines.append(f"- IS convention: positive = overpaid = leak")
    lines.append("")
    lines.append("## Per-ticker detail")
    lines.append("")
    lines.append("| Ticker | Buys | Invested | IS vs Open (bps) | IS vs VWAP (bps) |")
    lines.append("|--------|------|----------|-------------------|-------------------|")
    sorted_tickers = sorted(
        report["by_ticker"].items(),
        key=lambda x: x[1]["total_invested"],
        reverse=True,
    )
    for ticker, ts in sorted_tickers:
        vs_open_s = f"{ts['avg_is_vs_open_bps']:+.1f}" if ts["avg_is_vs_open_bps"] is not None else "N/A"
        vs_vwap_s = f"{ts['avg_is_vs_vwap_bps']:+.1f}" if ts["avg_is_vs_vwap_bps"] is not None else "N/A"
        lines.append(
            f"| {ticker} | {ts['n_buys']} | ${ts['total_invested']:,.0f} | {vs_open_s} | {vs_vwap_s} |"
        )

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S10: open-auction IS measurement")
    parser.add_argument("--db", required=True, help="path to runs.alpaca.db")
    parser.add_argument("--env", default=None, help=".env file for FMP_API_KEY")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--memo", default=None, help="write research memo to this path")
    parser.add_argument(
        "--weekend-remap", action="store_true",
        help="remap weekend run_date to the nearest prior weekday before matching",
    )
    parser.add_argument(
        "--exclude-outlier-bps", type=float, default=None,
        help="EX ANTE: exclude trades with |IS_vs_open| above this bps threshold "
             "(declared via this flag, not chosen after seeing results)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    api_key = os.environ.get("FMP_API_KEY")
    if not api_key and args.env:
        from pathlib import Path as P
        for line in P(args.env).read_text().splitlines():
            line = line.strip()
            if line.startswith("FMP_API_KEY="):
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not api_key:
        print("error: FMP_API_KEY not found", file=sys.stderr)
        return 1

    trades = load_live_buys(args.db)
    if not trades:
        print("no live buys found", file=sys.stderr)
        return 1

    log.info("loaded %d unique live buys", len(trades))
    if args.weekend_remap:
        trades = remap_weekend_run_dates(trades)
        log.info("weekend-remapped run_date to nearest prior weekday")

    tickers = sorted(set(t.ticker for t in trades))
    min_date = min(t.date for t in trades)
    max_date = max(t.date for t in trades)

    from datetime import datetime, timedelta
    from_dt = (datetime.strptime(min_date, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d")
    to_dt = (datetime.strptime(max_date, "%Y-%m-%d") + timedelta(days=5)).strftime("%Y-%m-%d")

    log.info("fetching OHLCV for %d tickers (%s to %s)", len(tickers), from_dt, to_dt)
    ohlcv = fetch_ohlcv(tickers, from_dt, to_dt, api_key)
    log.info("fetched %d tickers", len(ohlcv))

    results = compute_is(trades, ohlcv)
    matched = sum(1 for r in results if r.matched)
    log.info("matched %d/%d trades to OHLCV", matched, len(results))

    kept, excluded = apply_outlier_exclusion(
        results, threshold_bps=args.exclude_outlier_bps
    )
    if excluded:
        log.info(
            "excluded %d trade(s) as outliers (|IS_vs_open| > %.0f bps): %s",
            len(excluded), args.exclude_outlier_bps,
            [f"{r.trade.ticker}@{r.trade.date}" for r in excluded],
        )

    report = build_report(kept)
    report["outlier_exclusion_threshold_bps"] = args.exclude_outlier_bps
    report["n_excluded_outliers"] = len(excluded)
    report["weekend_remap_applied"] = args.weekend_remap

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report))

    if args.memo:
        memo_path = Path(args.memo)
        memo_path.parent.mkdir(parents=True, exist_ok=True)
        memo_path.write_text(render_memo(report))
        log.info("wrote research memo to %s", memo_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
