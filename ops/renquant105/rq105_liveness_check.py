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
                           schema AND a parseable timestamp (ts/source_ts/tick_time — all three
                           collectors write one unconditionally; a row missing all three does
                           NOT count as "complete" and is skipped by the backward scan, never
                           silently accepted on a date-only match). A corrupt/truncated/
                           missing-field last row is NEVER treated as evidence of liveness via a
                           raw-mtime fallback (that was fail-open: a process appending garbage
                           with a fresh mtime read as healthy). The found row's timestamp must be
                           within a tight <=10-minute bound of wall-clock now; a timestamp
                           materially AHEAD of now (beyond a small clock-skew tolerance) is
                           rejected as corrupt/clock-issue, not treated as "very fresh".
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


def _data_outputs(data_root: Path) -> list[tuple[str, Path]]:
    """Exact per-collector data-output contract, resolved via each module's
    OWN path resolver (never a hardcoded/guessed relative path or a glob) —
    verifies against the collector's actual current contract, so this check
    cannot silently drift out of sync if a collector's output path ever
    changes. All three are single continuously-appended JSONL files (not
    per-date files), so "fresh" means "the last row's own date field is
    today", not merely "the file exists"."""
    _orch_src_on_path()
    from renquant_orchestrator.intraday_quote_logger import default_tick_feed_path
    from renquant_orchestrator.intraday_pairing_logger import (
        default_pilot_path as pairing_pilot_path,
    )
    from renquant_orchestrator.entry_timing_shadow import (
        default_pilot_path as shadow_pilot_path,
    )

    return [
        ("intraday_quote_logger", default_tick_feed_path(data_root)),
        ("intraday_pairing_logger", pairing_pilot_path(data_root)),
        ("entry_timing_shadow", shadow_pilot_path(data_root)),
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


def _last_complete_jsonl_row(path: str) -> tuple[dict | None, bool]:
    """Scan backward through the file's tail for the most recent COMPLETE,
    parseable JSON row with the required schema fields present. Starts with a
    fixed-size tail read and DOUBLES the read size (up to
    ``_TAIL_CHUNK_MAX_BYTES``) if no complete row is found, so a legitimately
    oversized final row does not make an earlier, perfectly valid row
    unreachable by chopping it out of a single fixed-size window — while still
    never loading an unbounded file fully into memory just to check freshness.

    Returns ``(row_or_None, tail_was_corrupt)``. ``tail_was_corrupt`` is True
    iff the LAST physical line (from the initial, smallest read) failed to
    parse/validate (a truncated write in progress) even though an earlier
    complete row was found further back — reported by the caller as a
    diagnostic, not by itself a liveness failure. If the file's own last line
    itself is legitimately just very long (not corrupt, just chopped by the
    initial seek boundary), a later successful expanded read for a different
    row does not retroactively mark it corrupt — only the FIRST read's last
    line is used for that determination, matching "the physical last line
    failed to parse in the smallest read" rather than any read.
    """
    tail_was_corrupt = False
    checked_last_line = False
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
            return None, False
        lines = [ln for ln in tail.splitlines() if ln.strip()]
        if not lines:
            return None, tail_was_corrupt
        for i in range(len(lines) - 1, -1, -1):
            try:
                row = json.loads(lines[i])
            except (ValueError, json.JSONDecodeError):
                row = None
            schema_ok = isinstance(row, dict) and not any(
                not isinstance(row.get(f), str) or not row.get(f) for f in _REQUIRED_ROW_FIELDS
            )
            # All three collectors write one of ts/source_ts/tick_time
            # unconditionally (verified against their own record-construction
            # code). A row missing all three is treated the same as a
            # schema-invalid row — NOT a weaker "date-only" fallback — so it
            # can never bypass the tight age bound below by omission.
            has_timestamp = schema_ok and _row_timestamp(row) is not None
            if not (schema_ok and has_timestamp):
                if not checked_last_line:
                    tail_was_corrupt = True
                    checked_last_line = True
                continue
            return row, tail_was_corrupt
        checked_last_line = True
        if read_size >= size or chunk >= _TAIL_CHUNK_MAX_BYTES:
            return None, tail_was_corrupt
        chunk = min(chunk * 2, _TAIL_CHUNK_MAX_BYTES)


def _row_timestamp(row: dict) -> dt.datetime | None:
    """Fine-grained timestamp for the tight-age-bound check, preferring the
    most precise field each collector actually writes (mirrors the same
    ts/source_ts/tick_time fallback chain entry_timing_shadow.py itself uses
    when reading its own rows back)."""
    for field in ("ts", "source_ts", "tick_time"):
        val = row.get(field)
        if not isinstance(val, str) or not val:
            continue
        try:
            parsed = dt.datetime.fromisoformat(val)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    return None


def _data_output_fresh(path: str, today_iso: str) -> tuple[bool, str]:
    if not os.path.exists(path):
        return False, f"{path} missing"
    if os.path.getsize(path) == 0:
        return False, f"{path} EMPTY"
    row, tail_was_corrupt = _last_complete_jsonl_row(path)
    if row is None:
        return False, (
            f"{path} no parseable complete row (date+ticker+timestamp) found in tail "
            "— corrupt/truncated/missing timestamp field")
    date_val = row["date"]
    if date_val != today_iso:
        return False, f"{path} last complete row date={date_val!r} != today {today_iso!r} (stale)"
    corrupt_note = " [most-recent physical line was truncated/corrupt; used prior complete row]" if tail_was_corrupt else ""
    # _last_complete_jsonl_row now requires a parseable ts/source_ts/tick_time
    # for a row to count as "complete" at all, so ts_val is never None here —
    # asserted rather than silently branched around, so a future refactor
    # that weakens that invariant fails loudly instead of reintroducing the
    # date-only fallback this review flagged.
    ts_val = _row_timestamp(row)
    assert ts_val is not None, "complete row must carry a parseable timestamp"
    age = dt.datetime.now(dt.timezone.utc) - ts_val
    if age < -_CLOCK_SKEW_TOLERANCE:
        return False, (
            f"{path} last complete row timestamp is {-age} in the FUTURE, beyond the "
            f"{_CLOCK_SKEW_TOLERANCE} clock-skew tolerance — treated as corrupt/clock "
            f"issue, not freshness{corrupt_note}")
    if age > _TIGHT_AGE_BOUND:
        return False, f"{path} last complete row age={age} exceeds {_TIGHT_AGE_BOUND} bound{corrupt_note}"
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
    for name, full_path in _data_outputs(data_root):
        ok, reason = _data_output_fresh(str(full_path), today_iso)
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
