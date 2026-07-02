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
                           path and not a glob) — verified by parsing the LAST JSONL line and
                           checking its "date" field is today (falls back to file mtime if the
                           last line has no parseable date).
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


def _last_jsonl_row(path: str) -> dict | None:
    """Best-effort last-line parse (tail-reads in 8KB chunks so a large pilot
    file is not fully loaded into memory just to check freshness)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            chunk = min(size, 8192)
            fh.seek(-chunk, os.SEEK_END)
            tail = fh.read().decode("utf-8", errors="replace")
        lines = [ln for ln in tail.splitlines() if ln.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _data_output_fresh(path: str, today_iso: str) -> tuple[bool, str]:
    if not os.path.exists(path):
        return False, f"{path} missing"
    if os.path.getsize(path) == 0:
        return False, f"{path} EMPTY"
    row = _last_jsonl_row(path)
    if row is not None and isinstance(row.get("date"), str):
        if row["date"] == today_iso:
            return True, ""
        return False, f"{path} last row date={row['date']!r} != today {today_iso!r} (stale)"
    # No parseable "date" field on the last row — fall back to mtime, and say so
    # explicitly rather than silently trusting an unverified file.
    mtime_date = dt.date.fromtimestamp(os.path.getmtime(path)).isoformat()
    if mtime_date == today_iso:
        return True, ""
    return False, f"{path} last row unparseable and mtime date={mtime_date!r} != today (stale, fallback check)"


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
