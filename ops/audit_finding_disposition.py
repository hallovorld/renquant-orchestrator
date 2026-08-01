#!/usr/bin/env python3
"""The audit fleet has no quiet state, so it cannot signal. (GOAL-5)

MEASURED 2026-08-01 on `origin/main`: `ops/ops_audit.py` runs **10 detectors** and reports
`ok=0 findings=10` — every member, every run. It has **no ack, known, suppress or baseline
concept of any kind** (grepped: the only `ack` in the file is the *name* of the
`ack-ledger` member). And `com.renquant.ops-audit`'s plist is **not installed**, so the
aggregator has never run on schedule.

A fleet that reports 10 of 10 forever is indistinguishable from a fleet that always fires.
**A NEW finding cannot stand out against it**, and adding an 11th detector makes the
report worse, not better — which is the counterweight to a night spent adding detectors.

WHAT THIS ADDS. A disposition layer, so a run can be QUIET: each finding is fingerprinted,
a committed ledger may ack a fingerprint with a reason and an expiry, and an acked finding
reports as **INFO** instead of a finding. Nothing is suppressed silently — an acked finding
is still printed, with its reason.

THE FINGERPRINT IS THE WHOLE PROBLEM, and both failure modes are real:

  * Fingerprint the **raw message** and every ack dies the moment a count ticks
    (`"has not acted on 4 non-acting runs"` -> `5`), so the ledger is write-only.
  * Normalise the digits away and an **escalation is silently covered**: `4` runs and
    `40` runs fingerprint identically, and the ack keeps holding.

So the fingerprint normalises digits — and the numbers are **recorded alongside**. When an
acked finding's numbers move, it reports **`ACKED_BUT_CHANGED`**, not INFO. An ack covers
a situation, not a magnitude.

Read-only with respect to the ledger: this classifies, it never writes an ack. Acking is a
human decision and a reviewed diff.

Exit codes: ``0`` no undispositioned finding, ``1`` at least one NEW / CHANGED / EXPIRED,
``2`` usage/IO error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "renquant104"))

# IMPORTED, never re-implemented — `ack_expiry` is the single source for what "expired"
# means, and a second copy would drift exactly when it mattered.
from rq104_degradation_sentinel import ack_expiry  # noqa: E402

NEW, ACKED, CHANGED, EXPIRED = "NEW", "ACKED", "ACKED_BUT_CHANGED", "ACK_EXPIRED"

_DIGITS = re.compile(r"\d+")
#: Volatile beyond digits: timestamps and absolute paths drift without the situation
#: changing. Normalised for the fingerprint only; both are kept in the recorded text.
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}[T ]?[\d:.+]*")
_HOME = re.compile(r"/Users/[^/\s]+")


def normalise(text: str) -> str:
    t = _ISO.sub("<DATE>", text)
    t = _HOME.sub("<HOME>", t)
    return _DIGITS.sub("<N>", t)


def numbers(text: str) -> list[str]:
    """The digits the fingerprint threw away — kept so an escalation is visible."""
    return _DIGITS.findall(_HOME.sub("", _ISO.sub("", text)))


def fingerprint(member: str, text: str) -> str:
    return hashlib.sha256(f"{member}\x00{normalise(text)}".encode()).hexdigest()[:16]


def classify(member: str, text: str, ledger: dict, today: dt.date) -> dict:
    fp = fingerprint(member, text)
    nums = numbers(text)
    row = {"member": member, "fingerprint": fp, "numbers": nums, "text": text}
    ack = ledger.get(fp)
    if not isinstance(ack, dict):
        return {**row, "state": NEW}
    expiry, why = ack_expiry(ack, member)
    if expiry is None or expiry <= today:
        return {**row, "state": EXPIRED, "reason": ack.get("reason"),
                "expiry": expiry.isoformat() if expiry else None, "expiry_why": why}
    seen = ack.get("numbers_when_acked")
    if isinstance(seen, list) and seen != nums:
        return {**row, "state": CHANGED, "reason": ack.get("reason"),
                "numbers_when_acked": seen,
                "why": ("the situation is acked but its magnitudes moved; an ack covers a "
                        "situation, not a magnitude")}
    return {**row, "state": ACKED, "reason": ack.get("reason"),
            "expiry": expiry.isoformat()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--findings", required=True, type=Path,
                    help="JSON list of {member, text} — normally ops_audit --json output")
    ap.add_argument("--ledger", type=Path, default=HERE / "ops_audit_acks.json")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        raw = json.loads(a.findings.read_text())
        ledger = json.loads(a.ledger.read_text()) if a.ledger.exists() else {}
    except (OSError, ValueError) as exc:
        print(f"disposition: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(ledger, dict):
        print("disposition: ledger top level is not an object", file=sys.stderr)
        return 2
    try:
        today = dt.date.fromisoformat(a.as_of) if a.as_of else dt.date.today()
    except ValueError:
        print(f"disposition: --as-of is not a date: {a.as_of!r}", file=sys.stderr)
        return 2

    items = raw if isinstance(raw, list) else raw.get("findings", [])
    rows = [classify(str(i.get("member")), str(i.get("text", "")), ledger, today)
            for i in items if isinstance(i, dict)]
    loud = [r for r in rows if r["state"] != ACKED]
    rep = {"as_of": today.isoformat(), "n": len(rows),
           "n_acked": sum(1 for r in rows if r["state"] == ACKED),
           "n_loud": len(loud), "rows": rows,
           "note": ("An acked finding is still PRINTED with its reason — nothing is "
                    "suppressed silently. This never writes the ledger; acking is a "
                    "human decision and a reviewed diff.")}
    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        for r in rows:
            print(f"  {r['state']:<18}{r['member']:<24}{r['text'][:70]}")
            if r.get("reason"):
                print(f"      acked because: {str(r['reason'])[:90]}")
            if r["state"] == CHANGED:
                print(f"      numbers {r['numbers_when_acked']} -> {r['numbers']}")
        print(f"\n  {rep['n_acked']} acked / {rep['n_loud']} needing attention "
              f"of {rep['n']}")
        print(f"  {rep['note']}")
    return 1 if loud else 0


if __name__ == "__main__":
    raise SystemExit(main())
