#!/usr/bin/env python3
"""Notifications whose DELIVERY cannot be observed (GOAL-5).

`ops/undelivered_alert_scan.py` finds alarms that were raised and failed to send.
It works by matching the string `ntfy send failed`, which only
``renquant_common.notify.send`` emits. **That covers the Python senders and nothing
else.**

A second population exists. Measured 2026-07-30: **15** umbrella shell scripts post
to ntfy with a bare `curl`, **all 15** discard the result, and **12 of those are
launchd-scheduled**. The canonical line is:

    curl -s -H "Title: $title" -d "$body" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true

Three independent silences in one statement:

* ``-s``               — curl prints no error;
* ``>/dev/null 2>&1``  — anything it did print is discarded;
* ``|| true``          — the exit status is explicitly thrown away.

So a notification from any of these can fail with no log line, no exit code and no
trace of any kind. `undelivered_alert_scan.py` cannot see them: they never emit the
string it looks for. **A send that fails silently is indistinguishable from a send
that was never attempted** — which is exactly how "why didn't I get an alert?"
became unanswerable, and why a scan of this fleet's logs on 2026-07-30 reported
ZERO ntfy sends on a day the operator received several.

**This tool does not fix them.** The scripts live in the umbrella, which this repo
does not write to. It makes the population countable and regression-visible, and
separates the scheduled ones (where a lost alarm matters) from the rest.

    python ops/blind_notifier_scan.py            # human
    python ops/blind_notifier_scan.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

UMBRELLA = Path("/Users/renhao/git/github/RenQuant")
MANIFEST = Path(__file__).resolve().parent / "launchd_manifest.json"

#: How the delivery result gets thrown away. Each is reported separately: they fail
#: differently and a fix might address only one.
SILENCERS = {
    "status_discarded": ("|| true", "||true"),
    "output_discarded": (">/dev/null",),
    # `-s` alone. `-sS` is NOT silent (it keeps errors), so it must not match here
    # or the tool would report a sender that does report as one that does not.
    "curl_silent": ("curl -s ", "curl -s\t"),
}

EXIT_OK, EXIT_FINDINGS, EXIT_UNUSABLE = 0, 1, 2


def scheduled_scripts(manifest: Path) -> set[str]:
    jobs = json.loads(manifest.read_text())["jobs"]
    return {os.path.basename(a) for spec in jobs.values()
            for a in spec["program_args"] if a.endswith(".sh")}


def send_lines(text: str) -> list[str]:
    """Lines that actually POST to ntfy. Comments excluded — a line describing a
    send is not a send, and counting prose is how a scan reports a number nobody
    can act on."""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "ntfy.sh" in line and "curl" in line:
            out.append(raw)
    return out


def classify(line: str) -> list[str]:
    found = []
    for name, needles in SILENCERS.items():
        if any(n in line for n in needles):
            found.append(name)
    return found


def scan(scripts_dir: Path, manifest: Path) -> dict:
    if not scripts_dir.is_dir():
        raise FileNotFoundError(f"scripts dir absent: {scripts_dir}")
    sched = scheduled_scripts(manifest)
    findings, clean = [], []
    for p in sorted(scripts_dir.glob("*.sh")):
        lines = send_lines(p.read_text(errors="ignore"))
        if not lines:
            continue
        silenced = [(l.strip(), classify(l)) for l in lines]
        blind = [(l, c) for l, c in silenced if c]
        rec = {"script": p.name, "scheduled": p.name in sched,
               "send_lines": len(lines), "blind_lines": len(blind),
               "silencers": sorted({c for _, cs in blind for c in cs})}
        (findings if blind else clean).append(rec)
    return {
        "scripts_with_ntfy_sends": len(findings) + len(clean),
        "blind": len(findings),
        "blind_and_scheduled": sum(1 for f in findings if f["scheduled"]),
        "observable": len(clean),
        "findings": findings,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scripts-dir", default=str(UMBRELLA / "scripts"))
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        res = scan(Path(a.scripts_dir), Path(a.manifest))
    except Exception as exc:  # noqa: BLE001
        print(f"UNUSABLE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_UNUSABLE
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"ntfy senders in {a.scripts_dir}: {res['scripts_with_ntfy_sends']}; "
              f"delivery UNOBSERVABLE in {res['blind']} "
              f"({res['blind_and_scheduled']} of them launchd-scheduled)")
        for f in res["findings"]:
            mark = "SCHEDULED" if f["scheduled"] else "         "
            print(f"  {mark}  {f['script']:40} {','.join(f['silencers'])}")
    return EXIT_FINDINGS if res["blind"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
