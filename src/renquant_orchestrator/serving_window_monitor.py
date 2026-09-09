"""Count down the SERVING EXCEPTION the live book is trading under.

WHY THIS EXISTS. The RFC#210 A4-T1 license was granted on 2026-08-31 with a
stamped expiry of 2026-09-07. It closed itself exactly as designed — and the
2026-09-08 session went straight to sell-only, because the artifact the
license was covering has zero eligible regimes and nothing else was
servable: the previous model was 37 days old against a 28-day SLA, and every
candidate since 09-01 carried 0 eligible regimes with genuine_ic two orders
of magnitude under the floor. Nobody had scheduled what happens ON expiry, so
the window closed into a state with no servable model and the first anyone
knew was the daily aborting.

A self-expiring license is the right design. What was missing is the alarm in
front of it. This monitor answers one question every morning:

    if the serving exception closes on its stamped date, will the book still
    be able to buy the next day?

It reads the SERVED artifact only, and reports:
  * no exception in force              -> healthy, silent (the normal state);
  * exception with a replacement ready -> healthy (the artifact has eligible
    regimes of its own, so the standing gate passes without the license);
  * exception closing within the lead  -> WARN, naming the date, the days
    left, and what stops on that date;
  * exception already closed           -> BREACH: the buy path is shut now.

OBSERVE-ONLY: reads one JSON file and (behind ``--notify``) alerts. It
promotes nothing, writes no production state, and never changes a window.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from renquant_common.notify import send as post_ntfy  # canonical sender (campaign B6)

from .runtime_paths import default_data_root

DEFAULT_NTFY_TOPIC = "renquant"
DEFAULT_ARTIFACT_SUBPATH = (
    "backtesting", "renquant_104", "artifacts", "prod", "panel-ltr.alpha158_fund.json")
#: Days before the stamped expiry at which the alarm starts. One trading week:
#: long enough to land a governance decision, short enough not to nag.
DEFAULT_LEAD_DAYS = 7

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_CLOSED = "closed"
STATUS_UNKNOWN = "unknown"
_EXIT = {STATUS_OK: 0, STATUS_WARN: 1, STATUS_CLOSED: 2, STATUS_UNKNOWN: 3}


def default_artifact_path(data_root: Path) -> Path:
    return data_root.joinpath(*DEFAULT_ARTIFACT_SUBPATH)


def _eligible_regime_count(wf: dict) -> int | None:
    """How many regimes the served artifact's own WF evidence qualifies.

    ``None`` when the stamp cannot be read as a regime list at all — reported
    as unknown rather than guessed, because this number is the whole question
    of whether the artifact can stand without the license.
    """
    tm = wf.get("trade_monotonicity")
    if not isinstance(tm, dict):
        return None
    regimes = tm.get("regimes")
    if not isinstance(regimes, list):
        # an explicit failure reason with no regime list means zero eligible
        return 0 if tm.get("passed") is False else None
    return sum(1 for r in regimes if isinstance(r, dict) and r.get("eligible"))


def evaluate(payload: object, *, today: dt.date, lead_days: int = DEFAULT_LEAD_DAYS) -> dict[str, Any]:
    """Pure verdict for one served artifact. No I/O."""
    if not isinstance(payload, dict):
        return {"status": STATUS_UNKNOWN, "summary": "served artifact is not a JSON object"}
    meta = payload.get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    override = meta.get("fallback_a4t1_override")
    run_id = meta.get("fallback_a4t1_candidate_run_id")
    raw_expiry = meta.get("fallback_a4t1_expiry")
    if override is not True and not run_id and not raw_expiry:
        return {"status": STATUS_OK, "exception": None,
                "summary": "no serving exception in force on the served artifact"}
    # A partially-stamped exception is not readable as a window: say so.
    if not isinstance(raw_expiry, str) or not raw_expiry.strip():
        return {"status": STATUS_UNKNOWN, "exception": "a4t1",
                "summary": f"A4-T1 stamp present (run {run_id!r}) but fallback_a4t1_expiry is "
                           f"{raw_expiry!r} — the window cannot be read"}
    try:
        expiry = dt.date.fromisoformat(raw_expiry.strip())
    except ValueError:
        return {"status": STATUS_UNKNOWN, "exception": "a4t1",
                "summary": f"A4-T1 fallback_a4t1_expiry {raw_expiry!r} is not an ISO date"}

    wf = meta.get("wf_gate_metadata")
    eligible = _eligible_regime_count(wf if isinstance(wf, dict) else {})
    days_left = (expiry - today).days
    out: dict[str, Any] = {
        "exception": "a4t1", "run_id": run_id, "expiry": expiry.isoformat(),
        "days_left": days_left, "eligible_regimes": eligible,
        "trained_date": payload.get("trained_date"),
        "receipt_id": ((meta.get("fallback_a4t1_consumption_proof") or {}).get("receipt_id")
                       if isinstance(meta.get("fallback_a4t1_consumption_proof"), dict) else None),
    }
    # Does the artifact stand on its own once the window closes?
    if eligible is None:
        standalone = None
    else:
        standalone = eligible > 0
    out["stands_without_the_license"] = standalone

    if standalone is True:
        out["status"] = STATUS_OK
        out["summary"] = (
            f"A4-T1 window on {run_id} ends {expiry} ({days_left}d), but the served "
            f"artifact carries {eligible} eligible regime(s) of its own — the standing "
            "regime-IC gate passes without the license, so the close is harmless")
        return out
    consequence = (
        "P-REGIME-IC returns to HARD, the daily aborts to sell-only, and with it the "
        "shadow lanes and the rq105 export go dark — the book cannot buy at all")
    if days_left < 0:
        out["status"] = STATUS_CLOSED
        out["summary"] = (
            f"A4-T1 window on {run_id} CLOSED {expiry} ({-days_left}d ago) and the served "
            f"artifact has {eligible if eligible is not None else 'unknown'} eligible "
            f"regimes: {consequence}. Exits: promote a candidate whose WF produced "
            "round-trips, or record a new dated operator window.")
    elif days_left <= lead_days:
        out["status"] = STATUS_WARN
        out["summary"] = (
            f"A4-T1 window on {run_id} closes in {days_left}d ({expiry}) and the served "
            f"artifact has {eligible if eligible is not None else 'unknown'} eligible "
            f"regimes, so on that date {consequence}. Decide before then: promote a "
            "candidate whose WF produced round-trips, or record a new dated window.")
    else:
        out["status"] = STATUS_OK
        out["summary"] = (
            f"A4-T1 window on {run_id} closes {expiry} in {days_left}d; the served artifact "
            f"has {eligible if eligible is not None else 'unknown'} eligible regimes, so a "
            f"replacement must be in place by then (alarm starts at {lead_days}d)")
    return out


def format_alert(verdict: dict[str, Any]) -> tuple[str, str, int]:
    """``(title, body, priority)``; callers only alert on non-OK."""
    status = verdict.get("status")
    titles = {STATUS_WARN: "RenQuant 104 SERVING WINDOW closing",
              STATUS_CLOSED: "RenQuant 104 SERVING WINDOW CLOSED — buy path shut",
              STATUS_UNKNOWN: "RenQuant 104 SERVING WINDOW unreadable"}
    body = str(verdict.get("summary", ""))
    extra = {k: verdict.get(k) for k in ("run_id", "expiry", "days_left",
                                         "eligible_regimes", "trained_date")
             if verdict.get(k) is not None}
    if extra:
        body += "\n" + "  ".join(f"{k}={v}" for k, v in extra.items())
    prio = {STATUS_WARN: 4, STATUS_CLOSED: 5, STATUS_UNKNOWN: 4}.get(status, 3)
    return titles.get(status, "RenQuant 104 SERVING WINDOW"), body, prio


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=None)
    ap.add_argument("--artifact", type=Path, default=None,
                    help="served panel artifact (default: <data-root>/backtesting/…/prod/panel-ltr.alpha158_fund.json)")
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD; default today")
    ap.add_argument("--lead-days", type=int, default=DEFAULT_LEAD_DAYS)
    ap.add_argument("--topic", default=DEFAULT_NTFY_TOPIC)
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    data_root = args.data_root or default_data_root()
    artifact = args.artifact or default_artifact_path(data_root)
    today = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()
    try:
        payload = json.loads(Path(artifact).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        verdict = {"status": STATUS_UNKNOWN,
                   "summary": f"served artifact unreadable at {artifact}: "
                              f"{exc.__class__.__name__}"}
    else:
        verdict = evaluate(payload, today=today, lead_days=args.lead_days)
    verdict["artifact"] = str(artifact)
    verdict["as_of"] = today.isoformat()

    title, body, prio = format_alert(verdict)
    alerted = False
    if verdict["status"] != STATUS_OK:
        if args.notify and not args.quiet:
            post_ntfy(title, body, args.topic, priority=prio)
            alerted = True
    verdict["alert"] = {"title": title, "body": body, "sent": alerted}
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return _EXIT.get(verdict["status"], 3)


if __name__ == "__main__":
    sys.exit(main())
