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

THE THIRD FINDING: EXPIRY WITHOUT A VERDICT (orch#733)
------------------------------------------------------
`ack_expiry` reads DATES out of an ack; nothing read its CONDITION.  So "the fix
landed and the ack aged out afterwards" and "the fix never shipped" both surfaced
as the same word, "expired" — and "the fix landed early" surfaced as nothing at
all.  Issue #733 measured the live case: an ack whose 3-clause clearing condition
was 1-of-3 satisfied, with no mechanism able to say so.

`clears_check` is the repair: a structured, machine-evaluable predicate carried
next to the prose `clears_when`.  The audit evaluates it READ-ONLY and combines
the verdict with expiry into distinct states (`MET_UNEXPIRED`,
`EXPIRED_CONDITION_UNMET`, `EXPIRED_CONDITION_MET`, ...).  The kind set is CLOSED
and dispatch FAILS CLOSED: an unknown or malformed kind is a FINDING, never a
silent pass — the repo's standing rule is that an enumerated allow-list leaves a
fail-open default, so the default branch here IS the finding.  A row may declare
`kind=manual` with a `why` when its condition is not machine-evaluable BY DESIGN
(an open-ended research outcome has no exit code); the audit reports MANUAL and
never mistakes that honest declaration for a missing check.

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
import re as _re
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


#: `clears_when` machine-checkability buckets. Surveyed 2026-08-01 (orch#733): of the
#: 10 live acks only 4 carried ANY fragment a checker could bind to, and 6 of the 9
#: expired rows expired purely via the `acked_at + ACK_MAX_AGE_DAYS` backstop — their
#: `clears_when` never participated. This LINT makes that visible per row, so a
#: condition with no machine-bindable fragment is a FINDING instead of an invisible
#: default. Shape only: nothing is resolved, read, or evaluated.
#:
#: Classification only. Nothing here queries GitHub or the filesystem to CHECK a
#: condition: an audit that needs the network to run is an audit that silently stops
#: running, and "could not check" is precisely the state this tool must never confuse
#: with "checked".
BUCKET_DATE = "date"            # an ISO date ack_expiry already extracts
BUCKET_REF = "ref"              # a repo-qualified PR/issue reference, e.g. repo#73
BUCKET_ARTIFACT = "artifact"    # a testable config key=value or path-like token
BUCKET_BARE_REF = "bare_ref"    # `#75` with NO repo qualifier — unresolvable as written

#: Mirrors the sentinel's own date pattern. A parity test asserts this stays behaviorally
#: equal to what `ack_expiry` extracts on the live ledger, so the two cannot drift
#: silently.
_CW_DATE = _re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_CW_REF = _re.compile(r"\b[A-Za-z][\w.-]*#\d+\b")
_CW_BARE_REF = _re.compile(r"(?<![\w.-])#\d+\b")
_CW_KEYVAL = _re.compile(r"\b[a-z][a-z0-9_]{2,}\s*=\s*\S+")
_CW_PATH = _re.compile(r"\b[\w.-]+/[\w./-]+\b")


def classify_clears_when(text: str) -> dict:
    """Actionable-reference LINT over a `clears_when` — syntax, not semantics.

    Returns ``{"buckets": [...], "has_machine_bindable_fragment": bool}``. A bucket
    records that a fragment of the right SHAPE exists (a date, a repo#N, a key=value or
    path-like token). Nothing here resolves the reference, reads the path, or evaluates
    the condition — a bindable fragment is a precondition for automation, not a
    guarantee of it, and its absence means THIS AUDIT cannot automatically evaluate the
    stated condition.
    """
    t = text or ""
    buckets = []
    if _CW_DATE.search(t):
        buckets.append(BUCKET_DATE)
    if _CW_REF.search(t):
        buckets.append(BUCKET_REF)
    if _CW_BARE_REF.search(t):
        buckets.append(BUCKET_BARE_REF)
    if _CW_KEYVAL.search(t) or _CW_PATH.search(t):
        buckets.append(BUCKET_ARTIFACT)
    return {"buckets": buckets,
            "has_machine_bindable_fragment": any(
                b in (BUCKET_DATE, BUCKET_REF, BUCKET_ARTIFACT) for b in buckets)}


# --------------------------------------------------------------------------- #
# clears_check — the machine-evaluable clause orch#733 makes mandatory
# --------------------------------------------------------------------------- #
#: CLOSED kind set. Dispatch in `evaluate_clears_check` fails CLOSED: only these
#: three kinds can reach a verdict, and anything else — unknown kind, malformed
#: shape, missing required field — is a FINDING. Never enumerate the bad cases
#: and default to pass; enumerate the good cases and default to the finding.
CHECK_LAUNCHCTL = "launchctl_exit_zero"   # met iff launchctl shows last exit 0
CHECK_PATH = "path_exists"                # met iff the named path exists
CHECK_MANUAL = "manual"                   # not machine-evaluable BY DESIGN
KNOWN_CHECK_KINDS = (CHECK_LAUNCHCTL, CHECK_PATH, CHECK_MANUAL)

#: Per-row condition verdicts. UNEVALUABLE is load-bearing: "could not check" is
#: a distinct state, never collapsed into met or unmet — the same rule the module
#: docstring states for the classifier, now applied to evaluation.
CONDITION_MET = "met"
CONDITION_UNMET = "unmet"
CONDITION_UNEVALUABLE = "unevaluable"
CONDITION_MANUAL = "manual"
CONDITION_UNDECLARED = "undeclared"

#: condition x expiry, one word per cell — so "expired" alone can never again
#: stand in for both "aged out after the fix" and "the fix never shipped".
STATE_MET_UNEXPIRED = "MET_UNEXPIRED"
STATE_EXPIRED_CONDITION_MET = "EXPIRED_CONDITION_MET"
STATE_UNMET_UNEXPIRED = "UNMET_UNEXPIRED"
STATE_EXPIRED_CONDITION_UNMET = "EXPIRED_CONDITION_UNMET"
STATE_UNEVALUABLE_UNEXPIRED = "UNEVALUABLE_UNEXPIRED"
STATE_EXPIRED_CONDITION_UNEVALUABLE = "EXPIRED_CONDITION_UNEVALUABLE"
STATE_MANUAL_UNEXPIRED = "MANUAL_UNEXPIRED"
STATE_MANUAL_EXPIRED = "MANUAL_EXPIRED"
STATE_UNDECLARED_UNEXPIRED = "UNDECLARED_UNEXPIRED"
STATE_UNDECLARED_EXPIRED = "UNDECLARED_EXPIRED"


def combine_state(condition: str, expired: bool) -> str:
    """The distinct reported states #733 asks for.

    `MET_UNEXPIRED` and `EXPIRED_CONDITION_MET` are info-grade: the row should be
    removed at the next review touch, and the state says so without an alarm.
    `EXPIRED_CONDITION_UNMET` is the PROBLEM cell — it means the fix this ack was
    waiting on never shipped, which previously read as a plain "expired".
    """
    if condition == CONDITION_MET:
        return STATE_EXPIRED_CONDITION_MET if expired else STATE_MET_UNEXPIRED
    if condition == CONDITION_UNMET:
        return STATE_EXPIRED_CONDITION_UNMET if expired else STATE_UNMET_UNEXPIRED
    if condition == CONDITION_UNEVALUABLE:
        return (STATE_EXPIRED_CONDITION_UNEVALUABLE if expired
                else STATE_UNEVALUABLE_UNEXPIRED)
    if condition == CONDITION_MANUAL:
        return STATE_MANUAL_EXPIRED if expired else STATE_MANUAL_UNEXPIRED
    return STATE_UNDECLARED_EXPIRED if expired else STATE_UNDECLARED_UNEXPIRED


def launchctl_list_text() -> str | None:
    """`launchctl list` output, or ``None`` when launchctl is UNAVAILABLE.

    ``None`` is a distinct input, not a verdict: the evaluator maps it to
    UNEVALUABLE, never to met or unmet. On a linux CI runner launchctl does not
    exist; reporting every launchctl-kind condition "unmet" there would turn an
    environment property into ten false problems, and reporting "met" would be
    the fail-open default this module exists to refuse.
    """
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True,
                             text=True, timeout=30)
    except Exception:  # noqa: BLE001 — absent binary, non-darwin host, timeout
        return None
    return out.stdout if out.returncode == 0 else None


def _launchctl_status(text: str, job: str) -> str | None:
    """The status column for `job` in `launchctl list` output, else ``None``.

    Same 3-column shape the sentinel's `parse_launchctl_failures` reads:
    ``<pid>\t<status>\t<label>``.
    """
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == job:
            return parts[1]
    return None


def evaluate_clears_check(check, launchctl_text: str | None = None) -> dict:
    """Evaluate one row's `clears_check` — read-only, fail-closed.

    Returns ``{"condition": CONDITION_*, "detail": str, "finding": str | None}``.
    ``finding`` is non-None exactly when the check itself is defective (unknown
    kind, malformed shape, missing required field); the caller prefixes the job
    name. A defective check is UNEVALUABLE **and** a finding — a typo can only
    make the audit louder, never quieter.
    """
    if check is None:
        return {"condition": CONDITION_UNDECLARED,
                "detail": "no clears_check declared", "finding": None}
    if not isinstance(check, dict):
        return {"condition": CONDITION_UNEVALUABLE,
                "detail": f"clears_check is {type(check).__name__}, not an object",
                "finding": f"clears_check is {type(check).__name__}, not an "
                           f"object — fail-closed: a malformed check is a "
                           f"finding, never a silent pass"}
    kind = check.get("kind")
    if kind == CHECK_MANUAL:
        why = str(check.get("why") or "").strip()
        if not why:
            return {"condition": CONDITION_UNEVALUABLE,
                    "detail": "kind=manual with no why",
                    "finding": "clears_check kind 'manual' carries no `why` — a "
                               "manual declaration without its justification is "
                               "an undeclared check in disguise"}
        return {"condition": CONDITION_MANUAL,
                "detail": f"not machine-evaluable by design: {why}",
                "finding": None}
    if kind == CHECK_PATH:
        path = check.get("path")
        if not path:
            return {"condition": CONDITION_UNEVALUABLE,
                    "detail": "kind=path_exists with no path",
                    "finding": "clears_check kind 'path_exists' names no `path`"}
        if os.path.exists(str(path)):
            return {"condition": CONDITION_MET,
                    "detail": f"path exists: {path}", "finding": None}
        return {"condition": CONDITION_UNMET,
                "detail": f"path does not exist: {path}", "finding": None}
    if kind == CHECK_LAUNCHCTL:
        job = check.get("job")
        if not job:
            return {"condition": CONDITION_UNEVALUABLE,
                    "detail": "kind=launchctl_exit_zero with no job",
                    "finding": "clears_check kind 'launchctl_exit_zero' names "
                               "no `job`"}
        if launchctl_text is None:
            return {"condition": CONDITION_UNEVALUABLE,
                    "detail": f"launchctl unavailable on this host — cannot read "
                              f"{job}'s last exit; could-not-check is not a "
                              f"verdict in either direction", "finding": None}
        status = _launchctl_status(launchctl_text, str(job))
        if status == "0":
            return {"condition": CONDITION_MET,
                    "detail": f"launchctl list shows last exit 0 for {job}",
                    "finding": None}
        if status is None:
            return {"condition": CONDITION_UNMET,
                    "detail": f"{job} is not in launchctl list — an unloaded job "
                              f"shows no last exit 0", "finding": None}
        if status == "-":
            return {"condition": CONDITION_UNMET,
                    "detail": f"{job} is loaded but has not run since load — no "
                              f"exit 0 observed", "finding": None}
        return {"condition": CONDITION_UNMET,
                "detail": f"{job} last exit {status}", "finding": None}
    # FAIL-CLOSED DEFAULT. The enumerated branches above are the allow-list;
    # everything that falls through — a new kind somebody invents, a typo of a
    # known one — lands HERE, as a finding. Inverting this (an `else: pass`)
    # would recreate the exact defect the repo's standing rule names.
    return {"condition": CONDITION_UNEVALUABLE,
            "detail": f"unknown clears_check kind {kind!r}",
            "finding": f"unknown clears_check kind {kind!r} — the closed set is "
                       f"{sorted(KNOWN_CHECK_KINDS)}. Dispatch fails CLOSED, so "
                       f"an unknown kind is this finding, never a silent pass"}


#: Sentinel default for `audit(launchctl_text=...)`: distinguishes "caller gave
#: no text, fetch it if any row needs it" from an explicit ``None`` ("launchctl
#: unavailable"), which tests use to exercise the UNEVALUABLE path.
_FETCH = object()


def audit(today: dt.date, ledger_path: str | None = None,
          root: str | None = None, launchctl_text=_FETCH) -> dict:
    sent = _load_sentinel()
    root = root or resolve_root(ledger_path)
    acks = sent.load_acks(ledger_path) if ledger_path else sent.load_acks()
    edits = last_edit_dates(root, LEDGER_REL)

    if launchctl_text is _FETCH:
        # ONE subprocess for the whole run, and only when some row needs it —
        # a ledger of manual/path checks never shells out at all.
        need = any(isinstance(a.get("clears_check"), dict)
                   and a["clears_check"].get("kind") == CHECK_LAUNCHCTL
                   for a in acks.values())
        launchctl_text = launchctl_list_text() if need else None

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
        check = ack.get("clears_check")
        verdict = evaluate_clears_check(check, launchctl_text)
        expired = (expiry is None or expiry <= today)  # sentinel's own rule
        rows.append({
            "job": name,
            "acked_at": acked_at.isoformat() if acked_at else None,
            "last_edited": edited.isoformat() if edited else None,
            "stamp_lag_days": lag,
            "expiry": expiry.isoformat() if expiry else None,
            "expired": expired,
            "days_to_expiry": (expiry - today).days if expiry else None,
            "why": why,
            "clears_when_buckets": classify_clears_when(
                str(ack.get("clears_when") or ""))["buckets"],
            "check_kind": check.get("kind") if isinstance(check, dict) else None,
            "condition": verdict["condition"],
            "condition_detail": verdict["detail"],
            "condition_finding": verdict["finding"],
            "state": combine_state(verdict["condition"], expired),
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

    cw_texts = {name: str(ack.get("clears_when") or "") for name, ack in acks.items()}
    for r in rows:
        b = r["clears_when_buckets"]
        # The bare-ref lint stays a PROSE-quality check, independent of
        # clears_check: an unresolvable citation misleads the human reader even
        # when a structured predicate governs the machine's verdict.
        if not cw_texts.get(r["job"], "").strip():
            continue
        if BUCKET_BARE_REF in b and BUCKET_REF not in b:
            findings.append(
                f"{r['job']}: clears_when cites a bare #NN with no repo qualifier — "
                f"unresolvable as written (surveyed 2026-08-01: #75 matches unrelated "
                f"merged PRs in three repos and nothing in strategy-104)")

    # ----- orch#733: condition x expiry ---------------------------------------
    # The old finding here ("clears_when carries no machine-bindable fragment")
    # linted the PROSE. It is UPGRADED, not kept alongside: a structured
    # `clears_check` is now mandatory, so the finding is about the missing
    # predicate itself — and a row that declares one (including an honest
    # kind=manual) is never flagged for the shape of its prose.
    for r in rows:
        if r["condition_finding"]:
            findings.append(f"{r['job']}: {r['condition_finding']}")
        if r["condition"] == CONDITION_UNDECLARED:
            findings.append(
                f"{r['job']}: no clears_check declared — its clearing condition "
                f"exists only as prose this audit cannot evaluate, so 'condition "
                f"met early' and 'expired with the fix never shipped' would both "
                f"surface as the same word. orch#733 makes one machine-evaluable "
                f"clause mandatory: declare launchctl_exit_zero / path_exists, "
                f"or kind=manual with a why if the condition is not "
                f"machine-evaluable by design")
        if r["state"] == STATE_EXPIRED_CONDITION_UNMET:
            findings.append(
                f"{r['job']}: EXPIRED with its clearing condition UNMET "
                f"({r['condition_detail']}) — the fix this ack was waiting on "
                f"never shipped. Without this state the expiry reads as 'the ack "
                f"aged out'; it is actually 'the promised repair did not land "
                f"before the review window closed' (orch#733). Disposition the "
                f"underlying failure or re-review; do not let the returning "
                f"alarm be the only record")

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
          f"{'expiry':>12}{'d':>5}  {'state (condition x expiry, orch#733)'}")
    for r in R["rows"]:
        print(f"{r['job']:<44}{str(r['acked_at']):<12}{str(r['last_edited']):<12}"
              f"{str(r['stamp_lag_days']):>4}{str(r['expiry']):>12}"
              f"{str(r['days_to_expiry']):>5}  {r['state']}")
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
