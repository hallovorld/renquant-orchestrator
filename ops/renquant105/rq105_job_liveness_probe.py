#!/usr/bin/env python3
"""Is an rq105 launchd job alive? Ask its PRODUCT, not its StandardOutPath.

WHY (measured 2026-08-05): orch#621 reported four rq105 jobs silent for ~28 days
— "roughly 17–19 missed weekday firings each" — on the evidence of a 0-byte
`StandardOutPath` read from each plist. The plist reading was careful. The
OBJECT was wrong: these wrappers redirect their own output to a DATED log
(`>> "$LOG_DIR/<job>_$TS.log"`), so `StandardOutPath` stays 0 bytes forever
whether or not the job runs.

Measured the same day, the jobs had all run the previous session:

    quote_logger_2026-08-04.log            intraday_ticks.jsonl   709 MB, 12:59
    entry_timing_shadow_2026-08-04.log     entry_timing_shadow    12.4 MB, 13:15
    batch_scores_export_2026-08-04.log     batch_scores_...json   06:15
    shadow_serving_2026-08-04.log          (SKIP not-wired, by design)

So this probe asks two questions a 0-byte file cannot answer: **did the job
write its dated log for the session**, and **is the artefact it exists to
produce fresh**. A job whose log is fresh but whose product is stale is a
DIFFERENT fault from a job that never ran, and they are reported differently.

Read-only. Usage:
    python ops/renquant105/rq105_job_liveness_probe.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import sys

REPO = pathlib.Path(os.environ.get("RENQUANT_REPO_ROOT",
                                   "/Users/renhao/git/github/RenQuant"))
LOGS = REPO / "logs" / "rq105"
PILOT = REPO / "logs" / "renquant105_pilot"
DATA = REPO / "data" / "rq105"

# (job, dated-log stem, product path or None, product description)
# The product is the thing the job EXISTS to produce. `None` means the job has
# no artefact of its own — it is judged on its dated log alone, and that is
# recorded rather than silently treated as healthy.
JOBS = (
    ("rq105-quote-logger", "quote_logger",
     PILOT / "intraday_ticks.jsonl", "intraday tick feed"),
    ("rq105-postclose", "entry_timing_shadow",
     PILOT / "entry_timing_shadow.jsonl", "post-close entry-timing shadow"),
    ("rq105-postclose-pairing", "intraday_pairing_logger",
     PILOT / "paired_is.jsonl", "paired implementation-shortfall rows"),
    ("rq105-batch-scores-export", "batch_scores_export",
     None, "dated batch_scores_<date>.json (checked per date)"),
    ("rq105-session-scheduler", "session_scheduler", None, "drives the loop"),
    ("rq105-shadow-serving", "shadow_serving", None,
     "SKIPs by design until the Stage-3 producer exists (#221)"),
)

STATE_RAN = "RAN"
STATE_NO_LOG = "NO_LOG_FOR_SESSION"
STATE_STALE_PRODUCT = "PRODUCT_STALE"
ACTIONABLE = (STATE_NO_LOG, STATE_STALE_PRODUCT)


def _mtime(path: pathlib.Path):
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def probe(date: str) -> list[dict]:
    out = []
    for job, stem, product, description in JOBS:
        log = LOGS / f"{stem}_{date}.log"
        log_at = _mtime(log)
        row = {"job": job, "log": log.name, "log_written_at": None,
               "product": str(product) if product else None,
               "product_description": description,
               "product_fresh_at": None, "state": STATE_NO_LOG,
               "detail": f"no {log.name} — the job did not write its dated log "
                         f"for this session"}
        if log_at is None:
            out.append(row)
            continue
        row["log_written_at"] = log_at.strftime("%Y-%m-%d %H:%M")
        row["state"], row["detail"] = STATE_RAN, "dated log written for this session"
        if product is not None:
            p_at = _mtime(product)
            row["product_fresh_at"] = p_at.strftime("%Y-%m-%d %H:%M") if p_at else None
            if p_at is None:
                row["state"] = STATE_STALE_PRODUCT
                row["detail"] = (f"the job ran but its product is ABSENT: "
                                 f"{product} ({description})")
            elif p_at.date().isoformat() < date:
                row["state"] = STATE_STALE_PRODUCT
                row["detail"] = (f"the job ran but its product last changed "
                                 f"{p_at:%Y-%m-%d %H:%M} — older than the session "
                                 f"({description})")
        out.append(row)
    return out


def render(rows: list[dict], date: str) -> str:
    lines = [f"rq105 job liveness by PRODUCT — session {date}", ""]
    for r in rows:
        lines.append(f"[{r['state']}] {r['job']}: {r['detail']}")
        if r["log_written_at"]:
            lines.append(f"    log {r['log']} @ {r['log_written_at']}"
                         + (f" · product @ {r['product_fresh_at']}"
                            if r["product_fresh_at"] else ""))
    n = sum(1 for r in rows if r["state"] in ACTIONABLE)
    lines.append("")
    lines.append(f"rq105 PROBE: {n} actionable job state(s) on {date}"
                 if n else f"rq105 PROBE: all {len(rows)} jobs ran on {date}")
    lines.append("NOTE: StandardOutPath is NOT the object — these wrappers "
                 "redirect to a dated log,\n      so a 0-byte StandardOutPath "
                 "says nothing about whether the job ran.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args(argv)
    rows = probe(args.date)
    print(render(rows, args.date))
    return 1 if any(r["state"] in ACTIONABLE for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
