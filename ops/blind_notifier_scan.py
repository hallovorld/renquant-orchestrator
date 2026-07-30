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

#: THE FINDING PREDICATE. Codex BLOCKER on #646: the first version marked a sender
#: unobservable when it carried ANY ONE of three tokens, and that is materially
#: overbroad. `curl -s` still hands its exit status to the caller. So does a command
#: with stdout redirected. **Neither alone establishes that the result was
#: discarded**, so a count built on `any()` was not tied to the property claimed.
#:
#: Only an explicit status-discarding construct makes the outcome unobservable in
#: the caller's control flow, so that is now NECESSARY. `-s` and `>/dev/null` are
#: reported as ATTRIBUTES of an established finding — they say how much *additional*
#: evidence was destroyed, not whether the finding exists.
#:
#: Re-measured under the strict predicate on 2026-07-30: **15 scripts, 12
#: scheduled** — unchanged, because every one of them carries `|| true`. The number
#: survived the tightening; the reasoning behind it did not, and that is the part
#: that needed fixing.
STATUS_DISCARDERS = ("|| true", "||true", "|| :", "||:", "; true", ";true")

#: SECOND necessary condition, codex round 2 on #646. `|| true` discards the SHELL
#: status, but curl may still write its response or error into the job log — and an
#: error visible in the log IS delivery evidence. Status discard alone therefore
#: establishes "status ignored", NOT "delivery unobservable". Both are required for
#: the strong category, and the weak one is reported separately rather than folded in.
EVIDENCE_SUPPRESSORS = (">/dev/null", "curl -s ", "curl -s\t")

#: A line merely CONTAINING `curl` and `ntfy.sh` can be an echo, a comment fragment,
#: a variable assignment or a GET. The population is only meaningful if every member
#: is an actual POST, so a data/POST flag is required. Measured 2026-07-30: the
#: strict recogniser returns the same 15 scripts as the loose one, so nothing was
#: being counted that should not have been — but the recogniser was not established.
POST_FLAGS = ("-d ", "--data", "-X POST", "-X  POST", "--upload-file", "-T ")

#: Aggravating, never sufficient.
ATTRIBUTES = {
    # `-s` alone. `-sS` is NOT silent (it keeps errors) and must not match, or the
    # tool would describe a sender that does report as one that does not.
    "curl_silent": ("curl -s ", "curl -s\t"),
    "output_discarded": (">/dev/null",),
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
        if is_send(line):
            out.append(raw)
    return out


def is_send(line: str) -> bool:
    """A real POST to ntfy, not a mention of one."""
    return ("ntfy.sh" in line and "curl" in line
            and any(f in line for f in POST_FLAGS))


def discards_status(line: str) -> bool:
    return any(t in line for t in STATUS_DISCARDERS)


def suppresses_evidence(line: str) -> bool:
    return any(t in line for t in EVIDENCE_SUPPRESSORS)


def attributes(line: str) -> list[str]:
    """Extra evidence destroyed, reported only on lines that already qualify."""
    return sorted(n for n, needles in ATTRIBUTES.items()
                  if any(x in line for x in needles))


def scan(scripts_dir: Path, manifest: Path) -> dict:
    if not scripts_dir.is_dir():
        raise FileNotFoundError(f"scripts dir absent: {scripts_dir}")
    sched = scheduled_scripts(manifest)
    findings, clean, status_ignored = [], [], []
    for p in sorted(scripts_dir.glob("*.sh")):
        lines = send_lines(p.read_text(errors="ignore"))
        if not lines:
            continue
        unobs = [l for l in lines if discards_status(l) and suppresses_evidence(l)]
        status_only = [l for l in lines
                       if discards_status(l) and not suppresses_evidence(l)]
        rec = {"script": p.name, "scheduled": p.name in sched,
               "send_lines": len(lines),
               "delivery_unobservable_lines": len(unobs),
               "status_ignored_only_lines": len(status_only),
               "attributes": sorted({a for l in unobs for a in attributes(l)})}
        (findings if unobs else clean).append(rec)
        if status_only:
            status_ignored.append(rec)
    return {
        "scripts_with_ntfy_sends": len(findings) + len(clean),
        # STRONG category: status discarded AND evidence suppressed.
        "delivery_unobservable": len(findings),
        "delivery_unobservable_and_scheduled": sum(1 for f in findings if f["scheduled"]),
        # WEAK category, reported separately per codex: the shell status is thrown
        # away but curl's own output would still reach the job log.
        "status_ignored_only": len(status_ignored),
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
        print(f"ntfy POSTs in {a.scripts_dir}: {res['scripts_with_ntfy_sends']}; "
              f"delivery UNOBSERVABLE (status discarded AND evidence suppressed) in "
              f"{res['delivery_unobservable']} "
              f"({res['delivery_unobservable_and_scheduled']} launchd-scheduled); "
              f"status-ignored-only in {res['status_ignored_only']}")
        for f in res["findings"]:
            mark = "SCHEDULED" if f["scheduled"] else "         "
            attrs = ",".join(f["attributes"]) or "(status discarded only)"
            print(f"  {mark}  {f['script']:40} {attrs}")
    return EXIT_FINDINGS if res["delivery_unobservable"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
