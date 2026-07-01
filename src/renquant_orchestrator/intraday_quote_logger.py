"""renquant105 Stage-1 OPERATIONS-ONLY intraday quote logger (the tick feed).

STANDALONE, DECOUPLED, OBSERVE-ONLY quote poller for the intraday-decisioning RFC
(``doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md``,
converged r11/r12). During market hours it samples the daily watchlist's quotes
and appends a **structured JSONL tick feed** — the class-D "timing-only quote"
arrival/reference the paired-IS harness consumes (design §9.1, §9.2c: the
decision-time NBBO midpoint). Without this feed, ``intraday_pairing_logger.py``
(orchestrator PR #215) censors every pair ``no_intraday_tick``; this module is the
missing producer.

**This is a SEPARATE PROCESS from the live decision / intraday runner.** It is
NOT embedded in any decision path. It reads market data and appends a log file —
nothing else. A bug in it can never affect a live trade:

  * OBSERVE-ONLY read-only market data — places NO orders, touches NO positions,
    cash, pins, gates, or run state;
  * the quote SOURCE is dependency-injected (an interface) so the real Alpaca
    market-data client is only ever constructed for a real run — tests use a
    deterministic fake source and an injected clock (no wall-clock, no network);
  * the OUTPUT defaults under the operator data root
    (:func:`~renquant_orchestrator.runtime_paths.default_data_root`, honoring
    ``RENQUANT_DATA_ROOT``) — it NEVER writes into the umbrella git tree;
  * best-effort: a quote-fetch failure for one ticker (or the whole batch) is
    logged and skipped — it never crashes the loop.

Schema alignment (the load-bearing contract): each JSONL line carries the exact
keys ``intraday_pairing_logger.load_intraday_ticks`` reads — ``date`` (session,
filtered on equality), ``ticker``, ``mid`` (the decision-time reference mid), and
``tick_time`` — plus richer raw fields (``bid``/``ask``/``last``/``ts``) for the
future analysis. ``entry_price`` is deliberately NOT asserted here: the consumer
defaults the hypothetical intraday entry to ``mid`` (the honest neutral choice for
an observe-only feed); a fill model is the future experiment's call (design §9.4).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

from .env_files import load_env_file
from .runtime_paths import default_data_root, default_strategy_config_path

log = logging.getLogger("renquant.intraday_quote_logger")

# Schema version for the tick JSONL rows — bump if the record shape changes so the
# consumer (intraday_pairing_logger, §9.4 experiment) can migrate cleanly.
TICK_SCHEMA_VERSION = "1"
STAGE = "renquant105-stage1-operations-only"
RECORD_KIND = "intraday_quote_tick"

# Regular trading hours, US equities, America/New_York. A best-effort observe-only
# feed: weekday + [09:30, 16:00) ET. Holidays are NOT excluded (a holiday just
# yields stale/empty quotes that are logged and skipped — harmless); the operator
# schedule (progress doc) governs which days it is invoked.
ET = ZoneInfo("America/New_York")
RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)

DEFAULT_CADENCE_SEC = 60


def default_tick_feed_path(data_root: Path | None = None) -> Path:
    """Default accumulating tick-feed file, under the operator data root.

    Mirrors ``intraday_pairing_logger.default_pilot_path`` naming but for the tick
    source (its ``DEFAULT_TICK_SOURCE``): a single rolling JSONL the consumer
    filters by ``date``. Rooted at :func:`default_data_root` (honoring
    ``RENQUANT_DATA_ROOT``), NEVER the umbrella git tree.
    """
    root = data_root or default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "intraday_ticks.jsonl"


# ---------------------------------------------------------------------------
# Quote source interface (dependency-injected) + a plain quote value
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Quote:
    """A single quote observation. ``ts`` is the source's exchange timestamp for
    the quote (ISO-8601), used as the decision-time reference and the idempotency
    axis; ``bid``/``ask`` form the NBBO midpoint, ``last`` is the last trade."""

    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    ts: str | None = None

    def mid(self) -> float | None:
        """NBBO midpoint when both sides are present; fall back to last trade when
        the spread is one-sided/absent; ``None`` when nothing is priceable
        (recorded as a skip — never imputed)."""
        if self.bid is not None and self.ask is not None:
            return (float(self.bid) + float(self.ask)) / 2.0
        if self.last is not None:
            return float(self.last)
        return None


class QuoteSource(Protocol):
    """Pluggable read-only quote provider. The real impl hits Alpaca market data;
    tests inject a deterministic fake. A per-batch fetch keeps the network cost to
    one call per sample; a missing/unpriceable ticker is simply absent from the
    returned mapping."""

    name: str

    def get_quotes(self, tickers: Sequence[str]) -> Mapping[str, Quote]:
        ...


class AlpacaQuoteSource:
    """Real READ-ONLY Alpaca market-data quote source (IEX feed, free tier).

    Mirrors the umbrella construction (``backtesting/renquant_104/kernel/data.py``
    ``fetch_intraday_bars``): lazy ``alpaca-py`` import, credentials from
    ``ALPACA_API_KEY`` / ``ALPACA_SECRET_KEY``, forced IEX feed. This is a
    market-DATA client only — it has no trading client and can place no orders.
    """

    name = "alpaca-iex"

    def __init__(self, *, feed: str = "IEX", timeout_sec: float = 20.0) -> None:
        self._feed = feed
        self._timeout_sec = timeout_sec
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            from alpaca.data.historical import StockHistoricalDataClient  # noqa: PLC0415

            key = os.environ.get("ALPACA_API_KEY")
            secret = os.environ.get("ALPACA_SECRET_KEY")
            if not key or not secret:
                raise RuntimeError(
                    "AlpacaQuoteSource: ALPACA_API_KEY + ALPACA_SECRET_KEY must be "
                    "set (source .env before running)"
                )
            self._client = StockHistoricalDataClient(api_key=key, secret_key=secret)
        return self._client

    def get_quotes(self, tickers: Sequence[str]) -> Mapping[str, Quote]:
        if not tickers:
            return {}
        from alpaca.data.enums import DataFeed  # noqa: PLC0415
        from alpaca.data.requests import StockLatestQuoteRequest  # noqa: PLC0415

        client = self._get_client()
        feed = DataFeed.IEX if self._feed.upper() == "IEX" else DataFeed(self._feed)
        req = StockLatestQuoteRequest(symbol_or_symbols=list(tickers), feed=feed)
        raw = client.get_stock_latest_quote(req)  # {symbol: Quote}
        out: dict[str, Quote] = {}
        for symbol, q in (raw or {}).items():
            bid = getattr(q, "bid_price", None)
            ask = getattr(q, "ask_price", None)
            ts = getattr(q, "timestamp", None)
            out[str(symbol)] = Quote(
                bid=float(bid) if bid else None,
                ask=float(ask) if ask else None,
                last=None,
                ts=ts.isoformat() if hasattr(ts, "isoformat") else (str(ts) if ts else None),
            )
        return out


def alpaca_credentials_present() -> bool:
    """True when both Alpaca market-data credentials are in the environment."""
    return bool(os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY"))


# ---------------------------------------------------------------------------
# Market-hours gating (pure — clock is injected everywhere)
# ---------------------------------------------------------------------------
def market_phase(now: datetime) -> str:
    """``"open"`` / ``"before_open"`` / ``"closed"`` for an aware datetime, in ET.
    Weekends and post-close are ``"closed"``; a naive datetime is treated as ET."""
    et = now.astimezone(ET) if now.tzinfo is not None else now.replace(tzinfo=ET)
    if et.weekday() >= 5:  # Sat/Sun
        return "closed"
    t = et.timetz().replace(tzinfo=None)
    if t < RTH_OPEN:
        return "before_open"
    if t >= RTH_CLOSE:
        return "closed"
    return "open"


def is_market_hours(now: datetime) -> bool:
    """True during RTH (weekday, [09:30, 16:00) ET)."""
    return market_phase(now) == "open"


def session_date(now: datetime) -> str:
    """The ET calendar date (YYYY-MM-DD) of a sample — the session key the consumer
    filters on."""
    et = now.astimezone(ET) if now.tzinfo is not None else now.replace(tzinfo=ET)
    return et.date().isoformat()


# ---------------------------------------------------------------------------
# Watchlist loader (minimal + robust — never fails a read on an unrelated key)
# ---------------------------------------------------------------------------
def load_watchlist(config_path: str | Path | None = None) -> list[str]:
    """Read the ``watchlist`` array from the pinned strategy config.

    Deliberately a minimal ``json`` read (not the pydantic ``load_strategy_config``)
    so this observability tool never fails to sample because some unrelated typed
    key drifted. Defaults to :func:`default_strategy_config_path`."""
    path = Path(config_path) if config_path else default_strategy_config_path()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    watchlist = data.get("watchlist")
    if not isinstance(watchlist, list) or not watchlist:
        raise ValueError(f"strategy config {path} has no non-empty 'watchlist'")
    return [str(t) for t in watchlist]


# ---------------------------------------------------------------------------
# Pure tick-record builder (no I/O — fully testable)
# ---------------------------------------------------------------------------
def build_tick_record(
    *,
    ticker: str,
    quote: Quote,
    sample_ts: datetime,
    date: str | None = None,
    source_name: str = "unknown",
) -> dict[str, Any] | None:
    """Build one tick record aligned to the ``intraday_pairing_logger`` schema, or
    ``None`` when the quote is unpriceable (no mid — recorded as a skip, never
    imputed).

    ``date`` (consumer-filtered), ``ticker``, ``mid`` and ``tick_time`` are the
    keys the consumer reads; ``tick_time`` prefers the quote's exchange timestamp
    (the true as-of of the mid), falling back to the sample time. Raw
    ``bid``/``ask``/``last``/``ts`` and provenance ride along for the future
    analysis; the consumer ignores extra keys.
    """
    mid = quote.mid()
    if mid is None:
        return None
    sample_iso = sample_ts.isoformat()
    tick_time = quote.ts or sample_iso
    return {
        "schema_version": TICK_SCHEMA_VERSION,
        "stage": STAGE,
        "record_kind": RECORD_KIND,
        "observe_only": True,
        "date": date if date is not None else session_date(sample_ts),
        "ticker": ticker,
        "mid": mid,
        "tick_time": tick_time,
        "ts": sample_iso,
        "quote_ts": quote.ts,
        "bid": quote.bid,
        "ask": quote.ask,
        "last": quote.last,
        "source": source_name,
    }


def tick_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    """Idempotency key = one row per distinct quote observation
    ``(date, ticker, tick_time)``. Because ``tick_time`` prefers the exchange
    timestamp, re-polling an unchanged quote (or re-running a session) is a no-op,
    never a duplicate."""
    return (
        str(record.get("date")),
        str(record.get("ticker")),
        str(record.get("tick_time")),
    )


# ---------------------------------------------------------------------------
# Idempotent JSONL accumulation
# ---------------------------------------------------------------------------
class TickFeedWriter:
    """Append tick records to the accumulating JSONL, skipping any whose
    ``(date, ticker, tick_time)`` key is already present. Loads existing keys once
    at construction so idempotency survives process restarts."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._seen: set[tuple[str, str, str]] = self._load_keys()

    def _load_keys(self) -> set[tuple[str, str, str]]:
        keys: set[tuple[str, str, str]] = set()
        if not self.path.exists():
            return keys
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    keys.add(tick_key(json.loads(line)))
                except (json.JSONDecodeError, AttributeError):
                    continue
        return keys

    def append(self, records: Iterable[Mapping[str, Any]]) -> int:
        """Append new rows; return the count actually written (dedup on tick key)."""
        records = list(records)
        if not records:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with self.path.open("a", encoding="utf-8") as fh:
            for record in records:
                key = tick_key(record)
                if key in self._seen:
                    continue
                fh.write(json.dumps(record, sort_keys=True) + "\n")
                self._seen.add(key)
                written += 1
        return written


# ---------------------------------------------------------------------------
# The logger — ties source + watchlist + writer; observe-only sampling
# ---------------------------------------------------------------------------
class QuoteLogger:
    """Samples the watchlist's quotes and appends the tick feed. Holds NO trading
    client, NO positions/cash/state — read a quote, write a line."""

    def __init__(
        self,
        source: QuoteSource,
        writer: TickFeedWriter,
        tickers: Sequence[str],
    ) -> None:
        self.source = source
        self.writer = writer
        self.tickers = list(tickers)
        self.source_name = getattr(source, "name", "unknown")

    def sample_once(self, *, now: datetime, force: bool = False) -> dict[str, Any]:
        """One observe-only sample. Gated to RTH unless ``force``. A quote-fetch
        failure for the whole batch or any single ticker is logged and skipped —
        never raised. Returns operational counts (no verdict, no price analysis)."""
        if not force and not is_market_hours(now):
            return {
                "sampled": False,
                "reason": "market_closed",
                "date": session_date(now),
                "n_tickers": len(self.tickers),
                "n_quoted": 0,
                "n_skipped": 0,
                "rows_written": 0,
            }

        date = session_date(now)
        try:
            quotes = self.source.get_quotes(self.tickers)
        except Exception as exc:  # noqa: BLE0001 — best-effort observability
            log.warning("quote batch failed (%s) — skipping this sample", exc)
            quotes = {}

        records: list[dict[str, Any]] = []
        n_skipped = 0
        for ticker in self.tickers:
            try:
                quote = quotes.get(ticker)
                if quote is None:
                    n_skipped += 1
                    log.debug("no quote for %s at %s — skipped", ticker, date)
                    continue
                record = build_tick_record(
                    ticker=ticker,
                    quote=quote,
                    sample_ts=now,
                    date=date,
                    source_name=self.source_name,
                )
                if record is None:
                    n_skipped += 1
                    log.debug("unpriceable quote for %s — skipped (no mid)", ticker)
                    continue
                records.append(record)
            except Exception as exc:  # noqa: BLE0001 — one bad tick never stops the rest
                n_skipped += 1
                log.warning("tick failed for %s (%s) — skipped", ticker, exc)

        written = self.writer.append(records)
        return {
            "sampled": True,
            "date": date,
            "n_tickers": len(self.tickers),
            "n_quoted": len(records),
            "n_skipped": n_skipped,
            "rows_written": written,
        }

    def run_loop(
        self,
        *,
        cadence_sec: float = DEFAULT_CADENCE_SEC,
        now_fn: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        force: bool = False,
        max_cycles: int | None = None,
    ) -> dict[str, Any]:
        """Loop and sample every ``cadence_sec`` while the market is open. Waits
        (does not sample) before the open and STOPS at/after the close, so a
        09:30-ET scheduled start self-terminates at 16:00 ET. ``now_fn`` /
        ``sleep_fn`` / ``max_cycles`` are injected so tests run with no wall-clock
        and no real sleeps. With ``force`` the RTH gate is bypassed (use with
        ``max_cycles`` or an external stop)."""
        now_fn = now_fn or (lambda: datetime.now(ET))
        cycles = 0
        samples = 0
        rows_written = 0
        while True:
            now = now_fn()
            phase = "open" if force else market_phase(now)
            if phase == "open":
                summary = self.sample_once(now=now, force=True)
                samples += 1
                rows_written += summary["rows_written"]
            elif phase == "closed":
                break
            # "before_open": wait for the open (no sample this cycle)
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            sleep_fn(cadence_sec)
        return {
            "cycles": cycles,
            "samples": samples,
            "rows_written": rows_written,
            "out": str(self.writer.path),
            "observe_only": True,
        }


# ---------------------------------------------------------------------------
# CLI — OBSERVE-ONLY; --once / loop; --json summary
# ---------------------------------------------------------------------------
def _resolve_tickers(args: argparse.Namespace) -> list[str]:
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = load_watchlist(args.watchlist)
    if args.limit_tickers is not None:
        tickers = tickers[: args.limit_tickers]
    return tickers


def main(argv: Sequence[str] | None = None, *, source: QuoteSource | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="intraday-quote-logger",
        description=(
            "renquant105 Stage-1 OBSERVE-ONLY intraday quote logger. Read-only "
            "market data: samples the watchlist and appends the structured JSONL "
            "tick feed the paired-IS harness consumes. Places no orders, touches "
            "no state — a separate process from the live runner."
        ),
    )
    parser.add_argument(
        "--watchlist",
        default=None,
        help="strategy config JSON to read 'watchlist' from (default: pinned config)",
    )
    parser.add_argument(
        "--tickers",
        default=None,
        help="comma-separated tickers overriding the watchlist (ad-hoc/testing)",
    )
    parser.add_argument(
        "--limit-tickers", type=int, default=None, help="cap the number of names"
    )
    parser.add_argument(
        "--out",
        default=None,
        help="tick-feed JSONL (append, idempotent; default under the data root)",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="operator data root for the default --out (else RENQUANT_DATA_ROOT)",
    )
    parser.add_argument(
        "--cadence", type=float, default=DEFAULT_CADENCE_SEC, help="seconds between samples (loop)"
    )
    parser.add_argument(
        "--once", action="store_true", help="take a single sample and exit"
    )
    parser.add_argument(
        "--force", action="store_true", help="bypass the market-hours gate (testing/off-hours)"
    )
    parser.add_argument(
        "--max-cycles", type=int, default=None, help="stop the loop after N cycles"
    )
    parser.add_argument(
        "--env-file", default=None, help="optional .env loaded for Alpaca credentials"
    )
    parser.add_argument("--json", action="store_true", help="emit the summary as JSON")
    parser.add_argument(
        "--log-level", default="WARNING", help="logging level (default WARNING)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING))

    if args.env_file:
        load_env_file(args.env_file)

    tickers = _resolve_tickers(args)

    if source is None:
        if not alpaca_credentials_present():
            print(
                "[intraday-quote-logger] ALPACA_API_KEY + ALPACA_SECRET_KEY not set "
                "(pass --env-file or export them). OBSERVE-ONLY still needs read-only "
                "market-data credentials.",
                flush=True,
            )
            return 2
        source = AlpacaQuoteSource()

    data_root = Path(args.data_root).expanduser().resolve() if args.data_root else None
    out = Path(args.out) if args.out else default_tick_feed_path(data_root)
    writer = TickFeedWriter(out)
    logger = QuoteLogger(source, writer, tickers)

    if args.once:
        result = logger.sample_once(now=datetime.now(ET), force=args.force)
        mode = "once"
    else:
        result = logger.run_loop(
            cadence_sec=args.cadence, force=args.force, max_cycles=args.max_cycles
        )
        mode = "loop"

    summary = {"mode": mode, "out": str(out), "observe_only": True, "n_tickers": len(tickers), **result}
    if args.json:
        print(json.dumps(summary, sort_keys=True, indent=2))
    else:
        print(f"[OBSERVE-ONLY] renquant105 Stage-1 intraday quote logger — {mode}")
        print(f"  tickers          : {len(tickers)}")
        print(f"  out              : {out}")
        for key in ("sampled", "date", "n_quoted", "n_skipped", "cycles", "samples", "rows_written"):
            if key in summary:
                print(f"  {key:<16} : {summary[key]}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
