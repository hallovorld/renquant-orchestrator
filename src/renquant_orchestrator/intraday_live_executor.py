"""renquant105 STAGE-2 gate + state-book integration seam (dark, unarmable).

Sprint D2 of the renquant105 build (RFC #208
``doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md``
§7/§9.3a/§10; companion design note
``doc/design/2026-07-03-stage2-live-executor.md``). Round 2 (codex review):
this module SHRANK to the minimum orchestrator seam that can be exercised
end-to-end today — the §9.3a quadruple gate, the authorization contract,
and :class:`LiveTickExecutor` (which registers intents in slice 1's
``OrderStateBook`` and enforces the safety invariants below against an
injected fake broker port in tests). The session-driving loop that would
actually SCHEDULE and RUN a live session (``LiveSessionRunner`` + a CLI
entry point) was deferred, not merely dark-gated: shipping that machinery
now is design cost ahead of the §9.4 economic-authorization decision,
per codex's review, independent of whether it is reachable at runtime.
The full sketch is preserved in
``doc/design/2026-07-03-stage2-live-executor.md`` §"Deferred: session
runner" and in this PR's git history — it is not lost, just not shipped
as live code before that decision exists.

**The arming gate (§9.3a: the quadruple gate + the envelope gate).** Live
submission arms if and only if ALL FIVE hold, evaluated independently every
session (:func:`resolve_stage2_arming`):

1. ``intraday_decisioning.mode == "live"`` in the PINNED strategy config
   (today strategy-104 pins ``mode == "shadow"`` in its own tests — flipping
   that pin is part of the future authorization act itself, not this PR);
2. a valid, unexpired, schema-checked authorization FILE
   (``data/rq105/stage2_authorization.json`` —
   :class:`Stage2Authorization`): ``{authorized_by, date, evidence:
   {shadow_sessions_clean >= 5, replay_audits_green, entry_timing_report},
   daily_entry_notional_cap, canary_allowlist, max_cumulative_loss_usd,
   [max_live_sessions], expiry}``, consistent with any allowlist the pinned
   config declares (the authorization's list must be a SUBSET of it);
3. the env flag ``RENQUANT_INTRADAY_LIVE=1``;
4. the kill-switch file ABSENT (same file the Stage-1 scheduler honors,
   re-checked every cycle);
5. the §9.3a canary ENVELOPE still available (campaign A4, audit #296
   OR-3): the persisted per-authorization envelope state
   (``data/rq105/stage2_canary_state.json``) shows the cumulative loss
   budget NOT tripped and the live-session count BELOW the authorization's
   session ceiling. Envelope exhaustion ⇒ shadow (fail closed) until a NEW
   recorded authorization exists — §9.3a: never silent continuation, never
   automatic extension.

ANY missing gate ⇒ the session runs SHADOW, exactly as today, and the
downgrade is COUNTED in the session manifest (``live_mode_downgraded_count``
+ the per-gate arming record). There is no partial arming.

**The §9.3a canary envelope, ENFORCED (campaign A4 — audit #296 OR-3).**
The audit found the allowlist parsed and stamped but never enforced, and
the loss budget / session counter unimplemented. This module now enforces
all three, fail-closed:

- **Canary allowlist:** the authorization file MUST declare a non-empty
  ``canary_allowlist``. Absent, ``null``, and ``[]`` all FAIL validation:
  RFC #208 §9.3a/§10 define no unrestricted-canary mode (§10: "canary
  allowlist required"; §9.3a: "1–2 pre-declared names") — an unrestricted
  "canary" is watchlist-wide live trading, exactly the OR-3 risk. Entries
  are permitted ONLY for allowlisted symbols: a non-allowlisted BUY intent
  is skipped with the counted, journaled reason
  ``stage2_canary_allowlist``, pre-checked per intent AND hard-asserted
  (:func:`assert_canary_allowlist`) around every BUY submit. **Exits are
  NEVER blocked by the allowlist** (§10 exits-always-allowed — a position
  from before the canary can always be protected).
- **Cumulative loss budget:** the authorization's REQUIRED
  ``max_cumulative_loss_usd`` (§9.3a proposal: 1.5% of equity) bounds the
  realized + mark-to-market P&L of Stage-2-originated positions, tracked
  by :class:`CanaryEnvelopeTracker` from this executor's own fills and
  persisted across sessions. On breach the executor TRIPS: entries halt
  (sticky ACROSS sessions — §9.3a HARD halt, not a per-session pause),
  exits continue, and a CRITICAL ntfy fires.
- **Session ceiling:** live sessions are counted per authorization
  (``max_live_sessions``, default and hard cap
  ``MAX_CANARY_LIVE_SESSIONS = 20`` per §9.3a's "maximum canary DURATION")
  — the count is stamped into the action journal and every arming record;
  at the ceiling the envelope gate refuses to arm (fail-closed to shadow)
  until re-authorization.

The envelope state is keyed to the authorization file's content hash: a
NEW authorization file (a new recorded §9.3a decision) starts a fresh
envelope, and the exhausted one is archived inside the state file — the
§9.3a rule that extending the window is itself a decision requiring an
explicit recorded authorization, with the audit trail preserved.

**The live tick path** (:class:`LiveTickExecutor`): order INTENTS from the
slice-2 pipeline tick (renquant-pipeline ``intraday_decisioning`` — consumed
through the same normalized payload the shadow log records) are registered
as parent intents in slice 1's ``OrderStateBook``
(``renquant_execution.order_state_machine`` — consumed, never
reimplemented), submitted through an injected ``BrokerPort`` (the real
``renquant_execution.alpaca_broker_port.AlpacaBrokerPort`` in the deferred
session runner's sketch; a fake port in every test here — broker adapters
are owned in renquant-execution, never defined in this repo;
client-order-id = the slice-1 child id, DAY time-in-force, limit/market per
the recorded authorization), fills/cancels are reconciled back into the
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

import dataclasses
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from renquant_artifacts import hash_jsonable
from renquant_common.notify import send as _send_notification
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

from .intraday_session_scheduler import (
    MODE_LIVE,
    MODE_SHADOW,
    IntradayDecisioningConfig,
    KillSwitch,
    _atomic_write_json,
    apply_entry_window_policy,
    normalize_tick_result,
)
from .runtime_paths import default_data_root

log = logging.getLogger("renquant.intraday_live_executor")

LIVE_EXECUTOR_SCHEMA_VERSION = "rq105-intraday-live-v1"
RECORD_KIND_LIVE_TICK = "intraday_live_tick"
RECORD_KIND_ACTION = "intraday_live_action"
RECORD_KIND_ENVELOPE = "stage2_canary_envelope"
STAGE2 = "renquant105-stage2-live-canary"

CANARY_STATE_SCHEMA_VERSION = "rq105-stage2-canary-state-v1"

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

#: §9.3a "Maximum canary DURATION": 20 live canary sessions. Both the
#: default AND the hard cap on what an authorization file may declare —
#: a longer session grant is production by inertia, so it fails validation.
MAX_CANARY_LIVE_SESSIONS = 20

#: §9.3a proposed allowlist size ("1–2 pre-declared names"). NOT a hard cap
#: (the RFC marks the size an open operational question, §15.7) — a larger
#: explicitly-declared list validates but is warn-logged, because the
#: recorded authorization file is itself the §9.3a decision artifact.
PROPOSED_CANARY_ALLOWLIST_SIZE = 2

#: Plausible-symbol shape for canary_allowlist entries (after uppercasing).
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

#: Dead-man switch: consecutive broker rejects/errors that halt entries.
DEAD_MAN_CONSECUTIVE_FAILURES = 3

#: The §9.3a arming gates, by name (manifest / test surface): the original
#: quadruple gate + the campaign-A4 envelope gate (audit #296 OR-3).
GATE_CONFIG_MODE_LIVE = "config_mode_live"
GATE_AUTHORIZATION_FILE = "authorization_file_valid"
GATE_ENV_LIVE_FLAG = "env_live_flag"
GATE_KILL_SWITCH_ABSENT = "kill_switch_absent"
GATE_CANARY_ENVELOPE = "canary_envelope_available"
ALL_GATES = (
    GATE_CONFIG_MODE_LIVE,
    GATE_AUTHORIZATION_FILE,
    GATE_ENV_LIVE_FLAG,
    GATE_KILL_SWITCH_ABSENT,
    GATE_CANARY_ENVELOPE,
)

#: Skip reasons stamped by the live executor (audit surface).
REASON_ENTRY_CAP = "stage2_daily_entry_notional_cap"
REASON_ENTRIES_HALTED = "stage2_entries_halted"
REASON_NOT_ALLOWLISTED = "stage2_canary_allowlist"

#: Book halt reason stamped when the §9.3a cumulative loss budget trips.
HALT_REASON_LOSS_BUDGET = "stage2_cumulative_loss_budget"

#: ntfy topic for the CRITICAL loss-budget trip (house convention).
NTFY_TOPIC = "renquant"

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


def default_canary_state_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else default_data_root()
    return Path(root) / "data" / "rq105" / "stage2_canary_state.json"


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

    Campaign A4 (audit #296 OR-3) added the three §9.3a envelope fields:
    ``canary_allowlist`` (REQUIRED non-empty — absent/null/empty all fail
    closed; §9.3a defines no unrestricted-canary mode),
    ``max_cumulative_loss_usd`` (REQUIRED — the §9.3a cumulative loss
    budget, proposal 1.5% of equity), and ``max_live_sessions`` (optional,
    default and hard cap :data:`MAX_CANARY_LIVE_SESSIONS`).
    """

    authorized_by: str
    date: str
    expiry: str
    daily_entry_notional_cap: float
    shadow_sessions_clean: int
    replay_audits_green: bool
    entry_timing_report: str
    canary_allowlist: tuple[str, ...] = ()
    max_cumulative_loss_usd: float = 0.0
    max_live_sessions: int = MAX_CANARY_LIVE_SESSIONS
    entry_order_type: str = "limit"
    exit_order_type: str = "market"
    limit_price_offset_bps: float = 0.0
    content_sha256: str = ""

    def to_manifest_record(self) -> dict[str, Any]:
        record = dataclasses.asdict(self)
        record["canary_allowlist"] = list(self.canary_allowlist)
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

        # -- §9.3a canary allowlist (campaign A4): REQUIRED, non-empty. ------
        # Absent, null, and [] all fail closed: RFC #208 §10 says "canary
        # allowlist required" and §9.3a pre-declares 1-2 names — there is NO
        # unrestricted-canary mode to acknowledge, so no null bypass exists.
        allowlist: tuple[str, ...] = ()
        if "canary_allowlist" not in payload:
            errors.append(
                "canary_allowlist is required — the §9.3a canary envelope is "
                "constituted by pre-declared names (§10: 'canary allowlist "
                "required'); an authorization without one fails closed "
                "(audit #296 OR-3)"
            )
        elif payload.get("canary_allowlist") is None:
            errors.append(
                "canary_allowlist: null is not accepted — RFC #208 §9.3a/§10 "
                "define no unrestricted-canary mode; an unrestricted 'canary' "
                "is watchlist-wide live trading (audit #296 OR-3). Declare "
                "the explicit symbol list"
            )
        elif not isinstance(payload.get("canary_allowlist"), (list, tuple)):
            errors.append(
                "canary_allowlist must be a non-empty list of symbols: "
                f"{payload.get('canary_allowlist')!r}"
            )
        else:
            cleaned: list[str] = []
            for item in payload["canary_allowlist"]:
                sym = str(item or "").strip().upper()
                if not _SYMBOL_RE.match(sym):
                    errors.append(
                        f"canary_allowlist entry is not a plausible symbol: "
                        f"{item!r}"
                    )
                elif sym not in cleaned:
                    cleaned.append(sym)
            if not cleaned and not any(
                "canary_allowlist entry" in e for e in errors
            ):
                errors.append(
                    "canary_allowlist must not be empty — §9.3a requires "
                    "pre-declared names; an empty list is an unrestricted "
                    "grant, not a canary"
                )
            allowlist = tuple(sorted(cleaned))
            if len(allowlist) > PROPOSED_CANARY_ALLOWLIST_SIZE:
                log.warning(
                    "canary_allowlist has %d names — beyond the §9.3a "
                    "proposed 1-%d name canary envelope (validates, but make "
                    "sure this is a deliberate recorded decision)",
                    len(allowlist),
                    PROPOSED_CANARY_ALLOWLIST_SIZE,
                )

        # -- §9.3a cumulative loss budget (campaign A4): REQUIRED. -----------
        loss_raw = payload.get("max_cumulative_loss_usd")
        max_loss = 0.0
        if "max_cumulative_loss_usd" not in payload:
            errors.append(
                "max_cumulative_loss_usd is required — the §9.3a cumulative "
                "LOSS BUDGET (proposal: 1.5% of equity) must be declared in "
                "the recorded authorization (audit #296 OR-3)"
            )
        else:
            try:
                max_loss = float(loss_raw)
            except (TypeError, ValueError):
                errors.append(
                    f"max_cumulative_loss_usd must be a number: {loss_raw!r}"
                )
            else:
                if (
                    not max_loss > 0
                    or max_loss != max_loss
                    or max_loss in (float("inf"), float("-inf"))
                ):
                    errors.append(
                        "max_cumulative_loss_usd must be a positive finite "
                        f"USD amount (the loss MAGNITUDE): {loss_raw!r}"
                    )

        # -- §9.3a session ceiling (campaign A4): default AND hard cap 20. ---
        sessions_raw = payload.get("max_live_sessions", MAX_CANARY_LIVE_SESSIONS)
        max_sessions = MAX_CANARY_LIVE_SESSIONS
        if isinstance(sessions_raw, bool) or not isinstance(sessions_raw, int):
            errors.append(
                f"max_live_sessions must be an integer: {sessions_raw!r}"
            )
        elif not 1 <= sessions_raw <= MAX_CANARY_LIVE_SESSIONS:
            errors.append(
                f"max_live_sessions={sessions_raw} outside "
                f"[1, {MAX_CANARY_LIVE_SESSIONS}] — the §9.3a maximum canary "
                "DURATION is 20 live sessions; a longer grant is production "
                "by inertia, not a canary"
            )
        else:
            max_sessions = sessions_raw

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
            canary_allowlist=allowlist,
            max_cumulative_loss_usd=max_loss,
            max_live_sessions=max_sessions,
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
# §9.3a canary envelope — loss budget + session counter, persisted per
# authorization (campaign A4, audit #296 OR-3).
# ---------------------------------------------------------------------------
def _load_canary_state_payload(path: Path) -> dict[str, Any] | None:
    """Read the persisted envelope state; corrupt state fails LOUDLY.

    A corrupt/unreadable state file must never silently reset to a fresh
    envelope — that would forget an accumulated loss. Absent file ⇒ ``None``
    (a genuinely fresh envelope: nothing has ever run under it).
    """
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Stage2ContractError(
            f"stage2 canary state {path} unreadable ({exc}) — refusing to "
            "silently reset the §9.3a loss/session envelope"
        )
    if not isinstance(payload, dict):
        raise Stage2ContractError(
            f"stage2 canary state {path} is not a JSON object — refusing to "
            "silently reset the §9.3a loss/session envelope"
        )
    return payload


class CanaryEnvelopeTracker:
    """The persisted §9.3a canary envelope: loss budget + session counter.

    State lives in ``data/rq105/stage2_canary_state.json`` (operator data
    root, never the git tree), keyed to the authorization file's content
    hash. A NEW authorization (new recorded §9.3a decision) starts a fresh
    envelope; the superseded one is archived in ``previous_envelopes``.

    P&L accounting is deliberately simple and self-contained: it tracks
    ONLY Stage-2-originated positions from this executor's own fills
    (average-cost basis; SELL fills realize against it; SELL quantity
    beyond the tracked position — an exit of a pre-Stage-2 position — is
    NOT canary-attributable and contributes zero). Mark-to-market uses the
    latest observed price per symbol (intent prices, ``marks``/``quotes``
    in the tick payload, and fill prices). Fill prices prefer the broker
    row's ``fill_price``/``filled_avg_price`` when present and fall back
    to the child's limit/reference price.
    """

    def __init__(
        self, path: str | Path, *, authorization: Stage2Authorization
    ) -> None:
        self.path = Path(path)
        self.authorization = authorization
        self.sessions: list[str] = []
        self.positions: dict[str, dict[str, float]] = {}
        self.realized_pnl_usd = 0.0
        self.last_marks: dict[str, float] = {}
        self.loss_budget_tripped = False
        self.trip_reason: str | None = None
        self.previous_envelopes: list[dict[str, Any]] = []
        payload = _load_canary_state_payload(self.path)
        if payload is None:
            return
        self.previous_envelopes = [
            dict(row) for row in payload.get("previous_envelopes") or ()
        ]
        recorded_sha = str(payload.get("authorization_sha256", ""))
        if recorded_sha != authorization.content_sha256:
            # A new recorded §9.3a decision ⇒ a fresh envelope. Archive the
            # exhausted one — the audit trail must survive the reset.
            archived = {
                key: payload.get(key)
                for key in (
                    "authorization_sha256",
                    "sessions",
                    "positions",
                    "realized_pnl_usd",
                    "last_marks",
                    "loss_budget_tripped",
                    "trip_reason",
                )
            }
            archived["archived_at"] = datetime.now(timezone.utc).isoformat()
            self.previous_envelopes.append(archived)
            log.warning(
                "stage2 canary state %s was for authorization %s, not %s — "
                "starting a FRESH §9.3a envelope (previous one archived)",
                self.path,
                recorded_sha[:12],
                authorization.content_sha256[:12],
            )
            self._persist()
            return
        try:
            self.sessions = sorted(
                {str(d) for d in payload.get("sessions") or ()}
            )
            self.positions = {
                str(sym): {
                    "qty": float(row["qty"]),
                    "cost_basis": float(row["cost_basis"]),
                }
                for sym, row in (payload.get("positions") or {}).items()
            }
            self.realized_pnl_usd = float(payload.get("realized_pnl_usd", 0.0))
            self.last_marks = {
                str(sym): float(px)
                for sym, px in (payload.get("last_marks") or {}).items()
            }
            self.loss_budget_tripped = bool(
                payload.get("loss_budget_tripped", False)
            )
            raw_reason = payload.get("trip_reason")
            self.trip_reason = str(raw_reason) if raw_reason is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            raise Stage2ContractError(
                f"stage2 canary state {self.path} malformed ({exc}) — "
                "refusing to silently reset the §9.3a loss/session envelope"
            )

    # -- persistence ---------------------------------------------------------
    def _persist(self) -> None:
        _atomic_write_json(
            self.path,
            {
                "schema_version": CANARY_STATE_SCHEMA_VERSION,
                "authorization_sha256": self.authorization.content_sha256,
                "sessions": list(self.sessions),
                "positions": self.positions,
                "realized_pnl_usd": self.realized_pnl_usd,
                "last_marks": self.last_marks,
                "loss_budget_tripped": self.loss_budget_tripped,
                "trip_reason": self.trip_reason,
                "previous_envelopes": self.previous_envelopes,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # -- session counter -------------------------------------------------------
    @property
    def sessions_used(self) -> int:
        return len(self.sessions)

    @property
    def max_live_sessions(self) -> int:
        return int(self.authorization.max_live_sessions)

    def begin_live_session(self, session_date: str) -> None:
        """Count one live session (idempotent per date), persisted.

        Raises :class:`Stage2ContractError` if a NEW session would exceed
        the §9.3a ceiling — the arming gate refuses first; this is the
        defense-in-depth backstop.
        """
        day = str(session_date)
        if day in self.sessions:
            return  # a restart of an already-counted session
        if self.sessions_used >= self.max_live_sessions:
            raise Stage2ContractError(
                f"§9.3a session ceiling: {self.sessions_used} live sessions "
                f"already used of max {self.max_live_sessions} — "
                "re-authorization required (never silent continuation)"
            )
        self.sessions = sorted({*self.sessions, day})
        self._persist()

    # -- P&L accounting --------------------------------------------------------
    def observe_price(self, symbol: str, price: float) -> None:
        sym = str(symbol).upper()
        try:
            px = float(price)
        except (TypeError, ValueError):
            return
        if px > 0 and px == px and px != float("inf"):
            self.last_marks[sym] = px

    def record_fill(self, *, symbol: str, side: str, qty: float, price: float) -> None:
        sym = str(symbol).upper()
        qty = float(qty)
        price = float(price)
        if qty <= 0 or price <= 0:
            return
        self.observe_price(sym, price)
        position = self.positions.get(sym)
        if side == SIDE_BUY:
            if position is None:
                self.positions[sym] = {"qty": qty, "cost_basis": price}
            else:
                total = position["qty"] + qty
                position["cost_basis"] = (
                    position["qty"] * position["cost_basis"] + qty * price
                ) / total
                position["qty"] = total
        else:
            if position is None:
                # An exit of a position the canary did not originate: not
                # canary-attributable P&L (it belongs to the batch book).
                return
            matched = min(qty, position["qty"])
            self.realized_pnl_usd += (price - position["cost_basis"]) * matched
            position["qty"] -= matched
            if position["qty"] <= _EPS:
                del self.positions[sym]
        self._persist()

    def unrealized_pnl_usd(self) -> float:
        total = 0.0
        for sym, position in self.positions.items():
            mark = self.last_marks.get(sym, position["cost_basis"])
            total += (mark - position["cost_basis"]) * position["qty"]
        return total

    def cumulative_pnl(self) -> dict[str, float]:
        unrealized = self.unrealized_pnl_usd()
        return {
            "realized_pnl_usd": self.realized_pnl_usd,
            "unrealized_pnl_usd": unrealized,
            "total_pnl_usd": self.realized_pnl_usd + unrealized,
        }

    # -- the budget check --------------------------------------------------------
    def evaluate_budget(self) -> dict[str, Any]:
        """Evaluate the §9.3a cumulative loss budget; the trip is STICKY.

        Once tripped, the envelope stays tripped across sessions and
        restarts (persisted) — §9.3a envelope-exhaustion is a HARD halt of
        the canary window, never a per-session pause. Only a NEW recorded
        authorization (fresh envelope) clears it.
        """
        pnl = self.cumulative_pnl()
        budget = float(self.authorization.max_cumulative_loss_usd)
        newly_tripped = False
        if not self.loss_budget_tripped and pnl["total_pnl_usd"] <= -budget:
            self.loss_budget_tripped = True
            self.trip_reason = (
                f"cumulative canary P&L {pnl['total_pnl_usd']:.2f} USD "
                f"breached the §9.3a loss budget -{budget:.2f} USD "
                f"(realized {pnl['realized_pnl_usd']:.2f}, unrealized "
                f"{pnl['unrealized_pnl_usd']:.2f})"
            )
            newly_tripped = True
            self._persist()
        return {
            "tripped": self.loss_budget_tripped,
            "newly_tripped": newly_tripped,
            "trip_reason": self.trip_reason,
            "max_cumulative_loss_usd": budget,
            **pnl,
        }

    # -- audit surface -------------------------------------------------------------
    def to_record(self) -> dict[str, Any]:
        return {
            "authorization_sha256": self.authorization.content_sha256,
            "state_path": str(self.path),
            "sessions_used": self.sessions_used,
            "max_live_sessions": self.max_live_sessions,
            "sessions_remaining": max(
                0, self.max_live_sessions - self.sessions_used
            ),
            "loss_budget_tripped": self.loss_budget_tripped,
            "trip_reason": self.trip_reason,
            "max_cumulative_loss_usd": float(
                self.authorization.max_cumulative_loss_usd
            ),
            "open_positions": {
                sym: dict(row) for sym, row in self.positions.items()
            },
            **self.cumulative_pnl(),
        }


def read_canary_envelope(
    path: str | Path, *, authorization: Stage2Authorization
) -> dict[str, Any]:
    """READ-ONLY §9.3a envelope view for the arming gate (no writes).

    Absent state, or state recorded under a DIFFERENT authorization hash,
    is a fresh envelope: 0 sessions used, budget not tripped. Corrupt state
    raises :class:`Stage2ContractError` (the arming gate fails closed).
    """
    p = Path(path)
    payload = _load_canary_state_payload(p)
    if payload is None or (
        str(payload.get("authorization_sha256", ""))
        != authorization.content_sha256
    ):
        sessions_used = 0
        tripped = False
        trip_reason = None
    else:
        sessions_used = len({str(d) for d in payload.get("sessions") or ()})
        tripped = bool(payload.get("loss_budget_tripped", False))
        raw_reason = payload.get("trip_reason")
        trip_reason = str(raw_reason) if raw_reason is not None else None
    return {
        "state_path": str(p),
        "authorization_sha256": authorization.content_sha256,
        "sessions_used": sessions_used,
        "max_live_sessions": int(authorization.max_live_sessions),
        "sessions_remaining": max(
            0, int(authorization.max_live_sessions) - sessions_used
        ),
        "loss_budget_tripped": tripped,
        "trip_reason": trip_reason,
        "max_cumulative_loss_usd": float(
            authorization.max_cumulative_loss_usd
        ),
    }


# ---------------------------------------------------------------------------
# CRITICAL notification seam (loss-budget trip). Injectable for tests; the
# default posts to ntfy (house convention) and honors RENQUANT_NO_NOTIFY.
# ---------------------------------------------------------------------------
def post_critical_ntfy(title: str, body: str) -> None:
    # Canonical sender (campaign B6): RENQUANT_NO_NOTIFY suppression + the
    # never-raise guarantee now live in renquant_common.notify. Notification is
    # best-effort; the halt itself never depends on it.
    _send_notification(title, body, NTFY_TOPIC, priority=5, tags="rotating_light")


# ---------------------------------------------------------------------------
# The arming gate (quadruple gate + envelope gate).
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
    envelope: Mapping[str, Any] | None = None

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
            "envelope": dict(self.envelope) if self.envelope is not None else None,
        }


def resolve_stage2_arming(
    *,
    config: IntradayDecisioningConfig,
    authorization_path: str | Path,
    canary_state_path: str | Path,
    kill_switch: KillSwitch,
    environ: Mapping[str, str] | None = None,
    today: str,
) -> ArmDecision:
    """Evaluate the §9.3a arming gate. ANY missing gate ⇒ shadow (counted).

    All gates are evaluated independently (no short-circuit) so the session
    manifest records the complete arming picture, not just the first
    failure. Gate 5 (the campaign-A4 envelope gate) necessarily depends on
    gate 2's authorization identity: without a schema-valid authorization
    there is no envelope to evaluate, so it fails closed.
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

    # Allowlist CONSISTENCY (still gate 2 — authorization validity): when the
    # pinned config also declares a canary allowlist, the authorization's
    # must be a subset of it. Two declared allowlists that disagree are an
    # ambiguous envelope — ambiguity fails closed.
    if authorization is not None and config.canary_allowlist:
        config_set = {str(s).upper() for s in config.canary_allowlist}
        extra = sorted(set(authorization.canary_allowlist) - config_set)
        if extra:
            auth_ok = False
            reasons.append(
                "gate 2 (authorization file): canary_allowlist disagrees "
                f"with the pinned config's — {extra} authorized but not in "
                f"the config allowlist {sorted(config_set)}; two declared "
                "allowlists must agree (the authorization's must be a "
                "subset) — ambiguity fails closed"
            )

    env_ok = live_env_flag_enabled(environ)
    if not env_ok:
        reasons.append(f"gate 3 (env): {ENV_LIVE_FLAG} is not set truthy")

    kill_absent = not kill_switch.engaged()
    if not kill_absent:
        reasons.append(f"gate 4 (kill switch): {kill_switch.path} is present")

    # Gate 5 — the §9.3a envelope (campaign A4, audit #296 OR-3): loss
    # budget not tripped, session count below the ceiling.
    envelope: dict[str, Any] | None = None
    envelope_ok = False
    if authorization is None:
        reasons.append(
            "gate 5 (canary envelope): cannot evaluate the §9.3a envelope "
            "without a schema-valid authorization (fails closed)"
        )
    else:
        try:
            envelope = read_canary_envelope(
                canary_state_path, authorization=authorization
            )
        except Stage2ContractError as exc:
            reasons.append(f"gate 5 (canary envelope): {exc}")
        else:
            envelope_ok = True
            if envelope["loss_budget_tripped"]:
                envelope_ok = False
                reasons.append(
                    "gate 5 (canary envelope): §9.3a cumulative loss budget "
                    f"TRIPPED ({envelope['trip_reason']}) — HARD halt; a new "
                    "recorded authorization is required (never silent "
                    "continuation)"
                )
            if envelope["sessions_used"] >= envelope["max_live_sessions"]:
                envelope_ok = False
                reasons.append(
                    "gate 5 (canary envelope): §9.3a session ceiling reached "
                    f"({envelope['sessions_used']} of "
                    f"{envelope['max_live_sessions']} live sessions used) — "
                    "re-authorization required (never automatic extension)"
                )

    gates = {
        GATE_CONFIG_MODE_LIVE: config_live,
        GATE_AUTHORIZATION_FILE: auth_ok,
        GATE_ENV_LIVE_FLAG: env_ok,
        GATE_KILL_SWITCH_ABSENT: kill_absent,
        GATE_CANARY_ENVELOPE: envelope_ok,
    }
    armed = all(gates.values())
    downgraded = config.mode == MODE_LIVE and not armed
    if downgraded:
        log.warning(
            "intraday mode='live' requested but the §9.3a arming gate "
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
        envelope=envelope,
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

    def stamp_envelope(
        self, *, session_date: str, phase: str, envelope: Mapping[str, Any]
    ) -> None:
        """§9.3a envelope audit row (session count / budget trip) — an
        append-only journal stamp, NOT a write-ahead line (it precedes no
        broker call)."""
        self._append(
            {
                "schema_version": LIVE_EXECUTOR_SCHEMA_VERSION,
                "kind": RECORD_KIND_ENVELOPE,
                "phase": phase,
                "session_date": session_date,
                "ts": datetime.now(timezone.utc).isoformat(),
                "envelope": dict(envelope),
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


def assert_canary_allowlist(
    symbol: str, *, side: str, allowlist: tuple[str, ...] | frozenset[str]
) -> None:
    """Hard runtime assertion: a BUY submit is ONLY for allowlisted symbols.

    Defense in depth over the per-intent pre-check (campaign A4, audit #296
    OR-3). Exits are deliberately exempt (§10 exits-always-allowed): the
    allowlist bounds what the canary may ORIGINATE, never what it may
    protect.
    """
    if side == SIDE_BUY and str(symbol).upper() not in {
        str(s).upper() for s in allowlist
    }:
        raise Stage2ContractError(
            f"canary allowlist breach: BUY {symbol!r} is not in the §9.3a "
            f"authorized allowlist {sorted(str(s) for s in allowlist)}"
        )


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
        canary_state_path: str | Path,
        dead_man: DeadManSwitch | None = None,
        notify: Callable[[str, str], None] | None = None,
    ) -> None:
        self.account = str(account)
        self.trading_day = str(trading_day)
        self.port = port
        self.action_log = action_log
        self.book_path = Path(book_path)
        self.authorization = authorization
        self.canary = CanaryEnvelopeTracker(
            canary_state_path, authorization=authorization
        )
        self.notify = notify if notify is not None else post_critical_ntfy
        self.dead_man = dead_man or DeadManSwitch()
        self.book: OrderStateBook | None = None
        self.restored = False
        self._session_open = False

    # -- session lifecycle -----------------------------------------------------
    @property
    def cap(self) -> float:
        return float(self.authorization.daily_entry_notional_cap)

    @property
    def allowlist(self) -> frozenset[str]:
        return frozenset(self.authorization.canary_allowlist)

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
        # §9.3a session counter (campaign A4): an armed live session consumes
        # one envelope slot (idempotent per date), stamped in the journal.
        self.canary.begin_live_session(self.trading_day)
        # A STICKY loss-budget trip halts entries in every later session of
        # this envelope, fresh book or not (§9.3a HARD halt; exits continue).
        if self.canary.loss_budget_tripped and not self.book.entries_halted:
            self.book.halt_entries(HALT_REASON_LOSS_BUDGET)
        self.action_log.stamp_envelope(
            session_date=self.trading_day,
            phase="session_begin",
            envelope=self.canary.to_record(),
        )
        self._session_open = True
        self._persist()
        return {
            "restored": self.restored,
            "reconcile_clean": result.clean,
            "mismatches": [dataclasses.asdict(m) for m in result.mismatches],
            "entries_halted": self.book.entries_halted,
            "halt_reason": self.book.halt_reason,
            "canary_envelope": self.canary.to_record(),
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
        # HARD runtime assertion (campaign A4): every BUY that reaches the
        # broker is allowlisted — defense in depth over the per-intent check.
        assert_canary_allowlist(
            parent.symbol, side=parent.side, allowlist=self.allowlist
        )
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
                self.canary.record_fill(
                    symbol=parent.symbol,
                    side=side_u,
                    qty=immediate_fill,
                    price=_row_fill_price(response) or child.price,
                )
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
        parent, child = _child_parent(book, child_order_id)
        delta = float(outcome.get("filled_qty", 0.0) or 0.0) - child.filled_qty
        if delta > _EPS:
            book.on_fill(child_order_id, delta)
            self.canary.record_fill(
                symbol=parent.symbol,
                side=parent.side,
                qty=delta,
                price=_row_fill_price(outcome) or child.price,
            )
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
                fill_parent, _ = _child_parent(book, cid)
                self.canary.record_fill(
                    symbol=fill_parent.symbol,
                    side=fill_parent.side,
                    qty=delta,
                    price=_row_fill_price(row) or child.price,
                )
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

    # -- loss-budget trip --------------------------------------------------------
    def _evaluate_loss_budget(self) -> dict[str, Any]:
        """§9.3a budget check; a fresh trip halts entries + fires CRITICAL ntfy."""
        verdict = self.canary.evaluate_budget()
        if verdict["newly_tripped"]:
            book = self.book
            if book is not None and not book.entries_halted:
                book.halt_entries(HALT_REASON_LOSS_BUDGET)
            log.error(
                "STAGE-2 LOSS BUDGET TRIPPED: %s — entries halted (sticky "
                "across sessions); exits continue (§10 exits-always-allowed)",
                verdict["trip_reason"],
            )
            self.action_log.stamp_envelope(
                session_date=self.trading_day,
                phase="loss_budget_trip",
                envelope=self.canary.to_record(),
            )
            self.notify(
                "CRITICAL: Stage-2 canary loss budget tripped",
                f"{verdict['trip_reason']}\n"
                f"account={self.account} trading_day={self.trading_day}\n"
                "Entries HALTED (sticky across sessions; exits continue). "
                "§9.3a: HARD halt — a new recorded authorization is required "
                "to resume.",
            )
        return verdict

    def _harvest_marks(
        self, decisions: Mapping[str, Any], intents: list[dict[str, Any]]
    ) -> None:
        """Latest observed prices → MTM marks (intent prices + marks/quotes)."""
        for source_key in ("marks", "quotes"):
            source = decisions.get(source_key)
            if isinstance(source, Mapping):
                for sym, px in source.items():
                    price = self._positive(px)
                    if price is not None:
                        self.canary.observe_price(str(sym), price)
        for intent in intents:
            price = self._positive(intent.get("price"))
            if price is not None:
                self.canary.observe_price(str(intent.get("symbol", "")), price)

    # -- the tick ---------------------------------------------------------------
    def process_tick(
        self, decisions: Mapping[str, Any], *, now: datetime
    ) -> dict[str, Any]:
        """The live tick: watchdog → sync → exits (never capped/allowlisted)
        → §9.3a loss-budget check → entries (allowlist + cap enforced).

        Consumes the normalized decision payload (``normalize_tick_result``
        + ``apply_entry_window_policy`` output). Persists the book snapshot
        before returning, whatever happened.
        """
        book = self._require_open()
        submitted: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        allowlist_skips = 0
        try:
            stale = self._cancel_stale(now)
            sync = self._sync_open_children()

            intents = [dict(i) for i in decisions.get("intents") or ()]
            self._harvest_marks(decisions, intents)
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

            # -- §9.3a loss budget: evaluated AFTER this tick's fills/marks
            # landed and BEFORE any entry may submit (exits above are never
            # gated on it). A trip halts entries, sticky across sessions.
            budget = self._evaluate_loss_budget()

            # -- entries: halted? allowlisted? capped? then submit. -----------
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
                symbol = str(intent.get("symbol", "")).upper()
                if symbol not in self.allowlist:
                    # Campaign A4 (audit #296 OR-3): entries ONLY for
                    # allowlisted symbols — counted and journaled.
                    allowlist_skips += 1
                    skipped.append(
                        _skip(
                            intent,
                            REASON_NOT_ALLOWLISTED,
                            detail=(
                                f"{symbol!r} not in the §9.3a canary "
                                f"allowlist {sorted(self.allowlist)}"
                            ),
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
            "canary": {
                "allowlist": sorted(self.allowlist),
                "allowlist_skips": allowlist_skips,
                "loss_budget": budget,
                "envelope": self.canary.to_record(),
            },
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


def _child_parent(
    book: OrderStateBook, child_order_id: str
) -> tuple[ParentIntent, Any]:
    for parent in book.parents():
        for child in parent.children:
            if child.child_order_id == child_order_id:
                return parent, child
    raise Stage2ContractError(f"unknown child_order_id: {child_order_id!r}")


def _row_fill_price(row: Mapping[str, Any]) -> float | None:
    """Broker-reported fill price when present (``fill_price`` /
    ``filled_avg_price``); ``None`` ⇒ caller falls back to the child's
    limit/reference price."""
    for key in ("fill_price", "filled_avg_price"):
        raw = row.get(key)
        if raw is None:
            continue
        try:
            price = float(raw)
        except (TypeError, ValueError):
            continue
        if price > 0 and price == price and price != float("inf"):
            return price
    return None


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


__all__ = [
    "ALL_GATES",
    "ArmDecision",
    "CANARY_STATE_SCHEMA_VERSION",
    "CanaryEnvelopeTracker",
    "DEAD_MAN_CONSECUTIVE_FAILURES",
    "DEFAULT_DAILY_ENTRY_NOTIONAL_CAP",
    "DeadManSwitch",
    "ENV_LIVE_FLAG",
    "EntryCapExceededError",
    "GATE_AUTHORIZATION_FILE",
    "GATE_CANARY_ENVELOPE",
    "GATE_CONFIG_MODE_LIVE",
    "GATE_ENV_LIVE_FLAG",
    "GATE_KILL_SWITCH_ABSENT",
    "HALT_REASON_LOSS_BUDGET",
    "LIVE_EXECUTOR_SCHEMA_VERSION",
    "LiveActionLog",
    "LiveTickExecutor",
    "LiveTickWriter",
    "MAX_AUTHORIZATION_WINDOW_DAYS",
    "MAX_CANARY_LIVE_SESSIONS",
    "MIN_SHADOW_SESSIONS_CLEAN",
    "PROPOSED_CANARY_ALLOWLIST_SIZE",
    "REASON_ENTRIES_HALTED",
    "REASON_ENTRY_CAP",
    "REASON_NOT_ALLOWLISTED",
    "RECORD_KIND_ACTION",
    "RECORD_KIND_ENVELOPE",
    "RECORD_KIND_LIVE_TICK",
    "STAGE2",
    "Stage2Authorization",
    "Stage2AuthorizationError",
    "Stage2ContractError",
    "assert_canary_allowlist",
    "assert_entry_cap",
    "default_authorization_path",
    "default_canary_state_path",
    "default_live_actions_path",
    "default_live_log_path",
    "default_order_state_book_path",
    "entry_notional_submitted",
    "live_env_flag_enabled",
    "load_stage2_authorization",
    "post_critical_ntfy",
    "read_canary_envelope",
    "resolve_stage2_arming",
]
