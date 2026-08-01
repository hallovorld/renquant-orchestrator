#!/usr/bin/env python3
"""Re-derive the regime profile FROM THE ARTIFACTS, with digests. (GOAL-6)

WHY THIS EXISTS. codex on orch#680: a shape-only conclusion cannot rest on exact,
un-replayable statistics. The regime table was tagged "prior work, orch#677" and this
branch's own document then asserted that **ten of the eleven named artifacts could not
re-derive it**. That assertion was FALSE, and its cause is now a familiar one:

    the check read `wf_gate_metadata` at the TOP LEVEL of each artifact.
    The canonical location is `metadata.wf_gate_metadata`.

Measured 2026-07-31: **11 of 11** named artifacts carry
`metadata.wf_gate_metadata.sanity_regime_ic.regimes`; only **1** also carries a legacy
top-level copy. Reading the canonical key, all **44** rows of #677's CSV re-derive
EXACTLY (zero mismatches), and the profile medians reproduce to the last digit.

So the numbers are not un-replayable. They were never stamped anywhere else, but they
ARE stamped in the artifacts, and this tool reads them back and records what it read:
every source path, its sha256, and a root digest over the whole set.

WHAT THIS ESTABLISHES: that the committed table is the table the artifacts carry. It is
not an independent re-measurement of the underlying ICs -- the gate computed those, and
re-running it is the separate, blocked re-scoring study.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import statistics
import sys

SCHEMA = "regime_profile_census.v1"
CANONICAL_KEY = "metadata.wf_gate_metadata.sanity_regime_ic.regimes"
FIELDS = ("mean_ic", "std_ic", "hit_rate", "n_dates", "n_rows")


def _regimes(payload: dict) -> tuple[dict, str]:
    """The per-regime block and WHICH key answered.

    The legacy top-level copy is read only as a fallback and the source is recorded --
    reading the canonical key silently would fix the numbers and hide the reason the
    earlier count was wrong.
    """
    for path, node in (
        (CANONICAL_KEY, (payload.get("metadata") or {}).get("wf_gate_metadata")),
        ("wf_gate_metadata.sanity_regime_ic.regimes (legacy top-level)",
         payload.get("wf_gate_metadata")),
    ):
        if isinstance(node, dict):
            block = (node.get("sanity_regime_ic") or {}).get("regimes")
            if isinstance(block, dict) and block:
                return block, path
    return {}, ""


def census(artifact_names: list[str], search_root: str,
           recursive: bool = False) -> dict:
    """Resolve each name UNDER THE DECLARED ROOT and read its regime block.

    NON-RECURSIVE BY DEFAULT, and this is the load-bearing choice. The first version
    rglob'd the whole artifact tree and took `sorted(hits)[0]`. Measured 2026-07-31:
    `panel-ltr.alpha158_fund.json` exists at **23 paths** under that tree with **3
    distinct digests** -- 21 of them inside `diagnostics/modal_sweep_*/bundle/kernel/`
    -- and `sorted()[0]` silently picked a modal-sweep diagnostic copy instead of the
    deployed `prod/` one. That shifted a median without any error being raised.

    "Which copy executes" is the defect this programme keeps a registry of; here it was
    "which copy gets MEASURED", inside the tool written to make a measurement
    auditable. So: resolve against the declared root, and if a name still resolves to
    more than one DISTINCT digest, record it as AMBIGUOUS rather than choosing.
    """
    rows, sources, unresolved = [], [], []
    for name in sorted(set(artifact_names)):
        base = os.path.basename(name)
        if recursive:
            hits = sorted(glob.glob(os.path.join(search_root, "**", base),
                                    recursive=True))
        else:
            hits = sorted(glob.glob(os.path.join(search_root, base)))
        if not hits:
            unresolved.append({"artifact": base, "why": "not found under search_root"})
            continue
        by_digest = {}
        for h in hits:
            with open(h, "rb") as fh:
                by_digest.setdefault(hashlib.sha256(fh.read()).hexdigest(), []).append(
                    os.path.relpath(h, search_root))
        if len(by_digest) > 1:
            unresolved.append({
                "artifact": base,
                "why": f"AMBIGUOUS: {len(hits)} paths with {len(by_digest)} distinct "
                       f"digests under this root — refusing to choose",
                "candidates": {d: p for d, p in by_digest.items()}})
            continue
        path = hits[0]
        with open(path, "rb") as fh:
            raw = fh.read()
        regimes, source_key = _regimes(json.loads(raw))
        sources.append({
            "artifact": base,
            # Relative to search_root: an absolute path pins the evidence to one machine.
            "path": os.path.relpath(path, search_root),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "n_copies_same_bytes": len(hits),
            "scope_source": source_key,
            "n_regimes": len(regimes),
        })
        for regime, g in sorted(regimes.items()):
            row = {"artifact": base, "regime": regime}
            row.update({f: g.get(f) for f in FIELDS})
            rows.append(row)
    return {"rows": rows, "sources": sources, "unresolved": unresolved}


def _portable(root: str) -> str:
    """The root as it should be RECORDED. An absolute path names one laptop and leaks a
    home directory into committed evidence; the suffix from `backtesting/` names the
    corpus."""
    norm = os.path.normpath(root).replace(os.sep, "/")
    i = norm.find("backtesting/")
    return norm[i:] if i >= 0 else os.path.basename(norm)


def root_digest(sources: list[dict]) -> str:
    """One identity for the whole source set — catches a file appearing or vanishing."""
    lines = sorted(f"{s['artifact']}:{s['sha256']}" for s in sources)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def profile(rows: list[dict]) -> dict:
    out = {}
    for regime in sorted({r["regime"] for r in rows}):
        vals = [r for r in rows if r["regime"] == regime]
        out[regime] = {"n_artifacts": len(vals)}
        for f in FIELDS:
            got = [float(v[f]) for v in vals if v.get(f) is not None]
            out[regime][f"median_{f}"] = statistics.median(got) if got else None
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts", required=True,
                    help="file with one artifact name per line")
    ap.add_argument("--search-root", required=True)
    ap.add_argument("--out")
    ap.add_argument("--recursive", action="store_true",
                    help="search the root recursively — OFF by default; the tree "
                         "contains 23 copies of one artifact under 3 digests")
    a = ap.parse_args(argv)

    with open(a.artifacts, encoding="utf-8") as fh:
        names = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    res = census(names, a.search_root, recursive=a.recursive)
    if not res["rows"]:
        print("census: no artifact yielded a regime block — the census has no subjects, "
              "which is not the same as an unverifiable table", file=sys.stderr)
        return 2

    man = {
        "schema": SCHEMA,
        "canonical_key": CANONICAL_KEY,
        "search_root": _portable(a.search_root),
        "n_artifacts_named": len(names),
        "n_artifacts_resolved": len(res["sources"]),
        "n_unresolved": len(res["unresolved"]),
        "unresolved": res["unresolved"],
        "root_digest_sha256": root_digest(res["sources"]),
        "sources": res["sources"],
        "profile": profile(res["rows"]),
        "scope_note": (
            "Establishes that the committed table is the table the artifacts CARRY. "
            "Not an independent re-measurement of the underlying ICs — the gate "
            "computed those, and re-running it is the separate, blocked re-scoring "
            "study."),
    }
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(man, fh, indent=2, sort_keys=True)
    print(json.dumps({k: v for k, v in man.items() if k != "sources"},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
