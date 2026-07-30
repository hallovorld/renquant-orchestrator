"""Liveness receipt for the rq104 degradation sentinel (GOAL-1, issue #622).

**The defect this exists to fix.** The sentinel returns `1` when it has alarms —
that is its delivered signal, and the ack ledger says so explicitly. But an
uncaught exception in Python also exits `1`. So a **crashed** sentinel and an
**alarming** sentinel produce the identical observable: `launchctl` last exit 1,
permanently acked. The failure of the thing that detects failures was undetectable
by construction, and #622 records that this is why a shadow-feed job sat at exit 1
with a 0-byte log for 28 days without anyone being able to tell whether the alarm
was firing unheeded or the sentinel was simply dead.

**Two changes make those cases distinguishable.** An internal error now exits `3`
instead of `1`, and every firing writes the receipt defined here. The receipt is
what covers the third case no exit code can express: the sentinel *never ran at
all*, so `launchctl` still shows whatever it showed last week.

**Who reads it.** Not the sentinel — a process cannot attest to its own liveness.
`ops/run_surface_drift_check.py` (`com.renquant.run-surface-drift`, a separate
launchd job) checks the receipt's freshness, so a dead sentinel is surfaced by a
process that is still alive. That is the whole point of putting the check there.

**Where it is written.** Outside every git checkout, defaulting under
`~/.renquant/`. Deliberately NOT beside the ack ledger: `ops/renquant104/` lives in
the run checkout, and runtime state written into that checkout would leave it dirty,
which makes pin-align abort. Deliberately NOT under the umbrella either — that tree
is not a scratch space.

This module is shared by both jobs on purpose. A copy in each would be a
twin implementation, and the recurring lesson on this programme is that the copy
which runs is not the copy a reader finds first.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

#: Exit codes. 1 MUST keep meaning "alarms present" — `sentinel_acks.json` acks
#: the sentinel's own nonzero exit on exactly that basis, so renumbering it would
#: silently change what every existing ack means. Only the previously-colliding
#: crash case gets a new code.
EXIT_OK = 0
EXIT_ALARMS = 1
EXIT_INTERNAL = 3

RECEIPT_ENV = "RQ_SENTINEL_RECEIPT"
DEFAULT_RECEIPT = "~/.renquant/sentinel/rq104_degradation_receipt.json"

#: A receipt older than this is treated as "the sentinel is not running".
#: 4 days, not 1: the sentinel only fires on NYSE session days, so a Friday run
#: followed by a Monday holiday legitimately leaves the newest receipt 4 days old.
#: Tightening this below 4 would alarm on a normal long weekend.
MAX_RECEIPT_AGE_S = 4 * 24 * 3600


def receipt_path() -> Path:
    return Path(os.environ.get(RECEIPT_ENV, os.path.expanduser(DEFAULT_RECEIPT)))


def write_receipt(payload: dict[str, Any], path: Path | None = None) -> str | None:
    """Persist the receipt. NEVER raises.

    A liveness mechanism that can take down the process it instruments is worse
    than no mechanism at all, so every failure here is swallowed and returned as a
    string for the caller to print. The sentinel's real verdict and exit code must
    not depend on whether this file could be written.
    """
    target = path or receipt_path()
    body = {"schema_version": 1, **payload}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename so a reader never observes a half-written receipt and
        # mistakes it for a malformed one.
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(target)
    except Exception as exc:  # noqa: BLE001
        return f"could not write sentinel receipt to {target}: {type(exc).__name__}: {exc}"
    return None


def read_receipt(path: Path | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """(receipt, error). A missing file and a malformed file are DIFFERENT.

    The caller must be able to tell "never ran" from "wrote something unreadable",
    because the remedies differ and because collapsing them is how a guard ends up
    reporting the wrong cause.
    """
    target = path or receipt_path()
    if not target.exists():
        return None, None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return None, f"top level is {type(data).__name__}, not an object"
    return data, None


def utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
