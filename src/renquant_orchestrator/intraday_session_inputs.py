"""renquant105 Stage-1 intraday input assembly (RFC #208 §6, §8 row 3).

Builds the four-class point-in-time inputs the intraday decision tick
consumes (pipeline slice, renquant-pipeline #163), on the ORCHESTRATOR side
of the §8 boundary: this module reads committed run state + broker state and
assembles plain JSON-able mappings; it never scores, gates, sizes, or places
anything.

- **Class A (frozen signal)** — :func:`load_frozen_daily_signal`: the panel
  scores of the latest COMMITTED daily full run, read-only from
  ``runs.alpaca.db`` with the same selection discipline as
  ``ops/renquant105/export_batch_scores.py`` (joined ``pipeline_runs``,
  ``run_type='live'``, bound fingerprints, the run's own candidate roster as
  the coverage denominator). **Leak guard (§6):** the source run's date must
  equal EXACTLY the immediately preceding session per the injected exchange
  calendar — today's run (or any run dated >= the session) is refused with
  :class:`SignalLeakError`, and there is no fallback to an older run (a
  multi-day outage must fail loudly, never silently serve a stale vector).
- **Class B (session-start PIT gate inputs)** — :func:`capture_session_start`
  fingerprints the gate-input mapping with the SAME ``hash_jsonable``
  primitive the pipeline's ``SessionStartSnapshot.verify()`` re-computes, so
  the two sides agree byte-for-byte on what "frozen" means.
- **Class C (live state)** — :class:`AlpacaLiveStateSource` snapshots
  positions/cash/equity via READ-ONLY broker calls (GET account / GET
  positions only; it never constructs an order object and has no submit
  path), plus the §7 reservations parsed from a slice-1
  ``OrderStateBook.to_snapshot()`` state file
  (:func:`load_order_state_reservations` — schema
  ``order-state-machine-v1``, renquant-execution #20).
- **Class D (timing-only quote)** — reuses the observe-only
  :class:`~renquant_orchestrator.intraday_quote_logger.QuoteSource`
  protocol; prices ride in ``LiveStateSnapshot.prices`` where the pipeline
  contract structurally bars them from gates/scores (sizing reference only).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from renquant_artifacts import hash_jsonable

from .intraday_quote_logger import (
    ET,
    QuoteSource,
    SessionCalendar,
    _as_aware,
)

log = logging.getLogger("renquant.intraday_session_inputs")

#: Slice-1 state-file schema this module can read (renquant-execution #20,
#: ``order_state_machine.ORDER_STATE_SCHEMA_VERSION``).
ORDER_STATE_SCHEMA_VERSION = "order-state-machine-v1"

#: Child states that are live at the broker and therefore consume a §7
#: reservation — mirrors ``order_state_machine.OPEN_CHILD_STATES`` (a
#: STALE_PENDING order is still open until the cancel is reconciled).
OPEN_CHILD_STATES = frozenset(
    {"SUBMITTED", "ACCEPTED", "PARTIALLY_FILLED", "STALE_PENDING"}
)

#: Same floors export_batch_scores.py enforces (see its module docstring for
#: the Codex #236 review history); kept in lockstep until #227's gate-input
#: census ships a canonical expected-universe utility to defer to.
DEFAULT_MIN_ROWS = 80
DEFAULT_MIN_COVERAGE_FRACTION = 0.9

_MAX_PRIOR_SESSION_LOOKBACK_DAYS = 10


class FrozenSignalError(ValueError):
    """No qualifying class-A frozen signal exists for the session."""


class SignalLeakError(FrozenSignalError):
    """A candidate class-A signal violates the §6 point-in-time contract."""


class OrderStateFileError(ValueError):
    """The slice-1 order-state file is present but not readable as such."""


# ---------------------------------------------------------------------------
# Calendar helper — the prior session per the SAME injected NYSE primitive.
# ---------------------------------------------------------------------------
def previous_session(
    calendar: SessionCalendar,
    session_date: str,
    *,
    max_lookback_days: int = _MAX_PRIOR_SESSION_LOOKBACK_DAYS,
) -> str:
    """The immediately preceding exchange session strictly before ``session_date``.

    Campaign B5: delegates to the canonical
    :func:`renquant_common.market_calendar.previous_session_from_calendar`
    (injected-calendar day-walk — holiday / weekend / half-day aware; half
    days are still sessions). Raises :class:`FrozenSignalError` when no
    session exists within the lookback window (a data problem worth failing
    loudly on, not a fallback case).
    """
    from renquant_common.market_calendar import (  # noqa: PLC0415
        previous_session_from_calendar,
    )

    try:
        return previous_session_from_calendar(
            calendar, str(session_date), max_lookback_days=max_lookback_days
        ).isoformat()
    except ValueError as exc:
        raise FrozenSignalError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Class A — frozen daily signal from the committed run DB (read-only).
# ---------------------------------------------------------------------------
_REQUIRED_ARTIFACT_KEYS = frozenset({
    "panel",
    "global_calibration",
    "ranking.panel_scoring.artifact_path",
})


def _fingerprint_gaps(run_bundle: Mapping[str, Any]) -> list[str]:
    gaps = []
    if not run_bundle.get("config_hash"):
        gaps.append("config_hash")
    artifact_hashes = run_bundle.get("artifact_hashes") or {}
    if not artifact_hashes:
        gaps.append("artifact_hashes")
    else:
        missing_required = _REQUIRED_ARTIFACT_KEYS - {
            k for k, v in artifact_hashes.items() if v
        }
        if missing_required:
            gaps.append(f"artifact_hashes({','.join(sorted(missing_required))})")
    if not run_bundle.get("watchlist_hash"):
        gaps.append("watchlist_hash")
    return gaps


def load_frozen_daily_signal(
    *,
    db_path: str | Path,
    session_date: str,
    calendar: SessionCalendar,
    min_rows: int = DEFAULT_MIN_ROWS,
    min_coverage: float = DEFAULT_MIN_COVERAGE_FRACTION,
) -> dict[str, Any]:
    """Load the class-A frozen signal for ``session_date`` from ``runs.alpaca.db``.

    READ-ONLY (sqlite opened in query-only mode). Selection discipline
    matches ``export_batch_scores.py``: a completed ``pipeline_runs`` row
    (``run_type='live'``, non-empty strategy, bound config/artifact/watchlist
    fingerprints) joined to its ``role='candidate'`` scores, ordered by the
    run's own ``created_at``.

    §6 leak guard, enforced twice:

    1. The ONLY date queried is the immediately preceding exchange session
       (:func:`previous_session`) — a run dated ``session_date`` (today) can
       never be selected, and an older-than-one-session run is refused
       rather than silently served.
    2. A defensive re-assert that the selected run's date strictly predates
       the session — if the calendar or DB ever disagree, this raises
       :class:`SignalLeakError` instead of proceeding.
    """
    expected_run_date = previous_session(calendar, session_date)
    if expected_run_date >= str(session_date):  # calendar malfunction guard
        raise SignalLeakError(
            f"computed prior session {expected_run_date!r} does not predate "
            f"the session {session_date!r}"
        )

    uri = f"file:{Path(db_path)}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise FrozenSignalError(f"cannot open runs DB read-only at {db_path}: {exc}")
    try:
        row = con.execute(
            "select pr.run_id, pr.run_date, pr.run_bundle_json, "
            "count(cs.ticker) as n "
            "from pipeline_runs pr "
            "join candidate_scores cs "
            "  on cs.run_id = pr.run_id and cs.role = 'candidate' "
            "  and cs.panel_score is not null "
            "where pr.run_type = 'live' "
            "  and pr.run_date = ? "
            "  and pr.strategy is not null and pr.strategy != '' "
            "group by pr.run_id "
            "having n >= ? "
            "order by pr.created_at desc "
            "limit 1",
            (expected_run_date, int(min_rows)),
        ).fetchone()
        if not row:
            raise FrozenSignalError(
                f"no qualifying completed live run for the expected prior "
                f"session {expected_run_date} (before {session_date}) — "
                "refusing to fall back to an older or same-day run (§6)"
            )
        run_id, run_date, run_bundle_raw, _n = row

        if str(run_date) >= str(session_date):
            raise SignalLeakError(
                f"selected run {run_id} is dated {run_date!r}, which does not "
                f"strictly predate the session {session_date!r} (§6 class-A "
                "leak guard)"
            )

        try:
            run_bundle = json.loads(run_bundle_raw) if run_bundle_raw else {}
        except (TypeError, ValueError):
            run_bundle = {}
        gaps = _fingerprint_gaps(run_bundle)
        if gaps:
            raise FrozenSignalError(
                f"run {run_id} is missing required fingerprint field(s) "
                f"{', '.join(gaps)} — refusing an unfingerprinted class-A vector"
            )

        roster = con.execute(
            "select ticker, panel_score from candidate_scores "
            "where run_id = ? and role = 'candidate'",
            (run_id,),
        ).fetchall()
    finally:
        con.close()

    if not roster:
        raise FrozenSignalError(
            f"run {run_id} has a pipeline_runs row but no role='candidate' "
            "rows — inconsistent DB state"
        )
    scores = {str(t): float(s) for t, s in roster if s is not None}
    missing = sorted(str(t) for t, s in roster if s is None)
    coverage = len(scores) / len(roster)
    if coverage < min_coverage:
        raise FrozenSignalError(
            f"run {run_id} coverage {coverage:.1%} ({len(scores)}/{len(roster)}) "
            f"is below the {min_coverage:.0%} floor (missing: "
            f"{', '.join(missing) or 'n/a'})"
        )

    score_sha = hash_jsonable(scores)
    return {
        "signal_version": f"{run_id}:{score_sha[:12]}",
        "as_of": str(run_date),
        "scores": scores,
        "source_run_id": str(run_id),
        "source_run_date": str(run_date),
        "score_content_sha256": score_sha,
        "coverage": coverage,
        "missing_tickers": missing,
    }


def assert_signal_predates_session(signal: Mapping[str, Any], session_date: str) -> None:
    """Scheduler-side re-assert of the §6 class-A leak guard (defense in depth).

    Mirrors the pipeline's ``FrozenDailySignal.assert_predates_session``
    (lexicographic ISO compare) so the orchestrator refuses a leaking signal
    even when the tick runner is an injected test double.
    """
    as_of = str(signal.get("as_of") or "")
    if not as_of or as_of >= str(session_date):
        raise SignalLeakError(
            f"class-A signal as_of {as_of!r} does not strictly predate the "
            f"session {session_date!r} (§6)"
        )


# ---------------------------------------------------------------------------
# Class B — session-start snapshot (fingerprinted, then frozen).
# ---------------------------------------------------------------------------
def capture_session_start(
    gate_inputs: Mapping[str, Any], *, captured_at: str
) -> dict[str, Any]:
    """Capture + fingerprint the class-B gate inputs at the first eligible tick.

    Uses the SAME ``hash_jsonable`` the pipeline's
    ``SessionStartSnapshot.verify()`` recomputes, so the pipeline accepts the
    snapshot as-is and a mid-session mutation is a hard failure on either side.
    """
    inputs = dict(gate_inputs)
    return {
        "captured_at": str(captured_at),
        "gate_inputs": inputs,
        "gate_input_fingerprint": hash_jsonable(inputs),
    }


def verify_session_start(snapshot: Mapping[str, Any]) -> None:
    """Re-fingerprint a captured class-B snapshot; raise on any drift."""
    actual = hash_jsonable(dict(snapshot.get("gate_inputs") or {}))
    expected = str(snapshot.get("gate_input_fingerprint") or "")
    if actual != expected:
        raise SignalLeakError(
            "class-B session-start gate inputs mutated after capture: "
            f"fingerprint {expected!r} != {actual!r} (§6)"
        )


# ---------------------------------------------------------------------------
# §7 reservations from the slice-1 order-state file.
# ---------------------------------------------------------------------------
def load_order_state_reservations(
    path: str | Path | None,
    *,
    trading_day: str | None = None,
) -> dict[str, Any]:
    """Parse a slice-1 ``OrderStateBook.to_snapshot()`` file into §7 inputs.

    Returns ``open_buy_reservations`` (parent-intent-keyed, each the Σ of its
    OPEN buy children's ``unfilled_qty × price`` — the same accounting
    ``OrderStateBook.reserved_cash`` produces), the in-flight parent-intent
    ids (ALL parents in the book, both sides: a decision that exists must
    never be re-emitted), pending tickers, and the book's entry-halt state.

    A missing file (no execution activity yet — the normal Stage-1 shadow
    case) yields empty defaults. A file that EXISTS but cannot be parsed, or
    whose ``schema_version``/``trading_day`` do not match, raises
    :class:`OrderStateFileError` — silently ignoring a corrupt or stale book
    would understate reservations (§7: never size on raw broker cash).
    """
    empty = {
        "open_buy_reservations": {},
        "in_flight_parent_intents": [],
        "pending_broker_tickers": [],
        "entries_halted": False,
        "halt_reason": None,
        "source": None,
    }
    if path is None:
        return empty
    p = Path(path)
    if not p.exists():
        return empty
    try:
        book = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OrderStateFileError(f"order-state file {p} is unreadable: {exc}")
    version = book.get("schema_version")
    if version != ORDER_STATE_SCHEMA_VERSION:
        raise OrderStateFileError(
            f"order-state file {p} has schema_version {version!r}; this "
            f"reader supports {ORDER_STATE_SCHEMA_VERSION!r} only"
        )
    if trading_day is not None and str(book.get("trading_day")) != str(trading_day):
        raise OrderStateFileError(
            f"order-state file {p} is for trading_day "
            f"{book.get('trading_day')!r}, not {trading_day!r} — a stale "
            "book must be reconciled, never silently reused (§7)"
        )

    reservations: dict[str, float] = {}
    in_flight: list[str] = []
    pending_tickers: set[str] = set()
    for parent in book.get("parents", []):
        pid = str(parent.get("parent_intent_id") or "")
        if not pid:
            raise OrderStateFileError(
                f"order-state file {p} has a parent row without a "
                "parent_intent_id"
            )
        in_flight.append(pid)
        side = str(parent.get("side") or "").upper()
        open_reserved = 0.0
        has_open_child = False
        for child in parent.get("children", []):
            if str(child.get("state") or "") not in OPEN_CHILD_STATES:
                continue
            has_open_child = True
            unfilled = float(child.get("requested_qty", 0.0)) - float(
                child.get("filled_qty", 0.0)
            )
            if unfilled < 0:
                raise OrderStateFileError(
                    f"order-state file {p}: child "
                    f"{child.get('child_order_id')!r} has filled_qty > "
                    "requested_qty"
                )
            open_reserved += unfilled * float(child.get("price", 0.0))
        if has_open_child:
            pending_tickers.add(str(parent.get("symbol") or "").upper())
        if side == "BUY" and open_reserved > 0:
            reservations[pid] = open_reserved

    return {
        "open_buy_reservations": reservations,
        "in_flight_parent_intents": sorted(in_flight),
        "pending_broker_tickers": sorted(t for t in pending_tickers if t),
        "entries_halted": bool(book.get("entries_halted", False)),
        "halt_reason": book.get("halt_reason"),
        "source": str(p),
    }


# ---------------------------------------------------------------------------
# Class C — live broker state, READ-ONLY.
# ---------------------------------------------------------------------------
def live_state_fingerprint(live_state: Mapping[str, Any]) -> str:
    """Canonical content hash of one class-C snapshot (replay integrity key)."""
    return hash_jsonable(dict(live_state))


@dataclass
class AlpacaLiveStateSource:
    """Class-C snapshot provider over READ-ONLY Alpaca calls.

    Calls exactly two trading-API endpoints — ``get_account()`` and
    ``get_all_positions()`` (both GET) — plus the injected observe-only
    ``QuoteSource`` for class-D prices. It never constructs an order object
    and has no submit/cancel/replace path: the shadow harness's never-submit
    property starts here, structurally.

    ``order_state_path`` points at the slice-1 book snapshot for the session
    (may be absent — empty reservations). ``tickers`` is the watchlist whose
    class-D reference prices are sampled each tick.
    """

    quote_source: QuoteSource
    tickers: Sequence[str]
    order_state_path: str | Path | None = None
    paper: bool = True
    _client: Any = None

    def _trading_client(self) -> Any:
        if self._client is None:
            import os

            from alpaca.trading.client import TradingClient  # noqa: PLC0415

            if self.paper:
                key = os.environ.get("ALPACA_SHORTS_API_KEY", os.environ["ALPACA_API_KEY"])
                secret = os.environ.get("ALPACA_SHORTS_SECRET_KEY", os.environ["ALPACA_SECRET_KEY"])
            else:
                key = os.environ["ALPACA_API_KEY"]
                secret = os.environ["ALPACA_SECRET_KEY"]
            self._client = TradingClient(key, secret, paper=self.paper)
        return self._client

    def snapshot(self, *, now: datetime, trading_day: str) -> dict[str, Any]:
        """One class-C + class-D snapshot as plain JSON-able state."""
        client = self._trading_client()
        account = client.get_account()
        positions: dict[str, dict[str, Any]] = {}
        for pos in client.get_all_positions():
            ticker = str(getattr(pos, "symbol", "")).upper()
            if not ticker:
                continue
            positions[ticker] = {
                "ticker": ticker,
                "qty": float(getattr(pos, "qty", 0.0)),
                "avg_entry_price": float(getattr(pos, "avg_entry_price", 0.0)),
                "market_value": float(getattr(pos, "market_value", 0.0) or 0.0),
            }
        prices: dict[str, float] = {}
        try:
            quotes = self.quote_source.get_quotes(list(self.tickers))
        except Exception as exc:  # noqa: BLE001 — quotes are class D (timing only)
            log.warning("class-D quote batch failed (%s) — prices empty", exc)
            quotes = {}
        for ticker, quote in quotes.items():
            mid = getattr(quote, "mid", None)
            if callable(mid):
                mid = mid()
            if mid is not None:
                try:
                    prices[str(ticker).upper()] = float(mid)
                except (TypeError, ValueError):
                    pass

        reservations = load_order_state_reservations(
            self.order_state_path, trading_day=trading_day
        )
        return {
            "as_of": _as_aware(now).astimezone(ET).isoformat(),
            "trading_day": str(trading_day),
            "account": str(getattr(account, "account_number", "")) or "unknown",
            "cash": float(getattr(account, "cash", 0.0)),
            "equity": float(getattr(account, "equity", 0.0)),
            "positions": positions,
            "prices": prices,
            "open_buy_reservations": reservations["open_buy_reservations"],
            "unsettled_buys": 0.0,
            "pending_broker_tickers": reservations["pending_broker_tickers"],
            "entries_halted": reservations["entries_halted"],
            "in_flight_parent_intents": reservations["in_flight_parent_intents"],
        }


#: Provider signature the scheduler consumes; tests inject deterministic fakes.
LiveStateProvider = Callable[..., Mapping[str, Any]]


__all__ = [
    "AlpacaLiveStateSource",
    "DEFAULT_MIN_COVERAGE_FRACTION",
    "DEFAULT_MIN_ROWS",
    "FrozenSignalError",
    "LiveStateProvider",
    "OPEN_CHILD_STATES",
    "ORDER_STATE_SCHEMA_VERSION",
    "OrderStateFileError",
    "SignalLeakError",
    "assert_signal_predates_session",
    "capture_session_start",
    "live_state_fingerprint",
    "load_frozen_daily_signal",
    "load_order_state_reservations",
    "previous_session",
    "verify_session_start",
]
