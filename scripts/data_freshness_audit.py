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
process exit non-zero when any source is CRITICAL. Pass ``--fail-on-unknown``
when the audit itself must fail closed on missing/corrupt inputs.

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
from typing import Callable, Sequence

FRESH, STALE, CRITICAL, UNKNOWN = "FRESH", "STALE", "CRITICAL", "UNKNOWN"
_ICON = {FRESH: "✅", STALE: "⚠️", CRITICAL: "🔴", UNKNOWN: "❓"}
_STATUS_ORDER = {FRESH: 0, STALE: 1, UNKNOWN: 2, CRITICAL: 3}

# Fundamentals completeness thresholds: fraction of the ACTIVE watchlist whose
# latest fundamental row is fully populated. A current-date panel that is mostly
# empty is NOT operationally healthy — the 2026-06-23 incident was stale AND
# ~7% complete — so completeness must be able to turn the line warn/critical on
# its own, independent of date freshness.
FUND_COMPLETE_WARN = 0.90  # < 90% active complete → at least STALE
FUND_COMPLETE_CRIT = 0.50  # < 50% active complete → CRITICAL


def _worst(*statuses: "str | None") -> str:
    present = [s for s in statuses if s]
    return max(present, key=lambda s: _STATUS_ORDER[s]) if present else FRESH


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

    ``loader`` returns the per-ticker latest ``date`` that drives status for
    per-ticker stores (oldest for must-be-current stores like ohlcv; newest /
    feed-ingestion recency for sentiment), or the source latest date for panel
    files.
    """

    key: str
    description: str
    warn_days: int
    critical_days: int
    loader: Callable[[Path, Sequence[str]], "LoaderResult"]
    extra: Callable[[Path], str] | None = None  # optional completeness note


@dataclass
class FreshnessResult:
    key: str
    status: str
    lag_days: int | None
    last_date: str | None
    note: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class LoaderResult:
    last_date: date | None
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


def _latest_dates_per_ticker(
    dir_path: Path,
    tickers: Sequence[str],
    fname: str,
    basis: str = "oldest",
) -> LoaderResult:
    """Per-ticker latest-date across tickers, with coverage details.

    ``basis`` selects which per-ticker date drives the freshness status:
      - ``"oldest"`` (default): every ticker must be current, so the worst
        (oldest) latest-date drives status. Correct for ohlcv — one healthy
        symbol must not false-green a stale universe.
      - ``"newest"``: feed-ingestion recency — did the pipeline ingest ANY
        current data? Correct for sentiment, where a valid-but-quiet ticker
        with no recent news must NOT be read as a stale feed. Per-ticker news
        presence is surfaced as coverage (missing/oldest), not as a hard fail.

    Either way the oldest/newest pair and missing coverage are reported in the
    detail so the operator sees the full picture.
    """
    dated: dict[str, date] = {}
    missing: list[str] = []
    for t in tickers:
        d = (
            _max_date_in_parquet(dir_path / t / fname)
            if fname
            else _max_date_in_parquet(dir_path / f"{t}.parquet")
        )
        if d is None:
            missing.append(t)
        else:
            dated[t] = d
    if not dated:
        return LoaderResult(
            None,
            note=f"0/{len(tickers)} tickers present",
            detail={
                "checked_tickers": len(tickers),
                "present_tickers": 0,
                "missing_count": len(missing),
                "missing_tickers": missing[:20],
                "freshness_basis": basis,
            },
        )
    oldest = min(dated.values())
    newest = max(dated.values())
    chosen = newest if basis == "newest" else oldest
    basis_label = "newest(feed-ingest)" if basis == "newest" else "oldest(min-cover)"
    note = (
        f"{len(dated)}/{len(tickers)} tickers present; basis={basis_label}; "
        f"oldest_latest={oldest.isoformat()} newest_latest={newest.isoformat()}"
    )
    if missing:
        note += f"; missing={len(missing)}"
    return LoaderResult(
        chosen,
        note=note,
        detail={
            "checked_tickers": len(tickers),
            "present_tickers": len(dated),
            "missing_count": len(missing),
            "missing_tickers": missing[:20],
            "oldest_latest": oldest.isoformat(),
            "newest_latest": newest.isoformat(),
            "freshness_basis": basis,
        },
    )


_SAMPLE = ["AAPL", "MSFT", "NVDA", "AMZN", "PANW", "CSCO", "NFLX", "ZM"]


def _ohlcv_loader(repo: Path, tickers: Sequence[str]) -> LoaderResult:
    return _latest_dates_per_ticker(repo / "data" / "ohlcv", tickers, "1d.parquet")


def _sentiment_loader(repo: Path, tickers: Sequence[str]) -> LoaderResult:
    # Sentiment freshness = feed-ingestion recency (newest ticker-level news),
    # not the oldest quiet ticker. A valid ticker with no recent news is a
    # coverage/notable signal, NOT a stale feed — so classifying on the oldest
    # would false-RED the source whenever any single name is simply quiet.
    # Per-candidate news-presence gating is a separate DataIntegrityJob concern.
    return _latest_dates_per_ticker(
        repo / "data" / "news_sentiment_alpaca", tickers, "", basis="newest")


_FUND_COLS = ("earnings_yield", "book_to_price", "gross_profitability",
              "roe", "asset_growth")


def _fundamentals_loader(repo: Path, tickers: Sequence[str]) -> LoaderResult:
    """Panel date + completeness for SEC fundamentals.

    Status must reflect BOTH that the panel date is current AND that the active
    watchlist is actually populated: a fresh-dated but mostly-empty panel is the
    completeness half of the 2026-06-23 incident (stale AND ~7% complete).
    Completeness is measured on the **active watchlist** — what the daily-full
    actually scores — with panel-wide completeness reported alongside so the
    operator can tell a sparse universe from incomplete active names.
    """
    path = repo / "data" / "sec_fundamentals_daily.parquet"
    last = _max_date_in_parquet(path)
    if not path.exists():
        return LoaderResult(last)
    import pandas as pd  # noqa: PLC0415

    df = pd.read_parquet(path)
    fcols = [c for c in df.columns if c.lower() in _FUND_COLS]
    if not fcols or "ticker" not in df.columns or "date" not in df.columns:
        return LoaderResult(last)
    latest = df.sort_values("date").groupby("ticker").tail(1)
    panel_total = len(latest)
    panel_complete = int(latest[fcols].notna().all(axis=1).sum())
    by_ticker = latest.assign(_t=latest["ticker"].astype(str).str.upper()).set_index("_t")
    active = [str(t).upper() for t in tickers]
    present = [t for t in active if t in by_ticker.index]
    active_total = len(active)
    active_complete = int(
        by_ticker.loc[present, fcols].notna().all(axis=1).sum()) if present else 0
    active_pct = (active_complete / active_total) if active_total else 0.0
    comp_status = (
        CRITICAL if active_pct < FUND_COMPLETE_CRIT
        else STALE if active_pct < FUND_COMPLETE_WARN
        else FRESH)
    note = (
        f"active {active_complete}/{active_total} complete ({active_pct:.0%}); "
        f"panel {panel_complete}/{panel_total}")
    return LoaderResult(
        last,
        note=note,
        detail={
            "active_complete": active_complete,
            "active_total": active_total,
            "active_complete_pct": round(active_pct, 4),
            "panel_complete": panel_complete,
            "panel_total": panel_total,
            "completeness_status": comp_status,
            "complete_warn_pct": FUND_COMPLETE_WARN,
            "complete_critical_pct": FUND_COMPLETE_CRIT,
        },
    )


SOURCES: list[SourceSpec] = [
    SourceSpec("ohlcv", "price bars (data/ohlcv)", warn_days=4, critical_days=7,
               loader=_ohlcv_loader),
    SourceSpec("sentiment", "news sentiment (data/news_sentiment_alpaca)",
               warn_days=4, critical_days=10, loader=_sentiment_loader),
    SourceSpec("fundamentals", "SEC fundamentals (sec_fundamentals_daily)",
               warn_days=45, critical_days=90, loader=_fundamentals_loader),
]


def _default_strategy_config(repo: Path) -> Path | None:
    candidates = [
        repo / ".subrepo_runtime" / "repos" / "renquant-strategy-104"
        / "configs" / "strategy_config.json",
        repo / "backtesting" / "renquant_104" / "strategy_config.json",
    ]
    return next((p for p in candidates if p.exists()), None)


def load_watchlist(repo: Path, strategy_config: Path | None = None) -> list[str]:
    path = strategy_config or _default_strategy_config(repo)
    if path is None or not path.exists():
        return list(_SAMPLE)
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("watchlist") or payload.get("tickers") or []
    if not isinstance(raw, list):
        return list(_SAMPLE)
    tickers = sorted({str(t).upper() for t in raw if str(t).strip()})
    return tickers or list(_SAMPLE)


def audit(
    repo: Path,
    today: date,
    sources: list[SourceSpec] = SOURCES,
    tickers: Sequence[str] | None = None,
) -> list[FreshnessResult]:
    results: list[FreshnessResult] = []
    watchlist = [str(t).upper() for t in (tickers or load_watchlist(repo))]
    for spec in sources:
        try:
            loaded = spec.loader(repo, watchlist)
        except Exception as exc:  # never let a bad file crash the daily run
            results.append(FreshnessResult(spec.key, UNKNOWN, None, None,
                                           note=f"loader error: {exc!s}"[:120]))
            continue
        last = loaded.last_date
        lag = lag_in_days(last, today)
        status = classify(lag, spec.warn_days, spec.critical_days)
        if loaded.detail.get("missing_count") and status == FRESH:
            status = STALE
        # A source can be date-fresh yet operationally degraded (e.g.
        # fundamentals current-dated but mostly empty): escalate to the worst of
        # the date status and any completeness-derived status.
        status = _worst(status, loaded.detail.get("completeness_status"))
        notes = [loaded.note] if loaded.note else []
        if spec.extra is not None:
            try:
                extra = spec.extra(repo) or ""
            except Exception:
                extra = ""
            if extra:
                notes.append(extra)
        detail = {
            "warn_days": spec.warn_days,
            "critical_days": spec.critical_days,
            "description": spec.description,
            "watchlist_size": len(watchlist),
            **loaded.detail,
        }
        results.append(FreshnessResult(
            spec.key, status, lag,
            last.isoformat() if last else None,
            note="; ".join(notes),
            detail=detail))
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
    p.add_argument("--strategy-config", default=None,
                   help="strategy_config.json path used to load the active watchlist")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    p.add_argument("--fail-on-critical", action="store_true",
                   help="exit non-zero if any source is CRITICAL")
    p.add_argument("--fail-on-unknown", action="store_true",
                   help="exit non-zero if any source is UNKNOWN")
    p.add_argument("--summary-only", action="store_true",
                   help="print only the one-line ntfy summary")
    args = p.parse_args(argv)

    repo = Path(args.repo_dir).resolve()
    today = datetime.now().date()
    strategy_config = Path(args.strategy_config).resolve() if args.strategy_config else None
    tickers = load_watchlist(repo, strategy_config)
    results = audit(repo, today, tickers=tickers)
    summary = summarize(results)

    if args.json:
        print(json.dumps({"today": today.isoformat(), "summary": summary,
                          "watchlist_size": len(tickers),
                          "results": [asdict(r) for r in results]}, indent=2))
    elif args.summary_only:
        print(summary)
    else:
        print(render_table(results))
        print("\n" + summary)

    if args.fail_on_critical and any(r.status == CRITICAL for r in results):
        return 2
    if args.fail_on_unknown and any(r.status == UNKNOWN for r in results):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
