#!/usr/bin/env python3
"""SEC EDGAR XBRL harvester — free PIT financial data source (N2/RS-3).

Fetches quarterly and annual financial facts from SEC EDGAR's XBRL API,
preserving the ``filed`` date as the point-in-time (PIT) timestamp. This is
the ground-truth filing date — when the SEC received the document — and is
the correct ``available_at`` anchor for leak-free backtesting.

Output: JSONL with one record per (ticker, field, period, form), each carrying
the ``filed`` date. Never writes to canonical ``data/`` paths.

SEC API rules: User-Agent header required, ≤10 req/sec.

Usage:
    sec_edgar_harvester.py --tickers AAPL,GRMN,MU --output /tmp/edgar.jsonl
    sec_edgar_harvester.py --watchlist watchlist.txt --output /tmp/edgar.jsonl
    sec_edgar_harvester.py --tickers AAPL          # stdout
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

log = logging.getLogger("sec_edgar_harvester")

USER_AGENT = "RenQuant research renhao.overflow@gmail.com"
TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
REQUEST_DELAY = 0.15  # ≤10 req/sec

FIELDS = {
    "us-gaap:Revenues": "revenue",
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": "revenue_alt",
    "us-gaap:NetIncomeLoss": "net_income",
    "us-gaap:EarningsPerShareDiluted": "eps_diluted",
    "us-gaap:Assets": "total_assets",
}


def _session() -> "requests.Session":
    if requests is None:
        raise ImportError("requests is required: pip install requests")
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    s.headers["Accept"] = "application/json"
    return s


def fetch_ticker_cik_map(session: "requests.Session") -> dict[str, int]:
    """Download SEC's ticker→CIK mapping. Returns {TICKER: cik_int}."""
    time.sleep(REQUEST_DELAY)
    resp = session.get(TICKER_CIK_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {
        entry["ticker"].upper(): int(entry["cik_str"])
        for entry in data.values()
        if "ticker" in entry and "cik_str" in entry
    }


def parse_ticker_cik_map(data: dict[str, Any]) -> dict[str, int]:
    """Parse the SEC ticker-CIK JSON (for testing without HTTP)."""
    return {
        entry["ticker"].upper(): int(entry["cik_str"])
        for entry in data.values()
        if "ticker" in entry and "cik_str" in entry
    }


def fetch_company_facts(
    session: "requests.Session", cik: int
) -> dict[str, Any] | None:
    """Fetch XBRL company facts for a CIK. Returns None on error."""
    url = COMPANY_FACTS_URL.format(cik=str(cik).zfill(10))
    time.sleep(REQUEST_DELAY)
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 404:
            log.warning("CIK %s: 404 (no XBRL filings)", cik)
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception:
        log.exception("CIK %s: fetch failed", cik)
        return None


def extract_facts(
    ticker: str, facts_json: dict[str, Any]
) -> list[dict[str, Any]]:
    """Extract target fields from XBRL company facts JSON."""
    us_gaap = facts_json.get("facts", {}).get("us-gaap", {})
    records: list[dict[str, Any]] = []

    for xbrl_tag, field_name in FIELDS.items():
        concept_name = xbrl_tag.split(":", 1)[1]
        concept = us_gaap.get(concept_name)
        if concept is None:
            continue

        units = concept.get("units", {})
        unit_key = "USD/shares" if "EarningsPerShare" in concept_name else "USD"
        entries = units.get(unit_key, [])

        for entry in entries:
            form = entry.get("form", "")
            if form not in ("10-K", "10-Q"):
                continue

            records.append({
                "ticker": ticker,
                "field": field_name,
                "xbrl_tag": xbrl_tag,
                "value": entry.get("val"),
                "filed_date": entry.get("filed"),
                "period_end": entry.get("end"),
                "period_start": entry.get("start"),
                "fiscal_year": entry.get("fy"),
                "fiscal_period": entry.get("fp"),
                "form": form,
                "accession_number": entry.get("accn"),
                "source": "sec_edgar_xbrl",
            })

    return records


def load_completed_tickers(output_path: Path) -> set[str]:
    """Read already-harvested tickers from an existing JSONL file."""
    seen: set[str] = set()
    if not output_path.exists():
        return seen
    with open(output_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                seen.add(rec.get("ticker", ""))
            except json.JSONDecodeError:
                continue
    return seen


def harvest(
    tickers: list[str],
    output: Path | None = None,
    *,
    session: "requests.Session | None" = None,
    ticker_cik_map: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Harvest EDGAR XBRL facts for a list of tickers.

    Returns all extracted records. If *output* is given, appends JSONL there
    (resumable: skips tickers already present in the file).
    """
    if session is None:
        session = _session()

    if ticker_cik_map is None:
        log.info("Fetching SEC ticker→CIK mapping...")
        ticker_cik_map = fetch_ticker_cik_map(session)
        log.info("Loaded %d ticker→CIK mappings", len(ticker_cik_map))

    skip = load_completed_tickers(output) if output else set()
    all_records: list[dict[str, Any]] = []
    out_fh = open(output, "a") if output else None

    try:
        for i, ticker in enumerate(tickers):
            ticker = ticker.upper().strip()
            if ticker in skip:
                log.info("[%d/%d] %s: skipped (already harvested)", i + 1, len(tickers), ticker)
                continue

            cik = ticker_cik_map.get(ticker)
            if cik is None:
                log.warning("[%d/%d] %s: no CIK found", i + 1, len(tickers), ticker)
                continue

            facts = fetch_company_facts(session, cik)
            if facts is None:
                continue

            records = extract_facts(ticker, facts)
            all_records.extend(records)
            log.info(
                "[%d/%d] %s (CIK %d): %d records",
                i + 1, len(tickers), ticker, cik, len(records),
            )

            if out_fh:
                for rec in records:
                    out_fh.write(json.dumps(rec, sort_keys=True) + "\n")
                out_fh.flush()
    finally:
        if out_fh:
            out_fh.close()

    return all_records


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--tickers", help="Comma-separated ticker list (e.g. AAPL,GRMN,MU)"
    )
    group.add_argument(
        "--watchlist", help="Path to a file with one ticker per line"
    )
    ap.add_argument(
        "--output",
        help="Output JSONL path (default: stdout). NEVER use data/ paths.",
    )
    args = ap.parse_args()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = Path(args.watchlist).read_text().strip().splitlines()
        tickers = [t.strip() for t in tickers if t.strip() and not t.startswith("#")]

    output = Path(args.output) if args.output else None
    records = harvest(tickers, output)

    if output is None:
        for rec in records:
            print(json.dumps(rec, sort_keys=True))

    total = len(records)
    tickers_ok = len({r["ticker"] for r in records})
    log.info("Done: %d records from %d tickers", total, tickers_ok)


if __name__ == "__main__":
    main()
