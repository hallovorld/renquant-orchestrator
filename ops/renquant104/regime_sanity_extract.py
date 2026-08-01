#!/usr/bin/env python3
"""Emit / verify the regime placebo-vs-real table FROM THE ARTIFACTS. (GOAL-6)

WHY THIS EXISTS. Reviewed `[codex on orch#677]`: *"the new evidence CSV is still an
unproven snapshot: it records only artifact names, with no source paths, immutable
fingerprints, producer/run identity, or extraction command, and the tests validate the CSV
rather than its inputs."*

Correct, and it is this programme's recurring shape — **a test that validates a
transcription rather than the thing transcribed**. A CSV nobody can regenerate is an
assertion with a citation attached, and a digest column nobody verifies is decoration.

  ``--emit``   walks the declared root, reads each artifact's gate stamp, writes the CSV
               WITH a source path and content sha256 per row, plus a manifest naming the
               root, the inclusion query, the canonical key and the exact command.
  ``--verify`` re-reads every path the committed CSV names — resolved against ``--root``,
               so the evidence is not pinned to one machine — recomputes each sha256, and
               reports every way the CSV and the bytes on disk disagree.

`--verify` is the half that carries the weight: it turns the committed table from a claim
into something falsifiable against the artifacts.

SCOPE, STATED. These are files on one machine, not an immutable snapshot: an artifact
store is not content-addressed and a retrain can replace a file in place. The digest makes
that VISIBLE — a mismatch says "these bytes changed", which is information. It does not
make the store immutable and nothing here claims it does.

Read-only apart from the evidence directory it is told to write.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys

SCHEMA = "regime_sanity_extract.v1"
CANONICAL_KEY = "metadata.wf_gate_metadata.sanity_regime_ic.regimes"
CSV_NAME = "regime_placebo_vs_real.csv"
MANIFEST_NAME = "extract_manifest.json"

#: Columns carried from the gate stamp, plus the provenance the review asked for.
FIELDS = ["artifact", "artifact_path", "content_sha256", "scope_source",
          "deployed", "regime", "n_dates", "mean_ic", "placebo_60_ic",
          "aligned_real_ic", "ceiling", "placebo_leg_ok", "regime_passed",
          "placebo_over_real", "stamped_min_mean_ic", "stamped_max_placebo_ratio"]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _regimes(payload: dict) -> tuple[dict, str]:
    """The per-regime block and WHICH key answered.

    The legacy top-level copy is read only as a fallback and the source is RECORDED —
    reading the canonical key silently would fix the numbers and hide the reason an
    earlier count was wrong (twin-registry R8).
    """
    meta = payload.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        return {}, ""
    for node, name in (((meta or {}).get("wf_gate_metadata"), CANONICAL_KEY),
                       (payload.get("wf_gate_metadata"), "wf_gate_metadata (legacy)")):
        if isinstance(node, dict):
            block = (node.get("sanity_regime_ic") or {}).get("regimes")
            if isinstance(block, dict) and block:
                return block, name
    return {}, ""


def emit(root: str, query: str, deployed: str) -> tuple[list[dict], dict]:
    import glob
    rows, sources = [], []
    for path in sorted(glob.glob(os.path.join(root, query))):
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
            payload = json.loads(raw)
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        regimes, source = _regimes(payload)
        if not regimes:
            continue
        # Thresholds are STAMPED at the sanity_regime_ic level, not per regime, and the
        # derived columns below are computed FROM them rather than from a remembered
        # constant. `ceiling` and `placebo_over_real` are derived, not stored -- an
        # earlier version of this extractor guessed key names (`aligned_real_ic`,
        # `ceiling`) that do not exist in the block and emitted empty columns.
        meta_node = (payload.get("metadata") or {}).get("wf_gate_metadata") or {}
        sri = meta_node.get("sanity_regime_ic") or payload.get(
            "wf_gate_metadata", {}).get("sanity_regime_ic") or {}
        max_ratio = sri.get("max_placebo_ratio")
        min_mean_ic = sri.get("min_mean_ic")
        digest = hashlib.sha256(raw).hexdigest()
        name = os.path.basename(path)
        sources.append({"artifact": name,
                        "artifact_path": os.path.relpath(path, root),
                        "content_sha256": digest, "scope_source": source})
        for regime, g in sorted(regimes.items()):
            aligned = g.get("placebo_60_aligned_real_ic")
            placebo = g.get("placebo_60_ic")
            ceiling = (max_ratio * aligned
                       if isinstance(max_ratio, (int, float))
                       and isinstance(aligned, (int, float)) else None)
            over = (placebo / aligned
                    if isinstance(placebo, (int, float))
                    and isinstance(aligned, (int, float)) and aligned else None)
            rows.append({
                "artifact": name,
                "artifact_path": os.path.relpath(path, root),
                "content_sha256": digest,
                "scope_source": source,
                "deployed": str(name == deployed),
                "regime": regime,
                "n_dates": g.get("n_dates"),
                "mean_ic": g.get("mean_ic"),
                "placebo_60_ic": placebo,
                "aligned_real_ic": aligned,
                "ceiling": ceiling,
                "placebo_leg_ok": (None if ceiling is None or placebo is None
                                   else placebo <= ceiling),
                "regime_passed": g.get("passed"),
                "placebo_over_real": over,
                "stamped_min_mean_ic": min_mean_ic,
                "stamped_max_placebo_ratio": max_ratio,
            })
    manifest = {
        "schema": SCHEMA, "canonical_key": CANONICAL_KEY,
        "collection_root": root, "inclusion_query": query,
        "deployed_artifact": deployed,
        "n_artifacts": len(sources), "n_rows": len(rows),
        "sources": sources,
        "command": (f"python ops/renquant104/regime_sanity_extract.py --emit "
                    f"--root <root> --query {query!r} --deployed {deployed!r} "
                    f"--out <evidence-dir>"),
        "scope_note": ("an artifact store is not content-addressed; a digest makes a "
                       "change VISIBLE, it does not make the store immutable"),
    }
    return rows, manifest


def verify(root: str, csv_path: str) -> dict:
    """Re-read what the CSV names and report every way it disagrees with disk."""
    with open(csv_path) as fh:
        committed = list(csv.DictReader(fh))
    missing, changed, unbound = [], [], []
    for row in committed:
        rel = row.get("artifact_path")
        if not rel or not row.get("content_sha256"):
            unbound.append(row.get("artifact", "?"))
            continue
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            missing.append(row["artifact"])
            continue
        if _sha256(p) != row["content_sha256"]:
            changed.append(row["artifact"])
    return {"n_committed": len(committed), "missing": sorted(set(missing)),
            "digest_changed": sorted(set(changed)),
            "unbound_rows": sorted(set(unbound)),
            "ok": not (missing or changed or unbound)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit", action="store_true")
    mode.add_argument("--verify", action="store_true")
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--query", default="panel-ltr.alpha158_fund*.json")
    ap.add_argument("--deployed", default="panel-ltr.alpha158_fund.json")
    a = ap.parse_args(argv)

    if a.emit:
        rows, manifest = emit(a.root, a.query, a.deployed)
        if not rows:
            print(f"regime extract: no artifact under {a.root} matching {a.query} "
                  f"carries a regime block — the extract has no subjects, which is not "
                  f"the same as an empty table", file=sys.stderr)
            return 2
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, CSV_NAME), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        with open(os.path.join(a.out, MANIFEST_NAME), "w") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
        print(f"emitted {len(rows)} row(s) from {manifest['n_artifacts']} artifact(s)")
        return 0

    res = verify(a.root, os.path.join(a.out, CSV_NAME))
    print(f"verified {res['n_committed']} committed row(s) against {a.root}")
    for k in ("missing", "digest_changed", "unbound_rows"):
        if res[k]:
            print(f"  {k}: {len(res[k])} — {', '.join(res[k][:6])}")
    print("  OK" if res["ok"] else "  MISMATCH")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
