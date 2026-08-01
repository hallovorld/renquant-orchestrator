#!/usr/bin/env python3
"""Bind the WF-gate sub-criterion matrix to the artifacts it was read from.

Reviewed `[codex on orch#673]`: *"`subgate_matrix.csv` remains an unbound 11-file snapshot
with no artifact paths, digests, extraction command, or duplicate-content accounting."*

Correct. The committed CSV named artifacts by BASENAME and nothing else, so a reader could
not tell which file on disk produced a row, whether two rows came from byte-identical
files, or how to regenerate it. Eleven rows of "10/11 fail" is not evidence until each row
points at something.

`--emit` writes the matrix with, for every row: the resolved path, the file's sha256, and
a `content_group` id shared by byte-identical files. `--verify` re-derives the whole matrix
and fails on any drift, so the committed evidence is checkable rather than trusted. The
invocation is recorded in the sidecar, which is the part that was missing.

DUPLICATE-CONTENT ACCOUNTING, and why it is not cosmetic. `wf_gate_metadata` counts in this
programme have already been distorted once by an artifact with 23 copies at 3 digests. A
matrix whose rows are secretly the same file inflates every rate it reports, and the rate
is the whole claim. `content_group` makes that visible: rows sharing a group are ONE
observation wearing several filenames.

Read-only on the artifact tree. Writes only the paths given on the command line.

Exit codes: ``0`` emitted, or verified clean; ``1`` verification drift; ``2`` usage/IO
error; ``3`` SKIPPED — no artifact matched, so nothing was established.
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import sys
from pathlib import Path

FIELDS = ("artifact", "artifact_path", "artifact_sha256", "content_group", "deployed",
          "wf", "wf_before_override", "operator_authorized_override",
          "sanity", "sanity_regime_ic", "trade_monotonicity", "trade_contract",
          "regime_ic_failed_regimes", "monotonicity_failed_regimes")


def _gate_block(payload: dict) -> dict | None:
    """Canonical first, legacy second — reading one location silently is how two claims
    in this programme got retracted."""
    meta = payload.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        return None
    md = (meta or {}).get("wf_gate_metadata")
    if isinstance(md, dict) and md:
        return md
    md = payload.get("wf_gate_metadata")
    return md if isinstance(md, dict) and md else None


def _verdict(v: object) -> str:
    """PASS / FAIL / UNKNOWN. `UNKNOWN` is a third value: a missing sub-criterion has not
    been shown to pass, and folding it into either one invents a result."""
    if v is True:
        return "PASS"
    if v is False:
        return "FAIL"
    return "UNKNOWN"


def _sanity_verdict(block: dict) -> str:
    """The flat sanity leg. `UNKNOWN` when the block records no reason at all — absent is
    not passing."""
    reason = block.get("sanity_reason")
    if not isinstance(reason, str) or not reason.strip():
        return "UNKNOWN"
    return "FAIL" if "fail" in reason.lower() else "PASS"


_REASON_REGIMES = __import__("re").compile(r"regime\(s\):\s*([A-Z_,\s]+)")


def _regimes_from_reason(reason: object) -> str:
    """Failing regimes named in a free-text reason, e.g.
    `... failed in active regime(s): BULL_CALM`. Returns "" when the reason names none —
    which is not the same as "none failed", and the caller must not read it that way."""
    if not isinstance(reason, str):
        return ""
    m = _REASON_REGIMES.search(reason)
    if not m:
        return ""
    return ",".join(sorted({p.strip() for p in m.group(1).split(",") if p.strip()}))


def _failed_regimes(block: dict, key: str) -> str:
    node = block.get(key)
    if not isinstance(node, dict):
        return ""
    # `regimes`, NOT `per_regime`. My first version guessed the latter and returned an
    # empty string for every artifact -- a silent zero that would have read as "no regime
    # failed" instead of "I looked in the wrong place".
    #
    # AND THE TWO SUB-CRITERIA DO NOT SHARE A SHAPE. `sanity_regime_ic.regimes` is a DICT
    # keyed by regime; `trade_monotonicity.regimes` is a LIST of per-window records that
    # never names a regime. For the latter the failing regimes are stated only in
    # `reason`, so they are parsed from there rather than invented from the list.
    per = node.get("regimes")
    if isinstance(per, list):
        return _regimes_from_reason(node.get("reason"))
    if not isinstance(per, dict):
        return ""
    out = []
    for regime, res in sorted(per.items()):
        passed = res.get("passed") if isinstance(res, dict) else None
        if passed is False:
            out.append(regime)
    return ",".join(out)


def extract(pattern: str, deployed_basename: str) -> list[dict]:
    rows: list[dict] = []
    digests: dict[str, int] = {}
    for p in sorted(glob.glob(pattern)):
        path = Path(p)
        try:
            raw = path.read_bytes()
            payload = json.loads(raw)
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        block = _gate_block(payload)
        if block is None:
            continue
        sha = hashlib.sha256(raw).hexdigest()
        group = digests.setdefault(sha, len(digests))
        rows.append({
            "artifact": path.name,
            "artifact_path": str(path),
            "artifact_sha256": sha,
            "content_group": f"g{group}",
            "deployed": str(path.name == deployed_basename),
            # `wf` stays the POST-override verdict, matching the column the committed
            # matrix already published -- silently redefining it would move that PR's
            # numbers under its own conclusions. The pre-override value and the override
            # flag are added as SEPARATE columns instead, because they are the more
            # important fact: the served artifact's WF "pass" is an operator override
            # (`gate_verdict_before_override=False`, operator directive 2026-06-22), not
            # a gate pass.
            "wf": _verdict(block.get("passed")),
            "wf_before_override": _verdict(block.get("gate_verdict_before_override")),
            "operator_authorized_override": str(
                bool(block.get("operator_authorized_override"))),
            # There is no `sanity` sub-dict on this schema. The sanity verdict is carried
            # by the flat `sanity_reason`, and a FAIL is recorded when that names a
            # failure. Reading a non-existent `sanity.passed` returned UNKNOWN for every
            # artifact in the first version.
            "sanity": _sanity_verdict(block),
            "sanity_regime_ic": _verdict(
                (block.get("sanity_regime_ic") or {}).get("passed")
                if isinstance(block.get("sanity_regime_ic"), dict) else None),
            "trade_monotonicity": _verdict(
                (block.get("trade_monotonicity") or {}).get("passed")
                if isinstance(block.get("trade_monotonicity"), dict) else None),
            "trade_contract": _verdict(
                (block.get("trade_contract") or {}).get("passed")
                if isinstance(block.get("trade_contract"), dict) else None),
            "regime_ic_failed_regimes": _failed_regimes(block, "sanity_regime_ic"),
            "monotonicity_failed_regimes": _failed_regimes(block, "trade_monotonicity"),
        })
    return rows


def sidecar(rows: list[dict], pattern: str, deployed_basename: str) -> dict:
    groups: dict[str, list[str]] = {}
    for r in rows:
        groups.setdefault(r["content_group"], []).append(r["artifact"])
    dupes = {g: v for g, v in groups.items() if len(v) > 1}
    return {
        "extraction_command": (
            "python3 ops/renquant104/subgate_matrix_extract.py --emit "
            f"--artifact-glob {pattern!r} --deployed {deployed_basename!r} "
            "--out doc/research/evidence/2026-07-31-wf-gate-subcriteria/subgate_matrix.csv"),
        "artifact_glob": pattern,
        "deployed_basename": deployed_basename,
        "n_rows": len(rows),
        "n_distinct_content_groups": len(groups),
        "duplicate_content_groups": dupes,
        "note": ("Rows sharing a `content_group` are ONE observation wearing several "
                 "filenames. Any rate quoted over this matrix must say whether it counts "
                 "rows or groups — a `wf_gate_metadata` count in this programme has "
                 "already been distorted by an artifact with 23 copies at 3 digests."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact-glob", required=True)
    ap.add_argument("--deployed", required=True,
                    help="basename of the artifact currently served")
    ap.add_argument("--out", type=Path, required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit", action="store_true")
    mode.add_argument("--verify", action="store_true")
    a = ap.parse_args(argv)

    try:
        rows = extract(a.artifact_glob, a.deployed)
    except OSError as exc:
        print(f"subgate-extract: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print(f"SKIPPED: no stamped artifact matched {a.artifact_glob!r} — nothing was "
              f"established.", file=sys.stderr)
        return 3

    side = sidecar(rows, a.artifact_glob, a.deployed)
    side_path = a.out.with_suffix(".provenance.json")

    if a.emit:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(FIELDS))
            w.writeheader()
            w.writerows(rows)
        side_path.write_text(json.dumps(side, indent=2, sort_keys=True) + "\n")
        print(f"wrote {a.out} ({len(rows)} rows, "
              f"{side['n_distinct_content_groups']} distinct content group(s))")
        if side["duplicate_content_groups"]:
            print(f"  DUPLICATE CONTENT: {side['duplicate_content_groups']}")
        return 0

    # --verify
    if not a.out.exists():
        print(f"VERIFY FAILED: {a.out} does not exist", file=sys.stderr)
        return 1
    with a.out.open(newline="") as fh:
        committed = list(csv.DictReader(fh))
    drift = []
    if len(committed) != len(rows):
        drift.append(f"row count {len(committed)} != re-derived {len(rows)}")
    for c, r in zip(committed, rows):
        for f in FIELDS:
            if (c.get(f) or "") != str(r[f]):
                drift.append(f"{r['artifact']}.{f}: committed {c.get(f)!r} != {r[f]!r}")
    if drift:
        print("VERIFY FAILED:\n  " + "\n  ".join(drift[:20]), file=sys.stderr)
        return 1
    print(f"VERIFY OK: {len(rows)} rows re-derived identically from "
          f"{a.artifact_glob!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
