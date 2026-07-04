"""renquant105 STAGE-2 live executor — built DARK behind the §9.3a quadruple gate.

Sprint D2 of the renquant105 build (RFC #208
``doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md``
§7/§9.3a/§10; companion design note
``doc/design/2026-07-03-stage2-live-executor.md``): the ``mode: "live"``
tick path the Stage-1 scheduler deliberately did not implement. ALL of the
code lands now; ENABLEMENT stays behind the pre-registered §9.3a
authorization — that separation is the module's core design, not an
afterthought.

**The quadruple authorization gate (§9.3a).** Live submission arms if and
only if ALL FOUR hold, evaluated independently every session
(:func:`resolve_stage2_arming`):

1. ``intraday_decisioning.mode == "live"`` in the PINNED strategy config
   (today strategy-104 pins ``mode == "shadow"`` in its own tests — flipping
   that pin is part of the future authorization act itself, not this PR);
2. a valid, unexpired, schema-checked authorization FILE
   (``data/rq105/stage2_authorization.json`` —
   :class:`Stage2Authorization`): ``{authorized_by, date, evidence:
   {shadow_sessions_clean >= 5, replay_audits_green, entry_timing_report},
   daily_entry_notional_cap, expiry}``;
3. the env flag ``RENQUANT_INTRADAY_LIVE=1``;
4. the kill-switch file ABSENT (same file the Stage-1 scheduler honors,
   re-checked every cycle).

ANY missing gate ⇒ the session runs SHADOW, exactly as today, and the
downgrade is COUNTED in the session manifest (``live_mode_downgraded_count``
+ the per-gate arming record). There is no partial arming.

**The live tick path** (:class:`LiveTickExecutor`): order INTENTS from the
slice-2 pipeline tick (renquant-pipeline ``intraday_decisioning`` — consumed
through the same normalized payload the shadow log records) are registered
as parent intents in slice 1's ``OrderStateBook``
(``renquant_execution.order_state_machine`` — consumed, never
reimplemented), submitted through ``renquant_execution.alpaca_broker_port
.AlpacaBrokerPort`` (broker adapters are owned there, injected here as the
CLI's default ``port_factory`` — never defined in this repo; client-order-id
= the slice-1 child id, DAY time-in-force, limit/market per the recorded
authorization), fills/cancels are reconciled back into the
book, and the book snapshot is persisted after every tick to
``data/rq105/order_state_book.json`` in slice 1's exact snapshot/restore
shape (state file under the operator data root — never canonical prod data,
never the umbrella git tree).

**Safety invariants, runtime-asserted (not docstring promises):**

- **Entry-notional cap:** the day's SUBMITTED entry notional can never
  exceed the authorization's ``daily_entry_notional_cap`` (default proposal
  $500) — pre-checked per intent AND hard-asserted
  (:func:`assert_entry_cap`, :class:`EntryCapExceededError`) around every
  BUY submit. The cap binds on GROSS submitted notional (canceled/rejected
  attempts still count — conservative and monotone, restart-safe because it
  is recomputed from the book). **Exits are NEVER capped.**
- **One open child per parent:** slice 1's ``OrderStateBook.submit_child``
  enforces it; this module routes every submission through the book and
  adds no second path.
- **Reconcile-before-emit on session start:** :meth:`LiveTickExecutor
  .begin_session` ALWAYS runs slice 1's ``reconcile_on_restart`` against
  broker open-orders (fresh book included) before any tick may submit; a
  tick before ``begin_session`` raises :class:`Stage2ContractError`. A
  reconcile mismatch halts entries for the session (exits continue).
- **Write-ahead action log:** every MUTATING broker call (submit/cancel) is
  journaled to ``logs/renquant105_pilot/intraday_live_actions.jsonl``
  BEFORE the call (flushed + fsync'd) and its outcome journaled after —
  the broker can never know about an order the journal does not.
- **Dead-man switch:** ``>= 3`` CONSECUTIVE broker rejects/errors halt
  entries for the rest of the session (:class:`DeadManSwitch`); exits
  continue to the bell (§10 exits-always-allowed).

Nothing in this module weakens the Stage-1 shadow path: the scheduler's
``resolve_mode`` downgrade, ``assert_shadow_never_submits`` runtime
assertion, and the shadow log are untouched, and the unarmed fallback here
delegates to that exact scheduler.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from renquant_artifacts import hash_jsonable
from renquant_execution.alpaca_broker_port import AlpacaBrokerPort
from renquant_execution.order_state_machine import (
    MAX_PENDING_AGE_SECONDS,
    BrokerPort,
    ChildOrderState,
    DuplicateChildOrderError,
    EconomicInvariantError,
    EntryBlockedError,
    LifecycleError,
    OrderStateBook,
    ParentIntent,
    ReconcileResult,
    SIDE_BUY,
    SIDE_SELL,
    reconcile_on_restart,
)

from .env_files import load_env_file
from .intraday_quote_logger import ET, SessionCalendar, _as_aware, default_session_calendar
from .intraday_session_inputs import (
    FrozenSignalError,
    SignalLeakError,
    assert_signal_predates_session,
    capture_session_start,
    live_state_fingerprint,
    verify_session_start,
)
from .intraday_session_scheduler import (
    MODE_LIVE,
    MODE_SHADOW,
    PHASE_CLOSED,
    PHASE_ENTRIES_OPEN,
    PHASE_EXITS_ONLY,
    IntradayDecisioningConfig,
    KillSwitch,
    SessionScheduler,
    SessionWindows,
    ShadowTickWriter,
    TickRunner,
    _ZERO_COUNTERS,
    _atomic_write_json,
    apply_entry_window_policy,
    bind_pipeline_tick_runner,
    default_kill_switch_path,
    default_manifest_path,
    default_shadow_log_path,
    load_intraday_config,
    normalize_tick_result,
)
from .runtime_paths import default_data_root, default_strategy_config_path

log = logging.getLogger("renquant.intraday_live_executor")

LIVE_EXECUTOR_SCHEMA_VERSION = "rq105-intraday-live-v1"
RECORD_KIND_LIVE_TICK = "intraday_live_tick"
RECORD_KIND_ACTION = "intraday_live_action"
STAGE2 = "renquant105-stage2-live-canary"

#: Gate 3 of the §9.3a quadruple gate. Distinct from the Stage-1 scheduler's
#: ``RENQUANT_INTRADAY_DECISIONING`` on purpose: arming SHADOW ticks and
#: arming LIVE submission are separate acts with separate flags.
ENV_LIVE_FLAG = "RENQUANT_INTRADAY_LIVE"
_ENV_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: §9.3a default PROPOSAL for the canary entry-notional cap. The value that
#: BINDS is always the one in the signed authorization file; this constant
#: only documents the proposed starting point.
DEFAULT_DAILY_ENTRY_NOTIONAL_CAP = 500.0

#: §9.3 K: the readonly/shadow-session evidence floor the authorization file
#: must attest to before it validates.
MIN_SHADOW_SESSIONS_CLEAN = 5

#: §9.3a duration cap ≈ one month: an authorization window longer than this
#: is structurally an indefinite production grant, so it fails validation.
MAX_AUTHORIZATION_WINDOW_DAYS = 31

#: Dead-man switch: consecutive broker rejects/errors that halt entries.
DEAD_MAN_CONSECUTIVE_FAILURES = 3

#: The four §9.3a gates, by name (manifest / test surface).
GATE_CONFIG_MODE_LIVE = "config_mode_live"
GATE_AUTHORIZATION_FILE = "authorization_file_valid"
GATE_ENV_LIVE_FLAG = "env_live_flag"
GATE_KILL_SWITCH_ABSENT = "kill_switch_absent"
ALL_GATES = (
    GATE_CONFIG_MODE_LIVE,
    GATE_AUTHORIZATION_FILE,
    GATE_ENV_LIVE_FLAG,
    GATE_KILL_SWITCH_ABSENT,
)

#: Skip reasons stamped by the live executor (audit surface).
REASON_ENTRY_CAP = "stage2_daily_entry_notional_cap"
REASON_ENTRIES_HALTED = "stage2_entries_halted"

_ORDER_TYPES = ("limit", "market")
_EPS = 1e-9

#: Broker order statuses treated as an acknowledgment of a live order.
_ACK_STATUSES = frozenset({"accepted", "new", "pending_new", "accepted_for_bidding"})
_CANCELED_STATUSES = frozenset({"canceled", "cancelled", "done_for_day"})


class Stage2AuthorizationError(ValueError):
    """The §9.3a authorization file is absent, malformed, or expired."""


class Stage2ContractError(RuntimeError):
    """A Stage-2 safety contract would be violated (fail loudly, never trade)."""


class EntryCapExceededError(Stage2ContractError):
    """The daily entry-notional cap would be exceeded (hard runtime assert)."""


# ---------------------------------------------------------------------------
# Default paths — state under the operator data root, never the git tree.
# ---------------------------------------------------------------------------
def default_authorization_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else default_data_root()
    return Path(root) / "data" / "rq105" / "stage2_authorization.json"


def default_order_state_book_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else default_data_root()
    return Path(root) / "data" / "rq105" / "order_state_book.json"


def default_live_actions_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "intraday_live_actions.jsonl"


def default_live_log_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else default_data_root()
    return Path(root) / "logs" / "renquant105_pilot" / "intraday_decisions_live.jsonl"


# ---------------------------------------------------------------------------
# §9.3a gate 2 — the signed authorization file, schema-validated.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Stage2Authorization:
    """The recorded §9.3a authorizing decision, as a validated artifact.

    This is the "operator explicitly accepts the economic risk in a
    SEPARATE, RECORDED decision" leg of §9.3a — a distinct decision
    artifact, never implied by Stage-1's operational PASS. The evidence
    block makes the file self-describing about WHAT was reviewed:
    ``shadow_sessions_clean`` (the §9.3 K >= 5 readonly sessions),
    ``replay_audits_green`` (the §6 replay harness verdict), and
    ``entry_timing_report`` (the entry-timing shadow readout reviewed).
    """

    authorized_by: str
    date: str
    expiry: str
    daily_entry_notional_cap: float
    shadow_sessions_clean: int
    replay_audits_green: bool
    entry_timing_report: str
    entry_order_type: str = "limit"
    exit_order_type: str = "market"
    limit_price_offset_bps: float = 0.0
    content_sha256: str = ""

    def to_manifest_record(self) -> dict[str, Any]:
        record = dataclasses.asdict(self)
        return record

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any], *, today: str
    ) -> "Stage2Authorization":
        """Validate the authorization schema; raise with EVERY violation."""
        errors: list[str] = []
        if not isinstance(payload, Mapping):
            raise Stage2AuthorizationError(
                f"authorization payload is not a JSON object: {type(payload)!r}"
            )

        authorized_by = str(payload.get("authorized_by") or "").strip()
        if not authorized_by:
            errors.append("authorized_by is required (the accountable human)")

        def _iso_date(key: str) -> str | None:
            raw = payload.get(key)
            try:
                return date_cls.fromisoformat(str(raw)).isoformat()
            except (TypeError, ValueError):
                errors.append(f"{key} must be an ISO date: {raw!r}")
                return None

        auth_date = _iso_date("date")
        expiry = _iso_date("expiry")
        if auth_date is not None and auth_date > str(today):
            errors.append(f"date {auth_date!r} is post-dated (today: {today})")
        if expiry is not None and expiry < str(today):
            errors.append(f"authorization expired {expiry!r} (today: {today})")
        if auth_date is not None and expiry is not None:
            window = (
                date_cls.fromisoformat(expiry) - date_cls.fromisoformat(auth_date)
            ).days
            if window > MAX_AUTHORIZATION_WINDOW_DAYS:
                errors.append(
                    f"authorization window {window}d exceeds the §9.3a "
                    f"~one-month canary duration cap "
                    f"({MAX_AUTHORIZATION_WINDOW_DAYS}d) — an open-ended "
                    "grant is production by inertia, not a canary"
                )

        cap_raw = payload.get("daily_entry_notional_cap")
        cap = 0.0
        try:
            cap = float(cap_raw)
        except (TypeError, ValueError):
            errors.append(f"daily_entry_notional_cap must be a number: {cap_raw!r}")
        else:
            if not cap > 0 or cap != cap or cap in (float("inf"), float("-inf")):
                errors.append(
                    f"daily_entry_notional_cap must be a positive finite "
                    f"notional: {cap_raw!r}"
                )

        evidence = payload.get("evidence")
        sessions = 0
        replay_green = False
        timing_report = ""
        if not isinstance(evidence, Mapping):
            errors.append(
                "evidence is required: {shadow_sessions_clean, "
                "replay_audits_green, entry_timing_report}"
            )
        else:
            raw_sessions = evidence.get("shadow_sessions_clean")
            try:
                sessions = int(raw_sessions)
            except (TypeError, ValueError):
                errors.append(
                    f"evidence.shadow_sessions_clean must be an integer: "
                    f"{raw_sessions!r}"
                )
            else:
                if sessions < MIN_SHADOW_SESSIONS_CLEAN:
                    errors.append(
                        f"evidence.shadow_sessions_clean={sessions} is below "
                        f"the §9.3 K={MIN_SHADOW_SESSIONS_CLEAN} floor"
                    )
            replay_green = evidence.get("replay_audits_green")
            if replay_green is not True:
                errors.append(
                    "evidence.replay_audits_green must be literally true "
                    f"(got {replay_green!r})"
                )
            timing_report = str(evidence.get("entry_timing_report") or "").strip()
            if not timing_report:
                errors.append(
                    "evidence.entry_timing_report is required (path/URI of "
                    "the reviewed entry-timing readout)"
                )

        order = payload.get("order") or {}
        entry_type = "limit"
        exit_type = "market"
        offset_bps = 0.0
        if not isinstance(order, Mapping):
            errors.append(f"order must be a mapping when present: {order!r}")
        else:
            entry_type = str(order.get("entry_order_type", "limit"))
            exit_type = str(order.get("exit_order_type", "market"))
            for key, value in (
                ("entry_order_type", entry_type),
                ("exit_order_type", exit_type),
            ):
                if value not in _ORDER_TYPES:
                    errors.append(f"order.{key} must be one of {_ORDER_TYPES}: {value!r}")
            raw_offset = order.get("limit_price_offset_bps", 0.0)
            try:
                offset_bps = float(raw_offset)
            except (TypeError, ValueError):
                errors.append(
                    f"order.limit_price_offset_bps must be a number: {raw_offset!r}"
                )
            else:
                if not 0 <= offset_bps <= 100:
                    errors.append(
                        f"order.limit_price_offset_bps must be within [0, 100]: "
                        f"{raw_offset!r}"
                    )

        if errors:
            raise Stage2AuthorizationError(
                "stage2_authorization.json failed schema validation: "
                + "; ".join(errors)
            )
        return cls(
            authorized_by=authorized_by,
            date=str(auth_date),
            expiry=str(expiry),
            daily_entry_notional_cap=cap,
            shadow_sessions_clean=sessions,
            replay_audits_green=True,
            entry_timing_report=timing_report,
            entry_order_type=entry_type,
            exit_order_type=exit_type,
            limit_price_offset_bps=offset_bps,
            content_sha256=hash_jsonable(dict(payload)),
        )


def load_stage2_authorization(
    path: str | Path, *, today: str
) -> Stage2Authorization:
    """Load + schema-validate the §9.3a authorization file (gate 2)."""
    p = Path(path)
    if not p.exists():
        raise Stage2AuthorizationError(f"authorization file absent: {p}")
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Stage2AuthorizationError(f"authorization file {p} unreadable: {exc}")
    if not isinstance(payload, dict):
        raise Stage2AuthorizationError(f"authorization file {p} is not a JSON object")
    return Stage2Authorization.from_payload(payload, today=today)


# ---------------------------------------------------------------------------
# The quadruple gate.
# ---------------------------------------------------------------------------
def live_env_flag_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Gate 3: ``RENQUANT_INTRADAY_LIVE`` truthy, default OFF."""
    env = os.environ if environ is None else environ
    return str(env.get(ENV_LIVE_FLAG, "")).strip().lower() in _ENV_TRUTHY


@dataclass(frozen=True)
class ArmDecision:
    """The §9.3a arming verdict for one session — every gate, every reason."""

    armed: bool
    mode_effective: str
    downgraded: bool  # config asked for live but the gates refused it
    gates: Mapping[str, bool]
    reasons: tuple[str, ...]
    authorization: Stage2Authorization | None = None

    def to_manifest_record(self) -> dict[str, Any]:
        return {
            "armed": self.armed,
            "mode_effective": self.mode_effective,
            "downgraded": self.downgraded,
            "gates": dict(self.gates),
            "reasons": list(self.reasons),
            "authorization": (
                self.authorization.to_manifest_record()
                if self.authorization is not None
                else None
            ),
        }


def resolve_stage2_arming(
    *,
    config: IntradayDecisioningConfig,
    authorization_path: str | Path,
    kill_switch: KillSwitch,
    environ: Mapping[str, str] | None = None,
    today: str,
) -> ArmDecision:
    """Evaluate the §9.3a quadruple gate. ANY missing gate ⇒ shadow (counted).

    All four gates are evaluated independently (no short-circuit) so the
    session manifest records the complete arming picture, not just the
    first failure.
    """
    reasons: list[str] = []

    config_live = (
        bool(config.enabled)
        and not config.config_errors
        and config.mode == MODE_LIVE
    )
    if not config_live:
        reasons.append(
            "gate 1 (config): intraday_decisioning must be enabled, "
            f"error-free, and mode='live' (mode={config.mode!r}, "
            f"enabled={config.enabled}, errors={list(config.config_errors)})"
        )

    authorization: Stage2Authorization | None = None
    try:
        authorization = load_stage2_authorization(authorization_path, today=today)
        auth_ok = True
    except Stage2AuthorizationError as exc:
        auth_ok = False
        reasons.append(f"gate 2 (authorization file): {exc}")

    env_ok = live_env_flag_enabled(environ)
    if not env_ok:
        reasons.append(f"gate 3 (env): {ENV_LIVE_FLAG} is not set truthy")

    kill_absent = not kill_switch.engaged()
    if not kill_absent:
        reasons.append(f"gate 4 (kill switch): {kill_switch.path} is present")

    gates = {
        GATE_CONFIG_MODE_LIVE: config_live,
        GATE_AUTHORIZATION_FILE: auth_ok,
        GATE_ENV_LIVE_FLAG: env_ok,
        GATE_KILL_SWITCH_ABSENT: kill_absent,
    }
    armed = all(gates.values())
    downgraded = config.mode == MODE_LIVE and not armed
    if downgraded:
        log.warning(
            "intraday mode='live' requested but the §9.3a quadruple gate "
            "refused it — DOWNGRADING to shadow (counted): %s",
            "; ".join(reasons),
        )
    return ArmDecision(
        armed=armed,
        mode_effective=MODE_LIVE if armed else MODE_SHADOW,
        downgraded=downgraded,
        gates=gates,
        reasons=tuple(reasons),
        authorization=authorization,
    )


# ---------------------------------------------------------------------------
# Write-ahead broker-action journal.
# ---------------------------------------------------------------------------
class LiveActionLog:
    """Append-only write-ahead journal of every MUTATING broker call.

    Contract: :meth:`write_ahead` is called (and its line flushed + fsync'd)
    BEFORE the broker call; :meth:`record_outcome` after. A crash between
    the two leaves a write-ahead line with no outcome — exactly the evidence
    the restart reconcile needs. GET reads are not journaled (they mutate
    nothing).
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _append(self, row: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def write_ahead(self, *, action: str, session_date: str, **fields: Any) -> str:
        action_id = f"la-{uuid.uuid4().hex[:16]}"
        self._append(
            {
                "schema_version": LIVE_EXECUTOR_SCHEMA_VERSION,
                "kind": RECORD_KIND_ACTION,
                "phase": "write_ahead",
                "action_id": action_id,
                "action": action,
                "session_date": session_date,
                "ts": datetime.now(timezone.utc).isoformat(),
                **fields,
            }
        )
        return action_id

    def record_outcome(self, action_id: str, *, status: str, **fields: Any) -> None:
        self._append(
            {
                "schema_version": LIVE_EXECUTOR_SCHEMA_VERSION,
                "kind": RECORD_KIND_ACTION,
                "phase": "outcome",
                "action_id": action_id,
                "status": status,
                "ts": datetime.now(timezone.utc).isoformat(),
                **fields,
            }
        )


# ---------------------------------------------------------------------------
# Dead-man switch — consecutive broker failures halt entries.
# ---------------------------------------------------------------------------
@dataclass
class DeadManSwitch:
    """Halt entries after N CONSECUTIVE broker rejects/errors (exits continue).

    ``tripped`` is sticky for the session; a later success resets only the
    consecutive counter, never the trip.
    """

    threshold: int = DEAD_MAN_CONSECUTIVE_FAILURES
    consecutive_failures: int = 0
    tripped: bool = False

    def record_failure(self) -> bool:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold:
            self.tripped = True
        return self.tripped

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def to_record(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "consecutive_failures": self.consecutive_failures,
            "tripped": self.tripped,
        }


# ---------------------------------------------------------------------------
# Entry-notional cap — recomputed from the book, hard-asserted.
# ---------------------------------------------------------------------------
def entry_notional_submitted(book: OrderStateBook) -> float:
    """GROSS submitted BUY notional for the session (Σ requested_qty × price).

    Deliberately counts canceled/rejected attempts too: the cap is a bound
    on how much entry intent the day may PUSH AT the broker, it is monotone
    non-decreasing, and it is restart-safe because it is recomputed from the
    persisted book instead of a side counter.
    """
    total = 0.0
    for parent in book.parents():
        if parent.side != SIDE_BUY:
            continue
        for child in parent.children:
            total += child.requested_qty * child.price
    return total


def assert_entry_cap(
    book: OrderStateBook, *, additional_notional: float, cap: float
) -> None:
    """Hard runtime assertion: a BUY submit may never push past the cap."""
    used = entry_notional_submitted(book)
    if used + float(additional_notional) > cap + _EPS:
        raise EntryCapExceededError(
            f"daily entry-notional cap breach: submitted {used:.2f} + "
            f"new {float(additional_notional):.2f} > cap {cap:.2f} "
            "(§9.3a — the cap binds entries; exits are never capped)"
        )


# ---------------------------------------------------------------------------
# The REAL broker adapter — owned by renquant-execution, never here (per
# CLAUDE.md "do not implement broker adapters here"). AlpacaBrokerPort lives
# in renquant_execution.alpaca_broker_port; this module only injects it as
# the CLI's default port_factory, behind the §9.3a quadruple gate.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# The live tick executor — intents → book → broker → book → snapshot.
# ---------------------------------------------------------------------------
class LiveTickExecutor:
    """One session's ``mode:"live"`` execution driver over slice 1's book.

    Consumes the SAME normalized tick payload the shadow log records, so
    live and shadow decisions are byte-comparable. All safety invariants are
    runtime-asserted here (module docstring); the slice-1 lifecycle
    invariants (one open child per parent, the §7 economic invariant,
    reconcile-before-emit after restore) are consumed from
    ``OrderStateBook``, never re-implemented.
    """

    def __init__(
        self,
        *,
        account: str,
        trading_day: str,
        port: BrokerPort,
        action_log: LiveActionLog,
        book_path: str | Path,
        authorization: Stage2Authorization,
        dead_man: DeadManSwitch | None = None,
    ) -> None:
        self.account = str(account)
        self.trading_day = str(trading_day)
        self.port = port
        self.action_log = action_log
        self.book_path = Path(book_path)
        self.authorization = authorization
        self.dead_man = dead_man or DeadManSwitch()
        self.book: OrderStateBook | None = None
        self.restored = False
        self._session_open = False

    # -- session lifecycle -----------------------------------------------------
    @property
    def cap(self) -> float:
        return float(self.authorization.daily_entry_notional_cap)

    def cap_state(self) -> dict[str, float]:
        used = entry_notional_submitted(self.book) if self.book is not None else 0.0
        return {
            "daily_entry_notional_cap": self.cap,
            "entry_notional_submitted": used,
            "remaining": max(0.0, self.cap - used),
        }

    def begin_session(self) -> dict[str, Any]:
        """Restore-or-create the book, then ALWAYS reconcile-before-emit.

        Runs slice 1's ``reconcile_on_restart`` even on a FRESH book: a
        broker open order the book does not know about is a mismatch that
        halts entries (exits continue) — a fresh state file is not evidence
        that the broker is quiet.
        """
        if self.book_path.exists():
            try:
                payload = json.loads(self.book_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise Stage2ContractError(
                    f"order-state book {self.book_path} unreadable: {exc}"
                )
            same_session = (
                str(payload.get("trading_day")) == self.trading_day
                and str(payload.get("account")) == self.account
            )
            if same_session:
                self.book = OrderStateBook.from_snapshot(payload)
                self.restored = True
            else:
                # A prior-session book: its DAY children cannot have carried
                # (§11b no-carry); start fresh — the reconcile below still
                # catches any broker order the fresh book does not know.
                log.warning(
                    "order-state book %s is for %s/%s, not %s/%s — starting "
                    "a fresh session book (reconcile still runs)",
                    self.book_path,
                    payload.get("account"),
                    payload.get("trading_day"),
                    self.account,
                    self.trading_day,
                )
        if self.book is None:
            self.book = OrderStateBook(account=self.account, trading_day=self.trading_day)
        result: ReconcileResult = reconcile_on_restart(self.book, self.port)
        self._session_open = True
        self._persist()
        return {
            "restored": self.restored,
            "reconcile_clean": result.clean,
            "mismatches": [dataclasses.asdict(m) for m in result.mismatches],
            "entries_halted": self.book.entries_halted,
            "halt_reason": self.book.halt_reason,
        }

    def _persist(self) -> None:
        """Persist the book in slice 1's exact snapshot/restore shape."""
        _atomic_write_json(self.book_path, self.book.to_snapshot())

    def _require_open(self) -> OrderStateBook:
        if not self._session_open or self.book is None:
            raise Stage2ContractError(
                "reconcile-before-emit: begin_session() must reconcile the "
                "book against broker open-orders before any tick may submit"
            )
        return self.book

    # -- broker interaction ----------------------------------------------------
    def _record_broker_failure(self, context: str) -> None:
        if self.dead_man.record_failure():
            book = self.book
            if book is not None and not book.entries_halted:
                book.halt_entries("dead_man_consecutive_broker_errors")
                log.error(
                    "DEAD-MAN: %d consecutive broker rejects/errors (last: %s) "
                    "— entries halted for the session; exits continue",
                    self.dead_man.consecutive_failures,
                    context,
                )

    def _submit_parent_remainder(
        self,
        parent: ParentIntent,
        *,
        now: datetime,
        reference_price: float,
        limit_price: float | None,
    ) -> dict[str, Any]:
        """One WAL-journaled child submission through book + port.

        Slice-1 invariants (one OPEN child per parent, the §7 economic
        assertion, entry-halt honoring) are enforced by ``submit_child``;
        the write-ahead line lands BEFORE the broker learns anything.
        """
        book = self._require_open()
        child = book.submit_child(
            parent.parent_intent_id,
            qty=parent.remaining_unsubmitted,
            price=reference_price,
            now=now,
        )
        side_u = parent.side
        order_type = (
            self.authorization.entry_order_type
            if side_u == SIDE_BUY
            else self.authorization.exit_order_type
        )
        action_id = self.action_log.write_ahead(
            action="submit_order",
            session_date=self.trading_day,
            client_order_id=child.child_order_id,
            parent_intent_id=parent.parent_intent_id,
            symbol=parent.symbol,
            side=side_u,
            qty=child.requested_qty,
            order_type=order_type,
            limit_price=limit_price,
            time_in_force="day",
            cap=self.cap_state(),
        )
        try:
            response = self.port.submit_order(
                client_order_id=child.child_order_id,
                symbol=parent.symbol,
                side=side_u,
                qty=child.requested_qty,
                limit_price=limit_price,
            )
        except Exception as exc:  # noqa: BLE001 — journaled, dead-man counted
            book.on_reject(child.child_order_id)
            self.action_log.record_outcome(
                action_id, status="error", error=f"{type(exc).__name__}: {exc}"
            )
            self._record_broker_failure(f"submit {child.child_order_id}: {exc}")
            return {
                "client_order_id": child.child_order_id,
                "symbol": parent.symbol,
                "side": side_u,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        status = str(response.get("status", "") or "submitted").lower()
        self.action_log.record_outcome(
            action_id, status=status, broker_response=dict(response)
        )
        if status == "rejected":
            book.on_reject(child.child_order_id)
            self._record_broker_failure(f"submit {child.child_order_id}: rejected")
        else:
            self.dead_man.record_success()
            if status in _ACK_STATUSES:
                book.on_broker_ack(child.child_order_id)
            immediate_fill = float(response.get("filled_qty", 0.0) or 0.0)
            if immediate_fill > _EPS:
                book.on_fill(child.child_order_id, immediate_fill)
        return {
            "client_order_id": child.child_order_id,
            "symbol": parent.symbol,
            "side": side_u,
            "qty": child.requested_qty,
            "status": status,
        }

    def _cancel_child(self, child_order_id: str, *, reason: str) -> dict[str, Any]:
        book = self._require_open()
        action_id = self.action_log.write_ahead(
            action="cancel_order",
            session_date=self.trading_day,
            client_order_id=child_order_id,
            reason=reason,
        )
        try:
            outcome = self.port.cancel_order(child_order_id)
        except Exception as exc:  # noqa: BLE001 — journaled, dead-man counted
            self.action_log.record_outcome(
                action_id, status="error", error=f"{type(exc).__name__}: {exc}"
            )
            self._record_broker_failure(f"cancel {child_order_id}: {exc}")
            return {"client_order_id": child_order_id, "status": "error"}
        status = str(outcome.get("status", "") or "canceled").lower()
        self.action_log.record_outcome(
            action_id, status=status, broker_response=dict(outcome)
        )
        self.dead_man.record_success()
        child = _find_child(book, child_order_id)
        delta = float(outcome.get("filled_qty", 0.0) or 0.0) - child.filled_qty
        if delta > _EPS:
            book.on_fill(child_order_id, delta)
        if child.state is not ChildOrderState.FILLED and child.is_open:
            book.on_cancel(child_order_id)
        return {"client_order_id": child_order_id, "status": status}

    def _cancel_stale(self, now: datetime) -> list[dict[str, Any]]:
        """§10 stale-pending watchdog: a tick never inherits an overdue order."""
        book = self._require_open()
        return [
            self._cancel_child(child.child_order_id, reason="stale_pending_watchdog")
            for child in book.mark_stale(
                now=now, max_age_seconds=MAX_PENDING_AGE_SECONDS
            )
        ]

    def _sync_open_children(self) -> list[dict[str, Any]]:
        """Reconcile fills/cancels/rejects back into the book (GET-only)."""
        book = self._require_open()
        events: list[dict[str, Any]] = []
        for child in list(book.open_children()):
            cid = child.child_order_id
            try:
                row = self.port.order_status(cid)
            except Exception as exc:  # noqa: BLE001 — a read failure leaves it open
                log.warning("order_status(%s) failed (%s) — left open", cid, exc)
                continue
            delta = float(row.get("filled_qty", 0.0) or 0.0) - child.filled_qty
            if delta > _EPS:
                book.on_fill(cid, delta)
            status = str(row.get("status", "")).lower()
            if child.state is ChildOrderState.FILLED:
                pass
            elif status in _CANCELED_STATUSES:
                book.on_cancel(cid)
            elif status == "expired":
                book.on_expire(cid)
            elif status == "rejected":
                book.on_reject(cid)
                self._record_broker_failure(f"poll {cid}: rejected")
            events.append({"client_order_id": cid, "status": status, "fill_delta": delta})
        return events

    # -- id lockstep guard -------------------------------------------------------
    def _register(self, intent: Mapping[str, Any], side: str) -> ParentIntent:
        book = self._require_open()
        parent = book.register_intent(
            symbol=str(intent.get("symbol", "")),
            side=side,
            signal_version=str(intent.get("signal_version", "")),
            target_qty=float(intent.get("quantity", 0.0)),
        )
        declared = str(intent.get("parent_intent_id", "") or "")
        if declared and declared != parent.parent_intent_id:
            # The pipeline's compute_parent_intent_id must be in BYTE-LOCKSTEP
            # with slice 1's — a drift here is the calibrator-fingerprint
            # triple-impl failure mode all over again. Halt loudly.
            raise Stage2ContractError(
                f"parent_intent_id lockstep violation for {parent.symbol} "
                f"{side}: pipeline={declared!r} != execution="
                f"{parent.parent_intent_id!r}"
            )
        return parent

    @staticmethod
    def _positive(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != number or number <= 0 or number in (float("inf"),):
            return None
        return number

    # -- the tick ---------------------------------------------------------------
    def process_tick(
        self, decisions: Mapping[str, Any], *, now: datetime
    ) -> dict[str, Any]:
        """The live tick: watchdog → sync → exits (never capped) → entries.

        Consumes the normalized decision payload (``normalize_tick_result``
        + ``apply_entry_window_policy`` output). Persists the book snapshot
        before returning, whatever happened.
        """
        book = self._require_open()
        submitted: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        try:
            stale = self._cancel_stale(now)
            sync = self._sync_open_children()

            intents = [dict(i) for i in decisions.get("intents") or ()]
            exits = [
                i for i in intents if str(i.get("side", "")).upper() == SIDE_SELL
            ]
            entries = [
                i for i in intents if str(i.get("side", "")).upper() == SIDE_BUY
            ]

            # -- exits FIRST: never capped, never halted (§10). --------------
            attempted: set[str] = set()
            for intent in exits:
                try:
                    parent = self._register(intent, SIDE_SELL)
                except (EconomicInvariantError, DuplicateChildOrderError):
                    raise
                except LifecycleError as exc:
                    skipped.append(_skip(intent, str(exc)))
                    continue
                if not book.can_emit_remainder(parent.parent_intent_id):
                    skipped.append(_skip(intent, "no_emittable_remainder"))
                    continue
                price = self._positive(intent.get("price"))
                attempted.add(parent.parent_intent_id)
                submitted.append(
                    self._submit_parent_remainder(
                        parent,
                        now=now,
                        # §11b: exits favor action; a missing quote only
                        # degrades the audit reservation reference, it never
                        # blocks the exit (reserved_cash ignores SELLs).
                        reference_price=price if price is not None else 1.0,
                        limit_price=price,
                    )
                )
            # Protective-exit remainder chase: a SELL parent with an
            # unsubmitted remainder and no open child (from an earlier tick)
            # is re-emitted every tick — exits-always-allowed favors action.
            # BUY remainders are deliberately NOT chased in the Stage-2
            # canary (conservative under the entry cap; see design note).
            for parent in book.parents():
                if parent.side != SIDE_SELL:
                    continue
                if parent.parent_intent_id in attempted:
                    continue
                if not book.can_emit_remainder(parent.parent_intent_id):
                    continue
                submitted.append(
                    self._submit_parent_remainder(
                        parent,
                        now=now,
                        reference_price=max(parent.children[-1].price, 1.0)
                        if parent.children
                        else 1.0,
                        limit_price=None,
                    )
                )

            # -- entries: halted? capped? then submit. ------------------------
            for intent in entries:
                if book.entries_halted:
                    skipped.append(
                        _skip(
                            intent,
                            REASON_ENTRIES_HALTED,
                            detail=book.halt_reason,
                        )
                    )
                    continue
                price = self._positive(intent.get("price"))
                qty = self._positive(intent.get("quantity"))
                if price is None or qty is None:
                    skipped.append(_skip(intent, "missing_entry_price_or_quantity"))
                    continue
                notional = qty * price
                cap_used = entry_notional_submitted(book)
                if cap_used + notional > self.cap + _EPS:
                    skipped.append(
                        _skip(
                            intent,
                            REASON_ENTRY_CAP,
                            detail=(
                                f"submitted {cap_used:.2f} + intent "
                                f"{notional:.2f} > cap {self.cap:.2f}"
                            ),
                        )
                    )
                    continue
                try:
                    parent = self._register(intent, SIDE_BUY)
                except (EconomicInvariantError, DuplicateChildOrderError):
                    raise
                except LifecycleError as exc:
                    skipped.append(_skip(intent, str(exc)))
                    continue
                if not book.can_emit_remainder(parent.parent_intent_id):
                    skipped.append(_skip(intent, "no_emittable_remainder"))
                    continue
                # HARD runtime assertion (defense in depth over the pre-check).
                assert_entry_cap(
                    book,
                    additional_notional=parent.remaining_unsubmitted * price,
                    cap=self.cap,
                )
                try:
                    submitted.append(
                        self._submit_parent_remainder(
                            parent,
                            now=now,
                            reference_price=price,
                            limit_price=price,
                        )
                    )
                except EntryBlockedError as exc:
                    skipped.append(_skip(intent, exc.reason))
                    continue
                # Post-condition: the invariant must hold AFTER the submit too.
                assert_entry_cap(book, additional_notional=0.0, cap=self.cap)
        finally:
            self._persist()
        return {
            "stale_cancels": stale,
            "sync_events": sync,
            "submitted": submitted,
            "skipped": skipped,
            "cap": self.cap_state(),
            "entries_halted": book.entries_halted,
            "halt_reason": book.halt_reason,
            "dead_man": self.dead_man.to_record(),
            "book_path": str(self.book_path),
        }

    def close_session(self, *, now: datetime) -> dict[str, Any]:
        """§11b DAY-only no-carry: close-cancel every open child, snapshot."""
        book = self._require_open()
        cancels = [
            self._cancel_child(child.child_order_id, reason="session_close_cancel")
            for child in list(book.open_children())
        ]
        self._sync_open_children()
        self._persist()
        self._session_open = False
        return {"close_cancels": cancels, "open_children": len(book.open_children())}


def _find_child(book: OrderStateBook, child_order_id: str) -> Any:
    for parent in book.parents():
        for child in parent.children:
            if child.child_order_id == child_order_id:
                return child
    raise Stage2ContractError(f"unknown child_order_id: {child_order_id!r}")


def _skip(intent: Mapping[str, Any], reason: str, *, detail: Any = None) -> dict[str, Any]:
    row = {
        "symbol": str(intent.get("symbol", "")),
        "side": str(intent.get("side", "")),
        "parent_intent_id": str(intent.get("parent_intent_id", "")),
        "reasons": [reason],
    }
    if detail is not None:
        row["detail"] = detail
    return row


# ---------------------------------------------------------------------------
# Live tick log — append-only, idempotent on (session_date, tick_index).
# ---------------------------------------------------------------------------
class LiveTickWriter:
    """Same discipline as the shadow writer, keyed for live tick records."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._seen = self._load_keys()

    def _load_keys(self) -> set[tuple[str, int]]:
        keys: set[tuple[str, int]] = set()
        if not self.path.exists():
            return keys
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("kind") != RECORD_KIND_LIVE_TICK:
                    continue
                keys.add((str(row.get("session_date")), int(row.get("tick_index", -1))))
        return keys

    def append(self, record: Mapping[str, Any]) -> bool:
        key = (str(record.get("session_date")), int(record.get("tick_index", -1)))
        if key in self._seen:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        self._seen.add(key)
        return True


# ---------------------------------------------------------------------------
# The live session runner — shadow fallback when ANY gate is missing.
# ---------------------------------------------------------------------------
@dataclass
class LiveSessionRunner:
    """Drive one session: quadruple-gated LIVE, else the Stage-1 SHADOW path.

    Everything nondeterministic is injected (calendar, clock, providers,
    tick runner, broker-port factory) exactly like the shadow scheduler, so
    tests run whole live sessions with a fake broker and no wall clock. The
    ``port_factory`` is only invoked AFTER the quadruple gate arms — an
    unarmed session can never construct a submitting client.
    """

    config: IntradayDecisioningConfig
    tick_runner: TickRunner
    signal_loader: Callable[[str], Mapping[str, Any]]
    session_start_provider: Callable[[str, datetime], Mapping[str, Any]]
    live_state_provider: Callable[..., Mapping[str, Any]]
    port_factory: Callable[[Stage2Authorization], BrokerPort]
    writer: LiveTickWriter
    shadow_log_path: Path
    manifest_path: Path
    kill_switch: KillSwitch
    authorization_path: Path
    actions_log_path: Path
    book_path: Path
    calendar: SessionCalendar | None = None
    exit_orders_provider: Callable[[datetime], Sequence[Mapping[str, Any]]] | None = None
    environ: Mapping[str, str] | None = None
    strategy_config_fingerprint: str = ""
    _manifest: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.calendar is None:
            self.calendar = default_session_calendar()

    # -- manifest ---------------------------------------------------------------
    def _init_manifest(self, session_date: str, arming: ArmDecision) -> None:
        self._manifest = {
            "schema_version": LIVE_EXECUTOR_SCHEMA_VERSION,
            "kind": "intraday_live_session_manifest",
            "stage": STAGE2,
            "session_date": session_date,
            "calendar_id": getattr(self.calendar, "name", "unknown"),
            "status": "starting",
            "mode_requested": self.config.mode,
            "mode_effective": arming.mode_effective,
            "live_mode_downgraded_count": 1 if arming.downgraded else 0,
            "stage2_arming": arming.to_manifest_record(),
            "config": self.config.to_manifest_record(),
            "strategy_config_fingerprint": self.strategy_config_fingerprint,
            "kill_switch_file": str(self.kill_switch.path),
            "kill_switch_engaged": False,
            "authorization_file": str(self.authorization_path),
            "actions_log": str(self.actions_log_path),
            "order_state_book": str(self.book_path),
            "live_log": str(self.writer.path),
            "tick_count": 0,
            "last_tick_at": None,
            "counters": dict(_ZERO_COUNTERS),
            "errors": [],
        }

    def _stamp(self, status: str, **extra: Any) -> dict[str, Any]:
        self._manifest["status"] = status
        self._manifest.update(extra)
        self._manifest["updated_at"] = datetime.now(ET).isoformat()
        _atomic_write_json(self.manifest_path, self._manifest)
        return dict(self._manifest)

    # -- shadow fallback ----------------------------------------------------------
    def _run_shadow_fallback(
        self,
        arming: ArmDecision,
        *,
        now_fn: Callable[[], datetime],
        sleep_fn: Callable[[float], None],
        max_cycles: int | None,
    ) -> dict[str, Any]:
        """ANY missing gate ⇒ the Stage-1 shadow scheduler, unchanged + counted."""
        scheduler = SessionScheduler(
            config=self.config,
            tick_runner=self.tick_runner,
            signal_loader=self.signal_loader,
            session_start_provider=self.session_start_provider,
            live_state_provider=self.live_state_provider,
            writer=ShadowTickWriter(self.shadow_log_path),
            manifest_path=self.manifest_path,
            kill_switch=self.kill_switch,
            calendar=self.calendar,
            exit_orders_provider=self.exit_orders_provider,
            environ=self.environ,
            strategy_config_fingerprint=self.strategy_config_fingerprint,
        )
        manifest = scheduler.run_session(
            now_fn=now_fn, sleep_fn=sleep_fn, max_cycles=max_cycles
        )
        manifest["stage2_arming"] = arming.to_manifest_record()
        manifest["live_mode_downgraded_count"] = max(
            int(manifest.get("live_mode_downgraded_count", 0) or 0),
            1 if arming.downgraded else 0,
        )
        _atomic_write_json(self.manifest_path, manifest)
        return manifest

    # -- the session --------------------------------------------------------------
    def run_session(
        self,
        *,
        now_fn: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        max_cycles: int | None = None,
    ) -> dict[str, Any]:
        now_fn = now_fn or (lambda: datetime.now(ET))
        now = now_fn()
        session_date = _as_aware(now).astimezone(ET).date().isoformat()

        arming = resolve_stage2_arming(
            config=self.config,
            authorization_path=self.authorization_path,
            kill_switch=self.kill_switch,
            environ=self.environ,
            today=session_date,
        )
        if not arming.armed:
            return self._run_shadow_fallback(
                arming, now_fn=now_fn, sleep_fn=sleep_fn, max_cycles=max_cycles
            )

        # ---- ARMED: the quadruple gate passed; run the live session. ----
        self._init_manifest(session_date, arming)
        bounds = self.calendar.session_bounds(_as_aware(now).astimezone(ET).date())
        if bounds is None:
            return self._stamp("non_session_day")
        windows = SessionWindows.from_bounds(bounds, self.config)
        self._manifest["windows"] = windows.to_record()

        try:
            signal = dict(self.signal_loader(session_date))
            assert_signal_predates_session(signal, session_date)
        except SignalLeakError as exc:
            return self._stamp("aborted_class_a_leak", errors=[str(exc)])
        except FrozenSignalError as exc:
            return self._stamp("aborted_class_a_unavailable", errors=[str(exc)])
        self._manifest["class_a"] = {
            "signal_version": signal.get("signal_version"),
            "as_of": signal.get("as_of"),
            "source_run_id": signal.get("source_run_id"),
            "score_content_sha256": signal.get("score_content_sha256"),
        }
        self._stamp("running")

        executor: LiveTickExecutor | None = None
        session_start: dict[str, Any] | None = None
        counters: dict[str, Any] = dict(_ZERO_COUNTERS)
        tick_index = 0
        cycles = 0
        status = "completed"

        while True:
            now = now_fn()
            if self.kill_switch.engaged():
                status = "halted_kill_switch"
                self._manifest["kill_switch_engaged"] = True
                break
            phase = windows.phase(now)
            if phase == PHASE_CLOSED:
                break
            if phase in (PHASE_ENTRIES_OPEN, PHASE_EXITS_ONLY):
                try:
                    live_state = dict(
                        self.live_state_provider(now=now, trading_day=session_date)
                    )
                    if executor is None:
                        executor = LiveTickExecutor(
                            account=str(live_state.get("account", "unknown")),
                            trading_day=session_date,
                            port=self.port_factory(arming.authorization),
                            action_log=LiveActionLog(self.actions_log_path),
                            book_path=self.book_path,
                            authorization=arming.authorization,
                        )
                        self._manifest["session_start_reconcile"] = (
                            executor.begin_session()
                        )
                    if session_start is None:
                        session_start = capture_session_start(
                            self.session_start_provider(session_date, now),
                            captured_at=_as_aware(now).astimezone(ET).isoformat(),
                        )
                        self._manifest["class_b"] = dict(session_start)
                    verify_session_start(session_start)
                    exit_orders = list(
                        self.exit_orders_provider(now)
                        if self.exit_orders_provider
                        else ()
                    )
                    in_flight = sorted(
                        {p.parent_intent_id for p in executor.book.parents()}
                        | set(live_state.get("in_flight_parent_intents") or ())
                    )
                    raw = self.tick_runner(
                        signal=signal,
                        session_start=session_start,
                        live_state=live_state,
                        session_counters=dict(counters),
                        in_flight_parent_intents=in_flight,
                        exit_orders=exit_orders,
                    )
                    decisions = apply_entry_window_policy(
                        normalize_tick_result(raw),
                        phase=phase,
                        counters_before=counters,
                    )
                    execution = executor.process_tick(decisions, now=now)
                    record = {
                        "schema_version": LIVE_EXECUTOR_SCHEMA_VERSION,
                        "kind": RECORD_KIND_LIVE_TICK,
                        "stage": STAGE2,
                        "session_date": session_date,
                        "tick_index": tick_index,
                        "tick_at": _as_aware(now).astimezone(ET).isoformat(),
                        "mode": MODE_LIVE,
                        "window_phase": phase,
                        "fingerprints": {
                            "signal_version": str(signal.get("signal_version", "")),
                            "gate_input_fingerprint": str(
                                session_start.get("gate_input_fingerprint", "")
                            ),
                            "live_state_sha256": live_state_fingerprint(live_state),
                            "strategy_config_fingerprint": self.strategy_config_fingerprint,
                            "authorization_sha256": arming.authorization.content_sha256,
                        },
                        "decisions": decisions,
                        "execution": execution,
                    }
                    self.writer.append(record)
                except Exception as exc:
                    self._stamp(
                        "halted_tick_error", errors=[f"{type(exc).__name__}: {exc}"]
                    )
                    raise
                counters = {
                    **_ZERO_COUNTERS,
                    **dict(decisions.get("counters") or counters),
                }
                tick_index += 1
                self._manifest["tick_count"] = tick_index
                self._manifest["last_tick_at"] = record["tick_at"]
                self._manifest["counters"] = dict(counters)
                self._manifest["cap"] = execution["cap"]
                self._manifest["entries_halted"] = execution["entries_halted"]
                self._manifest["dead_man"] = execution["dead_man"]
                self._stamp("running")
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                status = "stopped_max_cycles"
                break
            sleep_fn(self.config.tick_seconds)

        if executor is not None:
            try:
                self._manifest["session_close"] = executor.close_session(now=now_fn())
            except Exception as exc:  # noqa: BLE001 — close is best-effort, audited
                self._manifest.setdefault("errors", []).append(
                    f"close_session: {type(exc).__name__}: {exc}"
                )
        return self._stamp(status)


# ---------------------------------------------------------------------------
# CLI — same read-only wiring as the shadow scheduler + the live pieces.
# ---------------------------------------------------------------------------
def main(
    argv: Sequence[str] | None = None,
    *,
    tick_runner: TickRunner | None = None,
    live_state_provider: Callable[..., Mapping[str, Any]] | None = None,
    calendar: SessionCalendar | None = None,
    port_factory: Callable[[Stage2Authorization], BrokerPort] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="intraday-live-executor",
        description=(
            "renquant105 STAGE-2 live executor (RFC #208 §9.3a). Runs LIVE "
            "only behind the quadruple authorization gate; ANY missing gate "
            "runs the Stage-1 shadow scheduler instead (counted)."
        ),
    )
    parser.add_argument("--strategy-config", default=None, help="pinned strategy config JSON")
    parser.add_argument("--data-root", default=None, help="operator data root")
    parser.add_argument("--db", default=None, help="runs.alpaca.db path (read-only)")
    parser.add_argument("--out", default=None, help="live decisions JSONL path")
    parser.add_argument("--shadow-out", default=None, help="shadow decisions JSONL path")
    parser.add_argument("--manifest", default=None, help="session manifest JSON path")
    parser.add_argument(
        "--authorization-file",
        default=None,
        help="§9.3a stage2_authorization.json path (gate 2)",
    )
    parser.add_argument(
        "--order-state-file",
        default=None,
        help="slice-1 OrderStateBook snapshot path (state file)",
    )
    parser.add_argument("--actions-log", default=None, help="write-ahead actions JSONL")
    parser.add_argument(
        "--broker-env",
        choices=("paper", "live"),
        default="paper",
        help="Alpaca endpoint for the broker port (default paper)",
    )
    parser.add_argument(
        "--data-manifest", default=None, help="data manifest JSON for the pipeline tick"
    )
    parser.add_argument(
        "--artifact-manifest",
        default=None,
        help="artifact manifest JSON for the pipeline tick",
    )
    parser.add_argument("--env-file", default=None, help=".env with Alpaca credentials")
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="print the final manifest")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    if args.env_file:
        load_env_file(args.env_file)

    data_root = Path(args.data_root) if args.data_root else default_data_root()
    strategy_config_path = (
        Path(args.strategy_config) if args.strategy_config else default_strategy_config_path()
    )
    strategy_config = json.loads(Path(strategy_config_path).read_text(encoding="utf-8"))
    if not isinstance(strategy_config, dict):
        print(f"refusing to run: {strategy_config_path} is not a JSON object", flush=True)
        return 2
    config = load_intraday_config(strategy_config)

    cal = calendar or default_session_calendar()
    session_date = datetime.now(ET).date().isoformat()
    db_path = Path(args.db) if args.db else data_root / "data" / "runs.alpaca.db"
    kill_path = (
        Path(config.kill_switch_file)
        if config.kill_switch_file
        else default_kill_switch_path(data_root)
    )
    book_path = (
        Path(args.order_state_file)
        if args.order_state_file
        else default_order_state_book_path(data_root)
    )

    if tick_runner is None:
        if not (args.data_manifest and args.artifact_manifest):
            print(
                "refusing to run: --data-manifest and --artifact-manifest are "
                "required for the real pipeline tick (fail closed; RFC #208 §8)",
                flush=True,
            )
            return 2
        try:
            tick_runner = bind_pipeline_tick_runner(
                strategy_config=strategy_config,
                data_manifest=json.loads(Path(args.data_manifest).read_text(encoding="utf-8")),
                artifact_manifest=json.loads(
                    Path(args.artifact_manifest).read_text(encoding="utf-8")
                ),
            )
        except Exception as exc:  # noqa: BLE001 — fail closed with the reason
            print(f"refusing to run: {exc}", flush=True)
            return 2

    if live_state_provider is None:
        from .intraday_quote_logger import AlpacaQuoteSource, load_watchlist  # noqa: PLC0415
        from .intraday_session_inputs import AlpacaLiveStateSource  # noqa: PLC0415

        source = AlpacaLiveStateSource(
            quote_source=AlpacaQuoteSource(),
            tickers=load_watchlist(strategy_config_path),
            order_state_path=book_path,
            paper=args.broker_env != "live",
        )

        def live_state_provider(**kwargs: Any) -> Mapping[str, Any]:
            return source.snapshot(**kwargs)

    if port_factory is None:

        def port_factory(authorization: Stage2Authorization) -> BrokerPort:
            return AlpacaBrokerPort(
                paper=args.broker_env != "live",
                entry_order_type=authorization.entry_order_type,
                exit_order_type=authorization.exit_order_type,
                limit_price_offset_bps=authorization.limit_price_offset_bps,
            )

    from .intraday_session_inputs import load_frozen_daily_signal  # noqa: PLC0415

    def signal_loader(day: str) -> Mapping[str, Any]:
        return load_frozen_daily_signal(db_path=db_path, session_date=day, calendar=cal)

    def session_start_provider(day: str, now: datetime) -> Mapping[str, Any]:
        return {
            "session_date": day,
            "strategy_config_path": str(strategy_config_path),
            "watchlist": list(strategy_config.get("watchlist") or []),
            "canary_allowlist": list(config.canary_allowlist),
        }

    runner = LiveSessionRunner(
        config=config,
        tick_runner=tick_runner,
        signal_loader=signal_loader,
        session_start_provider=session_start_provider,
        live_state_provider=live_state_provider,
        port_factory=port_factory,
        writer=LiveTickWriter(Path(args.out) if args.out else default_live_log_path(data_root)),
        shadow_log_path=(
            Path(args.shadow_out) if args.shadow_out else default_shadow_log_path(data_root)
        ),
        manifest_path=(
            Path(args.manifest)
            if args.manifest
            else default_manifest_path(session_date, data_root)
        ),
        kill_switch=KillSwitch(kill_path),
        authorization_path=(
            Path(args.authorization_file)
            if args.authorization_file
            else default_authorization_path(data_root)
        ),
        actions_log_path=(
            Path(args.actions_log) if args.actions_log else default_live_actions_path(data_root)
        ),
        book_path=book_path,
        calendar=cal,
        strategy_config_fingerprint=hash_jsonable(strategy_config),
    )
    manifest = runner.run_session(max_cycles=args.max_cycles)
    if args.json:
        print(json.dumps(manifest, sort_keys=True, indent=2))
    ok_statuses = {
        "completed",
        "stopped_max_cycles",
        "non_session_day",
        "disabled_config",
        "disabled_env_flag",
    }
    return 0 if manifest.get("status") in ok_statuses else 1


__all__ = [
    "ALL_GATES",
    "ArmDecision",
    "DEAD_MAN_CONSECUTIVE_FAILURES",
    "DEFAULT_DAILY_ENTRY_NOTIONAL_CAP",
    "DeadManSwitch",
    "ENV_LIVE_FLAG",
    "EntryCapExceededError",
    "GATE_AUTHORIZATION_FILE",
    "GATE_CONFIG_MODE_LIVE",
    "GATE_ENV_LIVE_FLAG",
    "GATE_KILL_SWITCH_ABSENT",
    "LIVE_EXECUTOR_SCHEMA_VERSION",
    "LiveActionLog",
    "LiveSessionRunner",
    "LiveTickExecutor",
    "LiveTickWriter",
    "MAX_AUTHORIZATION_WINDOW_DAYS",
    "MIN_SHADOW_SESSIONS_CLEAN",
    "REASON_ENTRIES_HALTED",
    "REASON_ENTRY_CAP",
    "RECORD_KIND_ACTION",
    "RECORD_KIND_LIVE_TICK",
    "STAGE2",
    "Stage2Authorization",
    "Stage2AuthorizationError",
    "Stage2ContractError",
    "assert_entry_cap",
    "default_authorization_path",
    "default_live_actions_path",
    "default_live_log_path",
    "default_order_state_book_path",
    "entry_notional_submitted",
    "live_env_flag_enabled",
    "load_stage2_authorization",
    "main",
    "resolve_stage2_arming",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
