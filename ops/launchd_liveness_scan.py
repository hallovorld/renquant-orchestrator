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
import glob
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

#: Every StartCalendarInterval key this function implements. Anything else REFUSES rather
#: than being ignored — see `expected_firings`.
SUPPORTED_SCHEDULE_KEYS = frozenset({"Minute", "Hour", "Day", "Weekday", "Month"})


class UnsupportedScheduleKey(ValueError):
    """A plist constrains firing by a key `expected_firings` does not implement."""


EVIDENCE_FRESH = "EVIDENCE_FRESH"
NO_EVIDENCE_STALE = "NO_EVIDENCE_STALE"

#: Corroboration verdicts, added 2026-08-01. `NO_EVIDENCE_STALE` is judged on the plist's
#: `StandardOutPath`, and many jobs here never write it -- they write a DATED log beside
#: it. Measured on this machine: **21 of 21** stale verdicts had newer material in the
#: job's own log directory, so the bucket was 100% noise and the scan trained its reader
#: to skip it.
#:
#: These are deliberately NOT "EVIDENCE_FRESH". The proxy surface still says nothing; all
#: that is established is that SOMETHING wrote in that directory. Promoting it to fresh
#: would be the same error in the other direction -- and for a shared directory it would
#: be plainly wrong, since the writer may be a different job entirely.
STALE_BUT_SIBLING_FILE_IS_NEWER = "STALE_BUT_SIBLING_FILE_IS_NEWER"
STALE_AMBIGUOUS_SHARED_LOG_DIR = "STALE_AMBIGUOUS_SHARED_LOG_DIR"
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

    A missing ``Weekday``/``Day``/``Month`` means every one of them; a missing
    ``Hour``/``Minute`` means every hour/minute, which would be an enormous count — so
    those are treated as 0, matching how every plist in this manifest is actually written
    and keeping the count finite. launchd's Weekday is 0-or-7 for Sunday; Python's
    weekday() is Monday=0, so the conversion is explicit rather than assumed.

    ``Day`` WAS NOT IMPLEMENTED, AND MONTHLY JOBS PAID FOR IT `[measured 2026-08-01]`.
    This honoured ``Weekday`` and silently ignored ``Day``, so a plist reading
    ``{Day: 1, Hour: 3}`` — fire on the 1st of the month — was counted as firing EVERY
    DAY. `com.renquant.monthly-calibrator-refresh` was reported **60 firings stale** over
    an interval containing **2** of its actual firings, and every monthly job went stale
    two days after each successful run.

    THE DEFAULT IS NOW INVERTED. An unrecognised ``StartCalendarInterval`` key raises
    `UnsupportedScheduleKey` instead of being skipped. Enumerating the keys you know and
    ignoring the rest is the shape that produced this: the next key nobody implements
    (``Month`` was also missing) inflates the count silently, and an inflated count reads
    as a dead job.
    """
    unknown = {k for e in entries for k in e} - SUPPORTED_SCHEDULE_KEYS
    if unknown:
        raise UnsupportedScheduleKey(
            f"StartCalendarInterval keys not implemented: {sorted(unknown)}. Refusing to "
            f"count firings rather than ignoring them — an ignored constraint inflates "
            f"the count and an inflated count reads as a dead job.")
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
            dom = e.get("Day")
            if dom is not None and int(dom) != day.day:
                continue
            mon = e.get("Month")
            if mon is not None and int(mon) != day.month:
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


def evidence_surface(label: str, plist: dict, manifest_entry: dict | None) -> tuple[str | None, str]:
    """(path to measure, which surface it is).

    **StandardOutPath is a PROXY, and for some jobs it is the wrong object.** launchd
    puts whatever the process writes to fd 1 there; a wrapper that redirects into its
    own dated file leaves that path untouched forever, so its mtime measures the last
    time the wrapper failed to redirect — not the last time the job ran.

    Measured 2026-07-30: `rq105-session-scheduler` and `rq105-quote-logger` create
    `logs/rq105/<name>_<date>.log` on **every session day** (newest dated 2026-07-30
    06:25) while their launchd stdout had not been touched since 2026-07-03/06. Scored
    on `StandardOutPath` they read as 18–19 missed firings; they had missed none. I
    filed that wrong reading myself as issue #621.

    So a manifest entry may declare ``evidence_glob`` — the job's real output surface —
    and it wins. Where it is absent the scan falls back to ``StandardOutPath`` and
    **says so**, because a proxy measurement labelled as a direct one is how the wrong
    reading got published in the first place.
    """
    glob_pat = (manifest_entry or {}).get("evidence_glob")
    if glob_pat:
        matches = glob.glob(os.path.expanduser(glob_pat))
        if matches:
            return max(matches, key=lambda p: os.path.getmtime(p)), "evidence_glob"
        return None, "evidence_glob (no match)"
    out = plist.get("StandardOutPath")
    return (out, "StandardOutPath (PROXY)") if out else (None, "none")


def scan_job(label: str, *, now: dt.datetime,
             agents_dir: Path = AGENTS_DIR,
             manifest_entry: dict | None = None,
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

    log_path, surface = evidence_surface(label, plist, manifest_entry)
    out["evidence_surface"] = surface
    out["evidence_is_proxy"] = surface.endswith("(PROXY)")
    if not log_path:
        out.update(status=UNJUDGEABLE_NO_LOG_PATH,
                   detail=f"no evidence surface ({surface}) — this job can never be "
                          f"judged by log freshness. Declare an evidence_glob in the "
                          f"manifest naming the file the job actually writes")
        return out
    out["log"] = log_path

    entries = schedule_entries(plist)
    if entries is None:
        out.update(status=UNJUDGEABLE_NO_SCHEDULE,
                   detail="no StartCalendarInterval — cadence undefined, so missed "
                          "firings is not a meaningful measure for this job")
        return out
    out["schedule_entries"] = len(entries)
    # Kept for `corroborate()`: re-deriving the cadence there would be a second
    # implementation of the same parse, and those drift.
    out["_schedule_entries_parsed"] = entries

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
    try:
        missed = expected_firings(entries, last_write, now)
    except UnsupportedScheduleKey as exc:
        out.update(status=UNJUDGEABLE_NO_SCHEDULE, detail=str(exc))
        return out
    out["missed_firings"] = missed

    if missed >= MISSED_FIRINGS_TOLERANCE:
        out.update(status=NO_EVIDENCE_STALE,
                   detail=f"{missed} scheduled firings have elapsed since the log was "
                          f"last written ({out['last_write']}), size {st.st_size}B — no "
                          f"evidence of running (does NOT prove it did not run)")
    else:
        out["status"] = EVIDENCE_FRESH
    return out


def corroborate(results: list[dict[str, Any]], *, now: dt.datetime | None = None,
                agents_dir: Path = AGENTS_DIR) -> None:
    """Re-judge `NO_EVIDENCE_STALE` against the job's own log DIRECTORY, in place.

    WHY. The verdict is computed from the plist's `StandardOutPath`, which many of these
    jobs never write -- they write `<logdir>/<date>.log` instead, leaving the declared
    file empty and frozen forever. Measured 2026-08-01: 21 of 21 stale verdicts had newer
    material in their own directory, i.e. the entire bucket was noise.

    WHY NOT JUST TAKE THE NEWEST FILE. Because several jobs SHARE a log directory, and
    the newest file there may belong to a neighbour. Attributing it would be the same
    defect the registry exists for -- a check passing on evidence about a different
    object. So a shared directory yields AMBIGUOUS, never a liveness claim.
    """
    now = now or dt.datetime.now()
    dir_owners: dict[str, set[str]] = {}
    for r in results:
        if r.get("log"):
            dir_owners.setdefault(os.path.realpath(os.path.dirname(r["log"])),
                                  set()).add(r["label"])

    for r in results:
        if r["status"] != NO_EVIDENCE_STALE or not r.get("log"):
            continue
        # A job judged on its OWN `evidence_glob` is already attributed, so none of the
        # corroboration below applies to it. Everything in this function exists to
        # qualify a verdict computed from a PROXY surface; running it over an attributed
        # verdict does the opposite of its purpose.
        #
        # Measured 2026-08-01: `rq105-shadow-serving` declares
        # `evidence_glob=.../shadow_serving_*.log`, the glob resolved its own newest file
        # (shadow_serving_2026-07-13.log, 2048B), and this loop then demoted the finding
        # to STALE_AMBIGUOUS_SHARED_LOG_DIR — because five neighbours share the directory
        # — and advised the operator to "declare an `evidence_glob`" that had been
        # declared all along. The job has written nothing for 14 scheduled firings; that
        # is a definite finding, and "ambiguous" reads as "we cannot tell".
        #
        # The shared directory is irrelevant once a glob names this job's files: the
        # attribution the AMBIGUOUS state protects against has already been made.
        if r.get("evidence_surface") == "evidence_glob":
            continue
        d = Path(r["log"]).parent
        owners = dir_owners.get(os.path.realpath(d), set())
        if len(owners) > 1:
            r["status"] = STALE_AMBIGUOUS_SHARED_LOG_DIR
            r["shared_log_dir_owners"] = sorted(owners)
            r["detail"] += (f" | {len(owners)} manifested jobs write to {d}, so no file "
                            f"there can be attributed to this one. Declare an "
                            f"`evidence_glob` in the manifest to make this judgeable.")
            continue
        newest_t, newest_n = None, None
        try:
            for f in d.iterdir():
                if not f.is_file() or f.name == Path(r["log"]).name:
                    continue
                if f.stat().st_size == 0:
                    continue
                m = f.stat().st_mtime
                if newest_t is None or m > newest_t:
                    newest_t, newest_n = m, f.name
        except OSError:
            continue
        if newest_t is None:
            continue
        watched = 0.0
        try:
            watched = Path(r["log"]).stat().st_mtime
        except OSError:
            pass
        if newest_t <= watched:
            continue
        # THE SIBLING MUST ITSELF BE FRESH `[caught before the PR]`. The first version
        # moved every job with ANY newer sibling out of the stale bucket -- which
        # rescued `daily103`, whose newest file is 94 DAYS old. A corroboration that
        # promotes a dead job because its corpse is newer than its headstone is the
        # fail-open version of the very defect being fixed.
        entries_ = r.get("_schedule_entries_parsed")
        if entries_ is not None:
            try:
                missed_sib = expected_firings(
                    entries_, dt.datetime.fromtimestamp(newest_t), now)
            except UnsupportedScheduleKey:
                continue
            if missed_sib >= MISSED_FIRINGS_TOLERANCE:
                r["sibling_evidence"] = newest_n
                r["sibling_missed_firings"] = missed_sib
                r["detail"] += (
                    f" | the newest file in that directory ({newest_n}) is ITSELF "
                    f"{missed_sib} firings stale, so this stays STALE.")
                continue
        r["status"] = STALE_BUT_SIBLING_FILE_IS_NEWER
        r["sibling_evidence"] = newest_n
        r["sibling_last_write"] = dt.datetime.fromtimestamp(
            newest_t).isoformat(timespec="seconds")
        r["detail"] += (f" | but {newest_n} in the same directory was written "
                        f"{r['sibling_last_write']}. This is NOT a liveness claim: the "
                        f"declared surface still shows nothing, and only an "
                        f"`evidence_glob` naming the file this job writes can settle it.")


def scan(labels: Iterable[str], *, now: dt.datetime | None = None,
         agents_dir: Path = AGENTS_DIR,
         manifest_entries: dict[str, dict] | None = None,
         launchctl_runner: Callable[[list[str]], str] | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now()
    entries = manifest_entries or {}
    results = [scan_job(lbl, now=now, agents_dir=agents_dir,
                        manifest_entry=entries.get(lbl),
                        launchctl_runner=launchctl_runner) for lbl in labels]
    corroborate(results, now=now, agents_dir=agents_dir)
    for r in results:
        r.pop("_schedule_entries_parsed", None)   # internal, never published
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "scanned_at": now.isoformat(timespec="seconds"),
        "missed_firings_tolerance": MISSED_FIRINGS_TOLERANCE,
        "jobs": len(results),
        "measured_by_proxy": sum(1 for r in results if r.get("evidence_is_proxy")),
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
    try:
        raw = json.loads(args.manifest.read_text(encoding="utf-8"))
        entries = ({k: v for k, v in raw} if isinstance(raw, list)
                   else raw.get("jobs", raw))
        if not isinstance(entries, dict):
            entries = {}
    except Exception:  # noqa: BLE001
        entries = {}
    report = scan(labels, manifest_entries=entries)
    print(json.dumps(report, indent=2) if args.json else _format(report))
    bad = sum(v for k, v in report["counts"].items() if k != EVIDENCE_FRESH)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
