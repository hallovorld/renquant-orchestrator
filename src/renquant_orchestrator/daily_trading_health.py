"""Daily trading-health reporter — make 'is renquant-104 actually trading?' observable.

For weeks the live renquant-104 account was effectively sell-only / under-deployed
without surfacing, because no scheduled job persisted a daily verdict on *trading
health* (as opposed to model-promotion health, which ``scheduled_health`` already
covers). This module closes that gap with one read-only, fail-soft record per day:

  1. **account trading** — has the broker placed any orders recently? (open orders
     today, or a recent order in the run bundle's submitted_orders).
  2. **model health** — is a fresh scorer artifact present, and did the last run
     produce buys, or was it sell-only / zero-buy?
  3. **cash deployment** — invested % vs cash %, so a high-cash + zero-buy day
     (the exact sell-only symptom) is loud instead of silent.

The record is shaped like the other ``build_*`` health surfaces in this package
(``schema_version`` / ``owner_repo`` / ``summary``). It is:

  * **read-only** against the broker — it reuses
    :func:`native_live_snapshots.build_native_live_account_snapshot`, which only
    calls broker *read* APIs (cash/positions/open-orders). It NEVER places or
    cancels orders and NEVER mutates live state.
  * **fail-soft** — any signal whose inputs are missing degrades to
    ``"unknown"`` rather than raising, so a single missing file can never wedge
    the daily job.
  * **persisted** — each run's signals are appended to the decision ledger as
    gate verdicts (the previously-unwired ``GateRegistry`` → ledger bridge), so
    'why did we buy nothing on day X?' becomes one SQL query.
  * **alerting** — a bad day (zero buys on high cash / no fresh model / no orders
    in N days) emits an ntfy alert, reusing the established ``post_ntfy`` path.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from renquant_common.notify import send as _send_notification

SCHEMA_VERSION = 1
OWNER_REPO = "renquant-orchestrator"

# --- Alert thresholds (named constants, not magic numbers) -------------------
# A day is "high cash" (i.e. under-deployed) when cash is at least this share of
# portfolio value. Combined with zero buys this is the sell-only symptom.
HIGH_CASH_FRACTION = 0.50
# Buys are stale once the most recent submitted buy is older than this many days.
MAX_DAYS_WITHOUT_ORDERS = 3
# A scorer artifact is stale once it is older than this many days.
MAX_MODEL_ARTIFACT_AGE_DAYS = 7

# Map a per-signal status to a ledger verdict. "unknown" is conservative: it is
# NOT a block (we never had the data to say the gate fired) but it is surfaced.
_STATUS_TO_VERDICT = {"ok": "allow", "warn": "halve", "bad": "block", "unknown": "allow"}


@dataclass
class TradingHealthRecord:
    """The structured result of one daily trading-health evaluation."""

    as_of: str
    run_id: str
    account_trading: dict[str, Any] = field(default_factory=dict)
    model_health: dict[str, Any] = field(default_factory=dict)
    cash_deployment: dict[str, Any] = field(default_factory=dict)
    health_verdict: str = "unknown"
    alert_title: str | None = None
    alert_body: str | None = None
    reasons: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "owner_repo": OWNER_REPO,
            "as_of": self.as_of,
            "run_id": self.run_id,
            "signals": {
                "account_trading": self.account_trading,
                "model_health": self.model_health,
                "cash_deployment": self.cash_deployment,
            },
            "summary": {
                "health_verdict": self.health_verdict,
                "alert": self.alert_title is not None,
                "alert_title": self.alert_title,
                "alert_body": self.alert_body,
                "reasons": self.reasons,
            },
        }

    def ledger_verdicts(self) -> list[dict[str, Any]]:
        """One ledger row per signal, recording the daily trading-health verdict.

        Wired through the decision ledger so a sell-only / under-deployed stretch
        is one ``verdicts_for(as_of, 'book')`` query instead of log archaeology.
        """
        rows = []
        for gate, signal in (
            ("account_trading", self.account_trading),
            ("model_health", self.model_health),
            ("cash_deployment", self.cash_deployment),
        ):
            status = str(signal.get("status", "unknown"))
            rows.append({
                "scope": "book",
                "gate": f"trading_health.{gate}",
                "verdict": _STATUS_TO_VERDICT.get(status, "allow"),
                "reason": str(signal.get("reason", status)),
                "inputs": {k: v for k, v in signal.items() if k != "reason"},
            })
        return rows


# --- low-level helpers -------------------------------------------------------

def _today_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        text = str(value)
        # tolerate full ISO timestamps as well as bare YYYY-MM-DD
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def _load_json(path: str | Path | None) -> Any | None:
    if path is None:
        return None
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def post_ntfy(title: str, body: str, topic: str) -> None:
    """This monitor's alert seam: the canonical ``renquant_common.notify`` sender
    with the house priority/tags for daily trading health (campaign B6 re-point;
    also honors ``RENQUANT_NO_NOTIFY``, which the local copy did not)."""
    _send_notification(title, body, topic, priority=4, tags="warning,chart")


# --- signal builders ---------------------------------------------------------

def _account_snapshot(
    *,
    broker_name: str,
    account_snapshot: Mapping[str, Any] | None,
    snapshot_builder: Callable[..., dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Return a read-only account snapshot, or ``None`` if unavailable.

    Prefers an already-materialized snapshot (e.g. from the daily run bundle) so
    we never hit the broker twice; otherwise calls the read-only snapshot builder.
    Any failure degrades to ``None`` (caller marks the signal ``unknown``).
    """
    if account_snapshot is not None:
        return dict(account_snapshot)
    if snapshot_builder is None:
        return None
    try:
        # build_native_live_account_snapshot is read-only (cash/positions/open
        # orders) and writes its own JSON; route it to a throwaway path so we do
        # not clobber any operator artifact.
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".json", delete=True) as tmp:
            return snapshot_builder(broker_name=broker_name, output_json=tmp.name)
    except Exception:  # noqa: BLE001 — fail-soft: any broker hiccup -> unknown
        return None


def build_account_trading_signal(
    snapshot: Mapping[str, Any] | None,
    submitted_orders: list[Mapping[str, Any]] | None,
    *,
    as_of: date,
    max_days_without_orders: int = MAX_DAYS_WITHOUT_ORDERS,
) -> dict[str, Any]:
    """Is the account actually trading? Open orders now, or a recent submitted order."""
    open_orders = list(snapshot.get("open_orders", [])) if snapshot else None
    last_order_date = _most_recent_order_date(submitted_orders)
    days_since = (as_of - last_order_date).days if last_order_date else None

    if snapshot is None and submitted_orders is None:
        return {"status": "unknown", "reason": "no account snapshot or order history available"}

    if open_orders:
        return {
            "status": "ok",
            "reason": f"{len(open_orders)} open order(s) at broker",
            "open_order_count": len(open_orders),
            "days_since_last_order": days_since,
        }
    if days_since is not None and days_since <= max_days_without_orders:
        return {
            "status": "ok",
            "reason": f"last order {days_since}d ago (<= {max_days_without_orders}d)",
            "open_order_count": 0,
            "days_since_last_order": days_since,
        }
    if days_since is not None:
        return {
            "status": "bad",
            "reason": f"no orders for {days_since}d (> {max_days_without_orders}d)",
            "open_order_count": 0,
            "days_since_last_order": days_since,
        }
    # We had a snapshot but no order history at all and no open orders.
    return {
        "status": "warn",
        "reason": "no open orders and no order history available",
        "open_order_count": 0,
        "days_since_last_order": None,
    }


def _most_recent_order_date(orders: list[Mapping[str, Any]] | None) -> date | None:
    if not orders:
        return None
    dates: list[date] = []
    for order in orders:
        for key in ("submitted_at", "filled_at", "created_at", "as_of", "date", "timestamp"):
            parsed = _parse_date(order.get(key)) if isinstance(order, Mapping) else None
            if parsed is not None:
                dates.append(parsed)
                break
    return max(dates) if dates else None


def build_model_health_signal(
    *,
    artifact_path: str | Path | None,
    decision_trace: list[Mapping[str, Any]] | None,
    submitted_orders: list[Mapping[str, Any]] | None,
    as_of: date,
    max_artifact_age_days: int = MAX_MODEL_ARTIFACT_AGE_DAYS,
) -> dict[str, Any]:
    """Fresh scorer artifact present, and did the last run buy anything?"""
    artifact_age_days = _artifact_age_days(artifact_path, as_of=as_of)
    n_buys = _count_buys(decision_trace, submitted_orders)

    if artifact_age_days is None:
        return {
            "status": "bad",
            "reason": "no fresh scorer artifact found",
            "artifact_age_days": None,
            "n_buys": n_buys,
        }
    if artifact_age_days > max_artifact_age_days:
        return {
            "status": "bad",
            "reason": f"scorer artifact {artifact_age_days}d old (> {max_artifact_age_days}d)",
            "artifact_age_days": artifact_age_days,
            "n_buys": n_buys,
        }
    if n_buys is None:
        return {
            "status": "unknown",
            "reason": f"fresh artifact ({artifact_age_days}d) but no run decision trace",
            "artifact_age_days": artifact_age_days,
            "n_buys": None,
        }
    if n_buys == 0:
        return {
            "status": "warn",
            "reason": f"fresh artifact ({artifact_age_days}d) but last run was zero-buy / sell-only",
            "artifact_age_days": artifact_age_days,
            "n_buys": 0,
        }
    return {
        "status": "ok",
        "reason": f"fresh artifact ({artifact_age_days}d), last run produced {n_buys} buy(s)",
        "artifact_age_days": artifact_age_days,
        "n_buys": n_buys,
    }


def _artifact_age_days(artifact_path: str | Path | None, *, as_of: date) -> int | None:
    if artifact_path is None:
        return None
    p = Path(artifact_path)
    if not p.exists():
        return None
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).date()
    return max((as_of - mtime).days, 0)


def _is_buy(row: Mapping[str, Any]) -> bool:
    side = str(row.get("side") or row.get("action") or row.get("direction") or "").lower()
    if side in ("buy", "long"):
        return True
    qty = row.get("quantity", row.get("qty"))
    if side == "" and qty is not None:
        try:
            return float(qty) > 0
        except (TypeError, ValueError):
            return False
    return False


def _count_buys(
    decision_trace: list[Mapping[str, Any]] | None,
    submitted_orders: list[Mapping[str, Any]] | None,
) -> int | None:
    source = submitted_orders if submitted_orders is not None else decision_trace
    if source is None:
        return None
    return sum(1 for row in source if isinstance(row, Mapping) and _is_buy(row))


def build_cash_deployment_signal(
    snapshot: Mapping[str, Any] | None,
    *,
    n_buys: int | None,
    high_cash_fraction: float = HIGH_CASH_FRACTION,
) -> dict[str, Any]:
    """Invested % vs cash %; a high-cash + zero-buy day is the sell-only symptom."""
    if snapshot is None:
        return {"status": "unknown", "reason": "no account snapshot available"}
    try:
        portfolio_value = float(snapshot.get("portfolio_value"))
        cash = float(snapshot.get("cash"))
    except (TypeError, ValueError):
        return {"status": "unknown", "reason": "account snapshot missing cash/portfolio_value"}
    if portfolio_value <= 0:
        return {"status": "unknown", "reason": "portfolio_value <= 0; cannot compute deployment"}

    cash_fraction = cash / portfolio_value
    invested_fraction = max(0.0, 1.0 - cash_fraction)
    base = {
        "cash": cash,
        "portfolio_value": portfolio_value,
        "cash_fraction": round(cash_fraction, 4),
        "invested_fraction": round(invested_fraction, 4),
        "n_buys": n_buys,
    }
    high_cash = cash_fraction >= high_cash_fraction
    if high_cash and (n_buys == 0 or n_buys is None):
        return {
            **base,
            "status": "bad",
            "reason": (
                f"under-deployed: cash {cash_fraction:.0%} >= {high_cash_fraction:.0%} "
                f"with {0 if n_buys == 0 else 'no'} buys (sell-only symptom)"
            ),
        }
    if high_cash:
        return {
            **base,
            "status": "warn",
            "reason": f"high cash {cash_fraction:.0%} >= {high_cash_fraction:.0%} but {n_buys} buy(s) placed",
        }
    return {**base, "status": "ok", "reason": f"deployed {invested_fraction:.0%} of portfolio"}


# --- top-level builder -------------------------------------------------------

def build_daily_trading_health(
    *,
    run_id: str | None = None,
    as_of: str | None = None,
    broker_name: str = "readonly-alpaca",
    account_snapshot: Mapping[str, Any] | None = None,
    run_bundle: Mapping[str, Any] | None = None,
    run_bundle_path: str | Path | None = None,
    artifact_path: str | Path | None = None,
    snapshot_builder: Callable[..., dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> TradingHealthRecord:
    """Assemble the daily trading-health record from read-only inputs.

    Everything is optional and fail-soft: missing inputs degrade individual
    signals to ``unknown`` rather than raising. ``snapshot_builder`` defaults to
    the read-only :func:`native_live_snapshots.build_native_live_account_snapshot`
    but is injectable so tests never touch a real broker.
    """
    as_of_str = as_of or _today_iso(now)
    as_of_date = _parse_date(as_of_str) or _parse_date(_today_iso(now))
    assert as_of_date is not None  # _today_iso always parses

    bundle = dict(run_bundle) if run_bundle is not None else (_load_json(run_bundle_path) or {})
    if not isinstance(bundle, Mapping):
        bundle = {}
    resolved_run_id = run_id or str(bundle.get("run_id") or f"{as_of_str}-trading-health")

    if snapshot_builder is None:
        from .native_live_snapshots import build_native_live_account_snapshot

        snapshot_builder = build_native_live_account_snapshot

    snapshot = _account_snapshot(
        broker_name=broker_name,
        account_snapshot=account_snapshot if account_snapshot is not None else bundle.get("account_snapshot"),
        snapshot_builder=snapshot_builder,
    )

    submitted_orders = _as_list(bundle.get("submitted_orders"))
    decision_trace = _as_list(bundle.get("decision_trace"))

    account_trading = build_account_trading_signal(
        snapshot, submitted_orders, as_of=as_of_date,
    )
    n_buys = _count_buys(decision_trace, submitted_orders)
    model_health = build_model_health_signal(
        artifact_path=artifact_path,
        decision_trace=decision_trace,
        submitted_orders=submitted_orders,
        as_of=as_of_date,
    )
    cash_deployment = build_cash_deployment_signal(snapshot, n_buys=n_buys)

    record = TradingHealthRecord(
        as_of=as_of_str,
        run_id=resolved_run_id,
        account_trading=account_trading,
        model_health=model_health,
        cash_deployment=cash_deployment,
    )
    _decide_health(record)
    return record


def _as_list(value: Any) -> list[Mapping[str, Any]] | None:
    if isinstance(value, list):
        return [v for v in value if isinstance(v, Mapping)]
    return None


def _decide_health(record: TradingHealthRecord) -> None:
    """Roll the three signals into one verdict + alert. ``bad`` dominates; a lone
    ``warn`` is surfaced but not paged."""
    signals = {
        "account_trading": record.account_trading,
        "model_health": record.model_health,
        "cash_deployment": record.cash_deployment,
    }
    bad = [name for name, sig in signals.items() if sig.get("status") == "bad"]
    warn = [name for name, sig in signals.items() if sig.get("status") == "warn"]
    record.reasons = [
        f"{name}: {sig.get('reason')}"
        for name, sig in signals.items()
        if sig.get("status") in ("bad", "warn")
    ]

    if bad:
        record.health_verdict = "bad"
        record.alert_title = "RenQuant 104 TRADING-HEALTH"
        record.alert_body = "; ".join(
            f"{name}: {signals[name].get('reason')}" for name in bad
        )
    elif warn:
        record.health_verdict = "warn"
    elif all(sig.get("status") == "unknown" for sig in signals.values()):
        record.health_verdict = "unknown"
    else:
        record.health_verdict = "ok"


# --- persistence + alert sinks ----------------------------------------------

def persist_to_ledger(
    record: TradingHealthRecord,
    *,
    db_path: str | Path | None = None,
    conn: Any | None = None,
) -> int:
    """Append the daily trading-health verdicts to the decision ledger.

    This is the previously-unwired GateRegistry -> ledger bridge: every daily run
    now leaves a per-signal audit row keyed by (run_id, scope, gate). Returns the
    number of new rows. Pass ``conn=connect(':memory:')`` in tests.
    """
    from .decision_ledger import connect, write_verdicts

    owns_conn = conn is None
    if conn is None:
        conn = connect(db_path)
    try:
        return write_verdicts(conn, record.run_id, record.as_of, record.ledger_verdicts())
    finally:
        if owns_conn:
            conn.close()


def emit_alert(record: TradingHealthRecord, *, topic: str, quiet: bool = False) -> bool:
    """Page on a bad day, reusing the ntfy path. Returns whether an alert fired."""
    if record.alert_title and record.alert_body and not quiet:
        post_ntfy(record.alert_title, record.alert_body, topic)
        return True
    return False


# --- CLI ---------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD; defaults to today (UTC)")
    parser.add_argument("--broker-name", default="readonly-alpaca")
    parser.add_argument("--run-bundle", default=None, help="path to a daily run_bundle.json")
    parser.add_argument("--account-snapshot", default=None, help="path to an account snapshot JSON")
    parser.add_argument("--artifact-path", default=None, help="path to the live scorer artifact")
    parser.add_argument("--topic", default=os.environ.get("NTFY_TOPIC", "renquant"))
    parser.add_argument("--ledger-db", default=None, help="decision ledger DB path (default: shared prod DB)")
    parser.add_argument("--no-persist", action="store_true", help="skip writing to the decision ledger")
    parser.add_argument("--quiet", action="store_true", help="never send the ntfy alert")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    account_snapshot = _load_json(args.account_snapshot)
    record = build_daily_trading_health(
        run_id=args.run_id,
        as_of=args.as_of,
        broker_name=args.broker_name,
        account_snapshot=account_snapshot if isinstance(account_snapshot, Mapping) else None,
        run_bundle_path=args.run_bundle,
        artifact_path=args.artifact_path,
    )
    if not args.no_persist:
        try:
            persist_to_ledger(record, db_path=args.ledger_db)
        except Exception as exc:  # noqa: BLE001 — persistence must never wedge the report
            print(f"trading-health: ledger persist skipped ({exc})", file=sys.stderr)
    emit_alert(record, topic=args.topic, quiet=args.quiet)
    print(json.dumps(record.to_payload(), indent=2, sort_keys=True))
    return 2 if record.health_verdict == "bad" else 0


__all__ = [
    "HIGH_CASH_FRACTION",
    "MAX_DAYS_WITHOUT_ORDERS",
    "MAX_MODEL_ARTIFACT_AGE_DAYS",
    "TradingHealthRecord",
    "build_account_trading_signal",
    "build_cash_deployment_signal",
    "build_daily_trading_health",
    "build_model_health_signal",
    "emit_alert",
    "main",
    "persist_to_ledger",
    "post_ntfy",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
