#!/usr/bin/env python
"""Audit the freshness (and key completeness) of the data sources the
renquant_104 daily-full pipeline depends on, and emit a compact one-line
summary suitable for an ntfy push.

Motivation (2026-06-23): the daily-full pipeline scored and traded on a
``sec_fundamentals_daily.parquet`` that was 91 days stale (last row
2026-03-24) with no operator-visible signal. Price/sentiment were fresh, so
the staleness was silent. This audit makes per-source staleness explicit in
the daily run and on the operator's phone.

It is intentionally read-only and defensive: every source is wrapped so a
missing/corrupt file degrades to ``status=unknown`` rather than throwing.
Exit code is 0 by default (non-fatal); pass ``--fail-on-critical`` to make the
process exit non-zero when any source is CRITICAL.

Usage:
    python scripts/data_freshness_audit.py --repo-dir /path/to/RenQuant
    python scripts/data_freshness_audit.py --repo-dir . --json
    python scripts/data_freshness_audit.py --repo-dir . --fail-on-critical
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Callable

FRESH, STALE, CRITICAL, UNKNOWN = "FRESH", "STALE", "CRITICAL", "UNKNOWN"
_ICON = {FRESH: "✅", STALE: "⚠️", CRITICAL: "🔴", UNKNOWN: "❓"}


def classify(lag_days: int | None, warn_days: int, critical_days: int) -> str:
    """Map an age-in-days to a freshness status using per-source thresholds.

    ``lag_days is None`` (could not determine a date) → UNKNOWN.
    """
    if lag_days is None:
        return UNKNOWN
    if lag_days >= critical_days:
        return CRITICAL
    if lag_days >= warn_days:
        return STALE
    return FRESH


def lag_in_days(last: date | None, today: date) -> int | None:
    """Calendar-day age of ``last`` relative to ``today`` (clamped at 0)."""
    if last is None:
        return None
    return max(0, (today - last).days)


@dataclass
class SourceSpec:
    """One data source to audit.

    ``loader`` returns the latest ``date`` available in the source (or None).
    For per-ticker stores, ``loader`` samples ``tickers`` and returns the max.
    """

    key: str
    description: str
    warn_days: int
    critical_days: int
    loader: Callable[[Path], date | None]
    extra: Callable[[Path], str] | None = None  # optional completeness note


@dataclass
class FreshnessResult:
    key: str
    status: str
    lag_days: int | None
    last_date: str | None
    note: str = ""
    detail: dict = field(default_factory=dict)


# ── date extraction helpers ───────────────────────────────────────────────
def _max_date_in_parquet(path: Path, date_cols=("date", "datetime", "asof",
                                                "as_of", "timestamp", "time")) -> date | None:
    if not path.exists():
        return None
    import pandas as pd  # noqa: PLC0415

    df = pd.read_parquet(path)
    for c in df.columns:
        if c.lower() in date_cols:
            s = pd.to_datetime(df[c], errors="coerce").dropna()
            if len(s):
                return s.max().date()
    # fall back to a DatetimeIndex
    idx = getattr(df, "index", None)
    if idx is not None and getattr(idx, "dtype", None) is not None:
        try:
            s = pd.to_datetime(idx, errors="coerce")
            s = s[~s.isna()]
            if len(s):
                return s.max().date()
        except Exception:
            pass
    return None


def _max_date_per_ticker(dir_path: Path, tickers: list[str], fname: str) -> date | None:
    """Max latest-date across a sample of per-ticker parquet files."""
    best: date | None = None
    for t in tickers:
        d = _max_date_in_parquet(dir_path / t / fname) if fname else _max_date_in_parquet(dir_path / f"{t}.parquet")
        if d and (best is None or d > best):
            best = d
    return best


_SAMPLE = ["AAPL", "MSFT", "NVDA", "AMZN", "PANW", "CSCO", "NFLX", "ZM"]


def _ohlcv_loader(repo: Path) -> date | None:
    return _max_date_per_ticker(repo / "data" / "ohlcv", _SAMPLE, "1d.parquet")


def _sentiment_loader(repo: Path) -> date | None:
    return _max_date_per_ticker(repo / "data" / "news_sentiment_alpaca", _SAMPLE, "")


def _fundamentals_loader(repo: Path) -> date | None:
    return _max_date_in_parquet(repo / "data" / "sec_fundamentals_daily.parquet")


def _fundamentals_completeness(repo: Path) -> str:
    """Report % of the watchlist with a complete (no-NaN) latest fundamental row."""
    path = repo / "data" / "sec_fundamentals_daily.parquet"
    if not path.exists():
        return ""
    import pandas as pd  # noqa: PLC0415

    df = pd.read_parquet(path)
    fcols = [c for c in df.columns if c.lower() in (
        "earnings_yield", "book_to_price", "gross_profitability", "roe", "asset_growth")]
    if not fcols or "ticker" not in df.columns or "date" not in df.columns:
        return ""
    latest = df.sort_values("date").groupby("ticker").tail(1)
    n = len(latest)
    if not n:
        return ""
    complete = int((latest[fcols].notna().all(axis=1)).sum())
    return f"{complete}/{n} tickers complete ({len(fcols)} fund cols)"


SOURCES: list[SourceSpec] = [
    SourceSpec("ohlcv", "price bars (data/ohlcv)", warn_days=4, critical_days=7,
               loader=_ohlcv_loader),
    SourceSpec("sentiment", "news sentiment (data/news_sentiment_alpaca)",
               warn_days=4, critical_days=10, loader=_sentiment_loader),
    SourceSpec("fundamentals", "SEC fundamentals (sec_fundamentals_daily)",
               warn_days=45, critical_days=90, loader=_fundamentals_loader,
               extra=_fundamentals_completeness),
]


def audit(repo: Path, today: date, sources: list[SourceSpec] = SOURCES) -> list[FreshnessResult]:
    results: list[FreshnessResult] = []
    for spec in sources:
        try:
            last = spec.loader(repo)
        except Exception as exc:  # never let a bad file crash the daily run
            results.append(FreshnessResult(spec.key, UNKNOWN, None, None,
                                           note=f"loader error: {exc!s}"[:120]))
            continue
        lag = lag_in_days(last, today)
        status = classify(lag, spec.warn_days, spec.critical_days)
        note = ""
        if spec.extra is not None:
            try:
                note = spec.extra(repo) or ""
            except Exception:
                note = ""
        results.append(FreshnessResult(
            spec.key, status, lag,
            last.isoformat() if last else None, note=note,
            detail={"warn_days": spec.warn_days, "critical_days": spec.critical_days,
                    "description": spec.description}))
    return results


def summarize(results: list[FreshnessResult]) -> str:
    """One compact line for ntfy, e.g.
    'DATA FRESHNESS 🔴 | ohlcv ✅0d | sentiment ✅1d | fundamentals 🔴91d'."""
    worst = FRESH
    order = {FRESH: 0, STALE: 1, UNKNOWN: 2, CRITICAL: 3}
    parts = []
    for r in results:
        if order[r.status] > order[worst]:
            worst = r.status
        age = f"{r.lag_days}d" if r.lag_days is not None else "?"
        parts.append(f"{r.key} {_ICON[r.status]}{age}")
    return f"DATA FRESHNESS {_ICON[worst]} | " + " | ".join(parts)


def render_table(results: list[FreshnessResult]) -> str:
    lines = [f"{'source':<14}{'status':<10}{'age':<8}{'last_date':<13}note"]
    for r in results:
        age = f"{r.lag_days}d" if r.lag_days is not None else "?"
        lines.append(f"{r.key:<14}{r.status:<10}{age:<8}{(r.last_date or '—'):<13}{r.note}")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--repo-dir", default=os.environ.get("RENQUANT_REPO_DIR", "."),
                   help="RenQuant umbrella repo root (holds data/).")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    p.add_argument("--fail-on-critical", action="store_true",
                   help="exit non-zero if any source is CRITICAL")
    p.add_argument("--summary-only", action="store_true",
                   help="print only the one-line ntfy summary")
    args = p.parse_args(argv)

    repo = Path(args.repo_dir).resolve()
    today = datetime.now().date()
    results = audit(repo, today)
    summary = summarize(results)

    if args.json:
        print(json.dumps({"today": today.isoformat(), "summary": summary,
                          "results": [asdict(r) for r in results]}, indent=2))
    elif args.summary_only:
        print(summary)
    else:
        print(render_table(results))
        print("\n" + summary)

    if args.fail_on_critical and any(r.status == CRITICAL for r in results):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
