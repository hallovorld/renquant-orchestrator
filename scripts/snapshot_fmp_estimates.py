#!/usr/bin/env python
"""Forward snapshotter for FMP analyst estimates / consensus / targets.

WHY (2026-06-27): the analyst estimate-*revision* signal is the literature's
best large-cap orthogonal lead (post-revision drift; Womack 1996, Gleason-Lee
2003 -- see ``doc/design/2026-06-24-analyst-revision-feature.md``). It is
currently **un-buildable** because our FMP harvest
(``data/fmp_harvest/`` in the umbrella, umbrella PR #409) is a single *current*
snapshot with **no revision history**: every parquet there reflects the
consensus as it was on the harvest day only. A point-in-time audit confirmed we
cannot reconstruct "what the consensus was 1m/3m ago" from a one-shot snapshot.

The fix is cheap and only needs *time*: start snapshotting the estimates
**forward from today** so a real as-of revision history accrues. Run this once a
day; after ~3-6 months you have a dated series and can compute trailing
Δ(consensus estimate) as-of each date with no look-ahead.

This script ONLY fetches and writes dated snapshots to a NEW dedicated path
(default ``data/estimate_snapshots/<YYYY-MM-DD>/<endpoint>.parquet``). It never
writes a canonical/existing data path and never schedules itself -- wiring a
cron/launchd job is a separate operator deploy decision.

Auth/endpoint pattern matches the existing harvest (the FMP ``stable`` API,
``apikey`` query param, key read read-only from the umbrella ``.env``).

Usage:
    # demo to /tmp (proves fetch+write without touching live data/)
    python scripts/snapshot_fmp_estimates.py --out /tmp/snap_demo

    # explicit universe file (one ticker per line, or a strategy_config.json)
    python scripts/snapshot_fmp_estimates.py --universe /path/to/universe.txt

    # backfill-label a snapshot to a specific as-of date (idempotent overwrite)
    python scripts/snapshot_fmp_estimates.py --as-of 2026-06-27

    # see what would be fetched/written without any network call or write
    python scripts/snapshot_fmp_estimates.py --dry-run

Cron-safety: this writer is idempotent per as-of date (re-running a date
overwrites only that date's directory). For a real scheduled deploy, wrap the
invocation in a ``flock`` guard so two runs can't race the same date dir, e.g.::

    flock -n /tmp/snapshot_fmp_estimates.lock \
        python scripts/snapshot_fmp_estimates.py --out data/estimate_snapshots

Scheduling itself is intentionally NOT done here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
import requests

# --- FMP endpoints to snapshot ------------------------------------------------
# Mirrors the umbrella harvest manifests (data/fmp_harvest/*.manifest.json):
#   - base = the FMP "stable" API
#   - each endpoint is a per-symbol GET with ?symbol={sym}&apikey={key}
# These four carry the consensus / estimate / target fields the revision signal
# is built from. analyst_estimates is THE one that revises (mean EPS/revenue
# estimate); the others give consensus rating + target drift.
FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"
ENDPOINTS: dict[str, str] = {
    "analyst_estimates": "analyst-estimates?symbol={sym}&period=annual",
    "grades_consensus": "grades-consensus?symbol={sym}",
    "price_target_consensus": "price-target-consensus?symbol={sym}",
    "price_target_summary": "price-target-summary?symbol={sym}",
}

DEFAULT_OUT = "data/estimate_snapshots"
DEFAULT_ENV = Path("/Users/renhao/git/github/RenQuant/.env")
DEFAULT_UNIVERSE_CONFIG = Path(
    "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/strategy_config.golden.json"
)
REQUEST_TIMEOUT_S = 30
THROTTLE_S = 0.20  # gentle on the rate limit (FMP Starter = 300/min)


# --- helpers ------------------------------------------------------------------
def _read_env_value(env_path: Path, key: str) -> str | None:
    """Read a single KEY=VALUE from a .env file, read-only. Never logs the value."""
    try:
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def load_api_key(env_path: Path) -> str | None:
    """FMP key: env var first, then read-only from the umbrella .env."""
    return os.environ.get("FMP_API_KEY") or _read_env_value(env_path, "FMP_API_KEY")


def load_universe(universe_arg: str | None) -> list[str]:
    """Resolve the ticker universe.

    --universe accepts either:
      * a strategy_config.json (reads the ``watchlist`` list), or
      * a plain text/CSV file (one ticker per line; '#' comments ignored).
    Default: the renquant_104 golden config watchlist (read-only).
    """
    path = Path(universe_arg) if universe_arg else DEFAULT_UNIVERSE_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"universe source not found: {path}")
    text = path.read_text()
    if path.suffix == ".json":
        cfg = json.loads(text)
        wl = cfg.get("watchlist") or cfg.get("universe") or cfg.get("tickers")
        if not isinstance(wl, list) or not wl:
            raise ValueError(f"no 'watchlist' list found in {path}")
        tickers = [str(t).strip().upper() for t in wl if str(t).strip()]
    else:
        tickers = []
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if line:
                tickers.append(line.upper())
    # dedupe, stable order
    seen: dict[str, None] = {}
    for t in tickers:
        seen.setdefault(t, None)
    return list(seen)


def fetch_endpoint(
    session: requests.Session, endpoint_path: str, sym: str, api_key: str
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Fetch one (endpoint, symbol). Returns (records, error). Never raises."""
    url = f"{FMP_STABLE_BASE}/{endpoint_path.format(sym=sym)}&apikey={api_key}"
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT_S)
    except requests.RequestException as exc:
        return None, f"fetch_error:{type(exc).__name__}"
    if resp.status_code != 200:
        return None, f"http_{resp.status_code}"
    try:
        data = resp.json()
    except ValueError:
        return None, "bad_json"
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return None, "unexpected_shape"
    return data, None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_one_endpoint(
    session: requests.Session,
    endpoint: str,
    endpoint_path: str,
    tickers: Sequence[str],
    api_key: str,
    as_of: str,
    out_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    """Fetch one endpoint across the universe and write a dated parquet + manifest."""
    started = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    with_data = no_data = http_error = fetch_error = 0
    error_samples: list[str] = []

    for sym in tickers:
        if dry_run:
            continue
        records, err = fetch_endpoint(session, endpoint_path, sym, api_key)
        if err is not None:
            if err.startswith("http_"):
                http_error += 1
            else:
                fetch_error += 1
            if len(error_samples) < 5:
                error_samples.append(f"{sym}:{err}")
        elif not records:
            no_data += 1
        else:
            with_data += 1
            for rec in records:
                rec = dict(rec)
                rec.setdefault("symbol", sym)
                # stamp the as-of so the accrued series is self-describing PIT
                rec["snapshot_as_of"] = as_of
                rows.append(rec)
        time.sleep(THROTTLE_S)

    out_path = out_dir / endpoint
    parquet_path = out_path.with_suffix(".parquet")
    manifest_path = out_path.with_suffix(".manifest.json")
    finished = datetime.now(timezone.utc)

    manifest: dict[str, Any] = {
        "endpoint": endpoint,
        "path_template": endpoint_path,
        "url_base": FMP_STABLE_BASE,
        "as_of": as_of,
        "requested": len(tickers),
        "with_data": with_data,
        "no_data": no_data,
        "http_error": http_error,
        "fetch_error": fetch_error,
        "error_samples": error_samples,
        "rows": len(rows),
        "tickers": with_data,
        "output": f"{endpoint}.parquet",
        "fetched_at": finished.isoformat(),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "status": "dry_run" if dry_run else "ok",
    }

    if dry_run:
        manifest["sha256"] = None
        return manifest

    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    # idempotent: overwrite this date's file in place
    df.to_parquet(parquet_path, index=False)
    manifest["sha256"] = _sha256_file(parquet_path)
    manifest["ticker_count"] = with_data
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


# Canonical inputs we must never touch.
_FORBIDDEN_LEAVES = frozenset(
    {
        "fmp_harvest",
        "fmp_harvest_finnhub",
        "sec_fundamentals_daily",
        "rawlabel.parquet",
        "score_db",
    }
)


def _is_scratch_arg(out_root: Path) -> bool:
    """True only when the user EXPLICITLY pointed at a scratch tree.

    Judged on the argument as given (not the cwd-resolved path), so a relative
    target like ``data/whatever`` is never mistaken for scratch just because the
    process happens to run from under /tmp.
    """
    s = str(out_root)
    return s.startswith("/tmp/") or s == "/tmp" or s.startswith("/private/var/folders")


def is_canonical_path(out_root: Path) -> bool:
    """Guard: refuse to write any existing/canonical data path.

    The whole point is a NEW dedicated directory. We accept ONLY an out-root
    whose leaf is the dedicated ``estimate_snapshots`` name, or an explicit
    scratch (/tmp) target. Judged on the path *as given* AND on its resolved
    form, so neither a relative arg nor the cwd can sneak a canonical leaf
    through. This makes it structurally hard to clobber, e.g., the fmp_harvest,
    rawlabel, or sec_fundamentals canonical inputs.
    """
    if _is_scratch_arg(out_root):
        return False  # explicit scratch is allowed
    # inspect components of BOTH the given arg and its resolved absolute form
    parts = set(out_root.parts) | set(out_root.resolve().parts)
    if parts & _FORBIDDEN_LEAVES:
        return True
    # require the dedicated leaf name for any non-scratch target
    return out_root.name != "estimate_snapshots"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--universe",
        default=None,
        help="strategy_config.json (reads 'watchlist') or a one-ticker-per-line file; "
        "default = renquant_104 golden config",
    )
    ap.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"output root (default {DEFAULT_OUT}); a dated subdir is created under it",
    )
    ap.add_argument(
        "--as-of",
        default=None,
        help="as-of date YYYY-MM-DD for the snapshot dir (default = today, UTC)",
    )
    ap.add_argument(
        "--env",
        default=str(DEFAULT_ENV),
        help="path to a .env holding FMP_API_KEY (read-only)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve universe + plan paths and print, but make NO network call or write",
    )
    args = ap.parse_args(argv)

    as_of = args.as_of or date.today().isoformat()
    try:
        datetime.strptime(as_of, "%Y-%m-%d")
    except ValueError:
        print(f"error: --as-of must be YYYY-MM-DD, got {as_of!r}", file=sys.stderr)
        return 2

    out_root = Path(args.out)
    if is_canonical_path(out_root):
        print(
            f"error: refusing to write canonical/non-dedicated path {out_root!r}; "
            f"use a 'estimate_snapshots' dir or a /tmp demo path",
            file=sys.stderr,
        )
        return 2

    try:
        tickers = load_universe(args.universe)
    except (OSError, ValueError) as exc:
        print(f"error: could not load universe: {exc}", file=sys.stderr)
        return 2

    out_dir = out_root / as_of
    print(
        f"snapshot_fmp_estimates: as_of={as_of} universe={len(tickers)} tickers "
        f"endpoints={list(ENDPOINTS)} out={out_dir}"
        + ("  [DRY-RUN]" if args.dry_run else ""),
        file=sys.stderr,
    )

    api_key = None
    if not args.dry_run:
        api_key = load_api_key(Path(args.env))
        if not api_key:
            print(
                f"error: FMP_API_KEY not found (env or {args.env})",
                file=sys.stderr,
            )
            return 2

    session = requests.Session()
    manifests: list[dict[str, Any]] = []
    for endpoint, endpoint_path in ENDPOINTS.items():
        m = snapshot_one_endpoint(
            session=session,
            endpoint=endpoint,
            endpoint_path=endpoint_path,
            tickers=tickers,
            api_key=api_key or "",
            as_of=as_of,
            out_dir=out_dir,
            dry_run=args.dry_run,
        )
        manifests.append(m)
        print(
            f"  {endpoint:24s} rows={m['rows']:6d} with_data={m['with_data']:4d} "
            f"no_data={m['no_data']:3d} http_err={m['http_error']:3d} "
            f"fetch_err={m['fetch_error']:3d} status={m['status']}",
            file=sys.stderr,
        )

    print(
        json.dumps(
            {
                "as_of": as_of,
                "out_dir": str(out_dir),
                "universe": len(tickers),
                "dry_run": args.dry_run,
                "endpoints": {m["endpoint"]: m["rows"] for m in manifests},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
