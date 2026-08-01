#!/usr/bin/env python3
"""Where the two copies of the WF-gate stamp DISAGREE. (GOAL-3, twin registry R8)

R8 records that `wf_gate_metadata` exists in two places inside one artifact —
`metadata.wf_gate_metadata` (canonical) and a legacy top-level copy — and that they do
not always agree. The registry's own retirement condition for that row asks for
"a parity check that reports the artifacts where the two copies disagree instead of
silently preferring one". This is that check; nothing else in the repo performs it.

WHY IT MATTERS RATHER THAN BEING TIDINESS. Reading the wrong copy produced three defects
in one evening, two of them published claims that had to be retracted (backtesting#89's
"fifteen rows were invented", orch#680's "ten of eleven cannot be re-derived"). Every
reader now consults the canonical key first — but a reader is only as good as the data,
and where the copies disagree the artifact ITSELF carries two answers. Preferring one
silently is what makes that invisible.

WHAT IS AND IS NOT A PROBLEM:
  * both copies present and DISAGREEING on a compared field -> PROBLEM. Two answers in
    one file is a defect of the artifact, regardless of which one a reader takes.
  * only the canonical copy -> fine, and the majority case.
  * only the legacy copy -> INFO. Not a disagreement, but worth counting: it is the one
    shape where a canonical-first reader falls through.
  * neither -> INFO. Not this check's subject.

Read-only. Never writes, never mutates an artifact.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

CANONICAL = "metadata.wf_gate_metadata"
LEGACY = "wf_gate_metadata (legacy top-level)"

#: Fields compared between the two copies. Chosen as the ones a consumer acts on:
#: the verdict, the override provenance, and the branch marker.
COMPARED_FIELDS = (
    "passed",
    "sanity_eval_scope",
    "wf_eval_scope",
    "gate_verdict_before_override",
    "operator_authorized_override",
    "override_reason",
    "diagnostic_only",
    "gate_version",
)


def _blocks(payload: dict) -> tuple[dict | None, dict | None]:
    meta = payload.get("metadata")
    canon = meta.get("wf_gate_metadata") if isinstance(meta, dict) else None
    legacy = payload.get("wf_gate_metadata")
    return (canon if isinstance(canon, dict) else None,
            legacy if isinstance(legacy, dict) else None)


def compare(canon: dict, legacy: dict) -> list[str]:
    """Fields where the two copies give different answers.

    A field ABSENT from one copy and present in the other counts as a disagreement:
    that is exactly the shape measured on the live tree — a legacy block with no
    `sanity_eval_scope` beside a canonical block that records one. Absent is not equal.
    """
    out = []
    for f in COMPARED_FIELDS:
        a, b = canon.get(f, "<absent>"), legacy.get(f, "<absent>")
        if a != b:
            out.append(f"{f}: canonical={a!r} legacy={b!r}")
    return out


def scan(root: str, query: str) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    both = canon_only = legacy_only = neither = unreadable = 0

    paths = sorted(glob.glob(os.path.join(root, query)))
    if not paths:
        return ([f"gate-stamp parity: no artifact under {root} matches {query} — "
                 f"the scan has no subjects, which is not the same as parity"], [])

    for path in paths:
        try:
            with open(path, "rb") as fh:
                payload = json.loads(fh.read())
        except Exception as exc:  # noqa: BLE001
            unreadable += 1
            problems.append(f"gate-stamp parity: {os.path.basename(path)} unreadable: "
                            f"{type(exc).__name__}: {exc}")
            continue
        if not isinstance(payload, dict):
            unreadable += 1
            continue
        canon, legacy = _blocks(payload)
        if canon and legacy:
            both += 1
            diffs = compare(canon, legacy)
            if diffs:
                problems.append(
                    f"gate-stamp parity: {os.path.basename(path)} carries TWO gate "
                    f"stamps that disagree — {'; '.join(diffs)}. A reader taking the "
                    f"legacy copy gets a different answer from one taking the canonical "
                    f"copy; the artifact itself holds both.")
        elif canon:
            canon_only += 1
        elif legacy:
            legacy_only += 1
        else:
            neither += 1

    infos = [
        f"gate-stamp parity: {len(paths)} artifact(s) scanned — {both} carry BOTH "
        f"copies, {canon_only} canonical-only, {legacy_only} legacy-only, "
        f"{neither} no stamp, {unreadable} unreadable",
    ]
    if legacy_only:
        infos.append(
            f"gate-stamp parity: {legacy_only} artifact(s) carry ONLY the legacy "
            f"top-level copy — the one shape where a canonical-first reader falls "
            f"through to it")
    return problems, infos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True)
    ap.add_argument("--query", default="panel-ltr.alpha158_fund*.json")
    a = ap.parse_args(argv)
    problems, infos = scan(a.root, a.query)
    for line in infos:
        print(line)
    for line in problems:
        print(line, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
