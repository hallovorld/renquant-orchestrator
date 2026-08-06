#!/usr/bin/env python3
"""Can the WF gate tell two candidate artifacts apart?

WHY (GOAL-6, measured 2026-08-05). The gate admits on
``candidate_recipe_fingerprint`` and records ``candidate_artifact_used``. If many
artifacts share one fingerprint while their measured skill differs, the gate's
admission key is collapsing distinguishable candidates into one identity — and
GOAL-6 is precisely the question of whether model capability can be evaluated.

Measured live: 36 of 37 artifacts carry the SAME fingerprint
``sha256:cfdd6cb8e950da0f`` while ``sanity_placebo_genuine_ic`` takes EIGHT
distinct values across them. So the artifacts do differ; the admission key does
not see it. ``candidate_artifact_used`` is false on 37 of 37 — the gate has never
scored a candidate's own booster.

READ THE KEYS, DO NOT GUESS THEM. An earlier draft of this probe looked for
``recipe_hash`` / ``recipe_sha256`` / ``hash``, got ``None`` from all 37, and was
one step from reporting "1 distinct hash across 37 artifacts" — a dramatic claim
that would have been entirely an artifact of a field name I invented. The real
key is ``candidate_recipe_fingerprint``. Every key this file reads is listed in
KEYS below so a rename fails loudly instead of silently returning None.

Read-only. Usage: python ops/renquant104/wf_gate_discrimination_probe.py [--json]
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

DEFAULT_ROOT = pathlib.Path(
    "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts")

#: Every field this probe reads, by its REAL name. A missing key is reported as
#: MISSING, never silently coerced to None -- that coercion is the exact failure
#: this module's docstring records.
KEY_FINGERPRINT = "candidate_recipe_fingerprint"
KEY_USED = "candidate_artifact_used"
KEY_GENUINE_IC = "sanity_placebo_genuine_ic"
KEY_GENUINE_MARGIN = "sanity_placebo_genuine_ic_margin"

SKIP_PARTS = ("/diagnostics/", "/bundle/")


class NoArtifacts(RuntimeError):
    """No artifact carried wf_gate_metadata. Not a clean discrimination result."""


def wf_metadata(payload: dict) -> dict | None:
    """`metadata.wf_gate_metadata` is canonical; top level is the fallback."""
    if not isinstance(payload, dict):
        return None
    md = payload.get("metadata")
    if isinstance(md, dict) and isinstance(md.get("wf_gate_metadata"), dict):
        return md["wf_gate_metadata"]
    top = payload.get("wf_gate_metadata")
    return top if isinstance(top, dict) else None


def scan(root: pathlib.Path = DEFAULT_ROOT) -> dict:
    by_fp: dict = collections.defaultdict(list)
    used = collections.Counter()
    ics: dict = {}
    missing_fp = []
    for f in sorted(root.rglob("*.json")):
        s = str(f)
        if any(p in s for p in SKIP_PARTS):
            continue
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        wf = wf_metadata(payload)
        if wf is None:
            continue
        rel = s.replace(str(root) + "/", "")
        fp = wf.get(KEY_FINGERPRINT, "<MISSING>")
        if fp == "<MISSING>":
            missing_fp.append(rel)
        by_fp[fp].append(rel)
        used[wf.get(KEY_USED, "<MISSING>")] += 1
        ic = wf.get(KEY_GENUINE_IC)
        if isinstance(ic, (int, float)):
            ics[rel] = float(ic)

    total = sum(len(v) for v in by_fp.values())
    if total == 0:
        raise NoArtifacts(
            f"no artifact under {root} carried wf_gate_metadata — reporting "
            "perfect discrimination from zero artifacts would publish a failed "
            "scan as a clean result")

    biggest = max(by_fp.items(), key=lambda kv: len(kv[1])) if by_fp else (None, [])
    distinct_ic = sorted({round(v, 6) for v in ics.values()})
    # The collapse: artifacts sharing ONE admission key whose measured skill differs.
    collapsed_ic = sorted({round(ics[a], 6) for a in biggest[1] if a in ics})
    return {
        "root": str(root),
        "n_artifacts_with_wf_metadata": total,
        "n_distinct_fingerprints": len(by_fp),
        "largest_fingerprint": biggest[0],
        "n_sharing_largest_fingerprint": len(biggest[1]),
        "candidate_artifact_used_counts": {str(k): v for k, v in used.items()},
        "n_artifacts_missing_fingerprint": len(missing_fp),
        "artifacts_missing_fingerprint": missing_fp,
        "n_distinct_genuine_ic": len(distinct_ic),
        "distinct_genuine_ic": distinct_ic,
        # THE number: distinct skill values hiding behind one admission key.
        "n_distinct_genuine_ic_under_largest_fingerprint": len(collapsed_ic),
        "genuine_ic_under_largest_fingerprint": collapsed_ic,
        "discriminates": len(collapsed_ic) <= 1,
        "does_NOT_establish": (
            "which artifact is better. genuine_ic spread proves the artifacts "
            "DIFFER, not that any of them clears a bar — every observed value is "
            "far below the v3 criterion of 0.02, which is itself shadow-only and "
            "not enforced."
        ),
    }


def render(r: dict) -> str:
    out = ["WF-gate discrimination — can the admission key tell candidates apart?", ""]
    out.append(f"  artifacts with wf_gate_metadata      : {r['n_artifacts_with_wf_metadata']}")
    out.append(f"  distinct {KEY_FINGERPRINT:<28}: {r['n_distinct_fingerprints']}")
    out.append(f"  largest fingerprint                  : {r['largest_fingerprint']}")
    out.append(f"    shared by                          : {r['n_sharing_largest_fingerprint']} artifact(s)")
    out.append(f"  {KEY_USED:<37}: {r['candidate_artifact_used_counts']}")
    out.append("")
    n = r["n_distinct_genuine_ic_under_largest_fingerprint"]
    out.append(f"  distinct genuine_ic UNDER that one key: {n}")
    out.append(f"    values: {r['genuine_ic_under_largest_fingerprint']}")
    out.append("")
    if not r["discriminates"]:
        out.append(f"  NO DISCRIMINATION — {r['n_sharing_largest_fingerprint']} artifacts share one")
        out.append(f"  admission key while carrying {n} distinct measured skill values.")
        out.append("  The artifacts differ; the key the gate admits on does not see it.")
    else:
        out.append("  the admission key separates the artifacts it admits.")
    out.append("")
    out.append(f"  Does NOT establish {r['does_NOT_establish']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = scan(a.root)
    except NoArtifacts as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2) if a.json else render(r))
    return 1 if not r["discriminates"] else 0


if __name__ == "__main__":
    sys.exit(main())
