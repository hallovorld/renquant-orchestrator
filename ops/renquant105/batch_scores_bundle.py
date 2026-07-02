"""Shared canonical-hash + verification logic for the rq105 frozen batch-score
bundle (score JSON + meta JSON). A single implementation used by BOTH the
producer (export_batch_scores.py, at write time) and the consumer
(run_shadow_serving.sh, via verify_bundle_cli, at read time) so the two sides
can never independently drift out of agreement on what "the hash" means
(Codex #236 round 2 — replay previously trusted session_date/run_id with no
verification that the on-disk bundle was actually today's or unmodified).

NOTE ON ATOMICITY (Codex #236 round 3): the score and meta files are each
written atomically (temp+fsync+rename) but are NOT a single atomic
transaction as a PAIR — there is a window between the two renames where only
one of the two files reflects the new export. This module does not attempt
true cross-file atomicity; instead, `verify_bundle` fails closed on any
inconsistency between them (mismatched hash, wrong/missing source_run_date)
so a reader can never be fooled by a partially-updated pair, even though the
write itself is not a single transaction."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys


def canonical_hash(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def expected_previous_session(
    today_iso: str, *, calendar_name: str = "NYSE", lookback_days: int = 14
) -> str:
    """The most recent NYSE trading-day strictly before `today_iso`
    (weekend/holiday aware). Same primitive (pandas_market_calendars) used
    elsewhere this session (intraday_quote_logger.NyseSessionCalendar,
    renquant_execution.preopen_cancel_gate). `lookback_days` bounds the query
    window — NYSE never has more than a handful of consecutive non-trading
    days, 14 is a generous margin. Raises ValueError if no session is found
    in that window (fail closed rather than silently returning nothing)."""
    import pandas_market_calendars as mcal  # noqa: PLC0415

    today = dt.date.fromisoformat(today_iso)
    cal = mcal.get_calendar(calendar_name)
    start = today - dt.timedelta(days=lookback_days)
    end = today - dt.timedelta(days=1)
    valid_days = cal.valid_days(start_date=start.isoformat(), end_date=end.isoformat())
    if len(valid_days) == 0:
        raise ValueError(
            f"no {calendar_name} session found in the {lookback_days}-day "
            f"window before {today_iso} (fail-closed)"
        )
    return valid_days[-1].date().isoformat()


def verify_bundle(score_path: str, meta_path: str, *, today: str) -> tuple[bool, str]:
    """Return (ok, reason). Checks: the meta's session_date is today; the
    meta's source_run_date is genuinely the immediately preceding NYSE
    session (Codex #236 round 3 — export previously accepted the latest
    qualifying run from ANY date before today, so a multi-day pipeline outage
    could silently republish a stale vector re-stamped as today's; this is a
    replay-side defense-in-depth check on top of the export-side fix); and
    the meta's recorded score_content_sha256 matches a fresh hash of the
    score file currently on disk — catches a stale leftover bundle from a
    prior day that was never cleaned up, or an on-disk score file that was
    corrupted/modified after export without a matching meta update."""
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"cannot read/parse meta {meta_path}: {exc}"

    session_date = meta.get("session_date")
    if session_date != today:
        return False, (
            f"stale bundle: meta.session_date={session_date!r} != today={today!r} "
            "(a prior day's export was never cleaned up, or today's export "
            "has not run yet)"
        )

    source_run_date = meta.get("source_run_date")
    if not source_run_date:
        return False, "meta has no source_run_date — bundle predates the freshness fix, refuse"
    try:
        expected_source_date = expected_previous_session(today)
    except ValueError as exc:
        return False, f"cannot compute expected prior session: {exc}"
    if source_run_date != expected_source_date:
        return False, (
            f"stale source: meta.source_run_date={source_run_date!r} != "
            f"expected prior session={expected_source_date!r} (the underlying "
            "pipeline run this bundle was exported from is not from the "
            "immediately preceding session — a multi-day pipeline outage may "
            "have caused an old run to be re-stamped as today's)"
        )

    expected_hash = meta.get("score_content_sha256")
    if not expected_hash:
        return False, "meta has no score_content_sha256 — bundle predates hashing, refuse"

    try:
        with open(score_path) as f:
            scores = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"cannot read/parse score file {score_path}: {exc}"

    actual_hash = canonical_hash(scores)
    if actual_hash != expected_hash:
        return False, (
            f"score content hash mismatch: on-disk={actual_hash} "
            f"meta-recorded={expected_hash} (corruption or tampering "
            "between export and replay)"
        )
    return True, "ok"


def _cli(argv: list[str]) -> int:
    """python3 -m batch_scores_bundle verify <scores.json> <meta.json> <today-iso>
    exits 0 if the bundle is valid for `today`, 1 otherwise (message on stderr)."""
    if len(argv) != 4 or argv[0] != "verify":
        print("usage: batch_scores_bundle.py verify <scores.json> <meta.json> <today-iso>",
              file=sys.stderr)
        return 2
    _, score_path, meta_path, today = argv
    ok, reason = verify_bundle(score_path, meta_path, today=today)
    print(reason, file=sys.stderr if not ok else sys.stdout)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
