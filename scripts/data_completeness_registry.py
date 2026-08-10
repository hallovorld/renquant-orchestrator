#!/usr/bin/env python3
"""Per-ticker data completeness registry (task #15, measurement only).

Measures, for every ticker in the corpus universe (the 292-name
``alpha158_291_fundamental_dataset.parquet``) plus the pinned strategy-104
watchlist, per-source completeness over a fixed window, and classifies each
ticker COMPLETE / DEGRADED / BROKEN.  This script is the DERIVATION for the
committed registry CSV at ``doc/research/data/<date>-data-completeness-
registry.csv`` — it makes NO pipeline changes and writes nothing outside the
``--out`` path.

Sources measured (read-only, from the umbrella tree):
  OHLCV       data/ohlcv/<T>/1d.parquet          — trading-day coverage vs
              SPY's calendar, longest gap, last bar
  SEC fund    data/sec_fundamentals_daily.parquet — coverage span, staleness
              (latest fiscal_period_end age; the daily panel itself is
              forward-filled to the build date for every covered ticker, so
              row-recency is NOT a staleness signal), null fund cols on the
              ticker's last row
  Earnings    data/earnings_surprise/<T>.parquet  — exists, rows, last quarter
  Sentiment   data/news_sentiment_alpaca/<T>.parquet — the source
              scripts/build_alpha158_fund_panel.py::_add_sentiment_features
              reads; coverage per ticker.  The builder fills SENT_COLS with 0
              for tickers without a file (documented as by-design for
              non-watchlist names), so absence is only counted against
              watchlist names.

Classification rules (frozen; all thresholds are prereg content and live in
the CONSTANTS block below — do not tune them after reading the output):
  BROKEN    — unusable for scoring at the window end: no OHLCV file, zero
              OHLCV rows in the window, or INACTIVE (last bar older than the
              5th-from-last SPY trading day: the harvest/listing ended, so no
              current feature row exists).  The delisted/dropped corpus tail
              falls out here naturally.
  DEGRADED  — scoreable but a named source is missing or stale (reasons are
              listed per ticker in the ``reasons`` column).
  COMPLETE  — active and no degraded reason fires.

ETFs carry no SEC fundamentals or earnings by nature; those two sources are
not expected for the frozen ETF set below.

Watchlist provenance (PR #963 review fix): the watchlist is read from the
strategy-104 checkout under ``.subrepo_runtime`` — a MUTABLE working tree.
Before any data is read, the script (a) extracts the strategy-104 pin from
``subrepos.lock.json``, (b) asserts ``git rev-parse HEAD`` of the checkout it
reads equals that pin, and (c) asserts the ``strategy_config.json`` bytes it
read are byte-identical to the blob committed at that HEAD (a dirty working
tree fails too).  Any mismatch exits nonzero naming both identifiers.  The
lock pin, checkout HEAD, and sha256 of the config content actually read are
recorded as ``#``-comment metadata lines at the top of the registry CSV
(read it with ``pandas.read_csv(..., comment="#")``).

Usage:
  python3 scripts/data_completeness_registry.py \
      --umbrella /Users/renhao/git/github/RenQuant \
      --out doc/research/data/2026-08-10-data-completeness-registry.csv
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

# ── CONSTANTS (frozen classification thresholds — prereg content) ──────────
WINDOW_START = pd.Timestamp("2023-01-01")
WINDOW_END = pd.Timestamp("2026-08-07")

# ACTIVE = OHLCV last bar >= the 5th-from-last SPY trading day in the window.
ACTIVE_LOOKBACK_TD = 5

# OHLCV degraded thresholds (within the ticker's alive-span ∩ window).
OHLCV_MIN_COVERAGE = 0.995   # fraction of SPY trading days present
OHLCV_MAX_GAP_TD = 2         # longest consecutive missing run, trading days
OHLCV_MIN_ROWS = 120         # short history: < ~6 months cannot warm up the
                             # 60d alpha158 feature windows with margin

# SEC fundamentals degraded thresholds (non-ETF only).
SEC_FPE_MAX_AGE_D = 200      # latest fiscal_period_end older than ~6.5 months
                             # at window end = a missed quarterly filing cycle
                             # even at maximum filing lag (normal cadence
                             # measured at median 129d on 2026-08-07)
SEC_MAX_NULL_FUND_COLS = 2   # >2 of the 5 fund cols null on the last row =
                             # majority of the fund vector is imputed
                             # (1-2 nulls, e.g. gross_profitability for
                             # financials, is structural and not flagged)

# Earnings-surprise degraded threshold (non-ETF only).
EARN_MAX_AGE_D = 140         # last quarter older than ~1 quarter + max
                             # announcement lag before window end

# Sentiment degraded threshold (watchlist names only — the panel builder
# fills 0 by design for names without a sentiment file).
SENT_MAX_AGE_D = 30

FUND_COLS = [
    "earnings_yield", "book_to_price", "gross_profitability", "roe",
    "asset_growth",
]

# Frozen ETF set (verified: none has SEC XBRL fundamentals or an
# earnings-surprise history; SPCX is a 2026-06 IPO *stock*, not an ETF).
ETF_TICKERS = frozenset({
    "SPY", "GLD", "TLT", "XLE", "XLF", "XLI", "XLK", "XLU", "XLV", "XLY",
})

DEFAULT_UMBRELLA = "/Users/renhao/git/github/RenQuant"
STRATEGY_REPO_NAME = "renquant-strategy-104"
DEFAULT_STRATEGY_CHECKOUT = f".subrepo_runtime/repos/{STRATEGY_REPO_NAME}"
STRATEGY_CONFIG_RELPATH = "configs/strategy_config.json"
LOCK_FILE = "subrepos.lock.json"
CORPUS_PARQUET = "data/alpha158_291_fundamental_dataset.parquet"


class PinMismatchError(RuntimeError):
    """The strategy checkout (or the config file inside it) does not match
    the subrepos.lock.json pin.  The message names both identifiers."""


def _git(checkout: Path, *args: str) -> bytes:
    res = subprocess.run(["git", "-C", str(checkout), *args],
                         capture_output=True)
    if res.returncode != 0:
        raise PinMismatchError(
            f"git {' '.join(args)} failed in {checkout}: "
            f"{res.stderr.decode(errors='replace').strip()}")
    return res.stdout


def load_pinned_watchlist_config(lock_path: Path,
                                 checkout: Path) -> tuple[dict, dict]:
    """Read strategy_config.json from ``checkout`` ONLY after proving the
    checkout is exactly the commit pinned in ``lock_path`` and the file bytes
    equal the blob committed at that HEAD.

    Returns (config_dict, provenance) where provenance carries
    ``lock_pin`` / ``checkout_head`` / ``config_sha256``.
    Raises PinMismatchError naming both identifiers otherwise.
    """
    lock = json.loads(lock_path.read_text())
    entries = [e for e in lock.get("subrepos", [])
               if e.get("name") == STRATEGY_REPO_NAME]
    if len(entries) != 1:
        raise PinMismatchError(
            f"{lock_path}: expected exactly one '{STRATEGY_REPO_NAME}' entry, "
            f"found {len(entries)}")
    lock_pin = entries[0]["commit"]

    head = _git(checkout, "rev-parse", "HEAD").decode().strip()
    if head != lock_pin:
        raise PinMismatchError(
            f"strategy checkout {checkout} is at HEAD {head} but "
            f"{lock_path.name} pins {STRATEGY_REPO_NAME} at {lock_pin} — "
            f"refusing to classify against an unpinned watchlist")

    cfg_path = checkout / STRATEGY_CONFIG_RELPATH
    read_bytes = cfg_path.read_bytes()
    read_sha = hashlib.sha256(read_bytes).hexdigest()
    blob_bytes = _git(checkout, "show", f"HEAD:{STRATEGY_CONFIG_RELPATH}")
    blob_sha = hashlib.sha256(blob_bytes).hexdigest()
    if read_sha != blob_sha:
        raise PinMismatchError(
            f"{cfg_path} working-tree content (sha256 {read_sha}) differs "
            f"from the blob committed at pinned HEAD {head} "
            f"(sha256 {blob_sha}) — dirty checkout; refusing to proceed")

    provenance = {"lock_pin": lock_pin, "checkout_head": head,
                  "config_sha256": read_sha}
    return json.loads(read_bytes.decode()), provenance


def spy_calendar(umbrella: Path) -> pd.DatetimeIndex:
    spy = pd.read_parquet(umbrella / "data/ohlcv/SPY/1d.parquet",
                          columns=["close"])
    days = spy.loc[WINDOW_START:WINDOW_END].index
    if len(days) == 0:
        raise RuntimeError("SPY calendar empty in window — wrong umbrella?")
    return days


def ohlcv_metrics(umbrella: Path, ticker: str,
                  spy_days: pd.DatetimeIndex) -> dict:
    out = {
        "ohlcv_exists": False, "ohlcv_rows_window": 0, "ohlcv_first": None,
        "ohlcv_last": None, "ohlcv_coverage": None, "ohlcv_missing_days": None,
        "ohlcv_longest_gap_td": None,
    }
    p = umbrella / "data" / "ohlcv" / ticker / "1d.parquet"
    if not p.exists():
        return out
    out["ohlcv_exists"] = True
    d = pd.read_parquet(p, columns=["close"]).loc[WINDOW_START:WINDOW_END]
    if len(d) == 0:
        return out
    first, last = d.index.min(), d.index.max()
    life = spy_days[(spy_days >= first) & (spy_days <= last)]
    have = set(d.index)
    missing = [day for day in life if day not in have]
    longest = cur = 0
    miss_set = set(missing)
    for day in life:
        cur = cur + 1 if day in miss_set else 0
        longest = max(longest, cur)
    out.update({
        "ohlcv_rows_window": len(d), "ohlcv_first": first.date(),
        "ohlcv_last": last.date(),
        "ohlcv_coverage": round(1 - len(missing) / len(life), 5) if len(life) else 0.0,
        "ohlcv_missing_days": len(missing), "ohlcv_longest_gap_td": longest,
    })
    return out


def sec_metrics(sec: pd.DataFrame) -> dict:
    """sec = the ticker's slice of sec_fundamentals_daily within the window."""
    if len(sec) == 0:
        return {"sec_rows_window": 0, "sec_first": None, "sec_last": None,
                "sec_fpe_latest": None, "sec_fpe_age_days": None,
                "sec_null_fund_cols_last": None}
    last_row = sec.loc[sec["date"].idxmax()]
    fpe = sec["fiscal_period_end"].max()
    return {
        "sec_rows_window": len(sec),
        "sec_first": sec["date"].min().date(),
        "sec_last": sec["date"].max().date(),
        "sec_fpe_latest": fpe.date() if pd.notna(fpe) else None,
        "sec_fpe_age_days": int((WINDOW_END - fpe).days) if pd.notna(fpe) else None,
        "sec_null_fund_cols_last": int(last_row[FUND_COLS].isna().sum()),
    }


def earn_metrics(umbrella: Path, ticker: str) -> dict:
    out = {"earn_file_exists": False, "earn_rows_total": 0,
           "earn_rows_window": 0, "earn_last_quarter": None,
           "earn_age_days": None}
    p = umbrella / "data" / "earnings_surprise" / f"{ticker}.parquet"
    if not p.exists():
        return out
    out["earn_file_exists"] = True
    e = pd.read_parquet(p)
    if len(e) == 0:
        return out
    dates = pd.to_datetime(e.index)
    out["earn_rows_total"] = len(e)
    out["earn_rows_window"] = int(
        ((dates >= WINDOW_START) & (dates <= WINDOW_END)).sum())
    out["earn_last_quarter"] = dates.max().date()
    out["earn_age_days"] = int((WINDOW_END - dates.max()).days)
    return out


def sent_metrics(umbrella: Path, ticker: str) -> dict:
    out = {"sent_file_exists": False, "sent_rows_window": 0,
           "sent_first": None, "sent_last": None, "sent_days_window": 0,
           "sent_age_days": None}
    p = umbrella / "data" / "news_sentiment_alpaca" / f"{ticker}.parquet"
    if not p.exists():
        return out
    out["sent_file_exists"] = True
    s = pd.read_parquet(p, columns=["date"])
    s = s[(s["date"] >= WINDOW_START) & (s["date"] <= WINDOW_END)]
    if len(s) == 0:
        return out
    out.update({
        "sent_rows_window": len(s), "sent_first": s["date"].min().date(),
        "sent_last": s["date"].max().date(),
        "sent_days_window": int(s["date"].nunique()),
        "sent_age_days": int((WINDOW_END - s["date"].max()).days),
    })
    return out


def classify(m: dict) -> tuple[str, str]:
    """Return (class, semicolon-joined reasons). Rules frozen in module doc."""
    is_etf = m["is_etf"]
    # BROKEN: no scoreable feature row at the window end.
    if not m["ohlcv_exists"]:
        return "BROKEN", "no OHLCV file"
    if m["ohlcv_rows_window"] == 0:
        return "BROKEN", "OHLCV file has zero rows in window"
    if not m["active"]:
        return "BROKEN", (
            f"inactive: OHLCV ends {m['ohlcv_last']} (harvest/listing ended; "
            f"no current bar to score)")

    reasons = []
    # OHLCV quality within alive-span.
    if m["ohlcv_coverage"] is not None and m["ohlcv_coverage"] < OHLCV_MIN_COVERAGE:
        reasons.append(
            f"OHLCV coverage {m['ohlcv_coverage']:.3f} < {OHLCV_MIN_COVERAGE}"
            f" ({m['ohlcv_missing_days']} missing trading days)")
    if (m["ohlcv_longest_gap_td"] or 0) > OHLCV_MAX_GAP_TD:
        reasons.append(
            f"OHLCV longest gap {m['ohlcv_longest_gap_td']}td > {OHLCV_MAX_GAP_TD}td")
    if m["ohlcv_rows_window"] < OHLCV_MIN_ROWS:
        reasons.append(
            f"OHLCV short history: {m['ohlcv_rows_window']} bars "
            f"(< {OHLCV_MIN_ROWS}; 60d feature windows cannot warm up)")

    if not is_etf:
        # SEC fundamentals.
        if m["sec_rows_window"] == 0:
            reasons.append(
                "SEC fundamentals absent (all 5 fund cols median-imputed "
                "at panel build)")
        else:
            if (m["sec_fpe_age_days"] is not None
                    and m["sec_fpe_age_days"] > SEC_FPE_MAX_AGE_D):
                reasons.append(
                    f"SEC stale: latest fiscal_period_end {m['sec_fpe_latest']} "
                    f"({m['sec_fpe_age_days']}d > {SEC_FPE_MAX_AGE_D}d — a "
                    f"missed filing cycle)")
            if (m["sec_null_fund_cols_last"] or 0) > SEC_MAX_NULL_FUND_COLS:
                reasons.append(
                    f"SEC fund vector majority-null: "
                    f"{m['sec_null_fund_cols_last']}/5 cols null on last row")
        # Earnings surprise.
        if not m["earn_file_exists"] or m["earn_rows_window"] == 0:
            reasons.append("earnings_surprise missing (PEAD/SUE features "
                           "median-imputed)")
        elif m["earn_age_days"] is not None and m["earn_age_days"] > EARN_MAX_AGE_D:
            reasons.append(
                f"earnings_surprise stale: last quarter {m['earn_last_quarter']} "
                f"({m['earn_age_days']}d > {EARN_MAX_AGE_D}d)")

    # Sentiment — expected only for watchlist names (fill-0 by design else).
    if m["in_watchlist"]:
        if not m["sent_file_exists"] or m["sent_rows_window"] == 0:
            reasons.append("sentiment missing for watchlist name "
                           "(SENT_COLS fill 0)")
        elif m["sent_age_days"] is not None and m["sent_age_days"] > SENT_MAX_AGE_D:
            reasons.append(
                f"sentiment stale: last article day {m['sent_last']} "
                f"({m['sent_age_days']}d > {SENT_MAX_AGE_D}d)")

    if reasons:
        return "DEGRADED", "; ".join(reasons)
    return "COMPLETE", ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--umbrella", default=DEFAULT_UMBRELLA)
    ap.add_argument("--strategy-checkout", default=None,
                    help="strategy-104 runtime checkout DIRECTORY; the config "
                         "is read as <checkout>/" + STRATEGY_CONFIG_RELPATH +
                         " only after the checkout HEAD is proven equal to "
                         "the subrepos.lock.json pin (default: <umbrella>/"
                         + DEFAULT_STRATEGY_CHECKOUT + ")")
    ap.add_argument("--lock", default=None,
                    help="subrepos.lock.json path (default: <umbrella>/"
                         + LOCK_FILE + ")")
    ap.add_argument("--out", required=True, help="registry CSV output path")
    args = ap.parse_args()

    umbrella = Path(args.umbrella)
    checkout = (Path(args.strategy_checkout) if args.strategy_checkout
                else umbrella / DEFAULT_STRATEGY_CHECKOUT)
    lock_path = Path(args.lock) if args.lock else umbrella / LOCK_FILE

    # Pin validation FIRST — before any data read, so a mismatched checkout
    # can never produce a registry.
    try:
        cfg, provenance = load_pinned_watchlist_config(lock_path, checkout)
    except PinMismatchError as e:
        print(f"PIN VALIDATION FAILED: {e}", file=sys.stderr)
        return 2

    corpus = sorted(pd.read_parquet(umbrella / CORPUS_PARQUET,
                                    columns=["ticker"])["ticker"].unique())
    watchlist = cfg["watchlist"]
    universe = sorted(set(corpus) | set(watchlist))
    spy_days = spy_calendar(umbrella)
    active_cutoff = spy_days[-ACTIVE_LOOKBACK_TD]

    sec_all = pd.read_parquet(
        umbrella / "data/sec_fundamentals_daily.parquet",
        columns=["date", "ticker", "fiscal_period_end"] + FUND_COLS)
    sec_all = sec_all[(sec_all["date"] >= WINDOW_START)
                      & (sec_all["date"] <= WINDOW_END)]
    sec_by_ticker = dict(tuple(sec_all.groupby("ticker")))

    records = []
    for t in universe:
        m = {"ticker": t, "in_corpus": t in set(corpus),
             "in_watchlist": t in set(watchlist), "is_etf": t in ETF_TICKERS}
        m.update(ohlcv_metrics(umbrella, t, spy_days))
        m["active"] = bool(m["ohlcv_last"] is not None
                           and pd.Timestamp(m["ohlcv_last"]) >= active_cutoff)
        m.update(sec_metrics(sec_by_ticker.get(
            t, sec_all.iloc[0:0])))
        m.update(earn_metrics(umbrella, t))
        m.update(sent_metrics(umbrella, t))
        m["class"], m["reasons"] = classify(m)
        records.append(m)

    df = pd.DataFrame(records)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    meta_lines = [
        "# data-completeness-registry rev2",
        f"# window: {WINDOW_START.date()}..{WINDOW_END.date()}",
        f"# umbrella: {umbrella}",
        f"# corpus_parquet: {CORPUS_PARQUET}",
        f"# strategy104_lock_pin: {provenance['lock_pin']}",
        f"# strategy104_checkout_head: {provenance['checkout_head']}",
        f"# strategy_config_sha256: {provenance['config_sha256']}",
        "# read with: pandas.read_csv(path, comment='#')",
    ]
    with out.open("w") as fh:
        fh.write("\n".join(meta_lines) + "\n")
        df.to_csv(fh, index=False)

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"watchlist provenance: lock pin {provenance['lock_pin']} == "
          f"checkout HEAD {provenance['checkout_head']}; "
          f"config sha256 {provenance['config_sha256']}")
    print(f"universe: {len(universe)} = {len(corpus)} corpus ∪ "
          f"{len(watchlist)} watchlist "
          f"(watchlist-only: {sorted(set(watchlist) - set(corpus))})")
    print(f"window: {WINDOW_START.date()}..{WINDOW_END.date()} "
          f"({len(spy_days)} SPY trading days); active cutoff "
          f"{active_cutoff.date()}")
    act = df[df["active"]]
    print(f"active: {len(act)}/{len(df)} union; "
          f"{int(df[df['in_corpus']]['active'].sum())}/{len(corpus)} corpus; "
          f"{int(df[df['in_watchlist']]['active'].sum())}/{len(watchlist)} "
          f"watchlist")
    print("\ncounts by class:")
    print(df["class"].value_counts().to_string())
    print("\ncounts by class, ACTIVE names only:")
    print(act["class"].value_counts().to_string())
    bad = df[df["class"] != "COMPLETE"].copy()
    bad_active = bad[bad["active"]]
    if len(bad_active):
        print("\nACTIVE non-COMPLETE names:")
        for _, r in bad_active.iterrows():
            wl = "WATCHLIST" if r["in_watchlist"] else "corpus-only"
            print(f"  {r['ticker']:<6} {r['class']:<9} [{wl}] {r['reasons']}")
    print(f"\nregistry written: {out} ({len(df)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
