#!/usr/bin/env python3
"""Re-runnable census of which log lines can attribute themselves to a run.

WHY THIS EXISTS (codex on orch#676). The first version of this evidence was produced by
an ad-hoc sweep: the committed CSVs carried a BASENAME (`launchd_stdout.log`) and no
digest, so "8,079 lines, 0 self-timestamped" could not be re-derived by anyone, and a
later reader could not tell whether the file they were looking at was the file that was
counted. A number nobody can recompute is an assertion with a citation attached.

This resolves every source path from the INSTALLED plist's `StandardOutPath`, records
the absolute path plus a sha256 of the exact bytes counted, and emits the counts beside
them. Read-only: it opens files, and writes only under the evidence directory it is
told to write to.

WHAT A NIL RESULT HERE MEANS, precisely. A line SELF-ATTRIBUTES iff it begins with an
ISO date, an ISO datetime, or HH:MM:SS, optionally preceded by `[` or `"`. That is a
statement about LEADING timestamps under that stated rule -- NOT proof that attribution
is impossible. A non-leading timestamp, an explicit start/end marker, or an external
index could all attribute a record; this census does not look for them and says nothing
about them.
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
import plistlib
import re
import sys

# A line self-attributes iff it BEGINS with a timestamp. A timestamp elsewhere in the
# line cannot order two lines from different runs, which is the whole question.
SELF_TS = re.compile(
    r"^\s*(?:\[|\")?"
    r"(?:\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}|\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2})")

RULE_PROSE = (
    "a line SELF-ATTRIBUTES iff it begins with an ISO date, an ISO datetime, or "
    "HH:MM:SS, optionally preceded by '[' or '\"'. Nothing else counts: a timestamp "
    "elsewhere in the line cannot order two lines from different runs."
)


def _plutil_load(path: str) -> dict | None:
    """Lenient re-parse via `plutil`, for plists expat refuses.

    Same fallback as `ops/run_surface_drift_check.py`. Deliberately a second
    implementation of a THREE-LINE shell-out rather than an import: this module is a
    standalone census that must run without the drift checker present. Recorded here so
    the duplication is a decision, not drift -- if it grows past this, extract it.
    """
    import subprocess
    try:
        res = subprocess.run(["plutil", "-convert", "xml1", "-o", "-", "--", path],
                             capture_output=True, timeout=30)
        return plistlib.loads(res.stdout) if res.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def installed_plists(agents_dir: str) -> dict:
    """label -> {path, StandardOutPath, plist_sha256}.

    The plist is digested too. It is the thing that decides WHICH file a job writes,
    so a census that pins the log but not the plist cannot tell a changed log from a
    redirected one.
    """
    out = {}
    for f in sorted(glob.glob(os.path.join(agents_dir, "com.renquant.*.plist"))):
        with open(f, "rb") as fh:
            raw = fh.read()
        try:
            d = plistlib.loads(raw)
        except Exception as exc:  # noqa: BLE001
            # `plistlib`'s expat rejects `--` inside an XML comment; two of the
            # heavily-annotated plists contain it, and launchd loads them fine
            # (`launchctl list` shows both). So a parse failure here is a statement
            # about THIS parser, not about the job -- normalize through the lenient
            # `plutil`, exactly as `ops/run_surface_drift_check.py:_plist_load` already
            # does. Without this the census silently under-covered 2 of 40 labels and
            # reported them as "absent", which reads as evidence about the surface.
            d = _plutil_load(f)
            if d is None:
                out[os.path.basename(f)] = {
                    "error": f"unparseable by plistlib AND plutil: "
                             f"{type(exc).__name__}: {exc}"}
                continue
        label = d.get("Label") or os.path.basename(f)
        out[label] = {
            "plist_path": f,
            "plist_sha256": hashlib.sha256(raw).hexdigest(),
            "std_out_path": d.get("StandardOutPath"),
            "std_err_path": d.get("StandardErrPath"),
        }
    return out


def census_file(path: str) -> dict:
    """Count and digest ONE file, or record exactly why it could not be counted.

    Absent is not zero. A missing file yields `present=False` and null counts, never a
    0 that would average in as evidence of a clean surface.
    """
    if not path:
        return {"present": False, "why": "plist declares no StandardOutPath"}
    if not os.path.exists(path):
        return {"present": False, "why": "declared path does not exist"}
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        return {"present": False, "why": f"unreadable: {type(exc).__name__}: {exc}"}
    text = raw.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    hit = sum(1 for ln in lines if SELF_TS.match(ln))
    return {
        "present": True,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "mtime": __import__("datetime").datetime.fromtimestamp(
            os.path.getmtime(path)).isoformat(timespec="seconds"),
        "n_nonblank_lines": len(lines),
        "n_self_timestamped": hit,
        "frac_self_timestamped": (round(hit / len(lines), 4) if lines else None),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agents-dir",
                    default=os.path.expanduser("~/Library/LaunchAgents"))
    ap.add_argument("--out", help="directory to write census.csv / census.json into")
    ap.add_argument("--labels", nargs="*", help="restrict to these labels")
    a = ap.parse_args(argv)

    plists = installed_plists(a.agents_dir)
    if not plists:
        print(f"census: no plists under {a.agents_dir} — the census has no subjects, "
              f"which is not the same as a clean surface", file=sys.stderr)
        return 2

    rows = []
    for label in sorted(plists):
        spec = plists[label]
        if a.labels and label not in a.labels:
            continue
        if "error" in spec:
            rows.append({"label": label, "present": False, "why": spec["error"]})
            continue
        r = {"label": label,
             "std_out_path": spec.get("std_out_path"),
             "plist_path": spec["plist_path"],
             "plist_sha256": spec["plist_sha256"]}
        r.update(census_file(spec.get("std_out_path")))
        rows.append(r)

    counted = [r for r in rows if r.get("present")]
    summary = {
        "matching_rule_prose": RULE_PROSE,
        "matching_rule_regex": SELF_TS.pattern,
        "agents_dir": a.agents_dir,
        "n_labels": len(rows),
        "n_files_counted": len(counted),
        "n_files_absent": len(rows) - len(counted),
        "total_nonblank_lines": sum(r["n_nonblank_lines"] for r in counted),
        "total_self_timestamped": sum(r["n_self_timestamped"] for r in counted),
        "scope_note": (
            "This measures LEADING timestamps only, under the stated rule. It does not "
            "establish that per-run attribution is impossible -- a non-leading "
            "timestamp, an explicit start/end marker or an external index could each "
            "attribute a record, and none of those was searched for."),
    }

    if a.out:
        os.makedirs(a.out, exist_ok=True)
        cols = ["label", "std_out_path", "present", "why", "sha256", "bytes", "mtime",
                "n_nonblank_lines", "n_self_timestamped", "frac_self_timestamped",
                "plist_path", "plist_sha256"]
        with open(os.path.join(a.out, "census.csv"), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        with open(os.path.join(a.out, "census.json"), "w", encoding="utf-8") as fh:
            json.dump({"summary": summary, "rows": rows}, fh, indent=2, sort_keys=True)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
