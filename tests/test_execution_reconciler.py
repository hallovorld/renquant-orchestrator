"""Tests for ``execution_reconciler`` — renquant105 §7 order-lifecycle safety core.

Deterministic and fixture-driven: no live broker, no network. Covers legal/illegal
lifecycle transitions, two-level idempotency (same intent key -> no duplicate), the §7
cumulative-quantity invariants (over-/under-fill, whole-share vs fractional), every
reconciliation divergence class + its severity, the §7 halt-new-entries advisory, and the
clean-state no-diff case. Also asserts the reconciler is observe-only (no mutation).
"""
from __future__ import annotations

import concurrent.futures
import threading

import pytest

from renquant_orchestrator.execution_reconciler import (
    ALPACA_STATUS_TO_STATE,
    BrokerState,
    ChildAttempt,
    Divergence,
    DivergenceKind,
    ExecutionReconciler,
    IllegalTransition,
    IntentRegistry,
    LifecycleMachine,
    LocalState,
    OrderIntent,
    OrderRecord,
    OrderState,
    Position,
    QuantityAccount,
    ReconciliationReport,
    Severity,
    SqliteIntentStore,
    account_from_children,
    accounts_by_parent,
    dedupe_latest_orders,
    is_whole_share,
    make_child_order_id,
    make_parent_intent_id,
    maybe_alert,
    parent_intent_id_of,
)


# ----------------------------------------------------------------------------------
# fixtures / DI loaders
# ----------------------------------------------------------------------------------
class _StaticLocal:
    def __init__(self, state: LocalState) -> None:
        self._state = state

    def load_local_state(self) -> LocalState:
        return self._state


class _StaticBroker:
    def __init__(self, state: BrokerState) -> None:
        self._state = state

    def load_broker_state(self) -> BrokerState:
        return self._state


def _reconciler(local: LocalState, broker: BrokerState, **kw) -> ExecutionReconciler:
    return ExecutionReconciler(_StaticLocal(local), _StaticBroker(broker), **kw)


# ==================================================================================
# 1. Lifecycle state machine
# ==================================================================================
def test_legal_happy_path_transitions():
    LifecycleMachine.validate_path(
        [
            OrderState.NONE,
            OrderState.INTENDED,
            OrderState.SUBMITTED,
            OrderState.ACCEPTED,
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
        ]
    )  # must not raise


def test_partial_then_partial_then_fill_is_legal():
    LifecycleMachine.validate_path(
        [OrderState.PARTIALLY_FILLED, OrderState.PARTIALLY_FILLED, OrderState.FILLED]
    )


def test_stale_pending_reconciles_to_cancel_or_fill():
    assert LifecycleMachine.is_legal(OrderState.ACCEPTED, OrderState.STALE_PENDING)
    assert LifecycleMachine.is_legal(OrderState.STALE_PENDING, OrderState.CANCELED)
    assert LifecycleMachine.is_legal(OrderState.STALE_PENDING, OrderState.FILLED)


@pytest.mark.parametrize(
    "src,dst",
    [
        (OrderState.FILLED, OrderState.SUBMITTED),  # terminal reuse
        (OrderState.CANCELED, OrderState.ACCEPTED),  # terminal reuse
        (OrderState.REJECTED, OrderState.FILLED),  # terminal reuse
        (OrderState.NONE, OrderState.FILLED),  # skip the whole lifecycle
        (OrderState.FILLED, OrderState.PARTIALLY_FILLED),  # run backwards
        (OrderState.ACCEPTED, OrderState.INTENDED),  # run backwards
    ],
)
def test_illegal_transitions_raise(src, dst):
    assert not LifecycleMachine.is_legal(src, dst)
    with pytest.raises(IllegalTransition):
        LifecycleMachine.advance(src, dst)


def test_broker_status_maps_to_canonical_state():
    assert LifecycleMachine.from_broker_status("partially_filled") is OrderState.PARTIALLY_FILLED
    assert LifecycleMachine.from_broker_status("FILLED") is OrderState.FILLED
    assert LifecycleMachine.from_broker_status("rejected") is OrderState.REJECTED
    assert LifecycleMachine.from_broker_status("canceled") is OrderState.CANCELED
    # a broker `replaced` is NOT a plain cancel — it keeps its own lineage state.
    assert LifecycleMachine.from_broker_status("replaced") is OrderState.REPLACED
    # An unknown broker status FAILS CLOSED to UNKNOWN — never fail-open to ACCEPTED, so a
    # broker API/schema drift can't masquerade as a valid open order.
    assert LifecycleMachine.from_broker_status("weird_new_status") is OrderState.UNKNOWN
    assert LifecycleMachine.from_broker_status("") is OrderState.UNKNOWN
    assert "expired" in ALPACA_STATUS_TO_STATE


def test_unknown_state_has_no_legal_transitions():
    # UNKNOWN is a fail-closed sentinel: never a legal source or destination.
    for st in OrderState:
        assert not LifecycleMachine.is_legal(OrderState.UNKNOWN, st)
        assert not LifecycleMachine.is_legal(st, OrderState.UNKNOWN)


def test_replaced_is_terminal_and_reachable_from_live_states():
    from renquant_orchestrator.execution_reconciler import TERMINAL_STATES

    assert OrderState.REPLACED in TERMINAL_STATES
    assert LifecycleMachine.is_legal(OrderState.ACCEPTED, OrderState.REPLACED)
    assert LifecycleMachine.is_legal(OrderState.PARTIALLY_FILLED, OrderState.REPLACED)
    # terminal: nothing leaves REPLACED
    assert not LifecycleMachine.is_legal(OrderState.REPLACED, OrderState.FILLED)


# ==================================================================================
# 2. Idempotency identity (two-level id, §7)
# ==================================================================================
def test_parent_intent_id_is_stable_for_same_decision():
    a = make_parent_intent_id("acct1", "MU", "2026-07-01", "buy", "sigv7")
    b = make_parent_intent_id("acct1", "mu", "2026-07-01", "BUY", "sigv7")  # normalized
    assert a == b
    assert a != make_parent_intent_id("acct1", "MU", "2026-07-01", "sell", "sigv7")
    assert a != make_parent_intent_id("acct1", "MU", "2026-07-01", "buy", "sigv8")


def test_child_order_id_is_unique_per_attempt():
    parent = make_parent_intent_id("acct1", "MU", "2026-07-01", "buy", "sigv7")
    c0 = make_child_order_id(parent, 0)
    c1 = make_child_order_id(parent, 1)
    assert c0 != c1
    assert c0.startswith(parent) and c1.startswith(parent)
    with pytest.raises(ValueError):
        make_child_order_id(parent, -1)


def test_intent_registry_dedups_reruns():
    reg = IntentRegistry()
    intent = OrderIntent.build(
        account="acct1",
        symbol="MU",
        trading_day="2026-07-01",
        side="buy",
        signal_version="sigv7",
        target_qty=10,
    )
    # First registration creates; a re-run / redelivery of the SAME decision is suppressed.
    assert reg.register(intent) is True
    dup = OrderIntent.build(
        account="acct1",
        symbol="MU",
        trading_day="2026-07-01",
        side="buy",
        signal_version="sigv7",
        target_qty=10,
    )
    assert reg.is_duplicate(dup) is True
    assert reg.register(dup) is False  # no duplicate order
    assert len(reg) == 1


# ==================================================================================
# 2b. Durable idempotency store (SqliteIntentStore) — the REAL safety core
# ==================================================================================
def _intent(target_qty=10, symbol="MU", side="buy", signal_version="sigv7"):
    return OrderIntent.build(
        account="acct1",
        symbol=symbol,
        trading_day="2026-07-01",
        side=side,
        signal_version=signal_version,
        target_qty=target_qty,
    )


def test_durable_store_create_or_get_is_atomic_and_idempotent(tmp_path):
    store = SqliteIntentStore(tmp_path / "intents.db")
    intent = _intent()
    stored, created = store.create_or_get_intent(intent)
    assert created is True
    assert stored.parent_intent_id == intent.parent_intent_id
    # a re-run / redelivery of the SAME decision is a no-op create
    stored2, created2 = store.create_or_get_intent(_intent())
    assert created2 is False
    assert stored2.parent_intent_id == intent.parent_intent_id
    assert len(store) == 1
    assert intent.parent_intent_id in store
    store.close()


def test_durable_store_survives_process_restart(tmp_path):
    path = tmp_path / "intents.db"
    intent = _intent()
    # "process 1": register + allocate a child, then close (simulating shutdown).
    s1 = SqliteIntentStore(path)
    s1.create_or_get_intent(intent)
    child0 = s1.allocate_child(intent.parent_intent_id)
    assert child0.attempt_n == 0
    s1.close()

    # "process 2": a brand-new store on the SAME file still knows the decision — the dedup
    # guarantee survives restart (this is exactly what an in-memory registry cannot do).
    s2 = SqliteIntentStore(path)
    assert s2.has_intent(intent.parent_intent_id) is True
    _, created = s2.create_or_get_intent(_intent())
    assert created is False  # not re-created after restart
    # attempt numbering continues monotonically across the restart, never reused.
    child1 = s2.allocate_child(intent.parent_intent_id)
    assert child1.attempt_n == 1
    assert child1.client_order_id != child0.client_order_id
    s2.close()


def test_durable_store_two_concurrent_registrants_create_exactly_one(tmp_path):
    path = tmp_path / "intents.db"
    # pre-create the schema so workers only race on the INSERT.
    SqliteIntentStore(path).close()

    n_workers = 16
    barrier = threading.Barrier(n_workers)

    def worker() -> bool:
        # each worker is its OWN connection == a distinct concurrent worker; DB-level UNIQUE
        # is what enforces "exactly one create", not any in-process lock.
        store = SqliteIntentStore(path)
        try:
            barrier.wait(timeout=10)
            _, created = store.create_or_get_intent(_intent())
            return created
        finally:
            store.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as ex:
        results = list(ex.map(lambda _: worker(), range(n_workers)))

    assert sum(results) == 1  # exactly one registrant won the create
    final = SqliteIntentStore(path)
    assert len(final) == 1  # no duplicate rows despite the race
    final.close()


def test_durable_store_child_allocation_is_unique_and_bindable(tmp_path):
    store = SqliteIntentStore(tmp_path / "intents.db")
    intent = _intent()
    store.create_or_get_intent(intent)
    c0 = store.allocate_child(intent.parent_intent_id)
    c1 = store.allocate_child(intent.parent_intent_id)
    assert (c0.attempt_n, c1.attempt_n) == (0, 1)
    assert c0.client_order_id == make_child_order_id(intent.parent_intent_id, 0)
    assert c0.client_order_id != c1.client_order_id
    assert c0.broker_order_id is None

    # broker client-order-id binding records the broker's own id for the attempt.
    store.bind_broker_order_id(c0.client_order_id, "brk-abc-1")
    attempts = store.child_attempts(intent.parent_intent_id)
    assert isinstance(attempts[0], ChildAttempt)
    assert attempts[0].broker_order_id == "brk-abc-1"
    with pytest.raises(KeyError):
        store.bind_broker_order_id("never-allocated", "brk-x")
    store.close()


def test_durable_store_allocate_child_requires_known_parent(tmp_path):
    store = SqliteIntentStore(tmp_path / "intents.db")
    with pytest.raises(KeyError):
        store.allocate_child("pi_does_not_exist")
    store.close()


def test_durable_store_concurrent_child_allocation_never_reuses_attempt(tmp_path):
    path = tmp_path / "intents.db"
    seed = SqliteIntentStore(path)
    intent = _intent()
    seed.create_or_get_intent(intent)
    seed.close()

    n_workers = 12
    barrier = threading.Barrier(n_workers)

    def worker() -> int:
        store = SqliteIntentStore(path)
        try:
            barrier.wait(timeout=10)
            return store.allocate_child(intent.parent_intent_id).attempt_n
        finally:
            store.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as ex:
        attempts = list(ex.map(lambda _: worker(), range(n_workers)))

    # every attempt number is distinct and they form a contiguous 0..n-1 range.
    assert sorted(attempts) == list(range(n_workers))


# ==================================================================================
# 3. Quantity accounting (§7 invariants)
# ==================================================================================
def _child(
    qty,
    filled,
    state,
    cid="c",
    sym="MU",
    side="buy",
    updated_at=None,
    replaced_by=None,
    broker_order_id=None,
):
    return OrderRecord(
        symbol=sym,
        side=side,
        qty=qty,
        filled_qty=filled,
        state=state,
        client_order_id=cid,
        updated_at=updated_at,
        replaced_by=replaced_by,
        broker_order_id=broker_order_id,
    )


def test_cancel_retry_never_over_fills_but_gross_may_exceed_target():
    # §7 worked example: target 10; child1 asks 10 fills 4 then cancels 6; child2 asks 6.
    child1 = _child(10, 4, OrderState.CANCELED, cid="pi:0")
    child2 = _child(6, 6, OrderState.FILLED, cid="pi:1")
    acct = account_from_children("pi", "MU", "buy", 10, [child1, child2])
    assert acct.cum_filled == 10
    assert acct.open_qty == 0
    assert acct.economic_exposure == 10
    assert acct.invariant_holds() is True
    assert acct.is_over_filled is False
    # audit invariant is allowed to exceed target (10 filled + 6 canceled = 16).
    assert acct.gross_submitted_qty == 16
    assert acct.remaining_unsubmitted == 0


def test_open_child_counts_against_economic_target():
    child = _child(10, 4, OrderState.PARTIALLY_FILLED, cid="pi:0")
    acct = account_from_children("pi", "MU", "buy", 10, [child])
    assert acct.cum_filled == 4
    assert acct.open_qty == 6
    assert acct.economic_exposure == 10
    assert acct.remaining_unsubmitted == 0
    assert acct.is_over_filled is False


def test_over_fill_detected():
    # Two fills summing beyond target -> economic invariant breach.
    child1 = _child(6, 6, OrderState.FILLED, cid="pi:0")
    child2 = _child(6, 6, OrderState.FILLED, cid="pi:1")
    acct = account_from_children("pi", "MU", "buy", 10, [child1, child2])
    assert acct.economic_exposure == 12
    assert acct.is_over_filled is True
    assert acct.invariant_holds() is False


def test_under_fill_detected_when_settled_below_target():
    child = _child(10, 4, OrderState.CANCELED, cid="pi:0")
    acct = account_from_children("pi", "MU", "buy", 10, [child])
    assert acct.is_settled is True
    assert acct.is_under_filled is True
    assert acct.cum_canceled == 6


def test_whole_share_vs_fractional_detection():
    assert is_whole_share(7.0) is True
    assert is_whole_share(7.5) is False
    frac = account_from_children(
        "pi", "MU", "buy", 3.5, [_child(3.5, 3.5, OrderState.FILLED)]
    )
    assert frac.is_fractional is True
    whole = account_from_children("pi", "MU", "buy", 3, [_child(3, 3, OrderState.FILLED)])
    assert whole.is_fractional is False


# ----------------------------------------------------------------------------------
# 3b. Snapshot dedup / latest-version / corrections & busts
# ----------------------------------------------------------------------------------
def test_duplicate_snapshot_of_same_child_counts_once():
    # The broker re-delivers the SAME child order twice — summing raw would double-count.
    snap = _child(10, 10, OrderState.FILLED, cid="pi:0", updated_at="2026-07-01T14:00:00Z")
    dup = _child(10, 10, OrderState.FILLED, cid="pi:0", updated_at="2026-07-01T14:00:00Z")
    acct = account_from_children("pi", "MU", "buy", 10, [snap, dup])
    assert acct.cum_filled == 10  # not 20
    assert acct.economic_exposure == 10


def test_latest_version_wins_over_stale_snapshot():
    # A stale snapshot (filled 4) arrives alongside the newer one (filled 10).
    stale = _child(10, 4, OrderState.PARTIALLY_FILLED, cid="pi:0",
                   updated_at="2026-07-01T14:00:00Z")
    fresh = _child(10, 10, OrderState.FILLED, cid="pi:0",
                   updated_at="2026-07-01T14:05:00Z")
    # order in the list is intentionally stale-last to prove we sort by updated_at, not order.
    acct = account_from_children("pi", "MU", "buy", 10, [fresh, stale])
    assert acct.cum_filled == 10
    assert acct.open_qty == 0
    assert acct.is_over_filled is False


def test_correction_bust_reduces_filled_via_latest_version():
    # A busted/corrected fill: an earlier snapshot booked 10 filled; the correction reduces it
    # to 6. Latest-version semantics must honour the correction, not sum 16.
    original = _child(10, 10, OrderState.FILLED, cid="pi:0",
                      updated_at="2026-07-01T14:00:00Z")
    corrected = _child(10, 6, OrderState.CANCELED, cid="pi:0",
                       updated_at="2026-07-01T14:10:00Z")
    acct = account_from_children("pi", "MU", "buy", 10, [original, corrected])
    assert acct.cum_filled == 6
    assert acct.cum_canceled == 4
    assert acct.is_over_filled is False


def test_dedupe_latest_orders_passes_through_keyless_records():
    keyless_a = OrderRecord(symbol="MU", side="buy", qty=1, filled_qty=0,
                            state=OrderState.ACCEPTED)
    keyless_b = OrderRecord(symbol="MU", side="buy", qty=2, filled_qty=0,
                            state=OrderState.ACCEPTED)
    keyed = _child(3, 3, OrderState.FILLED, cid="pi:0")
    out = dedupe_latest_orders([keyed, keyless_a, keyless_b])
    # keyless records can't be proven duplicates -> all pass through
    assert len(out) == 3


# ----------------------------------------------------------------------------------
# 3c. Replacement lineage (a `replaced` order is not a canceled under-fill)
# ----------------------------------------------------------------------------------
def test_replaced_remainder_is_not_canceled_and_not_false_under_fill():
    # target 10; child0 asks 10, fills 4, then is REPLACED by child1; child1 asks 6, fills 6.
    child0 = _child(10, 4, OrderState.REPLACED, cid="pi:0", replaced_by="pi:1")
    child1 = _child(6, 6, OrderState.FILLED, cid="pi:1")
    acct = account_from_children("pi", "MU", "buy", 10, [child0, child1])
    assert acct.cum_filled == 10
    assert acct.cum_replaced == 6  # the replaced remainder — a SEPARATE bucket
    assert acct.cum_canceled == 0  # NOT booked as canceled (no false retry eligibility)
    assert acct.is_under_filled is False
    assert acct.has_unlinked_replacement is False
    assert acct.economic_exposure == 10
    # gross audit trail still includes the replaced attempt (10 filled + 6 replaced).
    assert acct.gross_submitted_qty == 16


def test_unlinked_replacement_flags_lineage_break_not_under_fill():
    # child0 is REPLACED but its replacement (`pi:1`) is NOT present in the reconciled set.
    child0 = _child(10, 4, OrderState.REPLACED, cid="pi:0", replaced_by="pi:1")
    acct = account_from_children("pi", "MU", "buy", 10, [child0])
    assert acct.has_unlinked_replacement is True
    assert acct.unlinked_replacement_ids == ["pi:0"]
    # deliberately NOT reported as under-fill — the shortfall is a lineage gap, not a benign
    # canceled remainder.
    assert acct.is_under_filled is False


def test_replaced_with_null_lineage_is_unlinked():
    child0 = _child(10, 4, OrderState.REPLACED, cid="pi:0", replaced_by=None)
    acct = account_from_children("pi", "MU", "buy", 10, [child0])
    assert acct.has_unlinked_replacement is True


def test_replacement_lineage_break_surfaces_as_warning_and_advises_halt():
    child0 = _child(10, 4, OrderState.REPLACED, cid="pi:0", replaced_by="pi:1")
    acct = account_from_children("pi", "MU", "buy", 10, [child0])
    local = LocalState(accounts=[acct])
    report = _reconciler(local, BrokerState()).reconcile()
    d = report.of_kind(DivergenceKind.REPLACEMENT_LINEAGE_BREAK)
    assert len(d) == 1
    assert d[0].severity is Severity.WARNING
    # a lineage break is a ledger-integrity failure -> advise halting new entries.
    assert report.halt_new_entries_advised is True
    # and it must NOT be double-reported as a benign under-fill.
    assert report.of_kind(DivergenceKind.UNDER_FILL) == []


# ----------------------------------------------------------------------------------
# 3d. Per-parent reconciliation of authoritative broker children
# ----------------------------------------------------------------------------------
def test_parent_intent_id_of_prefers_field_then_client_order_id_prefix():
    explicit = OrderRecord(symbol="MU", side="buy", qty=1, parent_intent_id="pi_explicit")
    assert parent_intent_id_of(explicit) == "pi_explicit"
    derived = OrderRecord(symbol="MU", side="buy", qty=1, client_order_id="pi_abc:3")
    assert parent_intent_id_of(derived) == "pi_abc"
    assert parent_intent_id_of(OrderRecord(symbol="MU", side="buy", qty=1)) is None


def test_accounts_by_parent_groups_and_dedupes_broker_children():
    intent = OrderIntent.build(
        account="acct1", symbol="MU", trading_day="2026-07-01", side="buy",
        signal_version="sigv7", target_qty=10,
    )
    pid = intent.parent_intent_id
    # two attempts under the same parent + a duplicate snapshot of attempt 0.
    a0 = _child(6, 6, OrderState.FILLED, cid=f"{pid}:0", updated_at="2026-07-01T14:00:00Z")
    a0_dup = _child(6, 6, OrderState.FILLED, cid=f"{pid}:0",
                    updated_at="2026-07-01T14:00:00Z")
    a1 = _child(4, 4, OrderState.FILLED, cid=f"{pid}:1")
    # an unrelated order for a parent not in `intents` is ignored here (surfaces as orphan).
    stray = _child(5, 0, OrderState.ACCEPTED, cid="pi_other:0")
    accts = accounts_by_parent([intent], [a0, a0_dup, a1, stray])
    assert len(accts) == 1
    acct = accts[0]
    assert acct.parent_intent_id == pid
    assert acct.cum_filled == 10  # 6 + 4, duplicate snapshot not double-counted
    assert acct.is_over_filled is False


# ==================================================================================
# 4. Reconciliation divergence classes + severity
# ==================================================================================
def test_clean_state_no_diff():
    pos = {"MU": Position("MU", 10.0), "AMZN": Position("AMZN", 3.0)}
    local = LocalState(positions=dict(pos), orders=[], accounts=[])
    broker = BrokerState(positions=dict(pos), orders=[])
    report = _reconciler(local, broker).reconcile()
    assert report.is_clean is True
    assert report.divergences == []
    assert report.max_severity is None
    assert report.halt_new_entries_advised is False


def test_missing_local_fill_is_critical():
    local = LocalState(positions={}, orders=[])
    broker = BrokerState(positions={"MU": Position("MU", 10.0)}, orders=[])
    report = _reconciler(local, broker).reconcile()
    kinds = report.counts_by_kind()
    assert kinds.get("MISSING_LOCAL_FILL") == 1
    assert report.max_severity is Severity.CRITICAL
    assert report.halt_new_entries_advised is True


def test_phantom_local_position_is_critical():
    local = LocalState(positions={"MU": Position("MU", 10.0)}, orders=[])
    broker = BrokerState(positions={}, orders=[])
    report = _reconciler(local, broker).reconcile()
    d = report.of_kind(DivergenceKind.PHANTOM_LOCAL_POSITION)
    assert len(d) == 1
    assert d[0].severity is Severity.CRITICAL
    assert report.halt_new_entries_advised is True


def test_quantity_mismatch_is_warning_and_reports_delta():
    local = LocalState(positions={"MU": Position("MU", 7.0)}, orders=[])
    broker = BrokerState(positions={"MU": Position("MU", 10.0)}, orders=[])
    report = _reconciler(local, broker).reconcile()
    d = report.of_kind(DivergenceKind.QUANTITY_MISMATCH)
    assert len(d) == 1
    assert d[0].severity is Severity.WARNING
    assert d[0].local == 7.0 and d[0].broker == 10.0


def test_orphan_broker_order_warns_and_advises_halt():
    local = LocalState(positions={}, orders=[])
    broker = BrokerState(
        positions={},
        orders=[
            OrderRecord(
                symbol="MU",
                side="buy",
                qty=10,
                state=OrderState.ACCEPTED,
                client_order_id="pi_unknown:0",
            )
        ],
    )
    report = _reconciler(local, broker).reconcile()
    d = report.of_kind(DivergenceKind.ORPHAN_BROKER_ORDER)
    assert len(d) == 1
    assert d[0].severity is Severity.WARNING
    # §7: an open-order ledger mismatch advises halting new entries even though only WARNING.
    assert report.halt_new_entries_advised is True


def test_untracked_local_order_warns():
    local = LocalState(
        positions={},
        orders=[
            OrderRecord(
                symbol="MU",
                side="buy",
                qty=10,
                state=OrderState.SUBMITTED,
                client_order_id="pi_local:0",
            )
        ],
    )
    broker = BrokerState(positions={}, orders=[])
    report = _reconciler(local, broker).reconcile()
    d = report.of_kind(DivergenceKind.UNTRACKED_LOCAL_ORDER)
    assert len(d) == 1
    assert d[0].severity is Severity.WARNING
    assert report.halt_new_entries_advised is True


def test_matched_order_fill_drift_is_missing_local_fill():
    common = dict(symbol="MU", side="buy", qty=10, client_order_id="pi:0")
    local = LocalState(
        orders=[OrderRecord(**common, filled_qty=4.0, state=OrderState.PARTIALLY_FILLED)]
    )
    broker = BrokerState(
        orders=[OrderRecord(**common, filled_qty=10.0, state=OrderState.FILLED)]
    )
    report = _reconciler(local, broker).reconcile()
    d = report.of_kind(DivergenceKind.MISSING_LOCAL_FILL)
    assert len(d) == 1
    assert d[0].severity is Severity.CRITICAL
    assert d[0].local == 4.0 and d[0].broker == 10.0


def test_matched_order_state_drift_only_is_warning():
    common = dict(symbol="MU", side="buy", qty=10, filled_qty=0.0, client_order_id="pi:0")
    local = LocalState(orders=[OrderRecord(**common, state=OrderState.SUBMITTED)])
    broker = BrokerState(orders=[OrderRecord(**common, state=OrderState.ACCEPTED)])
    report = _reconciler(local, broker).reconcile()
    d = report.of_kind(DivergenceKind.ORDER_STATE_DRIFT)
    assert len(d) == 1
    assert d[0].severity is Severity.WARNING


def test_unknown_broker_status_surfaces_critical_and_advises_halt():
    # A broker status we cannot map fails CLOSED: the reconciler emits UNKNOWN_ORDER_STATUS
    # as CRITICAL and advises halting new entries, instead of the order masquerading as a
    # valid open order (Codex review, 2026-07-01).
    unknown = OrderRecord.from_broker(
        {
            "symbol": "MU",
            "side": "buy",
            "qty": "10",
            "status": "some_brand_new_status",
            "client_order_id": "pi:0",
            "id": "brk-999",
        }
    )
    assert unknown.state is OrderState.UNKNOWN
    broker = BrokerState(positions={}, orders=[unknown])
    # local tracks the SAME id so it can't be dismissed as an orphan — isolate the UNKNOWN.
    local = LocalState(
        orders=[
            OrderRecord(
                symbol="MU",
                side="buy",
                qty=10,
                state=OrderState.ACCEPTED,
                client_order_id="pi:0",
            )
        ]
    )
    report = _reconciler(local, broker).reconcile()
    d = report.of_kind(DivergenceKind.UNKNOWN_ORDER_STATUS)
    assert len(d) == 1
    assert d[0].severity is Severity.CRITICAL
    assert report.halt_new_entries_advised is True
    # An UNKNOWN status must NOT also be double-reported as a benign state drift — that would
    # understate the fail-closed condition.
    assert report.of_kind(DivergenceKind.ORDER_STATE_DRIFT) == []


def test_stale_pending_order_detected_against_as_of():
    broker = BrokerState(
        positions={},
        orders=[
            OrderRecord(
                symbol="MU",
                side="buy",
                qty=10,
                state=OrderState.ACCEPTED,
                client_order_id="pi:0",
                submitted_at="2026-07-01T14:00:00Z",
            )
        ],
    )
    # local also tracks it (so no orphan), to isolate the stale-pending signal.
    local = LocalState(
        orders=[
            OrderRecord(
                symbol="MU",
                side="buy",
                qty=10,
                state=OrderState.ACCEPTED,
                client_order_id="pi:0",
            )
        ]
    )
    rec = _reconciler(local, broker, max_pending_age_seconds=600)
    # 20 minutes later -> stale (>10 min).
    report = rec.reconcile(as_of="2026-07-01T14:20:00Z")
    assert report.counts_by_kind().get("STALE_PENDING_ORDER") == 1
    # 5 minutes later -> not stale.
    report2 = rec.reconcile(as_of="2026-07-01T14:05:00Z")
    assert report2.counts_by_kind().get("STALE_PENDING_ORDER") is None


def test_over_fill_account_surfaces_in_report():
    over = QuantityAccount("pi", "MU", "buy", target_qty=10, cum_filled=12)
    local = LocalState(accounts=[over])
    broker = BrokerState()
    report = _reconciler(local, broker).reconcile()
    d = report.of_kind(DivergenceKind.OVER_FILL)
    assert len(d) == 1
    assert d[0].severity is Severity.CRITICAL
    assert report.halt_new_entries_advised is True


def test_fractional_quantity_is_info_only():
    local = LocalState(positions={"MU": Position("MU", 3.5)})
    broker = BrokerState(positions={"MU": Position("MU", 3.5)})
    report = _reconciler(local, broker).reconcile()
    d = report.of_kind(DivergenceKind.FRACTIONAL_QUANTITY)
    assert len(d) == 1
    assert d[0].severity is Severity.INFO
    # INFO alone does not advise a halt.
    assert report.halt_new_entries_advised is False


def test_broker_row_normalization_matches_alpaca_field_names():
    pos = Position.from_broker(
        {"symbol": "mu", "qty": "10", "avg_entry_price": "100.5", "market_value": "1005"}
    )
    assert pos.symbol == "MU" and pos.qty == 10.0 and pos.avg_entry_price == 100.5
    order = OrderRecord.from_broker(
        {
            "symbol": "MU",
            "side": "buy",
            "qty": "10",
            "filled_qty": "4",
            "filled_avg_price": "101.2",
            "status": "partially_filled",
            "client_order_id": "pi:0",
            "id": "brk-123",
        }
    )
    assert order.state is OrderState.PARTIALLY_FILLED
    assert order.filled_qty == 4.0
    assert order.broker_order_id == "brk-123"
    assert order.is_open is True


# ==================================================================================
# 5. Report serialisation + ntfy alert (observe-only, behind a flag)
# ==================================================================================
def test_report_to_dict_is_serialisable_and_summarises():
    local = LocalState(positions={"MU": Position("MU", 10.0)})
    broker = BrokerState(positions={})
    report = _reconciler(local, broker).reconcile()
    d = report.to_dict()
    assert d["halt_new_entries_advised"] is True
    assert d["max_severity"] == "CRITICAL"
    assert d["counts_by_kind"]["PHANTOM_LOCAL_POSITION"] == 1
    assert "PHANTOM_LOCAL_POSITION" in report.summary_text()


def test_alert_suppressed_unless_enabled():
    posted: list[tuple[str, str, str]] = []

    def _poster(title, body, topic):
        posted.append((title, body, topic))
        return True

    local = LocalState(positions={"MU": Position("MU", 10.0)})
    broker = BrokerState(positions={})
    report = _reconciler(local, broker).reconcile()

    # flag OFF -> never posts (observe-only default)
    assert maybe_alert(report, enabled=False, topic="t", poster=_poster) is False
    assert posted == []
    # flag ON -> posts
    assert maybe_alert(report, enabled=True, topic="t", poster=_poster) is True
    assert len(posted) == 1
    assert "halt-new-entries advised" in posted[0][0]


def test_alert_suppressed_on_clean_or_below_min_severity():
    posted: list = []
    poster = lambda *a: posted.append(a) or True  # noqa: E731

    clean = ReconciliationReport(divergences=[])
    assert maybe_alert(clean, enabled=True, topic="t", poster=poster) is False

    info_only = ReconciliationReport(
        divergences=[Divergence(DivergenceKind.FRACTIONAL_QUANTITY, Severity.INFO, "frac")]
    )
    # default min_severity=WARNING -> INFO-only report does not alert
    assert maybe_alert(info_only, enabled=True, topic="t", poster=poster) is False
    assert posted == []


def test_reconcile_does_not_mutate_inputs():
    local_positions = {"MU": Position("MU", 10.0)}
    local_orders: list[OrderRecord] = []
    local = LocalState(positions=local_positions, orders=local_orders)
    broker = BrokerState(positions={})
    _reconciler(local, broker).reconcile()
    # observe-only: inputs untouched
    assert local.positions == {"MU": Position("MU", 10.0)}
    assert local.orders == []
    assert broker.positions == {}
