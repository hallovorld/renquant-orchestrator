"""renquant105 Stage-1 OPERATIONS-ONLY intraday quote logger (the tick feed).

STANDALONE, DECOUPLED, OBSERVE-ONLY quote poller for the intraday-decisioning RFC
(``doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md``,
converged r11/r12). During a real exchange session it samples the daily
watchlist's quotes and appends a **structured JSONL tick feed** — the class-D
"timing-only quote" arrival/reference the paired-IS harness consumes (design
§9.1, §9.2c: the decision-time NBBO midpoint). Without this feed,
``intraday_pairing_logger.py`` (orchestrator PR #215) censors every pair
``no_intraday_tick``; this module is the missing producer.

**This is a SEPARATE PROCESS from the live decision / intraday runner.** It is
NOT embedded in any decision path. It reads market data and appends a log file —
nothing else. A bug in it can never affect a live trade:

  * OBSERVE-ONLY read-only market data — places NO orders, touches NO positions,
    cash, pins, gates, or run state;
  * the quote SOURCE and the EXCHANGE CALENDAR are both dependency-injected
    (interfaces) so the real Alpaca market-data client / real NYSE calendar are
    only ever constructed for a real run — tests use a deterministic fake source,
    a fake calendar and an injected clock (no wall-clock, no network);
  * the OUTPUT defaults under the operator data root
    (:func:`~renquant_orchestrator.runtime_paths.default_data_root`, honoring
    ``RENQUANT_DATA_ROOT``) — it NEVER writes into the umbrella git tree;
  * best-effort: a quote-fetch failure for one ticker (or the whole batch) is
    logged and skipped — it never crashes the loop.

Data-validity (why the feed can be trusted as *eligible decision-tick* evidence):

  * **Session boundaries** come from the SAME exchange-calendar primitive
    execution uses (``pandas_market_calendars`` NYSE — see
    ``renquant_execution.preopen_cancel_gate``), so holidays, HALF DAYS / early
    closes and DST are honored. Out-of-session samples are CENSORED, never logged
    as eligible ticks.
  * **Causality + freshness**: every quote must carry a source timestamp with
    ``source_ts <= sampled_at``, be no older than a configured maximum age, and
    belong to the CURRENT session. A repeated prior-session quote, a future/skewed
    timestamp, or a crossed/invalid NBBO is CENSORED (recorded with a ``status``
    to a separate audit sidecar), never emitted to the eligible feed.
  * **Frozen eligibility policy**: each record stamps
    :data:`ELIGIBILITY_POLICY_VERSION` plus the concrete policy params, so a row
    self-identifies which eligibility/decision policy admitted it (a 60s stream
    alone does not identify which quote was available at the decision instant).

Schema alignment (the load-bearing contract): each ELIGIBLE JSONL line carries the
exact keys ``intraday_pairing_logger.load_intraday_ticks`` reads — ``date``
(session, filtered on equality), ``ticker``, ``mid`` (the decision-time reference
mid) and ``tick_time`` — plus richer raw fields (``bid``/``ask``/``last``/``ts``,
``status``, ``quote_age`` …) for the future analysis. ``entry_price`` is
deliberately NOT asserted here: the consumer defaults the hypothetical intraday
entry to ``mid`` (the honest neutral choice for an observe-only feed); a fill
model is the future experiment's call (design §9.4). Midpoint-as-fill yields zero
modeled shortfall by construction — this feed stores raw observations only and
implies NO executable performance.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import date as date_cls, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

from .env_files import load_env_file
from .runtime_paths import default_data_root, default_strategy_config_path

log = logging.getLogger("renquant.intraday_quote_logger")

# Schema version for the tick JSONL rows — bump if the record shape changes so the
# consumer (intraday_pairing_logger, §9.4 experiment) can migrate cleanly.
TICK_SCHEMA_VERSION = "2"
STAGE = "renquant105-stage1-operations-only"
RECORD_KIND = "intraday_quote_tick"

# FROZEN eligibility / decision policy. Bump when any admission rule below changes
# (session source, max age, NBBO validity, causality tolerance). Stamped on every
# record so a row self-identifies the policy that admitted or censored it.
ELIGIBILITY_POLICY_VERSION = "renquant105-eligibility-v1"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

DEFAULT_CADENCE_SEC = 60
# A decision tick must be fresh: quotes older than this (vs the sample instant) are
# censored ``stale_quote``. 120s comfortably covers a 60s cadence + slack.
DEFAULT_MAX_QUOTE_AGE_SEC = 120.0
# Small tolerance for benign sub-second clock skew before a quote is treated as a
# future/skewed timestamp (causality violation).
DEFAULT_FUTURE_TOLERANCE_SEC = 2.0

# Record statuses. Only ``ok`` rows are eligible decision ticks (written to the
# feed the consumer reads); every other status is a CENSOR reason (written to the
# audit sidecar, never emitted as evidence).
STATUS_OK = "ok"
STATUS_OUT_OF_SESSION = "out_of_session"
STATUS_UNPRICEABLE = "unpriceable"
STATUS_CROSSED_NBBO = "crossed_nbbo"
STATUS_INVALID_NBBO = "invalid_nbbo"
STATUS_NO_SOURCE_TS = "no_source_ts"
STATUS_FUTURE_QUOTE = "future_quote"
STATUS_STALE_PRIOR_SESSION = "stale_prior_session"
STATUS_STALE_QUOTE = "stale_quote"


def default_tick_feed_path(data_root: Path | None = None) -> Path:
    """Default accumulating tick-feed file, under the operator data root.

    Mirrors ``intraday_pairing_logger.default_pilot_path`` naming but for the tick
    source (its ``DEFAULT_TICK_SOURCE``): a single rolling JSONL the consumer
    filters by ``date``. Rooted at :func:`default_data_root` (honoring
    ``RENQUANT_DATA_ROOT``), NEVER the umbrella git tree.
    """
    root = data_root or default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "intraday_ticks.jsonl"


def default_censor_feed_path(feed_path: str | Path) -> Path:
    """Audit sidecar next to the eligible feed: ``<feed>.censored.jsonl``.

    Censored observations (out-of-session, stale, future, crossed/invalid NBBO …)
    are recorded here WITH a ``status`` so they are auditable, but are kept out of
    the eligible feed the consumer reads — a censored quote can never be mistaken
    for a valid decision tick."""
    p = Path(feed_path)
    return p.with_name(p.name + ".censored.jsonl")


# ---------------------------------------------------------------------------
# Quote source interface (dependency-injected) + a plain quote value
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Quote:
    """A single quote observation. ``ts`` is the source's exchange timestamp for
    the quote (ISO-8601), used as the decision-time reference, the causality axis
    and the idempotency axis; ``bid``/``ask`` form the NBBO midpoint, ``last`` is
    the last trade."""

    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    ts: str | None = None

    def mid(self) -> float | None:
        """NBBO midpoint when both sides are present; fall back to last trade when
        the spread is one-sided/absent; ``None`` when nothing is priceable
        (recorded as a skip — never imputed). Does NOT validate the NBBO — see
        :func:`evaluate_quote` for crossed/invalid censoring."""
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
# Exchange-calendar / session-boundary primitive (dependency-injected)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SessionBounds:
    """The regular-trading-hours boundaries of ONE exchange session, as aware ET
    datetimes. ``open`` is inclusive, ``close`` is exclusive. Early closes yield an
    earlier ``close``; DST is already resolved (the datetimes are tz-aware)."""

    open: datetime
    close: datetime

    def contains(self, moment: datetime) -> bool:
        """True when ``moment`` (aware) is within [open, close)."""
        m = _as_aware(moment)
        return self.open <= m < self.close


class SessionCalendar(Protocol):
    """Pluggable exchange session calendar. The real impl is NYSE via
    ``pandas_market_calendars`` (the SAME primitive execution uses); tests inject a
    deterministic fake. ``session_bounds`` returns ``None`` for a non-trading day
    (weekend/holiday)."""

    name: str

    def session_bounds(self, day: date_cls) -> SessionBounds | None:
        ...


class NyseSessionCalendar:
    """Real NYSE session calendar backed by ``pandas_market_calendars`` — the same
    primitive ``renquant_execution.preopen_cancel_gate`` uses. Handles holidays
    (no session), half days / early closes (earlier ``market_close``) and DST
    (tz-aware timestamps). Schedules are cached per date so the sampling loop pays
    the pandas cost once per session, not once per tick."""

    name = "NYSE"

    def __init__(self, calendar_name: str = "NYSE") -> None:
        self.name = calendar_name
        self._cal: Any | None = None
        self._cache: dict[str, SessionBounds | None] = {}

    def _calendar(self) -> Any:
        if self._cal is None:
            import pandas_market_calendars as mcal  # noqa: PLC0415

            self._cal = mcal.get_calendar(self.name)
        return self._cal

    def session_bounds(self, day: date_cls) -> SessionBounds | None:
        key = day.isoformat()
        if key in self._cache:
            return self._cache[key]
        cal = self._calendar()
        sched = cal.schedule(key, key)
        bounds: SessionBounds | None
        if sched.empty:
            bounds = None
        else:
            open_ts = sched["market_open"].iloc[0]
            close_ts = sched["market_close"].iloc[0]
            bounds = SessionBounds(open=_pandas_ts_to_et(open_ts), close=_pandas_ts_to_et(close_ts))
        self._cache[key] = bounds
        return bounds


_DEFAULT_CALENDAR: SessionCalendar | None = None


def default_session_calendar() -> SessionCalendar:
    """Lazily-constructed shared NYSE calendar for real runs. Tests inject a fake
    and never reach this."""
    global _DEFAULT_CALENDAR
    if _DEFAULT_CALENDAR is None:
        _DEFAULT_CALENDAR = NyseSessionCalendar()
    return _DEFAULT_CALENDAR


def _as_aware(moment: datetime) -> datetime:
    """Treat a naive datetime as ET; leave an aware one alone."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=ET)


def _pandas_ts_to_et(ts: Any) -> datetime:
    """Convert a (tz-aware, typically UTC) pandas Timestamp to an aware ET
    ``datetime``. DST is resolved by the tz conversion."""
    to_pydatetime = getattr(ts, "to_pydatetime", None)
    dt = to_pydatetime() if callable(to_pydatetime) else ts
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(ET)


# ---------------------------------------------------------------------------
# Market-hours gating (clock + calendar both injected)
# ---------------------------------------------------------------------------
def market_phase(now: datetime, calendar: SessionCalendar | None = None) -> str:
    """``"open"`` / ``"before_open"`` / ``"closed"`` for an aware datetime, per the
    exchange calendar. A non-trading day (weekend/holiday) and post-close are
    ``"closed"``; a naive datetime is treated as ET. Early closes are honored (the
    session ``close`` comes from the calendar)."""
    cal = calendar or default_session_calendar()
    et = _as_aware(now).astimezone(ET)
    bounds = cal.session_bounds(et.date())
    if bounds is None:
        return "closed"
    if et < bounds.open:
        return "before_open"
    if et >= bounds.close:
        return "closed"
    return "open"


def is_market_hours(now: datetime, calendar: SessionCalendar | None = None) -> bool:
    """True during a real exchange session (calendar-aware, incl. early closes)."""
    return market_phase(now, calendar) == "open"


def session_date(now: datetime) -> str:
    """The ET calendar date (YYYY-MM-DD) of a sample — the session key the consumer
    filters on."""
    return _as_aware(now).astimezone(ET).date().isoformat()


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
# Quote eligibility evaluation (pure — causality, freshness, NBBO validity)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class QuoteEval:
    """Verdict of the frozen eligibility policy for one quote at one sample instant.
    ``status`` is :data:`STATUS_OK` for an eligible tick, else a censor reason.
    ``mid`` is the decision-time reference mid (only populated when ``ok``)."""

    status: str
    mid: float | None
    quote_age: float | None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _as_aware(dt)


def evaluate_quote(
    quote: Quote,
    *,
    sampled_at: datetime,
    session: SessionBounds | None,
    max_age_sec: float = DEFAULT_MAX_QUOTE_AGE_SEC,
    future_tolerance_sec: float = DEFAULT_FUTURE_TOLERANCE_SEC,
) -> QuoteEval:
    """Apply the FROZEN eligibility policy to one quote. First failing check wins:

    1. sample outside a real session (``session is None`` or ``sampled_at`` not in
       it) -> ``out_of_session``;
    2. nothing priceable -> ``unpriceable``;
    3. crossed NBBO (bid > ask) -> ``crossed_nbbo``;
    4. non-positive / non-finite NBBO or mid -> ``invalid_nbbo``;
    5. no source timestamp (causality unprovable) -> ``no_source_ts``;
    6. source_ts > sampled_at (+tolerance) -> ``future_quote``;
    7. source_ts outside the current session (repeated prior-session /
       pre-open) -> ``stale_prior_session``;
    8. quote_age > max_age -> ``stale_quote``;
    9. otherwise -> ``ok`` (with the decision-time mid + quote_age)."""
    sampled = _as_aware(sampled_at)

    # 1. session membership of the SAMPLE
    if session is None or not session.contains(sampled):
        return QuoteEval(STATUS_OUT_OF_SESSION, None, None)

    # 2/3/4. priceability + NBBO validity
    bid, ask = quote.bid, quote.ask
    both_sides = bid is not None and ask is not None
    if both_sides:
        if float(bid) > float(ask):
            return QuoteEval(STATUS_CROSSED_NBBO, None, None)
        if not (math.isfinite(float(bid)) and math.isfinite(float(ask))) or float(bid) <= 0 or float(ask) <= 0:
            return QuoteEval(STATUS_INVALID_NBBO, None, None)
    mid = quote.mid()
    if mid is None:
        return QuoteEval(STATUS_UNPRICEABLE, None, None)
    if not math.isfinite(mid) or mid <= 0:
        return QuoteEval(STATUS_INVALID_NBBO, None, None)

    # 5/6/7/8. causality + freshness + same-session membership of the QUOTE
    source_ts = _parse_ts(quote.ts)
    if source_ts is None:
        return QuoteEval(STATUS_NO_SOURCE_TS, None, None)
    quote_age = (sampled - source_ts).total_seconds()
    if quote_age < -abs(future_tolerance_sec):
        return QuoteEval(STATUS_FUTURE_QUOTE, None, quote_age)
    if not session.contains(source_ts):
        return QuoteEval(STATUS_STALE_PRIOR_SESSION, None, quote_age)
    if quote_age > max_age_sec:
        return QuoteEval(STATUS_STALE_QUOTE, None, quote_age)

    return QuoteEval(STATUS_OK, mid, quote_age)


# ---------------------------------------------------------------------------
# Pure tick-record builder (no I/O — fully testable)
# ---------------------------------------------------------------------------
def build_tick_record(
    *,
    ticker: str,
    quote: Quote,
    sample_ts: datetime,
    session: SessionBounds | None,
    date: str | None = None,
    source_name: str = "unknown",
    max_age_sec: float = DEFAULT_MAX_QUOTE_AGE_SEC,
    future_tolerance_sec: float = DEFAULT_FUTURE_TOLERANCE_SEC,
) -> dict[str, Any]:
    """Build one tick record aligned to the ``intraday_pairing_logger`` schema.

    ALWAYS returns a record (never ``None``): a valid quote gets ``status="ok"``
    and a consumable ``mid``; a quote that fails the frozen eligibility policy gets
    the censor ``status`` and ``mid=None`` (so even if a censored row reached the
    consumer it could not be used as evidence). The caller routes ``ok`` rows to
    the eligible feed and censored rows to the audit sidecar.

    ``date`` (consumer-filtered), ``ticker``, ``mid`` and ``tick_time`` are the
    keys the consumer reads; ``tick_time`` is the quote's exchange timestamp (the
    true as-of of the mid) when present, else the sample time. Raw
    ``bid``/``ask``/``last``/``ts``, the frozen policy version, ``status`` and
    ``quote_age`` ride along for the future analysis; the consumer ignores extra
    keys.
    """
    verdict = evaluate_quote(
        quote,
        sampled_at=sample_ts,
        session=session,
        max_age_sec=max_age_sec,
        future_tolerance_sec=future_tolerance_sec,
    )
    sample_iso = _as_aware(sample_ts).isoformat()
    tick_time = quote.ts or sample_iso
    return {
        "schema_version": TICK_SCHEMA_VERSION,
        "stage": STAGE,
        "record_kind": RECORD_KIND,
        "observe_only": True,
        "eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
        "status": verdict.status,
        "date": date if date is not None else session_date(sample_ts),
        "ticker": ticker,
        # Only eligible ticks carry a consumable mid; censored rows are mid=None.
        "mid": verdict.mid,
        "tick_time": tick_time,
        "quote_age": verdict.quote_age,
        "max_quote_age_sec": max_age_sec,
        "session_open": session.open.isoformat() if session else None,
        "session_close": session.close.isoformat() if session else None,
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
# The logger — ties source + calendar + watchlist + writer; observe-only sampling
# ---------------------------------------------------------------------------
class QuoteLogger:
    """Samples the watchlist's quotes and appends the tick feed. Holds NO trading
    client, NO positions/cash/state — read a quote, evaluate eligibility, write a
    line. Eligible (``ok``) ticks go to the feed; censored observations go to the
    audit sidecar."""

    def __init__(
        self,
        source: QuoteSource,
        writer: TickFeedWriter,
        tickers: Sequence[str],
        *,
        calendar: SessionCalendar | None = None,
        censor_writer: TickFeedWriter | None = None,
        max_quote_age_sec: float = DEFAULT_MAX_QUOTE_AGE_SEC,
        future_tolerance_sec: float = DEFAULT_FUTURE_TOLERANCE_SEC,
    ) -> None:
        self.source = source
        self.writer = writer
        self.tickers = list(tickers)
        self.source_name = getattr(source, "name", "unknown")
        self.calendar = calendar or default_session_calendar()
        # Default the audit sidecar next to the eligible feed unless one is given.
        if censor_writer is None:
            censor_writer = TickFeedWriter(default_censor_feed_path(writer.path))
        self.censor_writer = censor_writer
        self.max_quote_age_sec = max_quote_age_sec
        self.future_tolerance_sec = future_tolerance_sec

    def sample_once(self, *, now: datetime, force: bool = False) -> dict[str, Any]:
        """One observe-only sample. Gated to a real session unless ``force``. Even
        under ``force`` an out-of-session quote is CENSORED (never eligible), so a
        forced off-hours run produces audit rows, not evidence. A quote-fetch
        failure for the whole batch or any single ticker is logged and skipped —
        never raised. Returns operational counts (no verdict, no price analysis)."""
        if not force and not is_market_hours(now, self.calendar):
            return {
                "sampled": False,
                "reason": "market_closed",
                "date": session_date(now),
                "n_tickers": len(self.tickers),
                "n_ok": 0,
                "n_censored": 0,
                "n_missing": 0,
                "rows_written": 0,
                "censored_written": 0,
                "censored_reasons": {},
            }

        date = session_date(now)
        session = self.calendar.session_bounds(_as_aware(now).astimezone(ET).date())
        try:
            quotes = self.source.get_quotes(self.tickers)
        except Exception as exc:  # noqa: BLE0001 — best-effort observability
            log.warning("quote batch failed (%s) — skipping this sample", exc)
            quotes = {}

        eligible: list[dict[str, Any]] = []
        censored: list[dict[str, Any]] = []
        censored_reasons: dict[str, int] = {}
        n_missing = 0
        for ticker in self.tickers:
            try:
                quote = quotes.get(ticker)
                if quote is None:
                    n_missing += 1
                    log.debug("no quote for %s at %s — skipped (source gap)", ticker, date)
                    continue
                record = build_tick_record(
                    ticker=ticker,
                    quote=quote,
                    sample_ts=now,
                    session=session,
                    date=date,
                    source_name=self.source_name,
                    max_age_sec=self.max_quote_age_sec,
                    future_tolerance_sec=self.future_tolerance_sec,
                )
                if record["status"] == STATUS_OK:
                    eligible.append(record)
                else:
                    censored.append(record)
                    censored_reasons[record["status"]] = censored_reasons.get(record["status"], 0) + 1
            except Exception as exc:  # noqa: BLE0001 — one bad tick never stops the rest
                n_missing += 1
                log.warning("tick failed for %s (%s) — skipped", ticker, exc)

        written = self.writer.append(eligible)
        censored_written = self.censor_writer.append(censored)
        return {
            "sampled": True,
            "date": date,
            "n_tickers": len(self.tickers),
            "n_ok": len(eligible),
            "n_censored": len(censored),
            "n_missing": n_missing,
            "rows_written": written,
            "censored_written": censored_written,
            "censored_reasons": censored_reasons,
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
        09:30-ET scheduled start self-terminates at the calendar close (incl. early
        closes). ``now_fn`` / ``sleep_fn`` / ``max_cycles`` are injected so tests
        run with no wall-clock and no real sleeps. With ``force`` the session gate
        is bypassed (use with ``max_cycles`` or an external stop); off-hours forced
        samples still censor to the audit sidecar."""
        now_fn = now_fn or (lambda: datetime.now(ET))
        cycles = 0
        samples = 0
        rows_written = 0
        censored_written = 0
        while True:
            now = now_fn()
            phase = "open" if force else market_phase(now, self.calendar)
            if phase == "open":
                summary = self.sample_once(now=now, force=True)
                samples += 1
                rows_written += summary["rows_written"]
                censored_written += summary["censored_written"]
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
            "censored_written": censored_written,
            "out": str(self.writer.path),
            "censored_out": str(self.censor_writer.path),
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
        "--max-quote-age",
        type=float,
        default=DEFAULT_MAX_QUOTE_AGE_SEC,
        help="max quote age (s) before a tick is censored stale (freshness policy)",
    )
    parser.add_argument(
        "--once", action="store_true", help="take a single sample and exit"
    )
    parser.add_argument(
        "--force", action="store_true", help="bypass the session gate (testing/off-hours; still censors out-of-session)"
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
    logger = QuoteLogger(source, writer, tickers, max_quote_age_sec=args.max_quote_age)

    if args.once:
        result = logger.sample_once(now=datetime.now(ET), force=args.force)
        mode = "once"
    else:
        result = logger.run_loop(
            cadence_sec=args.cadence, force=args.force, max_cycles=args.max_cycles
        )
        mode = "loop"

    summary = {
        "mode": mode,
        "out": str(out),
        "censored_out": str(logger.censor_writer.path),
        "observe_only": True,
        "eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
        "n_tickers": len(tickers),
        **result,
    }
    if args.json:
        print(json.dumps(summary, sort_keys=True, indent=2, default=str))
    else:
        print(f"[OBSERVE-ONLY] renquant105 Stage-1 intraday quote logger — {mode}")
        print(f"  tickers          : {len(tickers)}")
        print(f"  out              : {out}")
        print(f"  policy           : {ELIGIBILITY_POLICY_VERSION}")
        for key in (
            "sampled", "date", "n_ok", "n_censored", "n_missing",
            "cycles", "samples", "rows_written", "censored_written",
        ):
            if key in summary:
                print(f"  {key:<16} : {summary[key]}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
