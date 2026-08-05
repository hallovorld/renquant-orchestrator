#!/usr/bin/env python3
"""Does each SERVING artifact carry a checkable certification claim?

WHY (GOAL-6, measured 2026-08-05): orch#726 filed three defects against the
serving artifacts on 2026-08-01. Re-measuring today, **two were already fixed**
(the prod manifest and the override rollback no longer point at a vanished
`/tmp` path) and **one was unchanged** (the clf lane carries no
`wf_gate_metadata` at all, in either the canonical or the legacy location).

Nobody noticed either fact for four days, because checking meant reading two
artifacts by hand. A three-claim P0 sitting two-thirds fixed is how a reader
learns to discount P0s.

This probe answers one question per serving artifact, cheaply and repeatably:
**does it make a walk-forward claim that can be checked at all?** It deliberately
does NOT judge the claim — fold counts are counts of manifest rows and say
nothing about leakage or quality. Establishing that a claim EXISTS is a
different, prior question, and conflating them is what let one lane's 43 folds
read as coverage for a lane with zero.

Read-only. Usage:
    python ops/renquant104/serving_certification_probe.py [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

REPO = pathlib.Path(os.environ.get("RENQUANT_REPO_ROOT",
                                   "/Users/renhao/git/github/RenQuant"))
ARTIFACTS = REPO / "backtesting" / "renquant_104" / "artifacts"

# (label, path relative to ARTIFACTS). The SERVING set — what the live book and
# the shadow lanes actually load, not everything on disk.
SERVING = (
    ("prod panel (XGB recipe)", "prod/panel-ltr.alpha158_fund.json"),
    ("clf top-decile fwd60 (shadow member)", "shadow/panel-clf.top-decile.fwd60.json"),
)

STATE_CLAIM = "HAS_CHECKABLE_CLAIM"
STATE_NO_STAMP = "NO_GATE_STAMP"
STATE_DANGLING = "CLAIM_POINTS_AT_A_MISSING_PATH"
STATE_NOTHING_TO_CHECK = "CLAIM_REFERENCES_NO_PATH"
STATE_MALFORMED = "STAMP_MALFORMED"
STATE_UNREADABLE = "ARTIFACT_UNREADABLE"
STATE_ABSENT = "ARTIFACT_ABSENT"
ACTIONABLE = (STATE_NO_STAMP, STATE_DANGLING, STATE_NOTHING_TO_CHECK,
              STATE_MALFORMED, STATE_UNREADABLE, STATE_ABSENT)

# [codex on orch#820] ENUMERATING keys was the bug. The first version checked
# `/tmp` strings plus two manifest keys, and therefore reported
# HAS_CHECKABLE_CLAIM for the live prod artifact whose
# `config_parity.candidate_artifact` points at a staging file that does not
# exist. Invert the default: walk EVERY string in the stamp and treat anything
# path-shaped as a reference that must resolve.
_PATHISH = re.compile(r"^(?:/|\./|\.\./).*\.(?:json|parquet|jsonl|csv|txt|pkl)$")


class StampMalformed(Exception):
    """A stamp container exists but is not a mapping. NOT the same as absent —
    fail closed, the way wf_corpus_coverage.py and gate_stamp_parity.py do
    [codex on orch#820]."""


def _gate_stamp(payload: dict) -> dict | None:
    """The canonical location, then the legacy one. Both, because an artifact
    that only has the legacy key still makes a claim.

    Raises ``StampMalformed`` when a container is PRESENT but the wrong shape:
    collapsing that to "no stamp" reports a broken artifact as an honestly
    uncertified one.
    """
    meta = payload.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        raise StampMalformed(f"`metadata` is {type(meta).__name__}, not an object")
    if isinstance(meta, dict) and "wf_gate_metadata" in meta:
        stamp = meta["wf_gate_metadata"]
        if not isinstance(stamp, dict):
            raise StampMalformed("`metadata.wf_gate_metadata` is "
                                 f"{type(stamp).__name__}, not an object")
        return stamp
    if "wf_gate_metadata" in payload:
        stamp = payload["wf_gate_metadata"]
        if not isinstance(stamp, dict):
            raise StampMalformed("top-level `wf_gate_metadata` is "
                                 f"{type(stamp).__name__}, not an object")
        return stamp
    return None


def referenced_paths(stamp: dict) -> list[str]:
    """Every path-shaped string ANYWHERE in the stamp, deduplicated and sorted."""
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
        elif isinstance(node, str) and _PATHISH.match(node):
            found.add(node)

    walk(stamp)
    return sorted(found)


def probe_one(label: str, rel: str, artifacts: pathlib.Path = ARTIFACTS) -> dict:
    path = artifacts / rel
    row = {"artifact": label, "path": str(path)}
    if not path.exists():
        return {**row, "state": STATE_ABSENT,
                "detail": "the serving artifact is not on disk"}
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except Exception as exc:                     # noqa: BLE001
        return {**row, "state": STATE_UNREADABLE,
                "detail": f"could not be read/parsed ({exc}) — an unreadable "
                          f"artifact is not an absent claim"}
    try:
        stamp = _gate_stamp(payload)
    except StampMalformed as exc:
        return {**row, "state": STATE_MALFORMED,
                "detail": f"a gate-stamp container is present but malformed "
                          f"({exc}) — a broken stamp is not an absent one"}
    if stamp is None:
        return {**row, "state": STATE_NO_STAMP,
                "detail": "no wf_gate_metadata in either the canonical "
                          "metadata.wf_gate_metadata or the legacy top-level key "
                          "— this artifact makes NO claim that could be checked"}
    refs = referenced_paths(stamp)
    if not refs:
        # A claim naming nothing cannot be checked, whatever else it says.
        return {**row, "state": STATE_NOTHING_TO_CHECK,
                "detail": "the stamp references no path at all — there is "
                          "nothing to resolve, so the claim cannot be checked"}
    dangling = [p for p in refs if not pathlib.Path(p).exists()]
    if dangling:
        return {**row, "state": STATE_DANGLING,
                "detail": f"{len(dangling)} of {len(refs)} referenced path(s) do "
                          f"not exist: " + ", ".join(dangling[:3]),
                "dangling": dangling, "referenced": refs}
    return {**row, "state": STATE_CLAIM,
            "detail": f"all {len(refs)} referenced path(s) resolve — the claim "
                      f"can be CHECKED (this says nothing about whether it is a "
                      f"good claim)",
            "referenced": refs}


def probe(artifacts: pathlib.Path = ARTIFACTS) -> list[dict]:
    return [probe_one(label, rel, artifacts) for label, rel in SERVING]


def render(rows: list[dict]) -> str:
    out = ["serving-artifact certification probe", ""]
    for r in rows:
        out.append(f"[{r['state']}] {r['artifact']}")
        out.append(f"    {r['detail']}")
    n = sum(1 for r in rows if r["state"] in ACTIONABLE)
    out.append("")
    out.append(f"PROBE: {n} serving artifact(s) with no checkable claim"
               if n else f"PROBE: all {len(rows)} serving artifacts make a "
                         f"checkable claim")
    out.append("NOTE: this establishes that a claim EXISTS and resolves. It does "
               "NOT judge it —\n      fold counts are manifest rows and say "
               "nothing about leakage or quality.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = probe()
    print(json.dumps(rows, indent=2) if args.json else render(rows))
    return 1 if any(r["state"] in ACTIONABLE for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
