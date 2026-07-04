"""renquant105 execution reconciler — §7 order-lifecycle safety core (OBSERVE-ONLY).

Stage-1 safety infrastructure for the intraday (盘中) decisioning path described in
``doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`` (§7 order
lifecycle / idempotency, §10 safety envelope). This module is **advisory / observe-only
with respect to the broker and trading state**: it *detects and reports* divergence
between what the local decision loop believes and what the broker authoritatively holds;
it **never** places, cancels, or mutates any order, position, or broker/live-run state.
The one thing it *does* persist is its **own** idempotency ledger (``SqliteIntentStore``)
— parent-intent dedup rows and child-attempt allocations — because a dedup guarantee that
cannot survive a process restart or two concurrent workers is not a guarantee at all
(Codex review, 2026-07-01). That store is private bookkeeping for the reconciler; it
touches no order and no broker state. The live path (execution repo, §8 order 1) owns the
enforcing state machine; this orchestrator-side library is the independent audit that
rides alongside it, and it does **not** gate submission off any in-memory registry.

Three concerns, all pure/dependency-injected so they unit-test with fixtures — no live
broker calls anywhere in this module:

1. **Order-lifecycle state machine** (``LifecycleMachine``) — legal transitions over
   ``OrderState``, plus the two-level idempotency identity from §7
   (``parent_intent_id`` dedup key + per-attempt ``child_order_id`` broker client-order-id).
   ``SqliteIntentStore`` is the **durable** dedup authority (UNIQUE-constrained, atomic
   create-or-get, restart- and concurrency-safe); ``IntentRegistry`` is an in-memory index
   for a single reconcile pass and is explicitly *not* the safety guarantee. An unrecognised
   broker status maps to an explicit ``OrderState.UNKNOWN`` (never fail-open to ACCEPTED),
   and a broker *replacement* keeps lineage (``OrderState.REPLACED`` + ``replaced_by``) so a
   replaced remainder is never mistaken for a canceled under-fill.
2. **Quantity accounting** (``QuantityAccount``) — reconciles authoritative broker
   children/fills *per parent*, deduplicating superseded/duplicate snapshots to the
   latest version (so corrections/busts are honoured, not double-counted), enforcing the §7
   economic invariant ``cum_filled + open_qty <= target_qty`` and flagging over-/under-fill.
   Whole-share vs fractional is *detected*, never rounded (Stage 1 is whole-share; §11
   defers fractional to Stage 2).
3. **Broker/local reconciliation** (``ExecutionReconciler``) — diffs local state against the
   broker's authoritative positions/orders/fills, classifies each divergence
   (``DivergenceKind``) with a ``Severity``, and emits a structured report plus, behind an
   explicit flag, an ntfy alert. Per §7, an open-order ledger mismatch (and any unknown
   broker status or broken replacement lineage) advises *halt new entries* (exits still
   allowed) — this module only advises; it does not enforce.

**Canonical identity + terminal classification (campaign B3, audit #296 OR-1/OR-2).**
The §7 two-level identity (``compute_parent_intent_id`` / ``child_order_id``) and the
terminal broker-status classification (``classify_terminal_status`` /
``TERMINAL_STATUS_MAP``) are **imported from** ``renquant_execution.order_state_machine``
— the single canonical impl the Stage-2 executor uses — never re-implemented here. An
audit that computes "the same" identity with a different recipe than the system it audits
is divergent by construction (the calibrator-fingerprint triple-impl failure mode). Only
the *non-terminal* (open/in-flight) Alpaca vocabulary plus the REPLACED lineage state —
which execution's Stage-1 terminal map deliberately does not own — stays local, with an
import-time guard that fails loudly if execution's terminal vocabulary ever grows to
overlap it.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from enum import Enum

# Canonical §7 impls — consumed, never copied (RFC #208 §8 row 1: execution owns the
# identity + terminal-status vocabulary). Same top-level-import seam as
# ``intraday_live_executor``; renquant-execution is a declared dependency.
from renquant_execution.order_state_machine import (
    TERMINAL_STATUS_MAP,
    ChildOrderState,
    child_order_id,
    classify_terminal_status,
    compute_parent_intent_id,
)

__all__ = [
    "OrderState",
    "OPEN_STATES",
    "TERMINAL_STATES",
    "ALPACA_STATUS_TO_STATE",
    "TERMINAL_STATUS_MAP",  # re-export: canonical §7 terminal vocabulary (execution repo)
    "IllegalTransition",
    "LifecycleMachine",
    "compute_parent_intent_id",  # re-export: canonical §7 dedup identity (execution repo)
    "child_order_id",  # re-export: canonical §7 per-attempt broker client-order-id
    "classify_terminal_status",  # re-export: canonical terminal-status classifier
    "OrderIntent",
    "IntentRegistry",
    "ChildAttempt",
    "SqliteIntentStore",
    "is_whole_share",
    "QuantityAccount",
    "account_from_children",
    "dedupe_latest_orders",
    "parent_intent_id_of",
    "accounts_by_parent",
    "Position",
    "OrderRecord",
    "LocalState",
    "BrokerState",
    "LocalStateLoader",
    "BrokerStateLoader",
    "Severity",
    "DivergenceKind",
    "Divergence",
    "ReconciliationReport",
    "ExecutionReconciler",
    "post_ntfy",
    "maybe_alert",
]

# Quantity comparison tolerance — accounting is in shares; a whisker of float slop from
# broker JSON round-trips should not masquerade as a divergence.
_QTY_TOL = 1e-6


# --------------------------------------------------------------------------------------
# 1. Order-lifecycle state machine + idempotency identity (§7)
# --------------------------------------------------------------------------------------
class OrderState(str, Enum):
    """Lifecycle states for a single child order (§7 diagram)."""

    NONE = "NONE"
    INTENDED = "INTENDED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"  # superseded by a replacement child (keeps lineage; not a plain cancel)
    STALE_PENDING = "STALE_PENDING"
    # Explicit fail-CLOSED sentinel for a broker status we do not recognise. Never treated
    # as a valid open/accepted order — a schema/API drift surfaces as a CRITICAL divergence
    # instead of silently masquerading as a live order (Codex review, 2026-07-01).
    UNKNOWN = "UNKNOWN"


# Live / in-flight states: a child in one of these is consuming exposure + reserved cash
# and is what "no OPEN child per parent" (§7 re-emit rule) refers to.
OPEN_STATES: frozenset[OrderState] = frozenset(
    {
        OrderState.SUBMITTED,
        OrderState.ACCEPTED,
        OrderState.PARTIALLY_FILLED,
        OrderState.STALE_PENDING,
    }
)

# Absorbing states — no legal transition leaves them. REPLACED is terminal *for this
# child*, but unlike CANCELED it carries lineage (``replaced_by``) to the replacement child,
# so its unfilled remainder is NOT a canceled under-fill.
TERMINAL_STATES: frozenset[OrderState] = frozenset(
    {
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
        OrderState.REPLACED,
    }
)

# Legal transitions (§7). A superset that admits the real broker paths (immediate fill,
# partial then fill, stale-pending watchdog) while rejecting nonsense (terminal reuse,
# skipping straight from NONE to FILLED, running a lifecycle backwards).
_LEGAL_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.NONE: frozenset({OrderState.INTENDED}),
    OrderState.INTENDED: frozenset({OrderState.SUBMITTED, OrderState.REJECTED}),
    OrderState.SUBMITTED: frozenset(
        {
            OrderState.ACCEPTED,
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.REJECTED,
            OrderState.CANCELED,
            OrderState.EXPIRED,
            OrderState.REPLACED,
            OrderState.STALE_PENDING,
        }
    ),
    OrderState.ACCEPTED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELED,
            OrderState.EXPIRED,
            OrderState.REJECTED,
            OrderState.REPLACED,
            OrderState.STALE_PENDING,
        }
    ),
    OrderState.PARTIALLY_FILLED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELED,
            OrderState.EXPIRED,
            OrderState.REPLACED,
            OrderState.STALE_PENDING,
        }
    ),
    OrderState.STALE_PENDING: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELED,
            OrderState.EXPIRED,
            OrderState.REPLACED,
        }
    ),
    OrderState.FILLED: frozenset(),
    OrderState.CANCELED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.EXPIRED: frozenset(),
    OrderState.REPLACED: frozenset(),
    # UNKNOWN is a fail-closed sentinel: it is never a legal source or destination, so it
    # can never be quietly advanced into or out of a "valid" lifecycle.
    OrderState.UNKNOWN: frozenset(),
}

# Canonical terminal child state (execution's §7 vocabulary) -> this module's richer
# audit-side OrderState. Total over every state ``TERMINAL_STATUS_MAP`` can emit — the
# import-time check below fails loudly if execution's vocabulary grows past ours.
_TERMINAL_CHILD_TO_ORDER_STATE: dict[ChildOrderState, OrderState] = {
    ChildOrderState.FILLED: OrderState.FILLED,
    ChildOrderState.CANCELED: OrderState.CANCELED,
    ChildOrderState.REJECTED: OrderState.REJECTED,
    ChildOrderState.EXPIRED: OrderState.EXPIRED,
}

# NON-terminal (open / in-flight) Alpaca order.status -> OrderState, plus REPLACED.
# This is the ONLY status vocabulary owned locally: execution's canonical
# ``TERMINAL_STATUS_MAP`` deliberately covers terminal outcomes only (anything it does not
# classify is "still live — leave open"), and its Stage-1 machine does not model broker
# replacement, while this audit-side reconciler tracks REPLACED lineage explicitly so a
# replaced remainder is never booked as a canceled under-fill. Terminal statuses
# (incl. ``done_for_day``) must NEVER be added here — they belong to execution's map.
_OPEN_ALPACA_STATUS_TO_STATE: dict[str, OrderState] = {
    "new": OrderState.ACCEPTED,
    "pending_new": OrderState.SUBMITTED,
    "accepted": OrderState.ACCEPTED,
    "accepted_for_bidding": OrderState.ACCEPTED,
    "held": OrderState.ACCEPTED,
    "calculated": OrderState.ACCEPTED,
    "partially_filled": OrderState.PARTIALLY_FILLED,
    "pending_cancel": OrderState.ACCEPTED,
    # `replaced` is NOT a plain cancel — the remainder is carried by the replacement child.
    # Keep it a distinct state with lineage so accounting never books a false under-fill.
    "replaced": OrderState.REPLACED,
    "pending_replace": OrderState.ACCEPTED,
    "suspended": OrderState.ACCEPTED,
    "stopped": OrderState.ACCEPTED,
}

# Drift guard (fail loudly at import): the local open-vocabulary must never shadow the
# canonical terminal vocabulary. If renquant-execution later classifies a status we map
# here (e.g. adds "replaced" to TERMINAL_STATUS_MAP), the two repos must be reconciled
# explicitly — silently diverging again is exactly the OR-1/OR-2 failure mode.
_shadowed = sorted(set(_OPEN_ALPACA_STATUS_TO_STATE) & set(TERMINAL_STATUS_MAP))
if _shadowed:  # pragma: no cover - tripped only by a cross-repo vocabulary change
    raise RuntimeError(
        "execution_reconciler's local open-status map shadows renquant-execution's "
        f"canonical TERMINAL_STATUS_MAP for {_shadowed}; reconcile the vocabularies "
        "(the canonical terminal classification lives in "
        "renquant_execution.order_state_machine)"
    )

# Alpaca order.status -> canonical OrderState. Matches the broker field names seen in the
# live 104 broker state (``filled_qty`` / ``filled_avg_price`` / ``client_order_id`` etc.).
# DERIVED, not hand-written: terminal statuses come from execution's canonical
# ``TERMINAL_STATUS_MAP`` (so ``done_for_day`` -> CANCELED — the broker's close-out of a
# DAY order, see execution's module note — and ``failed`` -> REJECTED), and only the
# open/in-flight vocabulary is local.
ALPACA_STATUS_TO_STATE: dict[str, OrderState] = {
    **{
        status: _TERMINAL_CHILD_TO_ORDER_STATE[child_state]
        for status, child_state in TERMINAL_STATUS_MAP.items()
    },
    **_OPEN_ALPACA_STATUS_TO_STATE,
}


class IllegalTransition(ValueError):
    """Raised when a lifecycle transition is not permitted by §7."""


class LifecycleMachine:
    """Pure validator of §7 order-lifecycle transitions. Stateless; call ``is_legal`` /
    ``advance`` with the observed ``(from, to)`` pair. Observe-only: it never *drives*
    an order, it only rules a transition legal or not."""

    @staticmethod
    def is_legal(src: OrderState, dst: OrderState) -> bool:
        return dst in _LEGAL_TRANSITIONS.get(src, frozenset())

    @classmethod
    def advance(cls, src: OrderState, dst: OrderState) -> OrderState:
        if not cls.is_legal(src, dst):
            raise IllegalTransition(
                f"illegal order-lifecycle transition {src.value} -> {dst.value}"
                + (f" ({src.value} is terminal)" if src in TERMINAL_STATES else "")
            )
        return dst

    @classmethod
    def validate_path(cls, states: Sequence[OrderState]) -> None:
        """Assert a full observed lifecycle path is legal edge-by-edge."""
        for src, dst in zip(states, states[1:]):
            cls.advance(src, dst)

    @staticmethod
    def from_broker_status(status: str) -> OrderState:
        """Map a raw broker (Alpaca) ``order.status`` string to a canonical state.

        Terminal statuses are classified by renquant-execution's canonical
        :func:`classify_terminal_status` (so a terminal outcome can never drift from what
        the Stage-2 executor books — notably ``done_for_day`` -> CANCELED); only the
        open/in-flight vocabulary is resolved locally. An unrecognised status maps to
        :attr:`OrderState.UNKNOWN` — **fail-closed**. Mapping it to ACCEPTED (the old
        behaviour) is fail-*open*: a broker API/schema change would make a status we no
        longer understand look like a valid open order. UNKNOWN instead surfaces as a
        CRITICAL reconciliation divergence (Codex review, 2026-07-01)."""
        terminal = classify_terminal_status(status)
        if terminal is not None:
            return _TERMINAL_CHILD_TO_ORDER_STATE[terminal]
        return _OPEN_ALPACA_STATUS_TO_STATE.get(
            str(status).strip().lower(), OrderState.UNKNOWN
        )


# §7 identity: `compute_parent_intent_id` (dedup key of the *decision*) and
# `child_order_id` (per-attempt broker client-order-id) are the canonical
# renquant-execution impls imported above — one recipe, one id, in both repos. The
# previous local derivation (`pi_` + sha256[:16], `|` separator, lower-cased side) never
# matched execution's (`pi-` + sha256[:20], `\x1f` separator, upper-cased side) for the
# same decision and was removed (campaign B3; audit #296 OR-1).


@dataclass(frozen=True)
class OrderIntent:
    """A single INTENDED decision (one parent). ``parent_intent_id`` is the dedup identity."""

    parent_intent_id: str
    account: str
    symbol: str
    trading_day: str
    side: str
    signal_version: str
    target_qty: float

    @classmethod
    def build(
        cls,
        *,
        account: str,
        symbol: str,
        trading_day: str,
        side: str,
        signal_version: str,
        target_qty: float,
    ) -> "OrderIntent":
        return cls(
            parent_intent_id=compute_parent_intent_id(
                account=account,
                symbol=symbol,
                trading_day=trading_day,
                side=side,
                signal_version=signal_version,
            ),
            account=account,
            symbol=str(symbol).strip().upper(),
            trading_day=trading_day,
            side=str(side).strip().lower(),
            signal_version=signal_version,
            target_qty=float(target_qty),
        )


class IntentRegistry:
    """In-memory, single-pass index of intents keyed on ``parent_intent_id`` (§7 dedup).

    Useful for building/reporting within one reconcile pass, but it is **NOT** the
    idempotency safety guarantee: it is process-local, so it loses every key on restart and
    offers no atomic uniqueness across concurrent workers. The durable dedup authority is
    :class:`SqliteIntentStore`; do not gate order submission off this class (Codex review,
    2026-07-01)."""

    def __init__(self) -> None:
        self._intents: dict[str, OrderIntent] = {}

    def register(self, intent: OrderIntent) -> bool:
        """Register an intent. Returns ``True`` if newly created, ``False`` if the
        ``parent_intent_id`` was already present (duplicate suppressed)."""
        if intent.parent_intent_id in self._intents:
            return False
        self._intents[intent.parent_intent_id] = intent
        return True

    def is_duplicate(self, intent: OrderIntent) -> bool:
        return intent.parent_intent_id in self._intents

    def get(self, parent_intent_id: str) -> OrderIntent | None:
        return self._intents.get(parent_intent_id)

    def __len__(self) -> int:
        return len(self._intents)

    def __contains__(self, parent_intent_id: object) -> bool:
        return parent_intent_id in self._intents


@dataclass(frozen=True)
class ChildAttempt:
    """One persisted child-attempt row: the unique broker ``client_order_id``, its monotonic
    ``attempt_n`` under a parent, and (once known) the broker's own order id."""

    client_order_id: str
    parent_intent_id: str
    attempt_n: int
    broker_order_id: str | None = None


class SqliteIntentStore:
    """Durable §7 idempotency ledger — the *real* dedup safety core.

    Persists parent intents and their child-attempt allocations in a SQLite file so
    idempotency (a) **survives process restart** and (b) is enforced atomically against
    **concurrent workers** by DB-level UNIQUE constraints — the two guarantees the
    in-memory :class:`IntentRegistry` cannot make. It is observe-only with respect to the
    broker / trading state: it persists ONLY this reconciler's own dedup ledger and NEVER
    places, cancels, or mutates any order, position, or broker/live-run state.

    - :meth:`create_or_get_intent` is an atomic ``INSERT OR IGNORE`` on the
      ``parent_intent_id`` PRIMARY KEY, so a re-run / redelivery of the same decision — even
      from two workers racing at once — yields exactly one created row; every other caller
      observes the existing row (``created=False``). This is the "cannot double-submit" claim
      made true.
    - :meth:`allocate_child` hands out a monotonic ``attempt_n`` + unique broker
      ``client_order_id`` under a write transaction (``BEGIN IMMEDIATE`` + a
      ``UNIQUE(parent_intent_id, attempt_n)`` backstop), so overlapping ticks / restarts can
      never reuse an attempt id.
    - :meth:`bind_broker_order_id` records the broker's own id for an attempt (client-order-id
      binding) once the (external, execution-repo) submission returns it.

    Use a real file path for durability; ``":memory:"`` is accepted for throwaway unit work
    but is neither durable nor shareable across connections.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS parent_intents (
        parent_intent_id TEXT PRIMARY KEY,
        account          TEXT NOT NULL,
        symbol           TEXT NOT NULL,
        trading_day      TEXT NOT NULL,
        side             TEXT NOT NULL,
        signal_version   TEXT NOT NULL,
        target_qty       REAL NOT NULL,
        created_at       TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS child_attempts (
        client_order_id  TEXT PRIMARY KEY,
        parent_intent_id TEXT NOT NULL,
        attempt_n        INTEGER NOT NULL,
        broker_order_id  TEXT,
        created_at       TEXT NOT NULL,
        UNIQUE(parent_intent_id, attempt_n),
        FOREIGN KEY(parent_intent_id) REFERENCES parent_intents(parent_intent_id)
    );
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        # autocommit (isolation_level=None) so we control transactions explicitly; a generous
        # busy_timeout lets concurrent workers wait on the write lock rather than error.
        self._conn = sqlite3.connect(
            self._path, isolation_level=None, check_same_thread=False, timeout=30.0
        )
        # WAL: concurrent readers + a single serialized writer; the exact multi-worker shape.
        if self._path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(self._SCHEMA)
        # Guards a same-connection multi-statement transaction against this instance's own
        # threads; cross-connection (real "worker") races are serialized by SQLite itself.
        self._lock = threading.Lock()

    # -- lifecycle -------------------------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SqliteIntentStore":
        return self

    def __exit__(self, *exc: object) -> bool:
        self.close()
        return False

    # -- parent intents --------------------------------------------------------------
    def create_or_get_intent(self, intent: OrderIntent) -> tuple[OrderIntent, bool]:
        """Atomically create the parent intent, or return the already-persisted one.

        Returns ``(stored_intent, created)`` where ``created`` is ``True`` only for the single
        caller that actually inserted the row. Concurrency-safe: the UNIQUE PRIMARY KEY means
        only one INSERT of a given ``parent_intent_id`` can ever win."""
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO parent_intents"
            " (parent_intent_id, account, symbol, trading_day, side, signal_version,"
            "  target_qty, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                intent.parent_intent_id,
                intent.account,
                intent.symbol,
                intent.trading_day,
                intent.side,
                intent.signal_version,
                float(intent.target_qty),
                _utcnow_iso(),
            ),
        )
        created = cur.rowcount == 1
        stored = self.get_intent(intent.parent_intent_id)
        assert stored is not None  # just inserted or already present
        return stored, created

    def has_intent(self, parent_intent_id: str) -> bool:
        return (
            self._conn.execute(
                "SELECT 1 FROM parent_intents WHERE parent_intent_id=?",
                (parent_intent_id,),
            ).fetchone()
            is not None
        )

    def get_intent(self, parent_intent_id: str) -> OrderIntent | None:
        row = self._conn.execute(
            "SELECT parent_intent_id, account, symbol, trading_day, side, signal_version,"
            " target_qty FROM parent_intents WHERE parent_intent_id=?",
            (parent_intent_id,),
        ).fetchone()
        if row is None:
            return None
        return OrderIntent(
            parent_intent_id=row[0],
            account=row[1],
            symbol=row[2],
            trading_day=row[3],
            side=row[4],
            signal_version=row[5],
            target_qty=float(row[6]),
        )

    def __len__(self) -> int:
        return int(
            self._conn.execute("SELECT COUNT(*) FROM parent_intents").fetchone()[0]
        )

    def __contains__(self, parent_intent_id: object) -> bool:
        return isinstance(parent_intent_id, str) and self.has_intent(parent_intent_id)

    # -- child attempts --------------------------------------------------------------
    def allocate_child(self, parent_intent_id: str) -> ChildAttempt:
        """Allocate the next ``attempt_n`` for a parent and return the persisted
        :class:`ChildAttempt` (with its unique ``client_order_id``). Raises ``KeyError`` if
        the parent intent was never registered — a child must trace to a known decision."""
        if not self.has_intent(parent_intent_id):
            raise KeyError(f"unknown parent_intent_id {parent_intent_id!r}")
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT COALESCE(MAX(attempt_n), -1) + 1 FROM child_attempts"
                    " WHERE parent_intent_id=?",
                    (parent_intent_id,),
                ).fetchone()
                attempt_n = int(row[0])
                cid = child_order_id(parent_intent_id, attempt_n)
                self._conn.execute(
                    "INSERT INTO child_attempts"
                    " (client_order_id, parent_intent_id, attempt_n, broker_order_id, created_at)"
                    " VALUES (?,?,?,?,?)",
                    (cid, parent_intent_id, attempt_n, None, _utcnow_iso()),
                )
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
        return ChildAttempt(
            client_order_id=cid, parent_intent_id=parent_intent_id, attempt_n=attempt_n
        )

    def bind_broker_order_id(self, client_order_id: str, broker_order_id: str) -> None:
        """Bind the broker's own order id to a previously-allocated child attempt. Raises
        ``KeyError`` if the ``client_order_id`` was never allocated."""
        cur = self._conn.execute(
            "UPDATE child_attempts SET broker_order_id=? WHERE client_order_id=?",
            (broker_order_id, client_order_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"unknown client_order_id {client_order_id!r}")

    def child_attempts(self, parent_intent_id: str) -> list[ChildAttempt]:
        rows = self._conn.execute(
            "SELECT client_order_id, parent_intent_id, attempt_n, broker_order_id"
            " FROM child_attempts WHERE parent_intent_id=? ORDER BY attempt_n",
            (parent_intent_id,),
        ).fetchall()
        return [
            ChildAttempt(
                client_order_id=r[0],
                parent_intent_id=r[1],
                attempt_n=int(r[2]),
                broker_order_id=r[3],
            )
            for r in rows
        ]


# --------------------------------------------------------------------------------------
# 2. Quantity accounting (§7 cumulative-quantity invariants)
# --------------------------------------------------------------------------------------
def is_whole_share(qty: float, *, tol: float = _QTY_TOL) -> bool:
    """True if ``qty`` is an integer share count within ``tol``. Stage 1 is whole-share
    only (§11); a fractional quantity is *detected and reported*, never rounded here."""
    return abs(qty - round(qty)) <= tol


@dataclass
class QuantityAccount:
    """Per-``parent_intent_id`` quantity reconciliation (§7). Splits the two distinct
    invariants: the *economic* one (``cum_filled + open_qty <= target_qty``, caps exposure)
    and the *audit* one (``gross_submitted_qty``, which may legitimately exceed target via
    canceled/rejected retries)."""

    parent_intent_id: str
    symbol: str
    side: str
    target_qty: float
    cum_filled: float = 0.0
    open_qty: float = 0.0
    cum_canceled: float = 0.0
    cum_rejected: float = 0.0
    cum_expired: float = 0.0
    # Unfilled remainder of a REPLACED child. Kept SEPARATE from ``cum_canceled`` because a
    # replacement carries the remainder forward — booking it as canceled would fabricate
    # false retry eligibility / under-fill (Codex review, 2026-07-01).
    cum_replaced: float = 0.0
    # ``client_order_id`` of every REPLACED child whose replacement is not present among the
    # reconciled children (a broken replacement lineage). Empty == lineage intact.
    unlinked_replacement_ids: list[str] = field(default_factory=list)

    @property
    def has_unlinked_replacement(self) -> bool:
        """A REPLACED child exists whose replacement child could not be linked — the fills we
        booked cannot be trusted complete for this parent."""
        return bool(self.unlinked_replacement_ids)

    @property
    def economic_exposure(self) -> float:
        """Filled plus still-open — the quantity that counts against ``target_qty``."""
        return self.cum_filled + self.open_qty

    @property
    def remaining_unsubmitted(self) -> float:
        """What a remainder child may request next: ``target - filled - open`` (>= 0)."""
        return max(self.target_qty - self.economic_exposure, 0.0)

    @property
    def gross_submitted_qty(self) -> float:
        """Audit invariant — total ever submitted; MAY exceed target via canceled/rejected/
        replaced retries (the §7 example where target=10 but gross=16)."""
        return (
            self.cum_filled
            + self.open_qty
            + self.cum_canceled
            + self.cum_rejected
            + self.cum_expired
            + self.cum_replaced
        )

    @property
    def is_over_filled(self) -> bool:
        """Economic invariant breach: filled+open exceeds the target — a real over-exposure."""
        return self.economic_exposure - self.target_qty > _QTY_TOL

    @property
    def is_settled(self) -> bool:
        """No open child remains (terminal for the parent this session)."""
        return self.open_qty <= _QTY_TOL

    @property
    def is_under_filled(self) -> bool:
        """Settled but the target was never reached — an under-fill (informational; the
        canceled remainder stays eligible per §7, this is not an error by itself).

        A parent with a *broken replacement lineage* is deliberately NOT reported as
        under-filled: its short-fall is a lineage gap (surfaced as REPLACEMENT_LINEAGE_BREAK),
        not a benign canceled remainder, so we do not fabricate a false "retry-eligible"
        under-fill for it (Codex review, 2026-07-01)."""
        return (
            self.is_settled
            and (self.target_qty - self.cum_filled) > _QTY_TOL
            and not self.has_unlinked_replacement
        )

    @property
    def is_fractional(self) -> bool:
        """Any accounted quantity is fractional (Stage-1 whole-share expectation broken)."""
        return not all(
            is_whole_share(q)
            for q in (self.target_qty, self.cum_filled, self.open_qty)
        )

    def invariant_holds(self) -> bool:
        """The hard §7 pre-submit assertion: ``cum_filled + open_qty <= target_qty``."""
        return not self.is_over_filled

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_intent_id": self.parent_intent_id,
            "symbol": self.symbol,
            "side": self.side,
            "target_qty": self.target_qty,
            "cum_filled": self.cum_filled,
            "open_qty": self.open_qty,
            "cum_canceled": self.cum_canceled,
            "cum_rejected": self.cum_rejected,
            "cum_expired": self.cum_expired,
            "cum_replaced": self.cum_replaced,
            "economic_exposure": self.economic_exposure,
            "remaining_unsubmitted": self.remaining_unsubmitted,
            "gross_submitted_qty": self.gross_submitted_qty,
            "is_over_filled": self.is_over_filled,
            "is_under_filled": self.is_under_filled,
            "is_fractional": self.is_fractional,
            "has_unlinked_replacement": self.has_unlinked_replacement,
            "unlinked_replacement_ids": list(self.unlinked_replacement_ids),
        }


def _order_key(o: "OrderRecord") -> str | None:
    """Identity of a child order for dedup: its broker client-order-id, else the broker's own
    order id. ``None`` means the record carries no id and cannot be deduplicated."""
    return o.client_order_id or o.broker_order_id


def _is_newer(new: "OrderRecord", old: "OrderRecord") -> bool:
    """Latest-version comparison for two snapshots of the SAME child. Prefers the later
    ``updated_at``; with equal/absent timestamps the last-seen snapshot wins (so a caller's
    ordering breaks ties deterministically)."""
    nt = _parse_ts(new.updated_at)
    ot = _parse_ts(old.updated_at)
    if nt is not None and ot is not None:
        return nt >= ot
    if nt is not None:
        return True
    if ot is not None:
        return False
    return True


def dedupe_latest_orders(orders: Iterable["OrderRecord"]) -> list["OrderRecord"]:
    """Collapse duplicate / superseded snapshots of the same child to its LATEST version.

    The broker may hand us the same order (or fill) more than once, or a stale snapshot
    alongside a newer one after a correction / bust. Summing them raw double-counts; here we
    keep exactly one record per child identity (:func:`_order_key`), choosing the newest by
    ``updated_at`` (see :func:`_is_newer`). Records with no id are passed through untouched
    (they cannot be proven duplicates). First-seen order of ids is preserved.
    """
    latest: dict[str, "OrderRecord"] = {}
    key_order: list[str] = []
    passthrough: list["OrderRecord"] = []
    for o in orders:
        key = _order_key(o)
        if key is None:
            passthrough.append(o)
            continue
        if key not in latest:
            latest[key] = o
            key_order.append(key)
        elif _is_newer(o, latest[key]):
            latest[key] = o
    return [latest[k] for k in key_order] + passthrough


def account_from_children(
    parent_intent_id: str,
    symbol: str,
    side: str,
    target_qty: float,
    children: Sequence["OrderRecord"],
) -> QuantityAccount:
    """Fold a parent's authoritative child ``OrderRecord``s into a :class:`QuantityAccount`.

    Snapshots are first **deduplicated to their latest version** per child
    (:func:`dedupe_latest_orders`), so a re-delivered snapshot or a corrected/busted fill is
    counted once, at its corrected quantity — never summed with the version it supersedes.
    Each surviving child then contributes its ``filled_qty`` to ``cum_filled``; the *unfilled*
    remainder is attributed by the child's canonical state — open (SUBMITTED/ACCEPTED/PARTIAL/
    STALE), canceled, rejected, expired, or **replaced** (a distinct bucket that never counts
    as canceled/retry-eligible). Finally, replacement lineage is checked: a REPLACED child
    whose ``replaced_by`` is absent from the sibling set is recorded in
    ``unlinked_replacement_ids`` so the reconciler can flag the broken lineage.
    """
    acct = QuantityAccount(
        parent_intent_id=parent_intent_id,
        symbol=str(symbol).strip().upper(),
        side=str(side).strip().lower(),
        target_qty=float(target_qty),
    )
    deduped = dedupe_latest_orders(children)
    present_keys = {k for c in deduped for k in (c.client_order_id, c.broker_order_id) if k}
    for child in deduped:
        filled = child.filled_qty
        unfilled = max(child.qty - filled, 0.0)
        acct.cum_filled += filled
        state = child.state
        if state in OPEN_STATES:
            acct.open_qty += unfilled
        elif state is OrderState.CANCELED:
            acct.cum_canceled += unfilled
        elif state is OrderState.REJECTED:
            acct.cum_rejected += unfilled
        elif state is OrderState.EXPIRED:
            acct.cum_expired += unfilled
        elif state is OrderState.REPLACED:
            acct.cum_replaced += unfilled
            # Lineage: the remainder is only safe if we can see the replacement child.
            if child.replaced_by is None or child.replaced_by not in present_keys:
                acct.unlinked_replacement_ids.append(
                    child.client_order_id or child.broker_order_id or child.symbol
                )
        # FILLED contributes only via cum_filled (unfilled == 0 by definition).
    return acct


def parent_intent_id_of(order: "OrderRecord") -> str | None:
    """Recover a child order's ``parent_intent_id``: the explicit field if present, else the
    prefix of the ``client_order_id`` (``parent:attempt_n`` per §7)."""
    if order.parent_intent_id:
        return order.parent_intent_id
    cid = order.client_order_id
    if cid and ":" in cid:
        return cid.rsplit(":", 1)[0]
    return None


def accounts_by_parent(
    intents: Sequence[OrderIntent], orders: Sequence["OrderRecord"]
) -> list[QuantityAccount]:
    """Reconcile authoritative broker ``orders`` into one :class:`QuantityAccount` **per
    parent intent** (§7). Orders are grouped by :func:`parent_intent_id_of`; each group is
    deduped-and-folded against its intent's ``target_qty``. Orders whose parent is not among
    ``intents`` are ignored here (they surface as orphans in the reconciler, not accounts).
    """
    by_parent: dict[str, list["OrderRecord"]] = {}
    for o in orders:
        pid = parent_intent_id_of(o)
        if pid is None:
            continue
        by_parent.setdefault(pid, []).append(o)
    out: list[QuantityAccount] = []
    for intent in intents:
        children = by_parent.get(intent.parent_intent_id, [])
        out.append(
            account_from_children(
                intent.parent_intent_id,
                intent.symbol,
                intent.side,
                intent.target_qty,
                children,
            )
        )
    return out


# --------------------------------------------------------------------------------------
# 3. Reconciliation data model (local vs broker authoritative state)
# --------------------------------------------------------------------------------------
@dataclass
class Position:
    """A single holding. Field names match the live 104 broker snapshot
    (``symbol``/``ticker``, ``qty``/``quantity``, ``avg_entry_price``, ``market_value``)."""

    symbol: str
    qty: float
    avg_entry_price: float | None = None
    market_value: float | None = None

    @classmethod
    def from_broker(cls, row: Mapping[str, Any]) -> "Position":
        symbol = row.get("symbol") or row.get("ticker")
        qty = row.get("qty", row.get("quantity", row.get("shares")))
        return cls(
            symbol=str(symbol).strip().upper(),
            qty=float(qty if qty is not None else 0.0),
            avg_entry_price=_opt_float(row.get("avg_entry_price")),
            market_value=_opt_float(row.get("market_value")),
        )


@dataclass
class OrderRecord:
    """A local- or broker-side order. Normalizes the Alpaca order shape
    (``client_order_id``, ``id``, ``filled_qty``, ``filled_avg_price``, ``status`` ...)."""

    symbol: str
    side: str
    qty: float
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    state: OrderState = OrderState.ACCEPTED
    client_order_id: str | None = None
    broker_order_id: str | None = None
    parent_intent_id: str | None = None
    submitted_at: str | None = None
    created_at: str | None = None
    # Latest-version stamp for dedup (Alpaca ``updated_at``); replacement lineage ids
    # (Alpaca ``replaces`` / ``replaced_by`` are broker order ids).
    updated_at: str | None = None
    replaces: str | None = None
    replaced_by: str | None = None

    @property
    def is_open(self) -> bool:
        return self.state in OPEN_STATES

    @property
    def is_unknown_status(self) -> bool:
        return self.state is OrderState.UNKNOWN

    @classmethod
    def from_broker(cls, row: Mapping[str, Any]) -> "OrderRecord":
        return cls(
            symbol=str(row.get("symbol") or row.get("ticker") or "").strip().upper(),
            side=str(row.get("side", "")).strip().lower(),
            qty=float(row.get("qty", row.get("quantity", 0.0)) or 0.0),
            filled_qty=float(row.get("filled_qty", 0.0) or 0.0),
            filled_avg_price=_opt_float(row.get("filled_avg_price")),
            state=LifecycleMachine.from_broker_status(row.get("status", "accepted")),
            client_order_id=_opt_str(row.get("client_order_id")),
            broker_order_id=_opt_str(row.get("id") or row.get("order_id")),
            parent_intent_id=_opt_str(row.get("parent_intent_id")),
            submitted_at=_opt_str(row.get("submitted_at")),
            created_at=_opt_str(row.get("created_at")),
            updated_at=_opt_str(row.get("updated_at")),
            replaces=_opt_str(row.get("replaces")),
            replaced_by=_opt_str(row.get("replaced_by")),
        )


@dataclass
class LocalState:
    """What the local decision loop believes it holds and has working."""

    positions: dict[str, Position] = field(default_factory=dict)
    orders: list[OrderRecord] = field(default_factory=list)
    accounts: list[QuantityAccount] = field(default_factory=list)


@dataclass
class BrokerState:
    """The broker's authoritative view (positions + orders/fills)."""

    positions: dict[str, Position] = field(default_factory=dict)
    orders: list[OrderRecord] = field(default_factory=list)


class LocalStateLoader(Protocol):
    """DI seam for local state — a fixture in tests, the decision-ledger/live-state reader
    in production. Never called with a live broker in tests."""

    def load_local_state(self) -> LocalState: ...


class BrokerStateLoader(Protocol):
    """DI seam for broker state — a fixture in tests, the broker read-only APIs
    (get_all_positions / get_orders) in production."""

    def load_broker_state(self) -> BrokerState: ...


# --------------------------------------------------------------------------------------
# Divergence taxonomy + report
# --------------------------------------------------------------------------------------
class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


_SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}


class DivergenceKind(str, Enum):
    MISSING_LOCAL_FILL = "MISSING_LOCAL_FILL"
    PHANTOM_LOCAL_POSITION = "PHANTOM_LOCAL_POSITION"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    ORPHAN_BROKER_ORDER = "ORPHAN_BROKER_ORDER"
    UNTRACKED_LOCAL_ORDER = "UNTRACKED_LOCAL_ORDER"
    ORDER_STATE_DRIFT = "ORDER_STATE_DRIFT"
    STALE_PENDING_ORDER = "STALE_PENDING_ORDER"
    OVER_FILL = "OVER_FILL"
    UNDER_FILL = "UNDER_FILL"
    FRACTIONAL_QUANTITY = "FRACTIONAL_QUANTITY"
    # A broker order whose status we cannot map — fail-closed, never assumed valid.
    UNKNOWN_ORDER_STATUS = "UNKNOWN_ORDER_STATUS"
    # A REPLACED child whose replacement child is not visible — fills can't be trusted.
    REPLACEMENT_LINEAGE_BREAK = "REPLACEMENT_LINEAGE_BREAK"


# Open-order ledger mismatches (§7: "broker open-orders != ledger -> halt new entries").
# An unknown broker status and a broken replacement lineage are equally ledger-integrity
# failures — they advise halting new entries even before severity is considered.
_LEDGER_MISMATCH_KINDS = frozenset(
    {
        DivergenceKind.ORPHAN_BROKER_ORDER,
        DivergenceKind.UNTRACKED_LOCAL_ORDER,
        DivergenceKind.ORDER_STATE_DRIFT,
        DivergenceKind.UNKNOWN_ORDER_STATUS,
        DivergenceKind.REPLACEMENT_LINEAGE_BREAK,
    }
)


@dataclass
class Divergence:
    kind: DivergenceKind
    severity: Severity
    detail: str
    symbol: str | None = None
    local: Any = None
    broker: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "severity": self.severity.value,
            "symbol": self.symbol,
            "detail": self.detail,
            "local": self.local,
            "broker": self.broker,
        }


@dataclass
class ReconciliationReport:
    """Structured, serialisable output. Observe-only — carries an *advisory*
    ``halt_new_entries_advised`` per §7 but takes no action itself."""

    divergences: list[Divergence] = field(default_factory=list)
    as_of: str | None = None

    @property
    def is_clean(self) -> bool:
        return not self.divergences

    @property
    def max_severity(self) -> Severity | None:
        if not self.divergences:
            return None
        return max((d.severity for d in self.divergences), key=lambda s: _SEVERITY_ORDER[s])

    @property
    def halt_new_entries_advised(self) -> bool:
        """§7 advisory: halt NEW entries (exits still allowed) if anything CRITICAL, or if
        the broker open-orders disagree with the local ledger. Advice only — not enforced."""
        for d in self.divergences:
            if d.severity is Severity.CRITICAL or d.kind in _LEDGER_MISMATCH_KINDS:
                return True
        return False

    def counts_by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.divergences:
            out[d.kind.value] = out.get(d.kind.value, 0) + 1
        return out

    def counts_by_severity(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.divergences:
            out[d.severity.value] = out.get(d.severity.value, 0) + 1
        return out

    def of_kind(self, kind: DivergenceKind) -> list[Divergence]:
        return [d for d in self.divergences if d.kind is kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "is_clean": self.is_clean,
            "max_severity": self.max_severity.value if self.max_severity else None,
            "halt_new_entries_advised": self.halt_new_entries_advised,
            "counts_by_kind": self.counts_by_kind(),
            "counts_by_severity": self.counts_by_severity(),
            "divergences": [d.to_dict() for d in self.divergences],
        }

    def summary_text(self) -> str:
        if self.is_clean:
            return "execution-reconciler: CLEAN (local == broker)"
        head = (
            f"execution-reconciler: {len(self.divergences)} divergence(s), "
            f"max={self.max_severity.value if self.max_severity else 'INFO'}, "
            f"halt_new_entries_advised={self.halt_new_entries_advised}"
        )
        lines = [head]
        for d in self.divergences:
            sym = f" {d.symbol}" if d.symbol else ""
            lines.append(f"  [{d.severity.value}] {d.kind.value}{sym}: {d.detail}")
        return "\n".join(lines)


# --------------------------------------------------------------------------------------
# The reconciler
# --------------------------------------------------------------------------------------
class ExecutionReconciler:
    """OBSERVE-ONLY reconciliation of local vs broker-authoritative state.

    Given DI loaders, ``reconcile()`` diffs positions, orders, and per-intent quantity
    accounts and returns a :class:`ReconciliationReport`. It reads; it never places,
    cancels, mutates, or persists. ``max_pending_age_seconds`` mirrors the §10 default
    (10 min); ``as_of`` is injected for deterministic stale-pending detection in tests.
    """

    def __init__(
        self,
        local_loader: LocalStateLoader,
        broker_loader: BrokerStateLoader,
        *,
        max_pending_age_seconds: float = 600.0,
    ) -> None:
        self._local_loader = local_loader
        self._broker_loader = broker_loader
        self._max_pending_age_seconds = max_pending_age_seconds

    def reconcile(self, *, as_of: str | datetime | None = None) -> ReconciliationReport:
        local = self._local_loader.load_local_state()
        broker = self._broker_loader.load_broker_state()
        as_of_dt = _parse_ts(as_of) if not isinstance(as_of, datetime) else as_of
        as_of_str = as_of_dt.isoformat() if as_of_dt else (
            as_of if isinstance(as_of, str) else None
        )

        divergences: list[Divergence] = []
        divergences += self._diff_positions(local, broker)
        divergences += self._diff_orders(local, broker, as_of_dt)
        divergences += self._diff_accounts(local)
        return ReconciliationReport(divergences=divergences, as_of=as_of_str)

    # -- positions -------------------------------------------------------------------
    def _diff_positions(self, local: LocalState, broker: BrokerState) -> list[Divergence]:
        out: list[Divergence] = []
        symbols = sorted(set(local.positions) | set(broker.positions))
        for sym in symbols:
            lq = local.positions[sym].qty if sym in local.positions else 0.0
            bq = broker.positions[sym].qty if sym in broker.positions else 0.0

            # Fractional detection (read-only, Stage-1 is whole-share; §11). A fractional
            # holding is *information*, not a local-vs-broker divergence, so flag the symbol
            # ONCE and name whichever side(s) are fractional — never one row per side.
            frac_sides = [
                who
                for who, q in (("local", lq), ("broker", bq))
                if abs(q) > _QTY_TOL and not is_whole_share(q)
            ]
            if frac_sides:
                out.append(
                    Divergence(
                        kind=DivergenceKind.FRACTIONAL_QUANTITY,
                        severity=Severity.INFO,
                        symbol=sym,
                        detail=(
                            f"{sym} position qty is fractional "
                            f"({'/'.join(frac_sides)}: local={lq} broker={bq}); "
                            f"Stage-1 is whole-share"
                        ),
                        local=lq,
                        broker=bq,
                    )
                )

            if abs(lq - bq) <= _QTY_TOL:
                continue
            if abs(lq) <= _QTY_TOL and abs(bq) > _QTY_TOL:
                out.append(
                    Divergence(
                        kind=DivergenceKind.MISSING_LOCAL_FILL,
                        severity=Severity.CRITICAL,
                        symbol=sym,
                        detail=f"broker holds {bq} of {sym} but local records none (unrecorded fill)",
                        local=lq,
                        broker=bq,
                    )
                )
            elif abs(lq) > _QTY_TOL and abs(bq) <= _QTY_TOL:
                out.append(
                    Divergence(
                        kind=DivergenceKind.PHANTOM_LOCAL_POSITION,
                        severity=Severity.CRITICAL,
                        symbol=sym,
                        detail=f"local records {lq} of {sym} but broker holds none (phantom position)",
                        local=lq,
                        broker=bq,
                    )
                )
            else:
                out.append(
                    Divergence(
                        kind=DivergenceKind.QUANTITY_MISMATCH,
                        severity=Severity.WARNING,
                        symbol=sym,
                        detail=f"{sym} qty mismatch: local={lq} broker={bq} (delta={bq - lq})",
                        local=lq,
                        broker=bq,
                    )
                )
        return out

    # -- orders ----------------------------------------------------------------------
    def _diff_orders(
        self, local: LocalState, broker: BrokerState, as_of_dt: datetime | None
    ) -> list[Divergence]:
        out: list[Divergence] = []
        local_by_id = {o.client_order_id: o for o in local.orders if o.client_order_id}
        broker_by_id = {o.client_order_id: o for o in broker.orders if o.client_order_id}

        # Unknown broker status (fail-CLOSED): a status we cannot map is NOT assumed to be a
        # valid open order — it is a CRITICAL divergence so an API/schema drift halts entries
        # instead of masquerading as ACCEPTED. Emitted before the open-order passes because an
        # UNKNOWN order is (correctly) not ``is_open`` and would otherwise be silent.
        for o in broker.orders:
            if o.is_unknown_status:
                out.append(
                    Divergence(
                        kind=DivergenceKind.UNKNOWN_ORDER_STATUS,
                        severity=Severity.CRITICAL,
                        symbol=o.symbol,
                        detail=(
                            f"broker order {o.client_order_id or o.broker_order_id} "
                            f"({o.symbol} {o.side} {o.qty}) has an unrecognised status "
                            f"(mapped to UNKNOWN — possible broker API/schema drift)"
                        ),
                        broker=o.client_order_id or o.broker_order_id,
                    )
                )

        # Orphan broker orders: broker has an OPEN order local never tracked (incl. no id).
        for o in broker.orders:
            if not o.is_open:
                continue
            if o.client_order_id is None or o.client_order_id not in local_by_id:
                out.append(
                    Divergence(
                        kind=DivergenceKind.ORPHAN_BROKER_ORDER,
                        severity=Severity.WARNING,
                        symbol=o.symbol,
                        detail=(
                            f"broker open order {o.client_order_id or o.broker_order_id} "
                            f"({o.symbol} {o.side} {o.qty}) has no matching local record"
                        ),
                        broker=o.client_order_id or o.broker_order_id,
                    )
                )

        # Untracked local orders: local thinks an order is live, broker has no record of it.
        for o in local.orders:
            if not o.is_open:
                continue
            if o.client_order_id is None or o.client_order_id not in broker_by_id:
                out.append(
                    Divergence(
                        kind=DivergenceKind.UNTRACKED_LOCAL_ORDER,
                        severity=Severity.WARNING,
                        symbol=o.symbol,
                        detail=(
                            f"local open order {o.client_order_id} ({o.symbol} {o.side} {o.qty}) "
                            f"is absent from broker orders"
                        ),
                        local=o.client_order_id,
                    )
                )

        # Matched orders: fill/state drift.
        for cid, lo in local_by_id.items():
            bo = broker_by_id.get(cid)
            if bo is None:
                continue
            # An UNKNOWN broker status is already reported CRITICAL above; do not also emit a
            # benign state-drift for it (that would understate a fail-closed condition).
            if bo.is_unknown_status:
                continue
            if bo.filled_qty - lo.filled_qty > _QTY_TOL:
                out.append(
                    Divergence(
                        kind=DivergenceKind.MISSING_LOCAL_FILL,
                        severity=Severity.CRITICAL,
                        symbol=bo.symbol,
                        detail=(
                            f"order {cid} broker filled_qty={bo.filled_qty} > "
                            f"local filled_qty={lo.filled_qty} (unrecorded fill)"
                        ),
                        local=lo.filled_qty,
                        broker=bo.filled_qty,
                    )
                )
            elif bo.state is not lo.state:
                out.append(
                    Divergence(
                        kind=DivergenceKind.ORDER_STATE_DRIFT,
                        severity=Severity.WARNING,
                        symbol=bo.symbol,
                        detail=f"order {cid} state drift: local={lo.state.value} broker={bo.state.value}",
                        local=lo.state.value,
                        broker=bo.state.value,
                    )
                )

        # Stale-pending broker orders (§10 max-pending-age; advisory here).
        if as_of_dt is not None:
            for o in broker.orders:
                if not o.is_open:
                    continue
                ts = _parse_ts(o.submitted_at or o.created_at)
                if ts is None:
                    continue
                age = (as_of_dt - ts).total_seconds()
                if age > self._max_pending_age_seconds:
                    out.append(
                        Divergence(
                            kind=DivergenceKind.STALE_PENDING_ORDER,
                            severity=Severity.WARNING,
                            symbol=o.symbol,
                            detail=(
                                f"broker open order {o.client_order_id or o.broker_order_id} "
                                f"age {age:.0f}s exceeds max-pending-age "
                                f"{self._max_pending_age_seconds:.0f}s"
                            ),
                            broker=o.client_order_id or o.broker_order_id,
                        )
                    )
        return out

    # -- quantity accounts -----------------------------------------------------------
    def _diff_accounts(self, local: LocalState) -> list[Divergence]:
        out: list[Divergence] = []
        for acct in local.accounts:
            if acct.is_over_filled:
                out.append(
                    Divergence(
                        kind=DivergenceKind.OVER_FILL,
                        severity=Severity.CRITICAL,
                        symbol=acct.symbol,
                        detail=(
                            f"{acct.symbol} economic exposure {acct.economic_exposure} exceeds "
                            f"target {acct.target_qty} (invariant cum_filled+open<=target breached)"
                        ),
                        local=acct.to_dict(),
                    )
                )
            elif acct.is_under_filled:
                out.append(
                    Divergence(
                        kind=DivergenceKind.UNDER_FILL,
                        severity=Severity.INFO,
                        symbol=acct.symbol,
                        detail=(
                            f"{acct.symbol} settled at cum_filled={acct.cum_filled} below "
                            f"target {acct.target_qty} (remainder eligible per §7)"
                        ),
                        local=acct.to_dict(),
                    )
                )
            if acct.is_fractional:
                out.append(
                    Divergence(
                        kind=DivergenceKind.FRACTIONAL_QUANTITY,
                        severity=Severity.INFO,
                        symbol=acct.symbol,
                        detail=f"{acct.symbol} account has fractional quantities (Stage-1 is whole-share)",
                        local=acct.to_dict(),
                    )
                )
            if acct.has_unlinked_replacement:
                out.append(
                    Divergence(
                        kind=DivergenceKind.REPLACEMENT_LINEAGE_BREAK,
                        severity=Severity.WARNING,
                        symbol=acct.symbol,
                        detail=(
                            f"{acct.symbol} has REPLACED child(ren) "
                            f"{acct.unlinked_replacement_ids} whose replacement order is not "
                            f"visible; the {acct.cum_replaced} replaced share(s) cannot be "
                            f"confirmed carried forward (lineage break — halt new entries)"
                        ),
                        local=acct.to_dict(),
                    )
                )
        return out


# --------------------------------------------------------------------------------------
# ntfy alerting (behind an explicit flag; observe-only)
# --------------------------------------------------------------------------------------
def post_ntfy(title: str, body: str, topic: str) -> bool:
    """Best-effort ntfy POST (same pattern as ``state_backup.post_ntfy``). Never raises;
    returns whether the POST was attempted-and-not-errored. Injectable in tests."""
    url = f"https://ntfy.sh/{topic}"
    try:
        req = urllib.request.Request(
            url,
            data=body.encode("utf-8"),
            headers={"Title": title, "Priority": "4", "Tags": "warning"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5).read()
        return True
    except (urllib.error.URLError, OSError):
        return False


def maybe_alert(
    report: ReconciliationReport,
    *,
    enabled: bool,
    topic: str | None,
    min_severity: Severity = Severity.WARNING,
    poster: Callable[[str, str, str], bool] = post_ntfy,
) -> bool:
    """Fire an ntfy alert for a divergence report — but only behind the ``enabled`` flag
    (observe-only: reporting, never mutation). Returns whether an alert was posted.

    Suppressed unless ``enabled`` is True, a ``topic`` is set, the report is non-clean, and
    its severity is at least ``min_severity``. The default ``poster`` is injectable so tests
    assert on the payload without any network call."""
    if not enabled or not topic:
        return False
    sev = report.max_severity
    if sev is None or _SEVERITY_ORDER[sev] < _SEVERITY_ORDER[min_severity]:
        return False
    title = f"renquant105 reconcile: {sev.value}"
    if report.halt_new_entries_advised:
        title += " (halt-new-entries advised)"
    return poster(title, report.summary_text(), topic)


# --------------------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------------------
def _utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string (audit stamp for the durable ledger)."""
    return datetime.now(timezone.utc).isoformat()


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _parse_ts(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp (accepts a trailing ``Z``). Returns a tz-aware datetime
    (assumes UTC if naive), or ``None`` if unparseable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_json(report: ReconciliationReport) -> str:
    """Serialise a report to stable JSON (handy for the run-bundle / ledger)."""
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)
