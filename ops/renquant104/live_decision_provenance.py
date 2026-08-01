#!/usr/bin/env python3
"""What the live daily record says about WHICH model decided — and what it omits. (AC6)

AC6 R4's bundle gap is CLOSED — merged PR #685 added `wf_gate_provenance.py` and wired it
into `daily.py`. This is NOT that. `daily.py` does not write
`RenQuant/live/logs/renquant-104/<date>.json`; the intraday runners do, and that trade log
is a different surface with a different contract.

MEASURED 2026-08-01 over the 14 live per-date records in
`RenQuant/live/logs/renquant-104/2026-07-*.json` (63 decision rows):

  * **0 of 14** carry `operator_authorized_override`, `gate_verdict_before_override` or
    `override_reason`.
  * **No artifact digest of any kind** — `sha256`, `fingerprint`, `artifact_id`,
    `trained_date` appear nowhere in any row.
  * `active_scorer` IS recorded, and on **14 of 24 BUY rows it is `None`**.

STATED AS A PROPERTY, NOT A DEFECT. A trade log is not the audit bundle, and whether
artifact identity belongs in it is a design question this does not answer. What it does
establish: a reader of the trade log cannot tell which of the 12 distinct boosters
(orch#712) produced a decision, because no digest is recorded — only a scorer family.

A FALSE FINDING THIS FILE EXISTS TO STOP. `active_scorer` is `hf_patchtst` on **38** rows,
which reads as "the stale PatchTST checkpoint is deciding the book". It is not:
**all 38 are `SELL`**, i.e. the scorer that ENTERED the position historically. Every `BUY`
row carries `None`, `panel_ltr_xgboost` or `blend`. A KILL claim in this programme was
already retracted once for mistracing a PatchTST checkpoint (#569 → #570), so the split by
`action` is computed here rather than left to the reader.

Read-only. Reads the live decision records, writes nothing.

Exit codes: ``0`` every checked record carries provenance, ``1`` at least one does not,
``2`` usage/IO error, ``3`` SKIPPED — no record found, so nothing was established.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import sys
from pathlib import Path

PROVENANCE_KEYS = ("operator_authorized_override", "gate_verdict_before_override",
                   "override_reason")
IDENTITY_KEYS = ("sha256", "fingerprint", "artifact_id", "trained_date")


def survey(pattern: str) -> dict:
    files = sorted(glob.glob(pattern))
    if not files:
        return {"status": "no_records", "pattern": pattern}
    n_files = n_rows = 0
    with_prov = with_ident = 0
    by_action_scorer: collections.Counter = collections.Counter()
    buys_without_scorer = 0
    unreadable = []
    for p in files:
        try:
            text = Path(p).read_text()
            rows = json.loads(text)
        except (OSError, ValueError) as exc:
            # Unreadable is NOT "carries no provenance" — it is unmeasured, and counting
            # it as a finding would inflate the gap with files nobody read.
            unreadable.append(f"{Path(p).name}: {type(exc).__name__}")
            continue
        n_files += 1
        if any(k in text for k in PROVENANCE_KEYS):
            with_prov += 1
        if any(k in text for k in IDENTITY_KEYS):
            with_ident += 1
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict):
                continue
            n_rows += 1
            action, scorer = str(r.get("action")), str(r.get("active_scorer"))
            by_action_scorer[(action, scorer)] += 1
            if action == "BUY" and r.get("active_scorer") is None:
                buys_without_scorer += 1
    buys = sum(c for (a, _s), c in by_action_scorer.items() if a == "BUY")
    return {
        "status": "checked",
        "pattern": pattern,
        "n_files_read": n_files,
        "n_files_unreadable": len(unreadable),
        "unreadable": unreadable,
        "n_rows": n_rows,
        "files_with_override_provenance": with_prov,
        "files_with_any_artifact_identity": with_ident,
        "n_buy_rows": buys,
        "buy_rows_without_active_scorer": buys_without_scorer,
        "action_scorer_counts": {f"{a}/{s}": c
                                 for (a, s), c in sorted(by_action_scorer.items(),
                                                         key=lambda kv: -kv[1])},
        "not_a_finding": (
            "`active_scorer` being hf_patchtst on many rows is NOT the stale checkpoint "
            "deciding the book: those rows are SELLs, carrying the scorer that entered "
            "the position. Check the action split before reading it any other way — a "
            "KILL claim here was already retracted once for mistracing a PatchTST "
            "checkpoint (#569 -> #570)."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--records", required=True,
                    help="glob for the live per-date decision records")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        rep = survey(a.records)
    except OSError as exc:
        print(f"live-provenance: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if rep["status"] != "checked":
        print(f"SKIPPED: no record matched {a.records!r} — nothing was established.",
              file=sys.stderr)
        return 3

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(f"  {rep['n_files_read']} record(s), {rep['n_rows']} decision row(s)"
              + (f"  ({rep['n_files_unreadable']} unreadable)"
                 if rep["n_files_unreadable"] else ""))
        print(f"    with override provenance : "
              f"{rep['files_with_override_provenance']}/{rep['n_files_read']}")
        print(f"    with any artifact identity: "
              f"{rep['files_with_any_artifact_identity']}/{rep['n_files_read']}")
        print(f"    BUY rows with no active_scorer: "
              f"{rep['buy_rows_without_active_scorer']}/{rep['n_buy_rows']}")
        print("\n  action / active_scorer:")
        for k, c in rep["action_scorer_counts"].items():
            print(f"    {k:<34}{c}")
        print(f"\n  [not a finding] {rep['not_a_finding']}")

    return 1 if rep["files_with_override_provenance"] < rep["n_files_read"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
