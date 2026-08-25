"""S3-P4, OBSERVE-ONLY half: the guarded intraday entry loop, recording intents.

Design: ``doc/design/2026-08-23-rq105-stage3-live-entries.md`` §4/§4b/§5.
This module implements the DECISION surface of S3-P4 and deliberately nothing
else: it loads the T-1 batch admission through the SAME leak-guarded loader
the session scheduler uses (§4b(ii) — reused, never re-implemented), joins it
against the shadow-serving re-scores for one ``as_of`` (S3-b rows), applies
:func:`~renquant_orchestrator.intraday_entry_decision.decide_entries` with the
frozen v1 guardrails — ``max_concurrent_positions`` read from the PINNED
strategy config (orch#1050: the dataclass default must never be what live
relies on) — and appends the resulting :class:`EntryPlan` to an append-only
intents log.

NO ORDER PATH EXISTS IN THIS MODULE. There is no broker import, no execution
port, no live mode flag. The live emission stage is written WITH the S3-c
operator authorization, not before it — a dark order stage waiting for a flag
is exactly the inert scaffolding this fleet has agreed never to deploy. Until
then every invocation is a recorded counterfactual: "what would the v1 loop
have entered", which is the S3-c evidence base.

State, fail-closed:

* ``held_plus_pending`` comes from the session scheduler's OWN shadow tick log
  (the ticks carry the broker-read ``live_state``); the tick must be at or
  before ``as_of`` and no older than ``--live-state-max-age-min``. No tick, a
  future-only tick, or a stale one ⇒ the loop refuses with a named
  ``session_block`` rather than guessing the book's occupancy.
* ``entries_today`` / ``notional_today`` are recomputed from THIS log's own
  prior records for the session — the same recompute-from-evidence stance as
  the silent-refusal sentinel, no mutable counter to drift.
* Batch-side refusals (wrong prior session, missing fingerprints, low
  coverage) propagate from the loader untouched and are recorded with the
  run_id they refused (§4b rejection contract).
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from renquant_orchestrator.intraday_entry_decision import (
    EntryCandidate,
    Guardrails,
    decide_entries,
)
from renquant_orchestrator.intraday_session_inputs import (
    FrozenSignalError,
    SignalLeakError,
    load_frozen_daily_signal,
)

ET = ZoneInfo("America/New_York")
SCHEMA_VERSION = "rq105-entry-intents-shadow-1"
RECORD_KIND = "intraday_entry_plan_shadow"
STAGE = "s3p4-shadow"

#: Broker-submission vocabulary that must never appear in a record this module
#: writes. Mirrors assert_shadow_never_submits — kept local so this module
#: stays importable without the scheduler.
_FORBIDDEN_KEYS = ("order_id", "client_order_id", "submitted_at", "broker_order")


def default_intents_log_path(data_root: Path | None = None) -> Path:
    root = data_root or Path(
        os.environ.get("RENQUANT_DATA_ROOT",
                       "/Users/renhao/git/github/RenQuant"))
    return Path(root) / "logs" / "renquant105_pilot" / "intraday_entry_intents_shadow.jsonl"


def _as_aware_et(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError(f"as_of must be timezone-aware, got {value!r}")
    return parsed.astimezone(ET)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def load_shadow_rows(shadow_log: Path, *, session_date: str, as_of: str) -> list[dict]:
    """The S3-b rows for exactly this (session, as_of) — the intraday side."""
    rows: list[dict] = []
    if not shadow_log.exists():
        return rows
    with open(shadow_log, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if (r.get("session_date") == session_date
                    and r.get("as_of") == as_of
                    and r.get("ticker")):
                rows.append(r)
    return rows


def held_plus_pending_from_scheduler_log(
    log_path: Path, *, session_date: str, as_of_et: dt.datetime,
    max_age_min: float,
) -> tuple[int | None, str, dict | None]:
    """(count, why, tick_record). The book's occupancy from the scheduler's
    own shadow ticks: latest tick at or before ``as_of`` within the staleness
    bound. ``tick_record`` is the exact record used, returned so the caller
    can BIND the plan to it by content hash (codex on orch#1059 r3).

    None count means REFUSED, and ``why`` names the reason — the caller
    records it as a session_block instead of defaulting the occupancy to
    zero, which would overstate free slots on exactly the days the evidence
    is missing.
    """
    if not log_path.exists():
        return None, f"no scheduler shadow log at {log_path}", None
    best: dict | None = None
    best_at: dt.datetime | None = None
    with open(log_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("session_date") != session_date:
                continue
            tick_at_raw = r.get("tick_at")
            try:
                tick_at = dt.datetime.fromisoformat(str(tick_at_raw))
            except (TypeError, ValueError):
                continue
            if tick_at.tzinfo is None or tick_at > as_of_et:
                continue
            if best_at is None or tick_at > best_at:
                best, best_at = r, tick_at
    if best is None or best_at is None:
        return None, f"no scheduler tick at or before {as_of_et.isoformat()}", None
    age_min = (as_of_et - best_at).total_seconds() / 60.0
    if age_min > max_age_min:
        return None, (f"latest scheduler tick is {age_min:.1f} min before as_of "
                      f"(bound {max_age_min:.0f}) — occupancy evidence stale"), None
    ls = (best.get("inputs") or {}).get("live_state") or {}
    positions = ls.get("positions")
    if not isinstance(positions, Mapping):
        return None, "scheduler tick live_state carries no positions mapping", None
    occupied = set(str(t).upper() for t in positions)
    for key in ("pending_broker_tickers", "open_buy_reservations"):
        extra = ls.get(key) or ()
        occupied |= {str(t).upper() for t in
                     (extra.keys() if isinstance(extra, Mapping) else extra)}
    return len(occupied), f"tick_at={best_at.isoformat()} n={len(occupied)}", best


def session_totals_from_intents_log(
    log_path: Path, *, session_date: str,
) -> tuple[int, float]:
    """(entries_today, notional_today) recomputed from this log's own records."""
    entries, notional = 0, 0.0
    seen_ticks: set[str] = set()
    if not log_path.exists():
        return entries, notional
    with open(log_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") != RECORD_KIND or r.get("session_date") != session_date:
                continue
            # [codex on orch#1059 P1-2] one tick = one (session, as_of); a
            # retried tick's duplicate record must not consume the budget
            # twice. First record per as_of wins; later ones are ignored here
            # AND refused at write time (see the idempotency gate).
            tick_key = str(r.get("as_of"))
            if tick_key in seen_ticks:
                continue
            seen_ticks.add(tick_key)
            for intent in r.get("intents") or ():
                entries += 1
                try:
                    notional += float(intent.get("notional_budget") or 0.0)
                except (TypeError, ValueError):
                    pass
    return entries, notional


def _hash_jsonable(obj: Any) -> str:
    """The repository's canonical jsonable hash (renquant_artifacts).

    Lazy so unit tests need no artifacts checkout; REQUIRED at runtime —
    an unhashable evidence input refuses rather than emitting an unbound
    plan (codex on orch#1059 r3).
    """
    from renquant_artifacts import hash_jsonable  # noqa: PLC0415
    return hash_jsonable(obj)


def guardrails_from_pinned_config(config_path: Path) -> "tuple[Guardrails, str]":
    """(guardrails, config_bytes_sha256) — the SHARED cap from the pinned
    config, plus the content hash of the exact bytes read, so the persisted
    plan binds to the CONFIG CONTENT rather than a mutable path (codex on
    orch#1059 r3).

    orch#1050: the Guardrails dataclass default (8) must never be what a live
    surface relies on — the cap is policy, and policy lives in the reviewed
    config. Absent/malformed cap ⇒ raise, never default.
    """
    raw = Path(config_path).read_bytes()
    cfg = json.loads(raw.decode("utf-8"))
    cap = cfg.get("max_concurrent_positions")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
        raise ValueError(
            f"pinned config {config_path} carries no usable "
            f"max_concurrent_positions (got {cap!r}) — the shared cap is "
            f"policy and must come from the reviewed config, never a code "
            f"default (orch#1050)")
    import hashlib  # noqa: PLC0415
    return Guardrails(max_concurrent_positions=cap), \
        "sha256:" + hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# The tick
# ---------------------------------------------------------------------------
def _existing_tick_record(intents_log: Path, *, session_date: str,
                          as_of_iso: str) -> dict | None:
    """The already-persisted record for this (session, as_of), if any."""
    if not intents_log.exists():
        return None
    with open(intents_log, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if (r.get("kind") == RECORD_KIND
                    and r.get("session_date") == session_date
                    and r.get("as_of") == as_of_iso):
                return r
    return None


def run_entry_loop_tick(
    *,
    session_date: str,
    as_of: str,
    db_path: Path,
    calendar: Any,
    shadow_log: Path,
    scheduler_log: Path,
    pinned_config: Path,
    intents_log: Path,
    live_state_max_age_min: float = 30.0,
    serving_rc: int = 0,
    env: Mapping[str, str] | None = None,
) -> dict:
    """One observe-only decision tick; returns the record it appended.

    ``serving_rc`` is the exit code of the serving step that produced this
    tick's rows [codex on orch#1059 P1-1]: a failed serving can leave a
    PARTIAL row set for exactly this as_of, and a plan built from a subset
    reads as complete evidence. Nonzero ⇒ a named refusal is persisted and
    no rows are read.
    """
    as_of_et = _as_aware_et(as_of)
    g, config_sha = guardrails_from_pinned_config(pinned_config)
    per_entry_notional = g.max_notional_per_day / g.max_entries_per_day
    as_of_iso = as_of_et.isoformat()

    # [codex on orch#1059 P1-2] IDEMPOTENCY, checked before any work: one
    # (session, as_of) decides once. A scheduler retry returns the existing
    # record instead of appending a twin that would consume the daily budget
    # again and shift every later plan. Checked again under the writer lock
    # before appending, so two concurrent retries cannot both pass this gate.
    existing = _existing_tick_record(intents_log, session_date=session_date,
                                     as_of_iso=as_of_iso)
    if existing is not None:
        return {**existing, "duplicate_tick": True}

    # [codex on orch#1059 r2] The serving gate fires BEFORE any producer or
    # scheduler read: a failed serving tick can coincide with malformed
    # inputs, and crashing in a loader would leave NO record where the
    # contract promises a persisted named refusal. Only the config (already
    # read, for the record's guardrail provenance) and the idempotency check
    # precede this branch.
    batch_refusal: str | None = None
    signal: Mapping[str, Any] | None = None
    rows: list[dict] = []
    held: int | None = None
    held_why = "not_read: serving failed"
    held_tick: dict | None = None
    entries_today, notional_today = 0, 0.0

    if serving_rc == 0:
        try:
            signal = load_frozen_daily_signal(
                db_path=db_path, session_date=session_date, calendar=calendar)
        except (FrozenSignalError, SignalLeakError) as exc:
            batch_refusal = f"{type(exc).__name__}: {exc}"

        rows = load_shadow_rows(shadow_log, session_date=session_date,
                                as_of=as_of)
        held, held_why, held_tick = held_plus_pending_from_scheduler_log(
            scheduler_log, session_date=session_date, as_of_et=as_of_et,
            max_age_min=live_state_max_age_min)
        entries_today, notional_today = session_totals_from_intents_log(
            intents_log, session_date=session_date)

    if serving_rc != 0:
        plan_payload: dict[str, Any] = {
            "session_block": (f"serving_failed rc={serving_rc} — a failed "
                              f"serving step can leave a partial row set for "
                              f"this as_of; refusing to decide on possibly "
                              f"incomplete evidence"),
            "intents": [], "rejections": {},
        }
    elif batch_refusal is not None:
        plan_payload = {
            "session_block": f"batch_side_refused: {batch_refusal}",
            "intents": [], "rejections": {},
        }
    elif not rows:
        plan_payload = {
            "session_block": ("no_shadow_rows_for_as_of: the S3-b lane wrote "
                              "nothing for this tick — intraday side absent"),
            "intents": [], "rejections": {},
        }
    elif held is None:
        plan_payload = {
            "session_block": f"occupancy_unknown: {held_why}",
            "intents": [], "rejections": {},
        }
    else:
        batch_scores = signal["scores"] if signal else {}
        candidates = [
            EntryCandidate(
                ticker=str(r["ticker"]).upper(),
                batch_admitted=str(r["ticker"]).upper() in batch_scores,
                batch_expected_return=batch_scores.get(str(r["ticker"]).upper()),
                intraday_score=r.get("shadow_score"),
                quote_status="fresh" if r.get("quote_status") == "ok"
                             else str(r.get("quote_status") or "missing"),
                intraday_mid=r.get("intraday_mid"),
            )
            for r in rows
        ]
        plan = decide_entries(
            candidates,
            now_et=as_of_et,
            entries_today=entries_today,
            notional_today=notional_today,
            held_plus_pending=held,
            per_entry_notional=per_entry_notional,
            guardrails=g,
            env=env,
        )
        plan_payload = {
            "session_block": plan.session_block,
            "intents": list(plan.intents),
            "rejections": dict(plan.rejections),
        }

    # Evidence bindings (codex on orch#1059 r3): the plan must PROVE which
    # config bytes, which exact S3-b rows, and which occupancy record
    # produced it — a path or a count is re-writable; a content hash is not.
    # Bindings for inputs that were actually read; a PLAN (intents present)
    # with any binding missing refuses below rather than persisting unbound.
    evidence = {
        "pinned_config_sha256": config_sha,
        "shadow_rows_sha256": (
            _hash_jsonable(sorted(rows, key=lambda r: str(r.get("ticker"))))
            if rows else None),
        "occupancy_tick_sha256": (
            _hash_jsonable(held_tick) if held_tick is not None else None),
        "batch_signal_version": (signal or {}).get("signal_version"),
    }
    if plan_payload.get("intents"):
        unbound = [k for k, v in evidence.items() if not v]
        if unbound:
            raise AssertionError(
                f"refusing to persist a plan with intents but unbound "
                f"evidence: {unbound} — an unprovable plan is not an "
                f"evidence base (orch#1059 r3)")

    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECORD_KIND,
        "stage": STAGE,
        "observe_only": True,
        "session_date": session_date,
        "as_of": as_of_et.isoformat(),
        "guardrails": {
            "max_entries_per_day": g.max_entries_per_day,
            "max_notional_per_day": g.max_notional_per_day,
            "no_entry_first_minutes": g.no_entry_first_minutes,
            "no_entry_last_minutes": g.no_entry_last_minutes,
            "max_concurrent_positions": g.max_concurrent_positions,
            "cap_source": str(pinned_config),
            "per_entry_notional": per_entry_notional,
        },
        "evidence": evidence,
        "inputs": {
            "batch_run": (signal or {}).get("signal_version"),
            "batch_refusal": batch_refusal,
            "n_shadow_rows": len(rows),
            "held_plus_pending": held,
            "held_evidence": held_why,
            "entries_today_before": entries_today,
            "notional_today_before": notional_today,
        },
        **plan_payload,
    }

    flat = json.dumps(record)
    for key in _FORBIDDEN_KEYS:
        if key in flat:
            raise AssertionError(
                f"observe-only record carries broker vocabulary {key!r} — "
                f"refusing to persist")

    intents_log.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive writer lock around re-check + append: two concurrent retries
    # of the same tick serialize here, and the loser sees the winner's record
    # in the re-check instead of appending a twin. Single-host by design —
    # the intents log has exactly one producing wrapper.
    with open(intents_log, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0)
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if (r.get("kind") == RECORD_KIND
                        and r.get("session_date") == session_date
                        and r.get("as_of") == as_of_iso):
                    return {**r, "duplicate_tick": True}
            fh.seek(0, os.SEEK_END)
            fh.write(json.dumps(record, sort_keys=True) + "\n")
            fh.flush()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return record


def main(argv: Any | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session-date", required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--db-path", required=True, help="runs.alpaca.db (read-only)")
    ap.add_argument("--shadow-log", required=True, help="S3-b shadow serving JSONL")
    ap.add_argument("--scheduler-log", required=True,
                    help="scheduler shadow tick JSONL (occupancy evidence)")
    ap.add_argument("--pinned-strategy-config", required=True,
                    help="pin-verified config (rq105_pinned_common --verify-file)")
    ap.add_argument("--intents-log", default=None)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--live-state-max-age-min", type=float, default=30.0)
    ap.add_argument("--serving-rc", type=int, default=0,
                    help="exit code of the serving step that produced this "
                         "tick's rows; nonzero persists a named refusal "
                         "instead of deciding on possibly-partial rows")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    from renquant_orchestrator.intraday_session_scheduler import (  # noqa: PLC0415
        default_session_calendar,
    )

    data_root = Path(args.data_root).expanduser() if args.data_root else None
    intents_log = (Path(args.intents_log) if args.intents_log
                   else default_intents_log_path(data_root))
    record = run_entry_loop_tick(
        session_date=args.session_date,
        as_of=args.as_of,
        db_path=Path(args.db_path),
        calendar=default_session_calendar(),
        shadow_log=Path(args.shadow_log),
        scheduler_log=Path(args.scheduler_log),
        pinned_config=Path(args.pinned_strategy_config),
        intents_log=intents_log,
        live_state_max_age_min=args.live_state_max_age_min,
        serving_rc=args.serving_rc,
    )
    if args.json:
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print(f"[OBSERVE-ONLY] rq105 entry plan {args.session_date} {args.as_of}: "
              f"{len(record.get('intents') or [])} intent(s), "
              f"block={record.get('session_block')!r}")
    return 0


__all__ = [
    "RECORD_KIND",
    "SCHEMA_VERSION",
    "default_intents_log_path",
    "guardrails_from_pinned_config",
    "held_plus_pending_from_scheduler_log",
    "load_shadow_rows",
    "main",
    "run_entry_loop_tick",
    "session_totals_from_intents_log",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
