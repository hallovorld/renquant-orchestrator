#!/usr/bin/env python3
"""rq105 N1 liveness check (#212 rule: liveness is its own alert, never freshness).

Runs daily after the post-close window. Verifies TODAY's collector outputs exist
and are non-trivial; posts an ntfy alert per missing/empty output. Exit 0 iff all
present. Read-only; touches nothing but its own stdout/stderr (launchd redirects
those to logs/rq105/launchd_liveness.{out,err} — the parent directory for those
must already exist by install time, see README's install step; this script itself
never creates directories).

Session-day gating uses the REAL NYSE exchange calendar
(``renquant_orchestrator.intraday_quote_logger.default_session_calendar`` —
``pandas_market_calendars``-backed, the SAME primitive the quote logger and
``renquant_execution.preopen_cancel_gate`` use) rather than a bare weekday check,
so scheduled market holidays do not fire a false "collector lapsed" alert.

Checked (session days only):
  wrapper stdout logs   logs/rq105/{quote_logger,intraday_pairing_logger,entry_timing_shadow}_<date>.log
  collector data outputs  each collector's OWN ``default_*_path()`` resolver (not a hardcoded
                           path and not a glob) — verified by scanning the tail JSONL lines
                           BACKWARD for the most recent COMPLETE row with a valid "date"+"ticker"
                           schema.

                           FRESHNESS BASIS IS SPLIT BY COLLECTOR KIND — this is not one shared
                           row schema OR one shared freshness meaning (round-4 fix; round-3 got
                           the per-collector FIELD right but still applied event-time age to all
                           three, which is wrong for two of them):

                             intraday_quote_logger (CONTINUOUS, self-loops all session):
                               row_event_time basis — top-level ts/source_ts/tick_time, must be
                               within a tight <=10-minute bound of a reference time that is
                               min(wall-clock now, today's NYSE session close) (round-5 fix —
                               this check itself runs at 14:00 PT, ~1hr after the 13:00 PT
                               close, so a healthy sampler that correctly stopped at close would
                               otherwise be judged "stale" against raw wall-clock now EVERY
                               single day; capping the reference at session close asks the
                               right question, "did it run through the end of the session",
                               instead of "is it fresh relative to whenever this check happens
                               to run". During session hours the cap is a no-op (now < close),
                               so this is unchanged from the original tight-bound behavior while
                               the feed is actually live.

                             intraday_pairing_logger / entry_timing_shadow (POST-CLOSE ONE-SHOT
                             BATCH — run_postclose_loggers.sh fires once at 13:15 PT, liveness
                             checks at 14:00 PT, ~45min later per the plists/README):
                               file_mtime basis — the row's own timestamp fields (nested
                               intraday_arm/batch_arm.eligible_ts for pairing; top-level
                               entry_tick_time for entry-timing, legitimately None on a censored
                               row) are MARKET-EVENT instants, often near the session open —
                               NOT a collector-completion signal. A healthy job that ran on
                               schedule and wrote today's real data will have event timestamps
                               hours old at 14:00 PT; applying the quote feed's 10-minute bound
                               to them would fail a perfectly healthy post-close run. These two
                               collectors instead use the file's own mtime (the genuine
                               "when did this one-shot write happen" signal) against a wider,
                               still-tight bound (90 minutes — covers the 45min postclose→
                               liveness gap plus launchd scheduling jitter and runtime, while
                               remaining far tighter than "anywhere in today's ~6.5hr session").
                               Applied CONSISTENTLY to every row from these two collectors, not
                               only censored/timestamp-missing ones — round-3's inconsistency
                               (mtime only on the no-timestamp branch) meant a collector's
                               liveness MEANING silently changed based on policy outcome.

                           NO-ADMIT-AWARE staleness for the ADMIT-CONTINGENT collector
                           (intraday_pairing_logger only). intraday_pairing_logger writes ONE
                           row per daily-ADMITTED name (pair_records: "one raw-observation
                           record per admitted name"), so on a day renquant105 admits 0 names
                           — the current norm: the model has no bull edge and most watchlist
                           names have no panel score (orch#799) — the collector legitimately
                           writes 0 rows and its last row stays YESTERDAY's date. Before that
                           stale-date is reported as a failure, the check consults the
                           AUTHORITATIVE session manifest for today
                           (intraday_session_scheduler.default_manifest_path): if the session
                           status == "completed" AND the collector's OWN admission query
                           (runs DB: load_admitted UNION load_submitted_entries)
                           returns ZERO names, the stale-
                           dated paired_is is EXPECTED (nothing to pair), not a pairing-logger
                           failure, and passes. It still FAILS if the session admitted >=1 name
                           (a real pairing-logger failure) or if no completed session exists for
                           today (the "session didn't run" signal is never weakened). This is
                           scoped to the admit-contingent collector: entry_timing_shadow is NOT
                           admit-contingent — in production (run_postclose_loggers.sh, --date
                           only) its admits are every ticker present in the #216 tick feed, not
                           the batch admits, so it writes fresh rows on a 0-admit day (verified
                           2026-08-13: paired_is last row 08-12 while entry_timing_shadow wrote
                           08-13) — it keeps the unmodified date+mtime freshness logic.

                           A corrupt/truncated/missing-required-field last row is NEVER treated
                           as evidence of liveness via a raw-mtime fallback substituting for
                           genuine schema validation (that was the original fail-open bug: a
                           process appending garbage with a fresh mtime read as healthy) — mtime
                           is only ever used as the FRESHNESS metric for the two collectors where
                           it is the correct signal, never as a substitute for the date+ticker
                           schema check itself. Where row_event_time IS the basis, a timestamp
                           materially AHEAD of now (beyond a small clock-skew tolerance) is
                           rejected as corrupt/clock-issue, not treated as "very fresh"; the same
                           rejection applies to a file_mtime basis reading a future mtime.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
RQ105_ORCH_ROOT = os.environ.get(
    "RQ105_ORCH_ROOT", "/Users/renhao/git/github/renquant-orchestrator-run"
)
LOGS = os.path.join(RQ, "logs/rq105")

# Wrapper-log presence: proves the launchd job actually ran (distinct from the
# collector's own DATA output below, which proves it produced something).
_WRAPPER_LOGS = ("quote_logger", "intraday_pairing_logger", "entry_timing_shadow")


def _orch_src_on_path() -> None:
    p = os.path.join(RQ105_ORCH_ROOT, "src")
    if p not in sys.path:
        sys.path.insert(0, p)
    # Campaign B5: the primitive re-exported by intraday_quote_logger now
    # lives in renquant_common.market_calendar — a stale venv install may
    # predate it, so put a sibling renquant-common checkout on sys.path too.
    # orch#1016: ONE named checkout via the shared resolver, no fallback — this
    # used to try "renquant-common-run" then "renquant-common", which let
    # filesystem state decide which copy of the code ran.
    _ops_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _ops_dir not in sys.path:
        sys.path.insert(0, _ops_dir)
    from liveness_common import resolve_common_src  # noqa: PLC0415
    c = resolve_common_src(RQ105_ORCH_ROOT)
    if c not in sys.path:
        sys.path.insert(0, c)



def _session_calendar():
    """Real NYSE calendar (holiday/half-day aware) — lazily imported so this
    script's help/argument handling never requires the orchestrator package to
    be importable, only the actual liveness check does."""
    _orch_src_on_path()
    from renquant_orchestrator.intraday_quote_logger import default_session_calendar

    return default_session_calendar()


_ROW_EVENT_TIME = "row_event_time"
_FILE_MTIME = "file_mtime"


def _data_outputs(data_root: Path) -> list[tuple[str, Path, "TimestampExtractor", str, bool]]:
    """Exact per-collector data-output contract, resolved via each module's
    OWN path resolver (never a hardcoded/guessed relative path or a glob) —
    verifies against the collector's actual current contract, so this check
    cannot silently drift out of sync if a collector's output path ever
    changes.

    Each entry is ``(name, path, timestamp_extractor, freshness_basis,
    admit_contingent)``. The three collectors do NOT share one row schema
    (verified against their real record constructors, not assumed) — each gets
    its OWN ``timestamp_extractor(row) -> datetime | None``. ``freshness_basis``
    is ``_ROW_EVENT_TIME`` (the row's own extracted timestamp is the age
    signal, tight bound — correct for a continuously-sampled feed) or
    ``_FILE_MTIME`` (the file's own mtime is the age signal, wider bound —
    correct for a post-close one-shot batch writer, where the row's own
    timestamp is a market-event instant, not a collector-completion time;
    see module docstring). ``freshness_basis`` applies UNCONDITIONALLY to
    every row from that collector, not only ones where the extractor
    returns None.

    ``admit_contingent`` is True ONLY for a collector that writes one row per
    daily-ADMITTED name (intraday_pairing_logger — ``pair_records`` writes
    "one raw-observation record per admitted name"): on a completed 0-admit
    day it legitimately writes 0 rows, so a stale row-date is EXPECTED, not a
    failure (see ``_completed_session_zero_admits`` / module docstring). It is
    False for intraday_quote_logger (a continuous sampler) and for
    entry_timing_shadow: entry_timing_shadow is NOT admit-contingent — in
    production (run_postclose_loggers.sh invokes it with ``--date`` only) its
    admits fall back to every ticker present in the #216 tick feed, not the
    batch admits, so it writes fresh rows even on a 0-admit day (verified
    2026-08-13) and keeps the unmodified date+mtime freshness logic."""
    _orch_src_on_path()
    from renquant_orchestrator.intraday_quote_logger import default_tick_feed_path
    from renquant_orchestrator.intraday_pairing_logger import (
        default_pilot_path as pairing_pilot_path,
    )
    from renquant_orchestrator.entry_timing_shadow import (
        default_pilot_path as shadow_pilot_path,
    )

    return [
        ("intraday_quote_logger", default_tick_feed_path(data_root),
         _row_timestamp_quote, _ROW_EVENT_TIME, False),
        ("intraday_pairing_logger", pairing_pilot_path(data_root),
         _row_timestamp_pairing, _FILE_MTIME, True),
        ("entry_timing_shadow", shadow_pilot_path(data_root),
         _row_timestamp_entry_timing, _FILE_MTIME, False),
    ]


def _is_session_day(day: dt.date) -> bool:
    try:
        return _session_calendar().session_bounds(day) is not None
    except Exception as exc:  # pandas_market_calendars unavailable/broken — fail closed
        print(f"WARNING: NYSE calendar check failed ({exc}); treating {day} as a "
              f"session day (fail-closed: do not silently skip a possible lapse)",
              file=sys.stderr)
        return True


# GOAL-5 UN-MISSABLE alert (2026-07-22): a 105-DOWN alert shares the "renquant"
# ntfy topic with 104-daily and every other fleet sentinel, so on 07-14..07-22
# the "105 collector stale" alerts were buried in that noise and never actioned
# — the operator's "why didn't I get an ntfy" complaint. Elevate priority +
# distinctive tags + an unmistakable title so a 105-DOWN alert stands out on the
# shared topic. An operator who later stands up a dedicated ntfy topic can route
# 105-down there via RQ105_NTFY_TOPIC; absent that, the bounded fix is
# high-priority + tags on the topic the operator DEMONSTRABLY receives
# ("renquant"), never a brand-new topic nobody is subscribed to (that would make
# the alert MORE silent, not less).
_ALERT_PRIORITY = "urgent"
_ALERT_TAGS = "rotating_light,rq105"


def _alert(
    title: str,
    body: str,
    *,
    priority: str = _ALERT_PRIORITY,
    tags: str = _ALERT_TAGS,
) -> None:
    """Canonical sender re-point (campaign B6): topic resolution (NTFY_TOPIC env
    > $RQ/.env parse > "renquant") and RENQUANT_NO_NOTIFY suppression live in
    renquant_common.notify. Imported lazily + guarded so this liveness check
    still runs (and logs the loss loudly) against a venv whose renquant-common
    predates the notify module.

    Sends at elevated ``priority`` with distinctive ``tags`` (GOAL-5) so a
    105-DOWN alert is not lost in the shared-topic noise. ``RQ105_NTFY_TOPIC``,
    if set, routes to a dedicated topic; unset -> ``None`` -> the sender's normal
    resolution ($RQ/.env NTFY_TOPIC -> fleet default "renquant")."""
    try:
        from renquant_common.notify import send
    except ImportError as exc:  # stale venv — do not let the alert path crash the check
        print(
            f"WARNING: renquant_common.notify unavailable ({exc}); "
            f"alert NOT sent: {title}: {body}",
            file=sys.stderr,
        )
        return
    topic = os.environ.get("RQ105_NTFY_TOPIC") or None
    send(title, body, topic, priority=priority, tags=tags, env_file=os.path.join(RQ, ".env"))


_TAIL_CHUNK_BYTES = 8192
_TAIL_CHUNK_MAX_BYTES = 8192 * 16  # cap the expanding read so a truly pathological
# file (e.g. one enormous unparseable blob) cannot make this loop the whole file
# into memory just to check freshness.
# Tight bound for the CONTINUOUSLY-SAMPLED quote feed only (row_event_time
# basis) — the "writer is mid-write, last physical line is truncated, but an
# earlier complete row is fresh" case. intraday_quote_logger's default 60s
# sample cadence (DEFAULT_CADENCE_SEC) means 10 minutes is several missed
# cycles of slack for a transient hiccup, while still being far tighter than
# "anywhere in today". Scoped to this ONE collector — the post-close batch
# collectors have no sampling cadence at all (they run once per day) and use
# _POSTCLOSE_COMPLETION_AGE_BOUND below instead.
_TIGHT_AGE_BOUND = dt.timedelta(minutes=10)
# Wider bound for the two POST-CLOSE ONE-SHOT batch collectors (file_mtime
# basis) — covers the ~45min gap between run_postclose_loggers.sh's 13:15 PT
# fire and rq105_liveness_check's own 14:00 PT fire (per the plists/README),
# plus launchd scheduling jitter and normal script runtime, while remaining
# far tighter than "anywhere in today's ~6.5hr session" (the bug this fixes).
_POSTCLOSE_COMPLETION_AGE_BOUND = dt.timedelta(minutes=90)
# A row's own timestamp materially AHEAD of wall-clock now is clock skew or
# source corruption, not freshness — negative age must not read as "very
# fresh". A few seconds covers genuine inter-machine clock drift; this is
# NOT a grace window for a collector that's actually running ahead.
_CLOCK_SKEW_TOLERANCE = dt.timedelta(seconds=5)
_REQUIRED_ROW_FIELDS = ("date", "ticker")


def _parse_iso(val: object) -> dt.datetime | None:
    if not isinstance(val, str) or not val:
        return None
    try:
        parsed = dt.datetime.fromisoformat(val)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _row_timestamp_quote(row: dict) -> dt.datetime | None:
    """intraday_quote_logger: top-level ts/source_ts/tick_time (verified
    against the collector's own record-writing code)."""
    for field in ("ts", "source_ts", "tick_time"):
        parsed = _parse_iso(row.get(field))
        if parsed is not None:
            return parsed
    return None


def _row_timestamp_pairing(row: dict) -> dt.datetime | None:
    """intraday_pairing_logger.build_paired_record(): NO top-level timestamp
    field exists — timing lives nested inside intraday_arm/batch_arm
    (ArmObservation.to_dict()/QuoteRef.to_dict(), verified against the real
    dataclasses). Prefer the intraday arm (the later-occurring, closer-to-
    now side) over the batch arm (always session-T open); prefer
    ``eligible_ts`` (when the arm became executable) over the quote's own
    ``source_ts`` within each arm."""
    for arm_key in ("intraday_arm", "batch_arm"):
        arm = row.get(arm_key)
        if not isinstance(arm, dict):
            continue
        parsed = _parse_iso(arm.get("eligible_ts"))
        if parsed is not None:
            return parsed
        quote = arm.get("arrival_quote")
        if isinstance(quote, dict):
            parsed = _parse_iso(quote.get("source_ts"))
            if parsed is not None:
                return parsed
    return None


def _row_timestamp_entry_timing(row: dict) -> dt.datetime | None:
    """entry_timing_shadow.build_record(): top-level ``entry_tick_time``,
    legitimately ``None`` on a censored/no-entry-eligible row (verified
    against the real record constructor — ``entry.tick_time if entry else
    None``). A censored row has no OTHER timestamp field at all; this
    collector uses ``freshness_basis=_FILE_MTIME`` (see ``_data_outputs``)
    precisely because a per-row event time cannot be relied on to exist at
    all, let alone serve as a completion signal."""
    return _parse_iso(row.get("entry_tick_time"))


TimestampExtractor = "Callable[[dict], dt.datetime | None]"


def _last_complete_jsonl_row(
    path: str, extract_ts, *, freshness_basis: str,
) -> tuple[dict | None, bool, bool]:
    """Scan backward through the file's tail for the most recent COMPLETE,
    parseable JSON row with the required schema fields present. Starts with a
    fixed-size tail read and DOUBLES the read size (up to
    ``_TAIL_CHUNK_MAX_BYTES``) if no complete row is found, so a legitimately
    oversized final row does not make an earlier, perfectly valid row
    unreachable by chopping it out of a single fixed-size window — while still
    never loading an unbounded file fully into memory just to check freshness.

    ``extract_ts`` is the collector-specific timestamp extractor (see
    ``_row_timestamp_quote``/``_row_timestamp_pairing``/
    ``_row_timestamp_entry_timing``). A row missing date/ticker, or failing
    to parse as JSON, is never "complete" regardless of ``freshness_basis``.
    When ``freshness_basis`` is ``_FILE_MTIME`` (post-close one-shot
    collectors): a schema-valid row is complete regardless of whether
    ``extract_ts(row)`` returns a value — the row's own timestamp (if any)
    is a market-event instant, not the freshness signal, so its absence
    (e.g. a genuinely censored entry-timing row) does not disqualify the
    row. When ``freshness_basis`` is ``_ROW_EVENT_TIME`` (the continuously-
    sampled quote feed): a row is complete ONLY if ``extract_ts(row)`` also
    returns a value — a missing timestamp on a feed that's supposed to
    always carry one must never silently pass via a weaker date-only
    fallback (the original fail-open bug this file exists to close).

    Returns ``(row_or_None, tail_was_corrupt, row_has_timestamp)``.
    ``tail_was_corrupt`` is True iff the row ultimately RETURNED is NOT the
    file's actual last physical line (we had to fall back to an earlier
    line because the true last line never parsed as complete, at any read
    size). If the true last line simply needed a bigger read to parse (it
    was legitimately long, not corrupt) and THAT read is what produced the
    returned row, ``tail_was_corrupt`` is False — a line is only "corrupt"
    if it never becomes parseable no matter how much of it we read, not
    merely because the smallest window chopped it.
    """
    chunk = _TAIL_CHUNK_BYTES
    while True:
        try:
            with open(path, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                read_size = min(size, chunk)
                fh.seek(-read_size, os.SEEK_END)
                tail = fh.read().decode("utf-8", errors="replace")
        except OSError:
            return None, False, False
        lines = [ln for ln in tail.splitlines() if ln.strip()]
        if not lines:
            return None, False, False
        at_max_read = read_size >= size or chunk >= _TAIL_CHUNK_MAX_BYTES
        for i in range(len(lines) - 1, -1, -1):
            is_true_last_line = (i == len(lines) - 1)
            try:
                row = json.loads(lines[i])
            except (ValueError, json.JSONDecodeError):
                row = None
            schema_ok = isinstance(row, dict) and not any(
                not isinstance(row.get(f), str) or not row.get(f) for f in _REQUIRED_ROW_FIELDS
            )
            has_timestamp = schema_ok and extract_ts(row) is not None
            complete = schema_ok and (has_timestamp or freshness_basis == _FILE_MTIME)
            if not complete:
                if is_true_last_line and not at_max_read:
                    # The true last line failed to parse in THIS read — it
                    # may just be chopped by the current window; break out
                    # of the inner scan and retry with a bigger read before
                    # concluding anything about earlier lines.
                    break
                # Either not the true last line, or we're already at the
                # max read size (so a bigger buffer won't help) — this line
                # genuinely fails, keep scanning backward within this read.
                continue
            # complete row found. tail_was_corrupt iff it is NOT the file's
            # true last physical line (we fell back to an earlier one).
            return row, not is_true_last_line, has_timestamp
        else:
            # Scanned every line in this read without finding a complete
            # row, and the true last line DID parse-fail but we're already
            # at max read size — nothing more to try.
            return None, True, False
        # Reached only via the inner `break` (true last line needs a bigger
        # read) — expand and retry.
        chunk = min(chunk * 2, _TAIL_CHUNK_MAX_BYTES)


# Session-manifest status meaning the intraday session RAN FULLY to its close
# (not halted / disabled / aborted). Only under a genuinely completed session is a
# 0-admit day a LEGITIMATE reason for an admit-contingent post-close collector to
# have written no rows — a halted/disabled/missing session is NOT (that path keeps
# its existing "session didn't run" staleness signal, never weakened here).
_SESSION_COMPLETED_STATUS = "completed"


def _pairing_admit_count(as_of: dt.date) -> tuple[int | None, str]:
    """Count the admissions ``collect_pairs()`` would pair for session ``as_of``,
    using the SAME functions and the SAME dedupe key it uses.

    This must not be re-derived from a different object. ``collect_pairs()``
    resolves its admission set from the runs DB as
    ``load_admitted(T)`` UNION ``load_submitted_entries(resolve_admitting_run_date(T))``,
    deduplicated on ``(signal_version, ticker)`` — the batch that placed the
    entries ran post-close on the PREVIOUS session. The intraday session
    manifest's ``counters.entries_count`` is a different quantity (intraday tick
    intents), so a completed session with zero intraday entries can coexist with
    a nonempty batch admission set that legitimately requires pairing rows.
    Reading the manifest instead would suppress that real failure.

    Returns ``(count, evidence)``, or ``(None, reason)`` when the count cannot be
    established — the caller treats ``None`` as "do not exempt".
    """
    _orch_src_on_path()
    try:
        from renquant_orchestrator.intraday_pairing_logger import (  # noqa: PLC0415
            DEFAULT_RUNS_DB,
            connect,
            load_admitted,
            load_submitted_entries,
            resolve_admitting_run_date,
        )
    except Exception as exc:  # collector unimportable — do NOT suppress the alarm
        return None, f"pairing-collector admission API unavailable ({exc})"
    if not os.path.exists(str(DEFAULT_RUNS_DB)):
        return None, f"runs DB absent ({DEFAULT_RUNS_DB})"
    try:
        conn = connect(DEFAULT_RUNS_DB)
    except Exception as exc:
        return None, f"runs DB unreadable ({exc})"
    try:
        admitted = load_admitted(conn, as_of, run_type="live")
        seen = {(n.signal_version, n.ticker) for n in admitted}
        admit_date = resolve_admitting_run_date(conn, as_of, run_type="live")
        if admit_date is not None:
            for name in load_submitted_entries(
                conn, admit_date, session_date=as_of, run_type="live"
            ):
                seen.add((name.signal_version, name.ticker))
    except Exception as exc:
        return None, f"admission query failed ({exc})"
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    where = f"admit_run_date={admit_date}" if admit_date is not None else "no admitting run"
    return len(seen), f"runs DB admissions for {as_of.isoformat()}: {len(seen)} ({where})"


def _completed_session_zero_admits(
    as_of: dt.date, data_root: Path,
) -> tuple[bool, str]:
    """AUTHORITATIVE no-admit signal for ``as_of``: a session that COMPLETED and
    for which the pairing collector's OWN admission query returns zero names.

    Two independent conditions, both required:

    1. today's session manifest exists and its ``status == "completed"`` — the
       session ran fully to its close (resolved via the scheduler's own
       ``default_manifest_path``, never a hardcoded path); and
    2. :func:`_pairing_admit_count` — the collector's admission set — is **0**.

    Condition 2 replaces an earlier reading of ``counters.entries_count``, which
    was the WRONG OBJECT: the manifest counts intraday tick intents while the
    collector pairs batch admissions resolved from the runs DB. A session can
    complete with zero intraday entries while the batch admitted names that
    require pairing rows, and exempting on the manifest count would have marked a
    stale ``paired_is`` OK and suppressed a genuine collector failure.

    FAILS TOWARD ALARMING: any uncertainty (no manifest, unreadable, not
    completed, admissions unknown, or >=1 admission) returns ``(False, reason)``
    so a real staleness is never suppressed."""
    _orch_src_on_path()
    try:
        from renquant_orchestrator.intraday_session_scheduler import (
            default_manifest_path,
        )
    except Exception as exc:  # scheduler unimportable — do NOT suppress the alarm
        return False, f"session-manifest resolver unavailable ({exc})"
    mpath = default_manifest_path(as_of.isoformat(), data_root)
    if not os.path.exists(mpath):
        return False, f"no session manifest for {as_of.isoformat()} ({mpath})"
    try:
        with open(mpath, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        return False, f"session manifest unreadable ({exc})"
    if not isinstance(manifest, dict):
        return False, f"session manifest {mpath} is not a JSON object"
    status = manifest.get("status")
    if status != _SESSION_COMPLETED_STATUS:
        return False, (
            f"session status={status!r} is not {_SESSION_COMPLETED_STATUS!r} "
            "(session did not complete — staleness stands)")
    n_admits, admit_evidence = _pairing_admit_count(as_of)
    if n_admits is None:
        return False, f"admission count unavailable — staleness stands ({admit_evidence})"
    if n_admits != 0:
        return False, (
            f"{admit_evidence} — the collector had names to pair, so a stale "
            "row-date is a real failure")
    return True, (
        f"session manifest {os.path.basename(str(mpath))}: status='completed'; "
        f"{admit_evidence}")


def _data_output_fresh(
    path: str, today_iso: str, extract_ts, freshness_basis: str,
    session_close_utc: dt.datetime | None = None,
    no_admit_exempt: tuple[bool, str] | None = None,
) -> tuple[bool, str, dict | None]:
    """Returns ``(ok, reason, selected_row)`` — ``selected_row`` is the exact
    dict that determined the verdict (the same object ``_last_complete_
    jsonl_row`` returned), or ``None`` if no row was ever selected (missing
    file, empty file, or no parseable complete row at all). Exposing the
    real selected row (not a generic tail-read blob) lets a caller compute
    provenance evidence that is guaranteed to correspond to the row that
    actually determined the liveness verdict.

    ``no_admit_exempt`` is the AUTHORITATIVE no-admit signal
    (``_completed_session_zero_admits``), passed ONLY for an admit-contingent
    collector (intraday_pairing_logger). When it is ``(True, evidence)`` and the
    file's last complete row is stale-dated (``date != today``), the collector
    legitimately wrote no rows on a completed 0-admit session, so this returns
    ``ok=True`` instead of flagging stale. It has NO effect on any other path —
    a >=1-admit / no-completed-session signal ``(False, ...)`` (or ``None`` for a
    non-admit-contingent collector) leaves the original stale behavior intact,
    and all freshness/age/corrupt/clock-skew logic below is unchanged."""
    if not os.path.exists(path):
        return False, f"{path} missing", None
    if os.path.getsize(path) == 0:
        return False, f"{path} EMPTY", None
    row, tail_was_corrupt, has_timestamp = _last_complete_jsonl_row(
        path, extract_ts, freshness_basis=freshness_basis)
    if row is None:
        return False, (
            f"{path} no parseable complete row (date+ticker"
            f"{'' if freshness_basis == _FILE_MTIME else '+timestamp'}) found in tail "
            "— corrupt/truncated/missing required field"), None
    date_val = row["date"]
    if date_val != today_iso:
        if no_admit_exempt is not None and no_admit_exempt[0]:
            # Admit-contingent collector + AUTHORITATIVE confirmation that today's
            # session completed with 0 admitted names: it legitimately wrote no
            # rows, so a yesterday-dated last row is EXPECTED, not a failure.
            return True, (
                f"{path} not updated today but session completed with 0 admitted "
                f"names — pairing collector legitimately wrote no rows "
                f"(last complete row date={date_val!r}; {no_admit_exempt[1]})"), row
        return False, f"{path} last complete row date={date_val!r} != today {today_iso!r} (stale)", row
    corrupt_note = " [most-recent physical line was truncated/corrupt; used prior complete row]" if tail_was_corrupt else ""

    if freshness_basis == _ROW_EVENT_TIME:
        # Continuously-sampled feed: the row's own event timestamp IS the
        # freshness signal — a healthy sampler's last row is always recent
        # relative to whichever comes first, wall-clock now or today's
        # session close (round-5 fix; see module docstring — this check
        # runs post-close, so an uncapped "now" reference would fail every
        # healthy day once the sampler correctly stops at close).
        assert has_timestamp  # _last_complete_jsonl_row only returns a row this basis if it has one
        ts_val = extract_ts(row)
        assert ts_val is not None
        now = dt.datetime.now(dt.timezone.utc)
        if now - ts_val < -_CLOCK_SKEW_TOLERANCE:
            return False, (
                f"{path} last complete row timestamp is {ts_val - now} in the FUTURE, beyond the "
                f"{_CLOCK_SKEW_TOLERANCE} clock-skew tolerance — treated as corrupt/clock "
                f"issue, not freshness{corrupt_note}"), row
        reference = min(now, session_close_utc) if session_close_utc is not None else now
        age = max(dt.timedelta(0), reference - ts_val)
        if age > _TIGHT_AGE_BOUND:
            return False, f"{path} last complete row age={age} exceeds {_TIGHT_AGE_BOUND} bound{corrupt_note}", row
    else:
        # POST-CLOSE ONE-SHOT batch collector (pairing / entry-timing):
        # the row's own timestamp (if any) is a market-event instant, not a
        # collector-completion signal — applying the quote feed's tight
        # bound to it would fail a perfectly healthy job whose real data
        # simply describes an event from hours earlier in the session. The
        # file's own mtime is the genuine "when did this one-shot write
        # happen" signal, and is used UNCONDITIONALLY for every row from
        # these collectors (has_timestamp or not) against the wider
        # postclose bound — never the row's event time, and never the
        # quote feed's 10-minute bound.
        ts_note = "" if has_timestamp else " (row has no per-row event timestamp — censored/no-entry row)"
        mtime = dt.datetime.fromtimestamp(os.path.getmtime(path), tz=dt.timezone.utc)
        age = dt.datetime.now(dt.timezone.utc) - mtime
        if age < -_CLOCK_SKEW_TOLERANCE:
            return False, (
                f"{path} file mtime is {-age} in the FUTURE, beyond the "
                f"{_CLOCK_SKEW_TOLERANCE} clock-skew tolerance — treated as corrupt/clock "
                f"issue{corrupt_note}{ts_note}"), row
        if age > _POSTCLOSE_COMPLETION_AGE_BOUND:
            return False, (
                f"{path} file mtime age={age} exceeds the postclose-completion bound "
                f"{_POSTCLOSE_COMPLETION_AGE_BOUND}{corrupt_note}{ts_note}"), row

    if tail_was_corrupt:
        print(f"WARNING: {path} tail had a truncated/corrupt final line (writer likely mid-write); "
              f"prior complete row passed date+age freshness checks", file=sys.stderr)
    return True, "", row


def main() -> int:
    today = dt.date.today()
    today_iso = today.isoformat()

    if not _is_session_day(today):
        print(f"rq105 liveness: {today_iso} is not an NYSE session day (holiday/weekend) — skip")
        return 0

    missing: list[str] = []

    for mod in _WRAPPER_LOGS:
        p = os.path.join(LOGS, f"{mod}_{today_iso}.log")
        if not os.path.exists(p):
            missing.append(f"{mod} wrapper log missing ({p})")
        # Wrapper logs are checked for PRESENCE only. The quote logger's
        # wrapper log is legitimately zero-byte while ticks flow normally
        # (measured 2026-07-02: 3,900+ tick rows with an empty redirect —
        # the module writes data directly and emits no per-sample stderr
        # lines). Loop health is judged by the tick DATA feed above
        # (default_tick_feed_path), never by the plumbing's chatter.

    data_root = Path(RQ)
    for name, result in check_collector_data_outputs(data_root, today).items():
        if result["status"] != "ok":
            missing.append(f"{name}: {result['reason']}")

    if missing:
        _alert(f"🚨 rq105 DOWN — {len(missing)} collector issue(s) {today_iso}",
               "\n".join(missing))
        print("\n".join(missing))
        return 1
    print(f"rq105 liveness OK {today_iso}")
    return 0


def check_collector_data_outputs(data_root: Path, as_of: dt.date) -> dict[str, dict]:
    """STABLE PUBLIC interface — the one function external consumers (e.g.
    renquant-orchestrator#247's KPI scorecard) should call for per-collector
    data-output liveness. Encapsulates the per-collector timestamp-extractor
    and freshness-basis dispatch internals above (``_data_outputs``,
    ``_data_output_fresh``, ``_row_timestamp_*``) behind one call so a
    consumer never needs to know which of the three collectors uses
    row-event-time vs. file-mtime freshness, or how many positional fields
    ``_data_outputs()``'s tuples currently carry — that internal shape is
    free to change in a future round without breaking callers of this
    function.

    Returns ``{collector_name: {"status": "ok" | "stale_or_missing",
    "path": str, "reason": str | None, "freshness_basis":
    "row_event_time" | "file_mtime", "row_content_sha256": str | None}}`` —
    one entry per collector in ``_data_outputs()``, independent of the
    others (a consumer can report each collector separately or aggregate,
    its choice). ``row_content_sha256`` is a sha256 of the EXACT selected
    row's canonical JSON (sorted keys) that determined this verdict — not a
    generic tail-read hash of arbitrary file bytes — so a caller recording
    this as provenance evidence is provably anchored to the row the
    validator actually used, and ``None`` only when no row was ever
    selected (missing/empty file, or no parseable complete row at all)."""
    out: dict[str, dict] = {}
    today_iso = as_of.isoformat()
    bounds = _session_calendar().session_bounds(as_of)
    session_close_utc = bounds.close.astimezone(dt.timezone.utc) if bounds is not None else None
    # AUTHORITATIVE no-admit signal for today, read once. Only an admit-contingent
    # collector consults it: a stale-dated file on a completed 0-admit session is
    # EXPECTED for it (one row per admitted name → zero admits = zero rows), never
    # a collector failure. Non-admit-contingent collectors get ``None`` (unchanged).
    zero_admit_today = _completed_session_zero_admits(as_of, data_root)
    for entry in _data_outputs(data_root):
        # Tolerate both the current 5-tuple (..., admit_contingent) and any
        # legacy/mocked 4-tuple shape — this function promises callers that
        # _data_outputs()'s positional arity is free to change. A 4-tuple has no
        # admit-contingent flag, so it defaults to False (never exempted).
        name, full_path, extract_ts, freshness_basis = entry[:4]
        admit_contingent = entry[4] if len(entry) > 4 else False
        ok, reason, row = _data_output_fresh(
            str(full_path), today_iso, extract_ts, freshness_basis,
            session_close_utc=session_close_utc,
            no_admit_exempt=zero_admit_today if admit_contingent else None,
        )
        row_hash = (
            hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode("utf-8")).hexdigest()
            if row is not None else None)
        out[name] = {
            "status": "ok" if ok else "stale_or_missing",
            "freshness_basis": "row_event_time" if freshness_basis == _ROW_EVENT_TIME else "file_mtime",
            "row_content_sha256": row_hash,
            "path": str(full_path),
            "reason": reason if not ok else None,
        }
    return out


if __name__ == "__main__":
    sys.exit(main())
