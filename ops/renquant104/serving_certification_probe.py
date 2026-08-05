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
STATE_UNREADABLE = "ARTIFACT_UNREADABLE"
STATE_ABSENT = "ARTIFACT_ABSENT"
ACTIONABLE = (STATE_NO_STAMP, STATE_DANGLING, STATE_UNREADABLE, STATE_ABSENT)

_TMPISH = re.compile(r'"(/tmp/[^"]{0,120})"')


def _gate_stamp(payload: dict) -> dict | None:
    """The canonical location, then the legacy one. Both, because an artifact
    that only has the legacy key still makes a claim."""
    meta = payload.get("metadata")
    if isinstance(meta, dict) and isinstance(meta.get("wf_gate_metadata"), dict):
        return meta["wf_gate_metadata"]
    if isinstance(payload.get("wf_gate_metadata"), dict):
        return payload["wf_gate_metadata"]
    return None


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
    stamp = _gate_stamp(payload)
    if stamp is None:
        return {**row, "state": STATE_NO_STAMP,
                "detail": "no wf_gate_metadata in either the canonical "
                          "metadata.wf_gate_metadata or the legacy top-level key "
                          "— this artifact makes NO claim that could be checked"}
    # A claim that points at a path which no longer exists is worse than none:
    # it reads as certified. orch#726's first two halves were exactly this.
    dangling = [p for p in sorted(set(_TMPISH.findall(raw)))
                if not pathlib.Path(p).exists()]
    manifest = stamp.get("sanity_manifest_path") or stamp.get("wf_manifest_path")
    if manifest and not pathlib.Path(str(manifest)).exists():
        dangling.append(str(manifest))
    if dangling:
        return {**row, "state": STATE_DANGLING,
                "detail": "the claim references path(s) that do not exist: "
                          + ", ".join(dangling[:3]),
                "dangling": dangling}
    return {**row, "state": STATE_CLAIM,
            "detail": "carries a wf_gate_metadata claim whose referenced paths "
                      "resolve — the claim can be CHECKED (this says nothing "
                      "about whether it is a good claim)",
            "manifest_path": str(manifest) if manifest else None}


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
