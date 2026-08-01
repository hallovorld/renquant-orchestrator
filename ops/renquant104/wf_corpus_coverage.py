#!/usr/bin/env python3
"""Does a SERVING ARTIFACT have walk-forward evidence — resolved from the artifact? (GOAL-6)

WHY THIS EXISTS, AND WHY IT WAS REWRITTEN. A goal anchor said the certified clf recipe
had no out-of-sample corpus. I reported that anchor stale, citing 43 folds — real
numbers belonging to `walkforward_gbdt_prod_recipe_v2`, the GBDT production recipe, not
to clf. I measured one lane and retired an anchor about another.

The first version of this tool took **lane names as command-line directory strings**.
Reviewed `[codex on orch#691]`: *"its lanes are arbitrary command-line directory names,
so invoking it for the GBDT directory and labeling the result clf recreates the exact
substitution this PR corrects."* Correct — the tool did not prevent the error it was
written about; it only made that error faster to commit.

So the lane-to-corpus binding is no longer supplied by the caller. It is **resolved from
the artifact itself**:

    artifact  ->  metadata.wf_gate_metadata.artifact_usage.manifest_path
              ->  the walk-forward manifest
              ->  the fold artifact URIs it names
              ->  the corpus directory those folds live in

The caller names an ARTIFACT — the thing actually served — and every corpus statement is
derived from that artifact's own stamp. Mislabelling requires falsifying the stamp, not
mistyping a path.

WHAT THE RESOLUTION STATUSES MEAN. Each is a different fact and none is "no coverage":

  * ``resolved``          — the stamp names a manifest that exists and lists folds.
  * ``no_gate_stamp``     — the artifact carries no ``wf_gate_metadata`` in either
                            location, so it has no walk-forward binding at all. This is
                            the clf case, and it is now DERIVED rather than asserted.
  * ``no_manifest_named`` — stamped, but the stamp names no manifest.
  * ``manifest_missing``  — the stamp names a manifest that is not on disk. Measured
                            2026-07-31: 13 of 30 stamped prod artifacts name a path under
                            ``/tmp/``. The binding exists and is not durable; that is a
                            fact about provenance, NOT evidence the folds never existed.

Read-only: opens artifacts and manifests, writes nothing, never invokes git.

Exit codes: ``0`` every named artifact resolves to at least ``--min-folds``, ``1``
otherwise, ``2`` usage/IO error — so a broken invocation cannot be mistaken for coverage.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

CANONICAL = "metadata.wf_gate_metadata"
LEGACY = "wf_gate_metadata (legacy top-level)"


def _gate_block(payload: dict) -> tuple[dict | None, str]:
    """The gate block and WHICH key answered — canonical first, legacy recorded.

    Reading the canonical key silently would repeat the defect that produced two
    retracted claims this week: a checker looking in one place does not discover that
    its subjects are missing, it discovers that it is looking in the wrong place.
    """
    md = (payload.get("metadata") or {}).get("wf_gate_metadata")
    if isinstance(md, dict) and md:
        return md, CANONICAL
    md = payload.get("wf_gate_metadata")
    if isinstance(md, dict) and md:
        return md, LEGACY
    return None, ""


def _fold_uris(manifest: object) -> tuple[list[str], str]:
    """Fold artifact URIs, and WHICH manifest key answered.

    An earlier version guessed a fixed list of row keys (`rows`, `entries`, `artifacts`)
    and silently returned **0 folds** for the real manifest, whose rows live under
    `retrains`. Zero folds and "I do not understand this manifest" are different facts
    and must not share a code path.

    So: scan every list-valued key for dicts carrying a URI-shaped field, take the
    richest one, and RECORD its name. A manifest shape change then shows up as a
    different key in the report, or as `unrecognised_manifest_shape`, instead of as a
    quiet zero.
    """
    if not isinstance(manifest, dict):
        return [], ""
    best: tuple[list[str], str] = ([], "")
    for key, rows in manifest.items():
        if not isinstance(rows, list):
            continue
        uris = [u for r in rows if isinstance(r, dict)
                for u in (r.get("artifact_uri") or r.get("uri") or r.get("path"),)
                if isinstance(u, str)]
        if len(uris) > len(best[0]):
            best = (uris, key)
    return best


def resolve(artifact_path: str) -> dict:
    """Walk the artifact's OWN provenance chain to its corpus. Never guesses."""
    row: dict = {"artifact": os.path.basename(artifact_path),
                 "artifact_exists": os.path.exists(artifact_path)}
    if not row["artifact_exists"]:
        return {**row, "status": "artifact_missing", "n_folds": 0}
    try:
        with open(artifact_path, "rb") as fh:
            payload = json.loads(fh.read())
    except (OSError, ValueError) as exc:
        return {**row, "status": "artifact_unreadable",
                "why": f"{type(exc).__name__}: {exc}", "n_folds": 0}
    if not isinstance(payload, dict):
        return {**row, "status": "artifact_unreadable",
                "why": f"top-level JSON is {type(payload).__name__}, not an object",
                "n_folds": 0}

    block, source = _gate_block(payload)
    row["gate_stamp_source"] = source or None
    if block is None:
        return {**row, "status": "no_gate_stamp", "n_folds": 0,
                "note": "no wf_gate_metadata in either location — this artifact has no "
                        "walk-forward binding at all"}

    manifest_path = (block.get("artifact_usage") or {}).get("manifest_path")
    row["manifest_path"] = manifest_path
    if not manifest_path:
        return {**row, "status": "no_manifest_named", "n_folds": 0}
    if not os.path.exists(manifest_path):
        return {**row, "status": "manifest_missing", "n_folds": 0,
                "note": "the stamp names a manifest that is not on disk; the binding "
                        "exists but is not durable — this is NOT evidence the folds "
                        "never existed"}
    try:
        with open(manifest_path, "rb") as fh:
            manifest = json.loads(fh.read())
    except (OSError, ValueError) as exc:
        return {**row, "status": "manifest_unreadable",
                "why": f"{type(exc).__name__}: {exc}", "n_folds": 0}

    uris, rows_key = _fold_uris(manifest)
    if not uris:
        return {**row, "status": "unrecognised_manifest_shape", "n_folds": 0,
                "note": "the manifest is readable but no list of URI-carrying rows was "
                        "found in it — this is NOT zero folds, it is an unparsed "
                        "manifest, and the two must not be reported the same way"}
    corpora = sorted({os.path.basename(os.path.dirname(os.path.dirname(u)))
                      for u in uris if u})
    return {**row, "status": "resolved", "n_folds": len(uris),
            "manifest_rows_key": rows_key, "corpus_dirs": corpora,
            "note": ("more than one corpus directory among the folds"
                     if len(corpora) > 1 else None)}


def survey(artifact_paths: list[str]) -> dict:
    rows = [resolve(p) for p in artifact_paths]
    return {
        "artifacts": rows,
        "scope_note": (
            "Every corpus statement here is derived from the ARTIFACT'S OWN gate stamp, "
            "not from a directory name supplied on the command line. A fold count is a "
            "count of manifest rows; it does not open the folds and says nothing about "
            "leakage or quality. Results are per artifact and never summed — a total is "
            "what let one lane's 43 folds stand in for another lane's zero."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts", nargs="+", required=True,
                    help="paths to SERVING artifacts — not corpus directories")
    ap.add_argument("--min-folds", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        rep = survey(list(a.artifacts))
    except OSError as exc:
        print(f"wf-corpus coverage: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        for r in rep["artifacts"]:
            head = f"{r['status'].upper():18s} {r['artifact']}"
            if r["status"] == "resolved":
                ok = "COVERED" if r["n_folds"] >= a.min_folds else "THIN"
                print(f"{ok:18s} {r['artifact']}: {r['n_folds']} fold(s) from "
                      f"{r.get('corpus_dirs')} "
                      f"[manifest rows key: {r.get('manifest_rows_key')!r}]")
            else:
                print(head)
            for k in ("note", "why", "manifest_path"):
                if r.get(k):
                    print(f"                   {k}: {r[k]}")
        print("\n" + rep["scope_note"])

    short = [r for r in rep["artifacts"]
             if r["status"] != "resolved" or r["n_folds"] < a.min_folds]
    return 1 if short else 0


if __name__ == "__main__":
    raise SystemExit(main())
