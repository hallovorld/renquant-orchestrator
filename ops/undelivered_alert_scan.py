#!/usr/bin/env python3
"""An alarm that was raised and never delivered (GOAL-5).

Every sentinel in this fleet terminates in one function,
``renquant_common.notify.send``. That function is deliberately built never to
raise into a monitor: it swallows any failure, increments a counter, logs a
warning, and returns ``False``.

Measured 2026-07-29, this is what that cost:

    ntfy send failed (… title='🚨 rq105 DOWN — 2 collector issue(s) 2026-07-28'):
    'latin-1' codec can't encode character '\\U0001f6a8' in position 0

HTTP header values go out as latin-1, so a non-ASCII title makes the request
unbuildable and the WHOLE notification is discarded, body included. The rq105
liveness alarm hard-codes a 🚨 as the first character of its title, so **that
alarm could never have delivered a single notification in its life** — while
its own output log shows collector issues on seven distinct dates in July and
only three clean days.

Seven dropped alerts were found across five log files in two classes:

  * PERMANENT — an encoding defect. Deterministic: it will drop every future
    alarm from that call site until the code changes. Never self-heals.
  * TRANSIENT — a network timeout. `send` does a single POST with no retry, so
    one unlucky handshake loses the alarm. Two of these were the run-surface
    drift alarm itself.

Nothing surfaced any of it. `send_failure_count()` is exported and has **no
consumer anywhere in the fleet** — a counter whose existence suggests somebody
is watching, when nobody is. This scan is that consumer, reading the durable
evidence (the logs) rather than a per-process counter that dies with the run.

Read-only: reads log files, writes nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from liveness_common import alert  # noqa: E402

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
LOG_ROOT = os.path.join(RQ, "logs")

#: The sender's failure marker. Matching the message rather than a structured
#: record is deliberate: the whole point is that no structured record exists.
FAILURE_RE = re.compile(
    r"ntfy send failed \([^)]*title=(?P<title>'[^']*'|\"[^\"]*\")\): (?P<error>.*)"
)

#: Errors that will recur on every future alarm from the same call site.
PERMANENT_RE = re.compile(r"codec can't encode|ordinal not in range", re.I)

#: Only look at logs touched within this window, so a long-dead job's ancient
#: failures do not alarm forever.
MAX_LOG_AGE_DAYS = int(os.environ.get("RQ_UNDELIVERED_MAX_LOG_AGE_DAYS", "14"))


@dataclass(frozen=True)
class Undelivered:
    log_path: str
    title: str
    error: str

    @property
    def permanent(self) -> bool:
        return bool(PERMANENT_RE.search(self.error))


def scan_log(path: Path) -> list[Undelivered]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[Undelivered] = []
    for m in FAILURE_RE.finditer(text):
        out.append(Undelivered(
            log_path=str(path),
            title=m.group("title").strip("'\""),
            error=m.group("error").strip(),
        ))
    return out


def scan(log_root: str = LOG_ROOT, *, as_of: dt.date | None = None) -> list[Undelivered]:
    """Every undelivered alarm recorded in a recently-written fleet log."""
    as_of = as_of or dt.date.today()
    root = Path(log_root)
    if not root.is_dir():
        return []
    found: list[Undelivered] = []
    for path in sorted(root.rglob("*.log")) + sorted(root.rglob("*.err")):
        try:
            mtime = dt.date.fromtimestamp(path.stat().st_mtime)
        except OSError:
            continue
        if (as_of - mtime).days > MAX_LOG_AGE_DAYS:
            continue
        found += scan_log(path)
    return found


def findings(items: list[Undelivered]) -> list[str]:
    """One line per distinct (title, error), permanent failures first.

    Deduplicated on purpose: a permanent defect repeats identically every run,
    and a screen full of the same line reads as noise rather than as one code
    bug that needs fixing once.
    """
    if not items:
        return []
    seen: dict[tuple[str, bool], list[Undelivered]] = {}
    for it in items:
        seen.setdefault((it.title, it.permanent), []).append(it)
    lines: list[str] = []
    for (title, permanent), group in sorted(
        seen.items(), key=lambda kv: (not kv[0][1], kv[0][0])
    ):
        kind = "PERMANENT" if permanent else "transient"
        detail = group[0].error[:90]
        where = os.path.basename(group[0].log_path)
        lines.append(
            f"undelivered alarm [{kind}] x{len(group)}: {title!r} "
            f"({detail}) in {where}"
            + (" — this call site can never deliver until the code changes"
               if permanent else "")
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log-root", default=LOG_ROOT)
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print findings, send no alert")
    args = ap.parse_args(argv)
    as_of = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()

    items = scan(args.log_root, as_of=as_of)
    lines = findings(items)
    for line in lines:
        print(line)
    if not lines:
        print(f"undelivered-alert scan: no dropped alarms in logs touched "
              f"within {MAX_LOG_AGE_DAYS}d as of {as_of}")
        return 0
    if not args.dry_run:
        # ASCII-only title on purpose: an alarm ABOUT undeliverable alarms
        # must not be undeliverable for the same reason.
        alert("RenQuant UNDELIVERED ALARMS", " | ".join(lines))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
