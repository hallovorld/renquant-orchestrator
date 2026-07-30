#!/usr/bin/env python3
"""Which scheduled jobs have EVIDENCE of running, judged against their own cadence.

GOAL-5, issue #621. Four of the six rq105 jobs had 0-byte stdout last written
2026-07-02 … 07-06 while being scheduled every weekday — roughly 17-19 missed
firings each — and nothing surfaced it. The existing sentinel checks nonzero
`launchctl` exit codes, which those four do not have: three exited 0 and one exited 1.
A job that silently stops firing produces no nonzero exit at all, so exit codes cannot
detect it.

**The measurement this adds:** for every job in the reviewed manifest, how many
scheduled firings have elapsed since its log was last written. Staleness is judged
**against the job's own `StartCalendarInterval`**, never a fixed number of days — a
weekly job is not stale at three days and a weekday job is stale at three. Getting that
wrong is the recurring defect on this programme: a check whose subject is not the object
the reader assumes.

**What it deliberately does NOT claim.** #621 states it plainly and this tool honours
it: *0-byte stdout does not by itself prove a job did not run.* A job can run and write
nothing. So the classes below say **"no evidence"**, never "did not run". The remedy for
the ambiguity is a positive liveness record (see the receipt mechanism added for the
rq104 sentinel), not a stronger inference from an absence.

Classes:

* ``EVIDENCE_FRESH`` — the log was written within the tolerance of its schedule.
* ``NO_EVIDENCE_STALE`` — N expected firings have elapsed with no write. Reported with
  N. Does **not** prove the job did not run.
* ``UNJUDGEABLE_NO_LOG_PATH`` — the plist declares no ``StandardOutPath``, so this job
  can **never** be judged this way. Structurally invisible, which is worse than stale.
* ``UNJUDGEABLE_NO_SCHEDULE`` — no ``StartCalendarInterval``. A ``KeepAlive`` or
  ``WatchPaths`` job has no cadence, so "missed firings" is undefined for it; measuring
  it against a calendar would be validating the wrong object.
* ``UNJUDGEABLE_NO_PLIST`` — manifested but no plist on disk.

**Read-only.** Reads plists, stats log files, and queries ``launchctl list``. Writes
nothing, never invokes git, never touches a log.

Exit codes: ``0`` every judgeable job is fresh and nothing is unjudgeable, ``1``
otherwise, ``2`` usage/IO error — so a broken invocation cannot read as a clean scan.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

MANIFEST = Path(__file__).resolve().parent / "launchd_manifest.json"
AGENTS_DIR = Path(os.path.expanduser("~/Library/LaunchAgents"))

#: A job is stale only after this many expected firings have been missed. One miss can
#: be a boundary artifact — the scan running minutes before a firing, a log flushed
#: late, a holiday the calendar entry does not know about. Two consecutive misses is a
#: pattern. #621's four dead jobs had missed 17-19, so this bound is not what hid them.
MISSED_FIRINGS_TOLERANCE = 2

EVIDENCE_FRESH = "EVIDENCE_FRESH"
NO_EVIDENCE_STALE = "NO_EVIDENCE_STALE"
UNJUDGEABLE_NO_LOG_PATH = "UNJUDGEABLE_NO_LOG_PATH"
UNJUDGEABLE_NO_SCHEDULE = "UNJUDGEABLE_NO_SCHEDULE"
UNJUDGEABLE_NO_PLIST = "UNJUDGEABLE_NO_PLIST"

UNJUDGEABLE = (UNJUDGEABLE_NO_LOG_PATH, UNJUDGEABLE_NO_SCHEDULE, UNJUDGEABLE_NO_PLIST)


def load_plist(path: Path,
               plutil_runner: Callable[[list[str]], bytes] | None = None) -> dict:
    """Load a plist the way **launchd** does, not merely the way Python does.

    Python's `plistlib` uses expat, which rejects `--` inside an XML comment. Two of
    this manifest's plists carry a prose comment block with a `---` underline, so
    `plistlib` raises `ExpatError` on files that `plutil -lint` reports as **OK** and
    that launchd loads fine.

    I nearly shipped that as a finding — "2 plists are malformed XML, launchd cannot
    load them" — which would have been FALSE and would have sent someone to fix files
    that are not broken. The object this tool must read is the one launchd reads, so
    Apple's own parser is the fallback. Raises only when BOTH parsers fail.
    """
    try:
        with path.open("rb") as fh:
            return plistlib.load(fh)
    except Exception:  # noqa: BLE001
        run = plutil_runner or (lambda argv: subprocess.run(
            argv, capture_output=True, timeout=20).stdout)
        raw = run(["plutil", "-convert", "xml1", "-o", "-", str(path)])
        if not raw:
            raise
        return plistlib.loads(raw)


def decode_launchd_status(status: int | None) -> dict[str, Any]:
    """launchd's LastExitStatus is a raw wait status, not an exit code.

    `256` means exit code 1, `512` exit 2, `768` exit 3. Reporting the raw number
    invites a reader to treat 768 as an exit code, which it is not, and to conclude
    nothing at all from it.
    """
    if status is None:
        return {"raw": None, "exit_code": None, "signal": None}
    return {"raw": status, "exit_code": status >> 8, "signal": status & 0x7F}


def manifest_labels(path: Path | None = None) -> list[str]:
    """The reviewed job set, in manifest order."""
    raw = json.loads((path or MANIFEST).read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [entry[0] if isinstance(entry, (list, tuple)) else str(entry)
                for entry in raw]
    jobs = raw.get("jobs", raw)
    if isinstance(jobs, list):
        return [e[0] if isinstance(e, (list, tuple)) else str(e) for e in jobs]
    return sorted(jobs)


def schedule_entries(plist: dict) -> list[dict] | None:
    """Normalise ``StartCalendarInterval`` to a list, or None when absent.

    launchd accepts either a single dict or a list of them; treating only the list form
    as scheduled would silently mark every single-entry job unjudgeable.
    """
    sched = plist.get("StartCalendarInterval")
    if sched is None:
        return None
    if isinstance(sched, dict):
        return [sched]
    if isinstance(sched, list) and sched:
        return [e for e in sched if isinstance(e, dict)] or None
    return None


def expected_firings(entries: list[dict], since: dt.datetime,
                     until: dt.datetime) -> int:
    """Count scheduled firings in the half-open interval (since, until].

    A missing ``Weekday`` means every day; a missing ``Hour``/``Minute`` means every
    hour/minute, which would be an enormous count — so those are treated as 0, matching
    how every plist in this manifest is actually written and keeping the count finite.
    launchd's Weekday is 0-or-7 for Sunday; Python's weekday() is Monday=0, so the
    conversion is explicit rather than assumed.
    """
    if until <= since:
        return 0
    count = 0
    day = since.date()
    last_day = until.date()
    while day <= last_day:
        py_wd = day.weekday()              # Mon=0 … Sun=6
        launchd_wd = 0 if py_wd == 6 else py_wd + 1   # Sun=0, Mon=1 … Sat=6
        for e in entries:
            wd = e.get("Weekday")
            if wd is not None:
                wanted = 0 if int(wd) == 7 else int(wd)
                if wanted != launchd_wd:
                    continue
            fire = dt.datetime.combine(
                day, dt.time(int(e.get("Hour", 0)), int(e.get("Minute", 0))))
            if since < fire <= until:
                count += 1
        day += dt.timedelta(days=1)
    return count


def _launchctl_last_exit(label: str,
                         runner: Callable[[list[str]], str] | None = None) -> int | None:
    """LastExitStatus from ``launchctl list <label>``, or None if unavailable."""
    run = runner or (lambda argv: subprocess.run(
        argv, capture_output=True, text=True, timeout=20).stdout)
    try:
        out = run(["launchctl", "list", label])
    except Exception:  # noqa: BLE001
        return None
    for line in (out or "").splitlines():
        if "LastExitStatus" in line:
            digits = "".join(c for c in line if c.isdigit() or c == "-")
            try:
                return int(digits)
            except ValueError:
                return None
    return None


def scan_job(label: str, *, now: dt.datetime,
             agents_dir: Path = AGENTS_DIR,
             launchctl_runner: Callable[[list[str]], str] | None = None) -> dict[str, Any]:
    """Classify one job. Never raises."""
    out: dict[str, Any] = {"label": label}
    plist_path = agents_dir / f"{label}.plist"
    if not plist_path.exists():
        out.update(status=UNJUDGEABLE_NO_PLIST,
                   detail=f"manifested but no plist at {plist_path}")
        return out
    try:
        plist = load_plist(plist_path)
    except Exception as exc:  # noqa: BLE001
        out.update(status=UNJUDGEABLE_NO_PLIST,
                   detail=f"plist unreadable by BOTH plistlib and plutil: "
                          f"{type(exc).__name__}: {exc}")
        return out

    raw_exit = _launchctl_last_exit(label, launchctl_runner)
    out["last_exit"] = raw_exit
    out["last_exit_decoded"] = decode_launchd_status(raw_exit)

    log_path = plist.get("StandardOutPath")
    if not log_path:
        out.update(status=UNJUDGEABLE_NO_LOG_PATH,
                   detail="plist declares no StandardOutPath — this job can never be "
                          "judged by log freshness")
        return out
    out["log"] = log_path

    entries = schedule_entries(plist)
    if entries is None:
        out.update(status=UNJUDGEABLE_NO_SCHEDULE,
                   detail="no StartCalendarInterval — cadence undefined, so missed "
                          "firings is not a meaningful measure for this job")
        return out
    out["schedule_entries"] = len(entries)

    p = Path(log_path)
    if not p.exists():
        out.update(status=NO_EVIDENCE_STALE, missed_firings=None, size_bytes=None,
                   detail="log path declared but absent — no evidence of any run "
                          "(does NOT prove the job never ran)")
        return out

    st = p.stat()
    out["size_bytes"] = st.st_size
    last_write = dt.datetime.fromtimestamp(st.st_mtime)
    out["last_write"] = last_write.isoformat(timespec="seconds")
    missed = expected_firings(entries, last_write, now)
    out["missed_firings"] = missed

    if missed >= MISSED_FIRINGS_TOLERANCE:
        out.update(status=NO_EVIDENCE_STALE,
                   detail=f"{missed} scheduled firings have elapsed since the log was "
                          f"last written ({out['last_write']}), size {st.st_size}B — no "
                          f"evidence of running (does NOT prove it did not run)")
    else:
        out["status"] = EVIDENCE_FRESH
    return out


def scan(labels: Iterable[str], *, now: dt.datetime | None = None,
         agents_dir: Path = AGENTS_DIR,
         launchctl_runner: Callable[[list[str]], str] | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now()
    results = [scan_job(lbl, now=now, agents_dir=agents_dir,
                        launchctl_runner=launchctl_runner) for lbl in labels]
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "scanned_at": now.isoformat(timespec="seconds"),
        "missed_firings_tolerance": MISSED_FIRINGS_TOLERANCE,
        "jobs": len(results),
        "counts": counts,
        "results": results,
    }


def _format(report: dict[str, Any]) -> str:
    lines = [f"launchd liveness scan at {report['scanned_at']} "
             f"({report['jobs']} manifested jobs, tolerance "
             f"{report['missed_firings_tolerance']} missed firings)", ""]
    for r in report["results"]:
        if r["status"] == EVIDENCE_FRESH:
            continue
        lines.append(f"{r['status']:26} {r['label']}")
        lines.append(f"{'':26}   {r.get('detail','')}")
        dec = r.get("last_exit_decoded") or {}
        if dec.get("raw") not in (None, 0):
            lines.append(
                f"{'':26}   launchctl LastExitStatus raw={dec['raw']} "
                f"=> exit code {dec['exit_code']}"
                + (f", signal {dec['signal']}" if dec.get("signal") else ""))
    fresh = report["counts"].get(EVIDENCE_FRESH, 0)
    lines += ["", "  ".join(f"{k}={v}" for k, v in sorted(report["counts"].items()))]
    lines.append(f"(fresh={fresh}/{report['jobs']})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        labels = manifest_labels(args.manifest)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: cannot read the launchd manifest: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2
    if not labels:
        print("FATAL: manifest lists no jobs — nothing was checked", file=sys.stderr)
        return 2
    report = scan(labels)
    print(json.dumps(report, indent=2) if args.json else _format(report))
    bad = sum(v for k, v in report["counts"].items() if k != EVIDENCE_FRESH)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
