#!/usr/bin/env python3
"""rq105 N1 liveness check (#212 rule: liveness is its own alert, never freshness).

Runs daily after the post-close window. Verifies TODAY's collector outputs exist
and are non-trivial; posts an ntfy alert per missing/empty output. Exit 0 iff all
present. Read-only; touches nothing but its own log line.

Checked (session days only — NYSE calendar via the quote log's own presence):
  logs/rq105/quote_logger_<date>.log        non-empty
  logs/rq105/intraday_pairing_logger_<date>.log  exists
  logs/rq105/entry_timing_shadow_<date>.log      exists
  + the collectors' data outputs under the data root (best-effort glob)
"""
import datetime as dt
import glob
import os
import subprocess
import sys

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
LOGS = os.path.join(RQ, "logs/rq105")


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


def main() -> int:
    today = dt.date.today().isoformat()
    quote_log = os.path.join(LOGS, f"quote_logger_{today}.log")
    if not os.path.exists(quote_log):
        # not a session day OR the logger never started; distinguish by weekday
        if dt.date.today().weekday() < 5:
            _alert("rq105 LIVENESS: quote logger absent",
                   f"{quote_log} missing on a weekday — collector lapsed?")
            return 1
        return 0
    missing = []
    if os.path.getsize(quote_log) == 0:
        missing.append("quote_logger log EMPTY")
    for mod in ("intraday_pairing_logger", "entry_timing_shadow"):
        p = os.path.join(LOGS, f"{mod}_{today}.log")
        if not os.path.exists(p):
            missing.append(f"{mod} log missing")
    data_hits = glob.glob(os.path.join(RQ, "data", "**", f"*{today}*intraday*"),
                          recursive=True) + \
        glob.glob(os.path.join(RQ, "data", "**", f"*rq105*{today}*"),
                  recursive=True)
    if not data_hits:
        missing.append("no dated collector data outputs found (best-effort glob)")
    if missing:
        _alert(f"rq105 LIVENESS: {len(missing)} issue(s) {today}",
               "\n".join(missing))
        print("\n".join(missing))
        return 1
    print(f"rq105 liveness OK {today}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
