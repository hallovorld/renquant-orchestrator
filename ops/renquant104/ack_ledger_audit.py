"""Audit the sentinel ack ledger — the ack's own clock measures the wrong event.

WHAT AN ACK IS
--------------
`sentinel_acks.json` turns a KNOWN nonzero last-exit from ALARM into INFO.  Per
CLAUDE.md's CONTAINMENT PROTOCOL every such suppression must carry an expiry, and
`rq104_degradation_sentinel.ack_expiry()` implements it: the EARLIEST of an explicit
`expires_at`, a date found in `clears_when`, or `acked_at + ACK_MAX_AGE_DAYS`.  An
expired ack stops suppressing, and the alarm returning is the designed reminder.

THE DEFECT THIS AUDITS
----------------------
`ack_expiry()` treats `acked_at` as *"when a human last reviewed this suppression."*
Nothing enforces that reading.  In practice `acked_at` records **when the row was first
written**, and a later re-disposition — a corrected diagnosis, a widened or narrowed
scope — rewrites `reason` and `clears_when` and leaves `acked_at` untouched.

So the one clock that forces re-review is stamped with the wrong event.  Measured on
`origin/main` at f59d4609: `com.renquant.rq104-degradation-sentinel` was **rewritten on
2026-07-30** and still declares `acked_at: 2026-07-17` — a **13-day** stale stamp.

Which direction is dangerous matters, and both are reported:

* stamp **older** than the real edit  -> expiry fires EARLY -> noisy, safe;
* stamp **newer** than its introducing commit -> expiry fires LATE. **This is NOT a
  detector for "re-stamped without re-review", and an earlier version of this file
  claimed it was.** Measured: a genuine re-review and an unreviewed re-stamp both write
  today's `acked_at` in today's commit, so both yield lag **0** and identical evidence.
  What a negative lag actually identifies is a stamp dated AFTER the commit that
  introduced it -- timestamp chronology corruption (a future-dated stamp, or a
  backdated commit), which is worth reporting under its own name and is a different
  event. Distinguishing the two human actions would need review evidence the ledger
  does not carry.

THE SECOND FINDING: THE EXPIRY CLIFF
------------------------------------
Staggered expiry is what makes the reminder usable — one suppression resurfaces, gets
judged, gets lifted or renewed.  When a batch of acks is written on one day they all
expire on one day, and the reminder arrives as a burst.  A burst is the alarm-fatigue
shape: the ledger gets ignored wholesale, which is exactly the failure the ledger
exists to prevent.

Measured at f59d4609: all 10 acks carry `acked_at: 2026-07-17`, so 6 expire on
2026-07-31 and the other 4 already expired on 2026-07-20 — **10/10 expired as of
2026-07-31** under the sentinel's own `expiry <= today` rule.

NO TWIN IMPLEMENTATION
----------------------
Expiry is NOT recomputed here.  `ack_expiry` and `ACK_MAX_AGE_DAYS` are imported from
the sentinel, so this audit cannot drift away from the rule actually in force.  A copy
would agree on the day it was written and diverge silently afterwards — the failure
this repo already has a registry for.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER_REL = "ops/renquant104/sentinel_acks.json"

EXIT_OK, EXIT_FINDINGS, EXIT_HARNESS = 0, 1, 3


def _load_sentinel():
    """Import the sentinel module for `ack_expiry` — never re-implement it."""
    for extra in (os.path.dirname(HERE), HERE):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    path = os.path.join(HERE, "rq104_degradation_sentinel.py")
    spec = importlib.util.spec_from_file_location("_rq104_sentinel_for_ack_audit", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the sentinel from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # dataclasses/typing resolve through this
    spec.loader.exec_module(mod)
    return mod


def repo_root(start: str | None = None) -> str:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         cwd=start or HERE, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"not a git checkout: {out.stderr.strip()}")
    return out.stdout.strip()


def last_edit_dates(root: str, rel: str) -> dict[str, dt.date]:
    """For each ack key, the date its CURRENT value was introduced.

    Walk the file's history newest -> oldest; the oldest commit still carrying the
    current value is the commit that introduced it.  A key absent from an older
    commit ends the walk for that key, which is correct: that is where it was added.
    """
    log = subprocess.run(["git", "log", "--format=%H %cI", "--", rel],
                         cwd=root, capture_output=True, text=True)
    if log.returncode != 0:
        raise RuntimeError(f"git log failed: {log.stderr.strip()}")
    revs = [ln.split() for ln in log.stdout.splitlines() if ln.strip()]
    if not revs:
        raise RuntimeError(f"{rel} has no commits — cannot date any ack")

    cache: dict[str, dict | None] = {}

    def blob(h: str):
        if h not in cache:
            o = subprocess.run(["git", "show", f"{h}:{rel}"], cwd=root,
                               capture_output=True, text=True)
            try:
                cache[h] = json.loads(o.stdout) if o.returncode == 0 else None
            except json.JSONDecodeError:
                cache[h] = None
        return cache[h]

    current = blob(revs[0][0])
    if current is None:
        raise RuntimeError(f"{rel} at HEAD is not readable JSON")
    out: dict[str, dt.date] = {}
    for key, val in current.items():
        seen = None
        for h, iso in revs:
            b = blob(h)
            if b is None or key not in b or b[key] != val:
                break
            seen = dt.date.fromisoformat(iso[:10])
        if seen is not None:
            out[key] = seen
    return out


def resolve_root(ledger_path: str | None) -> str:
    """The repo whose HISTORY dates this ledger — derived FROM the ledger.

    The audit compares each ack's `acked_at` against the commit that last changed
    it, so the ledger and the history must be the same checkout.  Taking the
    ledger from `--ledger` and the history from wherever the process happens to
    run would date one repo's acks against another repo's commits and report the
    mismatch as "unreadable" — a checker validating the wrong object, which is the
    exact shape this repo keeps a registry of.  So the root is resolved from the
    ledger's own directory, and a ledger sitting outside it is a HARNESS failure,
    never a finding.
    """
    if ledger_path is None:
        return repo_root()
    ledger = os.path.abspath(ledger_path)
    if not os.path.exists(ledger):
        raise RuntimeError(f"ledger does not exist: {ledger}")
    root = repo_root(os.path.dirname(ledger))
    rel = os.path.relpath(ledger, root)
    if rel != LEDGER_REL:
        raise RuntimeError(
            f"ledger {ledger} sits at {rel!r} inside {root}, but this audit dates "
            f"acks against the history of {LEDGER_REL!r} — refusing rather than "
            f"dating one file against another file's commits")
    return root


def audit(today: dt.date, ledger_path: str | None = None,
          root: str | None = None) -> dict:
    sent = _load_sentinel()
    root = root or resolve_root(ledger_path)
    acks = sent.load_acks(ledger_path) if ledger_path else sent.load_acks()
    edits = last_edit_dates(root, LEDGER_REL)

    rows, by_expiry = [], {}
    for name, ack in sorted(acks.items()):
        expiry, why = sent.ack_expiry(ack, name)
        acked_at = None
        try:
            acked_at = dt.date.fromisoformat(str(ack.get("acked_at")))
        except (TypeError, ValueError):
            pass
        edited = edits.get(name)
        # stamp_lag > 0: the row was edited AFTER its acked_at claims (clock too old,
        # expiry early, noisy-safe).  < 0: acked_at is ahead of any edit that produced
        # it: chronology corruption, NOT evidence of an unreviewed re-stamp. See the
        # module docstring -- both human actions produce lag 0.
        lag = (edited - acked_at).days if (edited and acked_at) else None
        rows.append({
            "job": name,
            "acked_at": acked_at.isoformat() if acked_at else None,
            "last_edited": edited.isoformat() if edited else None,
            "stamp_lag_days": lag,
            "expiry": expiry.isoformat() if expiry else None,
            "expired": (expiry is None or expiry <= today),  # sentinel's own rule
            "days_to_expiry": (expiry - today).days if expiry else None,
            "why": why,
        })
        if expiry:
            by_expiry.setdefault(expiry.isoformat(), []).append(name)

    findings = []
    for r in rows:
        if r["stamp_lag_days"] is None:
            findings.append(f"{r['job']}: acked_at or edit date unreadable — the "
                            f"expiry clock cannot be checked at all")
        elif r["stamp_lag_days"] > 0:
            findings.append(
                f"{r['job']}: acked_at {r['acked_at']} but the row was actually last "
                f"edited {r['last_edited']} ({r['stamp_lag_days']}d) — the expiry "
                f"clock is stamped with the wrong event; expiry fires early")
        elif r["stamp_lag_days"] < 0:
            findings.append(
                f"{r['job']}: acked_at {r['acked_at']} is AHEAD of the commit that "
                f"introduced it ({r['last_edited']}) — timestamp chronology is "
                f"corrupt (a future-dated stamp or a backdated commit), so the expiry "
                f"clock runs {abs(r['stamp_lag_days'])}d late. This is NOT evidence of "
                f"an unreviewed re-stamp: that action is indistinguishable here")

    # LONG-EXPIRED: "expired" and "expired for longer than an ack's whole life" are
    # different facts, and only the first was reported. An ack that lapsed yesterday
    # means the reminder just fired, working as designed. One that lapsed longer ago
    # than ACK_MAX_AGE_DAYS means a FULL REVIEW CYCLE has passed since it did, with
    # nobody lifting or renewing it -- so the reminder has been firing unheeded, which
    # is the failure this ledger exists to prevent rather than a normal state.
    #
    # The threshold is DERIVED, not chosen: it is the ledger's own review cadence.
    # A magic number here would be one more constant nobody could re-derive.
    for r in rows:
        d = r["days_to_expiry"]
        if d is not None and -d > sent.ACK_MAX_AGE_DAYS:
            findings.append(
                f"{r['job']}: expired {-d}d ago, which is longer than the "
                f"{sent.ACK_MAX_AGE_DAYS}d an ack is allowed to live — a full review "
                f"cycle has passed since it lapsed and nobody lifted or renewed it. "
                f"The alarm has been returning unheeded, which is the state this "
                f"ledger exists to prevent")

    cliffs = {d: n for d, n in by_expiry.items() if len(n) > 1}
    for day, names in sorted(cliffs.items()):
        findings.append(
            f"expiry cliff {day}: {len(names)} acks expire together "
            f"({', '.join(sorted(names)[:4])}{'…' if len(names) > 4 else ''}) — the "
            f"reminder arrives as a burst, which is the alarm-fatigue shape")

    return {"today": today.isoformat(), "n_acks": len(rows),
            "n_expired": sum(1 for r in rows if r["expired"]),
            "ack_max_age_days": sent.ACK_MAX_AGE_DAYS,
            "rows": rows, "cliffs": cliffs, "findings": findings}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--today", default=None, help="YYYY-MM-DD, defaults to today")
    ap.add_argument("--ledger", default=None)
    # `--json-out` REMOVED 2026-08-01. It had no caller anywhere in the repo, and its
    # single `open(..., "w")` was the only write in this file — which disqualified the
    # detector from `ops_audit` membership under that module's read-only rule, enforced
    # by `test_no_member_writes`. An unused write flag that keeps a working detector dark
    # is a liability, not a feature; `--json` prints the same payload to stdout, which a
    # caller can redirect. Deleting it is what made this tool schedulable.
    ap.add_argument("--json", action="store_true",
                    help="emit the full report as JSON on stdout")
    a = ap.parse_args(argv)
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()

    try:
        R = audit(today, a.ledger)
    except Exception as exc:  # noqa: BLE001
        print(f"ack-ledger-audit HARNESS FAILURE: {exc}", file=sys.stderr)
        return EXIT_HARNESS

    print(f"ack ledger audit — {R['today']}  ({R['n_acks']} acks, "
          f"ACK_MAX_AGE_DAYS={R['ack_max_age_days']})")
    print(f"{'job':<44}{'acked_at':<12}{'edited':<12}{'lag':>4}"
          f"{'expiry':>12}{'d':>5}  {'state'}")
    for r in R["rows"]:
        print(f"{r['job']:<44}{str(r['acked_at']):<12}{str(r['last_edited']):<12}"
              f"{str(r['stamp_lag_days']):>4}{str(r['expiry']):>12}"
              f"{str(r['days_to_expiry']):>5}  "
              f"{'EXPIRED' if r['expired'] else 'active'}")
    print(f"\nexpired under the sentinel's own rule (expiry <= today): "
          f"{R['n_expired']}/{R['n_acks']}")
    if R["findings"]:
        print(f"\n{len(R['findings'])} finding(s):")
        for f in R["findings"]:
            print(f"  - {f}")
    else:
        print("\nno findings")

    if a.json:
        print(json.dumps(R, indent=2, sort_keys=True, default=str))
    return EXIT_FINDINGS if R["findings"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
