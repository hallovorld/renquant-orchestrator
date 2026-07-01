"""renquant105 Stage-1 OBSERVE-ONLY real-time DATA PLANE (design §4 piece 2, §6).

Assembles a point-in-time intraday MARKET SNAPSHOT for the daily watchlist from
the streaming tick feed (the ``intraday_ticks.jsonl`` schema produced by the
#216 intraday quote logger) joined to the latest daily feature reference. It is
OBSERVE-ONLY: pure assembly + causality/staleness censoring — it places NO
orders and touches NO positions, cash, pins, gates, or run state.

Point-in-time / causality contract (design §6 class-C/D; the #216 freshness /
session / causality rules, reused verbatim in spirit):

  * **SAME-SESSION** — only ticks whose session ``date`` equals the ``as_of``
    session date are eligible; nothing carries across the session boundary.
  * **CAUSALITY** (``source_ts <= as_of``) — only ticks whose exchange
    ``tick_time`` is at/earlier than the decision ``as_of`` are eligible. A tick
    that arrives *after* ``as_of`` can never enter an earlier decision; this is
    exactly what makes a 10:00 vs 12:00 snapshot differ *only* in newly-arrived
    state, with no after-the-cutoff data path.
  * **FRESHNESS / staleness censoring** — among eligible ticks the LATEST (by
    ``tick_time``) is chosen; if its age (``as_of - tick_time``) exceeds
    ``staleness_sec`` the quote is CENSORED (``quote_status = "stale"``,
    ``intraday_mid = None``) so a stale tape can never masquerade as a fresh
    quote to any downstream consumer.

Snapshot row schema (design + task): ``{as_of, ticker, intraday_mid,
quote_status, daily_feature_ref}`` plus provenance (``source_ts``, ``age_sec``,
``source``, ``session_date``).

The tick-feed SOURCE is dependency-injected (a ``Protocol``): the real source
reads the accumulating ``intraday_ticks.jsonl`` under the operator data root
(:func:`~renquant_orchestrator.runtime_paths.default_data_root`, honoring
``RENQUANT_DATA_ROOT`` — NEVER the umbrella git tree); tests inject a
deterministic fake with an explicit ``as_of`` (no wall-clock, no network, no I/O).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

from .runtime_paths import default_data_root, default_strategy_config_path

STAGE = "renquant105-stage1-operations-only"
RECORD_KIND = "intraday_market_snapshot_row"
SNAPSHOT_SCHEMA_VERSION = "1"

# Reused from the #216 tick feed: US-equities regular session, America/New_York.
ET = ZoneInfo("America/New_York")

# Design §10 quote-staleness (entries): 5 s soft / 15 s hard-skip. The data plane
# censors at the hard-skip bound so a stale tape is never surfaced as a fresh mid.
DEFAULT_STALENESS_SEC = 15.0

QUOTE_OK = "ok"
QUOTE_STALE = "stale"
QUOTE_MISSING = "missing"


def default_tick_feed_path(data_root: Path | None = None) -> Path:
    """The accumulating #216 tick feed, under the operator data root.

    Mirrors the #216 ``intraday_quote_logger.default_tick_feed_path`` location so
    the data plane reads exactly what the logger writes. Rooted at
    :func:`default_data_root` (honoring ``RENQUANT_DATA_ROOT``), NEVER the
    umbrella git tree.
    """
    root = data_root or default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "intraday_ticks.jsonl"


# ---------------------------------------------------------------------------
# Time helpers (pure — no wall-clock; as_of is always explicit)
# ---------------------------------------------------------------------------
def _parse_dt(value: Any) -> datetime:
    """Parse an ISO-8601 timestamp (or pass a ``datetime`` through) into an
    aware datetime. A naive value is interpreted as ET (the session tz)."""
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt


def session_date(when: Any) -> str:
    """The ET calendar date (YYYY-MM-DD) of a timestamp — the session key ticks
    are filtered on (same rule as the #216 feed)."""
    return _parse_dt(when).astimezone(ET).date().isoformat()


# ---------------------------------------------------------------------------
# Tick-feed source interface (dependency-injected)
# ---------------------------------------------------------------------------
class TickFeedSource(Protocol):
    """Pluggable read-only tick source. The real impl reads the #216
    ``intraday_ticks.jsonl``; tests inject a deterministic fake. Yields raw tick
    mappings; the join applies the session + causality + staleness rules."""

    name: str

    def read_ticks(self) -> Iterable[Mapping[str, Any]]:
        ...


class JsonlTickFeedSource:
    """Read-only reader for the accumulating #216 ``intraday_ticks.jsonl``.

    Best-effort: blank or malformed lines are skipped, never raised — an
    observability feed must not crash the assembler."""

    name = "intraday_ticks_jsonl"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read_ticks(self) -> Iterable[Mapping[str, Any]]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row


# ---------------------------------------------------------------------------
# Snapshot data model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class IntradaySnapshotRow:
    """One point-in-time snapshot row for a single watchlist name."""

    as_of: str
    ticker: str
    intraday_mid: float | None
    quote_status: str
    daily_feature_ref: Any | None
    source_ts: str | None
    age_sec: float | None
    source: str | None
    session_date: str

    def to_record(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "ticker": self.ticker,
            "intraday_mid": self.intraday_mid,
            "quote_status": self.quote_status,
            "daily_feature_ref": self.daily_feature_ref,
            "source_ts": self.source_ts,
            "age_sec": self.age_sec,
            "source": self.source,
            "session_date": self.session_date,
        }


@dataclass(frozen=True)
class MarketSnapshot:
    """A watchlist-wide point-in-time snapshot at a single ``as_of``."""

    as_of: str
    session_date: str
    rows: tuple[IntradaySnapshotRow, ...]
    metadata: Mapping[str, Any]

    def by_ticker(self) -> dict[str, IntradaySnapshotRow]:
        return {row.ticker: row for row in self.rows}

    def fresh_rows(self) -> list[IntradaySnapshotRow]:
        """Rows with a fresh, priceable quote (``quote_status == "ok"``)."""
        return [row for row in self.rows if row.quote_status == QUOTE_OK]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "stage": STAGE,
            "record_kind": "intraday_market_snapshot",
            "observe_only": True,
            "as_of": self.as_of,
            "session_date": self.session_date,
            "rows": [row.to_record() for row in self.rows],
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# The assembler — pure, deterministic from (as_of, feed, daily features)
# ---------------------------------------------------------------------------
def _tick_mid(row: Mapping[str, Any]) -> float | None:
    mid = row.get("mid")
    if mid is None:
        return None
    try:
        return float(mid)
    except (TypeError, ValueError):
        return None


def _latest_eligible_ticks(
    *,
    ticks: Iterable[Mapping[str, Any]],
    tickers: set[str],
    sess: str,
    as_of_dt: datetime,
) -> dict[str, tuple[datetime, float, str | None]]:
    """Fold the raw feed into the latest same-session, causal, priceable tick per
    watchlist ticker: ``ticker -> (tick_dt, mid, source)``.

    A tick is eligible iff (i) its session ``date`` equals ``sess``, (ii) its
    exchange ``tick_time`` parses and is ``<= as_of`` (causality), and (iii) it
    carries a priceable ``mid``. Among eligible ticks the one with the greatest
    ``tick_time`` wins.
    """
    best: dict[str, tuple[datetime, float, str | None]] = {}
    for row in ticks:
        ticker = str(row.get("ticker", "")).strip().upper()
        if ticker not in tickers:
            continue
        if str(row.get("date", "")) != sess:
            continue  # cross-session tick — never carried
        raw_ts = row.get("tick_time")
        if raw_ts is None:
            continue
        try:
            tick_dt = _parse_dt(raw_ts)
        except (ValueError, TypeError):
            continue
        if tick_dt > as_of_dt:
            continue  # future tick — causality censors it
        mid = _tick_mid(row)
        if mid is None:
            continue  # unpriceable — never imputed
        prior = best.get(ticker)
        if prior is None or tick_dt > prior[0]:
            source = row.get("source")
            best[ticker] = (tick_dt, mid, str(source) if source is not None else None)
    return best


def build_realtime_snapshot(
    *,
    as_of: Any,
    daily_features: Mapping[str, Any],
    feed_source: TickFeedSource,
    staleness_sec: float = DEFAULT_STALENESS_SEC,
    tickers: Sequence[str] | None = None,
) -> MarketSnapshot:
    """Assemble a point-in-time :class:`MarketSnapshot` at ``as_of``.

    ``daily_features`` maps ``ticker -> daily_feature_ref`` — the frozen class-A/B
    reference from the T-1 EOD build (a ``signal_version`` string, a fingerprint
    dict, whatever the caller pins); its keys define the watchlist unless
    ``tickers`` overrides. Each name is joined to the latest same-session, causal,
    non-stale tick from ``feed_source`` per the §6 contract above.
    """
    as_of_dt = _parse_dt(as_of)
    as_of_iso = as_of_dt.isoformat()
    sess = as_of_dt.astimezone(ET).date().isoformat()

    ref_by_ticker = {str(t).strip().upper(): ref for t, ref in daily_features.items()}
    if tickers is not None:
        watchlist = [str(t).strip().upper() for t in tickers]
    else:
        watchlist = sorted(ref_by_ticker)

    best = _latest_eligible_ticks(
        ticks=feed_source.read_ticks(),
        tickers=set(watchlist),
        sess=sess,
        as_of_dt=as_of_dt,
    )

    rows: list[IntradaySnapshotRow] = []
    counts = {QUOTE_OK: 0, QUOTE_STALE: 0, QUOTE_MISSING: 0}
    for ticker in watchlist:
        ref = ref_by_ticker.get(ticker)
        chosen = best.get(ticker)
        if chosen is None:
            status, mid, source_ts, age_sec, source = QUOTE_MISSING, None, None, None, None
        else:
            tick_dt, tick_mid, source = chosen
            age_sec = (as_of_dt - tick_dt).total_seconds()
            source_ts = tick_dt.isoformat()
            if age_sec > staleness_sec:
                status, mid = QUOTE_STALE, None  # censored — never surfaced as fresh
            else:
                status, mid = QUOTE_OK, tick_mid
        counts[status] += 1
        rows.append(
            IntradaySnapshotRow(
                as_of=as_of_iso,
                ticker=ticker,
                intraday_mid=mid,
                quote_status=status,
                daily_feature_ref=ref,
                source_ts=source_ts,
                age_sec=age_sec,
                source=source,
                session_date=sess,
            )
        )

    metadata = {
        "feed_source": getattr(feed_source, "name", "unknown"),
        "staleness_sec": float(staleness_sec),
        "n_tickers": len(watchlist),
        "n_ok": counts[QUOTE_OK],
        "n_stale": counts[QUOTE_STALE],
        "n_missing": counts[QUOTE_MISSING],
        "schema_ref": "intraday_ticks.jsonl (#216)",
    }
    return MarketSnapshot(
        as_of=as_of_iso,
        session_date=sess,
        rows=tuple(rows),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# CLI — OBSERVE-ONLY snapshot assembly (no orders, no state)
# ---------------------------------------------------------------------------
def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"payload must be a JSON object: {path}")
    return payload


def _daily_features_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = payload.get("features", payload)
    if not isinstance(raw, Mapping):
        raise ValueError("daily-features JSON must be an object (ticker -> ref)")
    return {str(t).strip().upper(): ref for t, ref in raw.items()}


def _load_watchlist_features(config_path: str | Path | None) -> dict[str, Any]:
    """Fallback daily-feature refs = the pinned watchlist, each ref = the config
    session date (a minimal frozen ref) when no explicit features JSON is given."""
    path = Path(config_path) if config_path else default_strategy_config_path()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    watchlist = data.get("watchlist")
    if not isinstance(watchlist, list) or not watchlist:
        raise ValueError(f"strategy config {path} has no non-empty 'watchlist'")
    ref = {"source": "strategy_config_watchlist", "config_path": str(path)}
    return {str(t).strip().upper(): ref for t in watchlist}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="realtime-data-plane",
        description=(
            "renquant105 Stage-1 OBSERVE-ONLY real-time data plane. Assembles a "
            "point-in-time intraday market snapshot for the watchlist from the "
            "#216 intraday_ticks.jsonl feed. Places no orders, touches no state."
        ),
    )
    parser.add_argument("--as-of", required=True, help="decision point-in-time (ISO-8601)")
    parser.add_argument(
        "--tick-feed", default=None, help="intraday_ticks.jsonl (default under the data root)"
    )
    parser.add_argument(
        "--daily-features-json",
        default=None,
        help="JSON object ticker->daily_feature_ref (default: pinned watchlist)",
    )
    parser.add_argument("--watchlist", default=None, help="strategy config for the fallback watchlist")
    parser.add_argument(
        "--staleness-sec", type=float, default=DEFAULT_STALENESS_SEC, help="stale-quote censor bound"
    )
    parser.add_argument("--data-root", default=None, help="operator data root for the default feed")
    parser.add_argument("--output-json", default=None, help="optional file to write the snapshot to")
    parser.add_argument("--json", action="store_true", help="emit the snapshot payload as JSON")
    args = parser.parse_args(argv)

    data_root = Path(args.data_root).expanduser().resolve() if args.data_root else None
    feed_path = Path(args.tick_feed) if args.tick_feed else default_tick_feed_path(data_root)

    if args.daily_features_json:
        daily_features = _daily_features_from_payload(_load_json_object(args.daily_features_json))
    else:
        daily_features = _load_watchlist_features(args.watchlist)

    snapshot = build_realtime_snapshot(
        as_of=args.as_of,
        daily_features=daily_features,
        feed_source=JsonlTickFeedSource(feed_path),
        staleness_sec=args.staleness_sec,
    )
    payload = snapshot.to_payload()

    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        meta = payload["metadata"]
        print("[OBSERVE-ONLY] renquant105 Stage-1 real-time data plane")
        print(f"  as_of        : {snapshot.as_of}")
        print(f"  session_date : {snapshot.session_date}")
        print(f"  feed         : {feed_path}")
        print(f"  tickers      : {meta['n_tickers']}")
        print(f"  ok/stale/miss: {meta['n_ok']}/{meta['n_stale']}/{meta['n_missing']}")
    return 0


__all__ = [
    "DEFAULT_STALENESS_SEC",
    "IntradaySnapshotRow",
    "JsonlTickFeedSource",
    "MarketSnapshot",
    "QUOTE_MISSING",
    "QUOTE_OK",
    "QUOTE_STALE",
    "RECORD_KIND",
    "SNAPSHOT_SCHEMA_VERSION",
    "STAGE",
    "TickFeedSource",
    "build_realtime_snapshot",
    "default_tick_feed_path",
    "main",
    "session_date",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
