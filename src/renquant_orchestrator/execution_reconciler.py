"""renquant105 execution reconciler — §7 order-lifecycle safety core (OBSERVE-ONLY).

Stage-1 safety infrastructure for the intraday (盘中) decisioning path described in
``doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`` (§7 order
lifecycle / idempotency, §10 safety envelope). This module is **advisory / observe-only**:
it *detects and reports* divergence between what the local decision loop believes and
what the broker authoritatively holds; it **never** places, cancels, mutates, or persists
anything. The live path (execution repo, §8 order 1) owns the enforcing state machine;
this orchestrator-side library is the independent audit that rides alongside it.

Three concerns, all pure and dependency-injected so they unit-test with fixtures — no live
broker calls anywhere in this module:

1. **Order-lifecycle state machine** (``LifecycleMachine``) — legal transitions over
   ``OrderState``, plus the two-level idempotency identity from §7
   (``parent_intent_id`` dedup key + per-attempt ``child_order_id`` broker client-order-id)
   and an ``IntentRegistry`` so a re-run / redelivery cannot double-submit the same decision.
2. **Quantity accounting** (``QuantityAccount``) — reconciles intended vs submitted vs
   filled, enforcing the §7 economic invariant ``cum_filled + open_qty <= target_qty`` and
   flagging over-/under-fill. Whole-share vs fractional is *detected*, never rounded
   (Stage 1 is whole-share; §11 defers fractional to Stage 2).
3. **Broker/local reconciliation** (``ExecutionReconciler``) — diffs local state against the
   broker's authoritative positions/orders/fills, classifies each divergence
   (``DivergenceKind``) with a ``Severity``, and emits a structured report plus, behind an
   explicit flag, an ntfy alert. Per §7, an open-order ledger mismatch advises *halt new
   entries* (exits still allowed) — this module only advises; it does not enforce.
"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence

__all__ = [
    "OrderState",
    "OPEN_STATES",
    "TERMINAL_STATES",
    "ALPACA_STATUS_TO_STATE",
    "IllegalTransition",
    "LifecycleMachine",
    "make_parent_intent_id",
    "make_child_order_id",
    "OrderIntent",
    "IntentRegistry",
    "is_whole_share",
    "QuantityAccount",
    "account_from_children",
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
    STALE_PENDING = "STALE_PENDING"


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

# Absorbing states — no legal transition leaves them.
TERMINAL_STATES: frozenset[OrderState] = frozenset(
    {
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
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
            OrderState.STALE_PENDING,
        }
    ),
    OrderState.PARTIALLY_FILLED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELED,
            OrderState.EXPIRED,
            OrderState.STALE_PENDING,
        }
    ),
    OrderState.STALE_PENDING: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELED,
            OrderState.EXPIRED,
        }
    ),
    OrderState.FILLED: frozenset(),
    OrderState.CANCELED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.EXPIRED: frozenset(),
}

# Alpaca order.status -> canonical OrderState. Matches the broker field names seen in the
# live 104 broker state (``filled_qty`` / ``filled_avg_price`` / ``client_order_id`` etc.).
ALPACA_STATUS_TO_STATE: dict[str, OrderState] = {
    "new": OrderState.ACCEPTED,
    "pending_new": OrderState.SUBMITTED,
    "accepted": OrderState.ACCEPTED,
    "accepted_for_bidding": OrderState.ACCEPTED,
    "held": OrderState.ACCEPTED,
    "calculated": OrderState.ACCEPTED,
    "partially_filled": OrderState.PARTIALLY_FILLED,
    "filled": OrderState.FILLED,
    "done_for_day": OrderState.ACCEPTED,
    "canceled": OrderState.CANCELED,
    "cancelled": OrderState.CANCELED,
    "pending_cancel": OrderState.ACCEPTED,
    "expired": OrderState.EXPIRED,
    "replaced": OrderState.CANCELED,
    "pending_replace": OrderState.ACCEPTED,
    "rejected": OrderState.REJECTED,
    "suspended": OrderState.ACCEPTED,
    "stopped": OrderState.ACCEPTED,
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
        """Map a raw broker (Alpaca) ``order.status`` string to a canonical state."""
        return ALPACA_STATUS_TO_STATE.get(str(status).strip().lower(), OrderState.ACCEPTED)


def make_parent_intent_id(
    account: str, symbol: str, trading_day: str, side: str, signal_version: str
) -> str:
    """§7 dedup key — a stable hash of the *decision*, not a broker id. Re-deriving it for
    the same (account, symbol, trading_day, side, signal_version) yields the identical id,
    so a re-run or redelivery collides on the existing INTENDED row instead of creating a
    duplicate order."""
    payload = "|".join(
        [
            str(account).strip(),
            str(symbol).strip().upper(),
            str(trading_day).strip(),
            str(side).strip().lower(),
            str(signal_version).strip(),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"pi_{digest}"


def make_child_order_id(parent_intent_id: str, attempt_n: int) -> str:
    """§7 per-attempt broker client-order-id: ``parent_intent_id + ':' + attempt_n``. Every
    submission (initial + each remainder) gets a fresh unique id so the broker never
    duplicate-rejects, while all attempts still trace back to one parent decision."""
    if attempt_n < 0:
        raise ValueError(f"attempt_n must be >= 0, got {attempt_n}")
    return f"{parent_intent_id}:{attempt_n}"


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
            parent_intent_id=make_parent_intent_id(
                account, symbol, trading_day, side, signal_version
            ),
            account=account,
            symbol=str(symbol).strip().upper(),
            trading_day=trading_day,
            side=str(side).strip().lower(),
            signal_version=signal_version,
            target_qty=float(target_qty),
        )


class IntentRegistry:
    """Idempotent registry of intents keyed on ``parent_intent_id`` (§7 dedup). Registering
    the same decision twice is a no-op — this is the guard that a re-run / redelivery can
    never spawn a duplicate order for the same decision."""

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
        """Audit invariant — total ever submitted; MAY exceed target via canceled/rejected
        retries (the §7 example where target=10 but gross=16)."""
        return (
            self.cum_filled
            + self.open_qty
            + self.cum_canceled
            + self.cum_rejected
            + self.cum_expired
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
        canceled remainder stays eligible per §7, this is not an error by itself)."""
        return self.is_settled and (self.target_qty - self.cum_filled) > _QTY_TOL

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
            "economic_exposure": self.economic_exposure,
            "remaining_unsubmitted": self.remaining_unsubmitted,
            "gross_submitted_qty": self.gross_submitted_qty,
            "is_over_filled": self.is_over_filled,
            "is_under_filled": self.is_under_filled,
            "is_fractional": self.is_fractional,
        }


def account_from_children(
    parent_intent_id: str,
    symbol: str,
    side: str,
    target_qty: float,
    children: Sequence["OrderRecord"],
) -> QuantityAccount:
    """Fold a parent's child ``OrderRecord``s into a :class:`QuantityAccount`.

    Each child contributes its ``filled_qty`` to ``cum_filled``; the *unfilled* remainder is
    attributed by the child's canonical state — open (SUBMITTED/ACCEPTED/PARTIAL/STALE),
    canceled, rejected, or expired — so both the economic and audit invariants stay exact.
    """
    acct = QuantityAccount(
        parent_intent_id=parent_intent_id,
        symbol=str(symbol).strip().upper(),
        side=str(side).strip().lower(),
        target_qty=float(target_qty),
    )
    for child in children:
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
        # FILLED contributes only via cum_filled (unfilled == 0 by definition).
    return acct


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

    @property
    def is_open(self) -> bool:
        return self.state in OPEN_STATES

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


# Open-order ledger mismatches (§7: "broker open-orders != ledger -> halt new entries").
_LEDGER_MISMATCH_KINDS = frozenset(
    {
        DivergenceKind.ORPHAN_BROKER_ORDER,
        DivergenceKind.UNTRACKED_LOCAL_ORDER,
        DivergenceKind.ORDER_STATE_DRIFT,
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
