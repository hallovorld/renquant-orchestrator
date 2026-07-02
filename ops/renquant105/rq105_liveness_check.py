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
                           schema, using a PER-COLLECTOR timestamp extractor (the three
                           collectors do NOT share one row schema — verified against their real
                           record constructors, not assumed):
                             intraday_quote_logger:    top-level ts/source_ts/tick_time
                             intraday_pairing_logger:  nested in intraday_arm/batch_arm
                                                        (eligible_ts, arrival_quote.source_ts)
                             entry_timing_shadow:      top-level entry_tick_time — legitimately
                                                        None on a censored/no-entry row; this
                                                        collector is a POST-CLOSE ONE-SHOT batch
                                                        write (not continuously appended), so a
                                                        censored row's freshness falls back to
                                                        the file's own mtime (the genuine
                                                        collector-completion signal for a
                                                        one-shot write), not a row event time
                           A corrupt/truncated/missing-field last row is NEVER treated as
                           evidence of liveness via a raw-mtime fallback for the two
                           continuously-appended collectors (that was fail-open: a process
                           appending garbage with a fresh mtime read as healthy). Where a
                           row-level timestamp IS available, it must be within a tight
                           <=10-minute bound of wall-clock now; a timestamp materially AHEAD of
                           now (beyond a small clock-skew tolerance) is rejected as
                           corrupt/clock-issue, not treated as "very fresh".
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
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


def _session_calendar():
    """Real NYSE calendar (holiday/half-day aware) — lazily imported so this
    script's help/argument handling never requires the orchestrator package to
    be importable, only the actual liveness check does."""
    _orch_src_on_path()
    from renquant_orchestrator.intraday_quote_logger import default_session_calendar

    return default_session_calendar()


def _data_outputs(data_root: Path) -> list[tuple[str, Path, "TimestampExtractor", bool]]:
    """Exact per-collector data-output contract, resolved via each module's
    OWN path resolver (never a hardcoded/guessed relative path or a glob) —
    verifies against the collector's actual current contract, so this check
    cannot silently drift out of sync if a collector's output path ever
    changes.

    Each entry is ``(name, path, timestamp_extractor, allow_file_completion)``.
    The three collectors do NOT share one row schema (verified against their
    real record constructors, not assumed) — each gets its OWN
    ``timestamp_extractor(row) -> datetime | None``.
    ``allow_file_completion=True`` means: a schema-valid row whose extractor
    returns ``None`` (no per-row timestamp available, e.g. a legitimately
    censored entry-timing row) is still treated as a complete/healthy row,
    with the file's own mtime used as the collector-completion signal
    instead of a row-level event time — correct ONLY for a genuine
    post-close one-shot batch writer, never for a continuously-appended
    feed (where it would reintroduce the original fail-open mtime bug)."""
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
         _row_timestamp_quote, False),
        ("intraday_pairing_logger", pairing_pilot_path(data_root),
         _row_timestamp_pairing, False),
        ("entry_timing_shadow", shadow_pilot_path(data_root),
         _row_timestamp_entry_timing, True),
    ]


def _is_session_day(day: dt.date) -> bool:
    try:
        return _session_calendar().session_bounds(day) is not None
    except Exception as exc:  # pandas_market_calendars unavailable/broken — fail closed
        print(f"WARNING: NYSE calendar check failed ({exc}); treating {day} as a "
              f"session day (fail-closed: do not silently skip a possible lapse)",
              file=sys.stderr)
        return True


def _alert(title: str, body: str) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        env = os.path.join(RQ, ".env")
        if os.path.exists(env):
            for line in open(env):
                if line.startswith("NTFY_TOPIC="):
                    topic = line.split("=", 1)[1].strip().strip('"')
    if topic:
        subprocess.run(
            ["curl", "-s", "-H", f"Title: {title}", "-d", body,
             f"ntfy.sh/{topic}"], capture_output=True)


_TAIL_CHUNK_BYTES = 8192
_TAIL_CHUNK_MAX_BYTES = 8192 * 16  # cap the expanding read so a truly pathological
# file (e.g. one enormous unparseable blob) cannot make this loop the whole file
# into memory just to check freshness.
# Tight bound for the "writer is mid-write, last physical line is truncated,
# but an earlier complete row is fresh" case. All three collectors default to
# a 60s sample cadence (intraday_quote_logger.DEFAULT_CADENCE_SEC); 10 minutes
# is several missed cycles of slack for a transient hiccup while still being
# far tighter than "anywhere in today" (the bug this replaces).
_TIGHT_AGE_BOUND = dt.timedelta(minutes=10)
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
    None``). A censored row has no OTHER timestamp field at all; callers
    must use ``allow_file_completion=True`` for this collector (see
    ``_data_outputs``) rather than treating a censored row as incomplete."""
    return _parse_iso(row.get("entry_tick_time"))


TimestampExtractor = "Callable[[dict], dt.datetime | None]"


def _last_complete_jsonl_row(
    path: str, extract_ts, *, allow_file_completion: bool,
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
    to parse as JSON, is never "complete" regardless of ``allow_file_
    completion``. When ``extract_ts(row)`` is ``None`` on an otherwise
    schema-valid row: if ``allow_file_completion`` is True (post-close
    one-shot collectors only, e.g. a genuinely censored entry-timing row),
    the row IS accepted as complete with no row-level timestamp, and the
    caller falls back to file mtime; if False (continuously-appended
    collectors), the row is treated as incomplete and the backward scan
    continues — a missing timestamp on a feed that's supposed to always
    carry one must never silently pass via a weaker date-only fallback.

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
            complete = schema_ok and (has_timestamp or allow_file_completion)
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


def _data_output_fresh(path: str, today_iso: str, extract_ts, allow_file_completion: bool) -> tuple[bool, str]:
    if not os.path.exists(path):
        return False, f"{path} missing"
    if os.path.getsize(path) == 0:
        return False, f"{path} EMPTY"
    row, tail_was_corrupt, has_timestamp = _last_complete_jsonl_row(
        path, extract_ts, allow_file_completion=allow_file_completion)
    if row is None:
        return False, (
            f"{path} no parseable complete row (date+ticker"
            f"{'' if allow_file_completion else '+timestamp'}) found in tail "
            "— corrupt/truncated/missing required field")
    date_val = row["date"]
    if date_val != today_iso:
        return False, f"{path} last complete row date={date_val!r} != today {today_iso!r} (stale)"
    corrupt_note = " [most-recent physical line was truncated/corrupt; used prior complete row]" if tail_was_corrupt else ""

    if has_timestamp:
        ts_val = extract_ts(row)
        assert ts_val is not None
        age = dt.datetime.now(dt.timezone.utc) - ts_val
        if age < -_CLOCK_SKEW_TOLERANCE:
            return False, (
                f"{path} last complete row timestamp is {-age} in the FUTURE, beyond the "
                f"{_CLOCK_SKEW_TOLERANCE} clock-skew tolerance — treated as corrupt/clock "
                f"issue, not freshness{corrupt_note}")
        if age > _TIGHT_AGE_BOUND:
            return False, f"{path} last complete row age={age} exceeds {_TIGHT_AGE_BOUND} bound{corrupt_note}"
    else:
        # allow_file_completion path only (e.g. a genuinely censored
        # entry-timing row): no row-level event time exists at all for a
        # post-close one-shot batch writer, so the file's own mtime IS the
        # collector-completion signal — the write time on disk literally
        # records when this one-shot job ran, unlike a continuously-appended
        # feed where mtime alone is fail-open (the original bug this file's
        # earlier round fixed).
        mtime = dt.datetime.fromtimestamp(os.path.getmtime(path), tz=dt.timezone.utc)
        age = dt.datetime.now(dt.timezone.utc) - mtime
        if age < -_CLOCK_SKEW_TOLERANCE:
            return False, (
                f"{path} file mtime is {-age} in the FUTURE, beyond the "
                f"{_CLOCK_SKEW_TOLERANCE} clock-skew tolerance — treated as corrupt/clock "
                f"issue{corrupt_note}")
        if age > _TIGHT_AGE_BOUND:
            return False, (
                f"{path} last row has no per-row timestamp (censored) and file mtime "
                f"age={age} exceeds {_TIGHT_AGE_BOUND} bound{corrupt_note}")

    if tail_was_corrupt:
        print(f"WARNING: {path} tail had a truncated/corrupt final line (writer likely mid-write); "
              f"prior complete row passed date+age freshness checks", file=sys.stderr)
    return True, ""


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
    for name, full_path, extract_ts, allow_file_completion in _data_outputs(data_root):
        ok, reason = _data_output_fresh(
            str(full_path), today_iso, extract_ts, allow_file_completion)
        if not ok:
            missing.append(f"{name}: {reason}")

    if missing:
        _alert(f"rq105 LIVENESS: {len(missing)} issue(s) {today_iso}",
               "\n".join(missing))
        print("\n".join(missing))
        return 1
    print(f"rq105 liveness OK {today_iso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
