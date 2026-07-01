"""Tests for ``execution_reconciler`` — renquant105 §7 order-lifecycle safety core.

Deterministic and fixture-driven: no live broker, no network. Covers legal/illegal
lifecycle transitions, two-level idempotency (same intent key -> no duplicate), the §7
cumulative-quantity invariants (over-/under-fill, whole-share vs fractional), every
reconciliation divergence class + its severity, the §7 halt-new-entries advisory, and the
clean-state no-diff case. Also asserts the reconciler is observe-only (no mutation).
"""
from __future__ import annotations

import pytest

from renquant_orchestrator.execution_reconciler import (
    ALPACA_STATUS_TO_STATE,
    BrokerState,
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
    account_from_children,
    is_whole_share,
    make_child_order_id,
    make_parent_intent_id,
    maybe_alert,
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
    # unknown broker status is not silently dropped -> treated as a live/accepted order
    assert LifecycleMachine.from_broker_status("weird_new_status") is OrderState.ACCEPTED
    assert "expired" in ALPACA_STATUS_TO_STATE


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
# 3. Quantity accounting (§7 invariants)
# ==================================================================================
def _child(qty, filled, state, cid="c", sym="MU", side="buy"):
    return OrderRecord(
        symbol=sym,
        side=side,
        qty=qty,
        filled_qty=filled,
        state=state,
        client_order_id=cid,
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
